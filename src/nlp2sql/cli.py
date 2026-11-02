"""Enhanced command line interface for nlp2sql."""

import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

import click

from . import create_ai_provider, create_and_initialize_service
from .config.settings import settings
from .core.entities import DatabaseType
from .core.runtime import ExecutionMode
from .core.provider_config import ProviderConfig
from .exceptions import (
    NLP2SQLException,
    ProviderAuthenticationError,
    ProviderException,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from .ports.ai_provider import QueryContext
from .ports.schema_repository import TableInfo
from .schema.filters import filter_tables
from .utils.artifact_loader import (
    create_example_store_from_payload,
    load_examples_payload,
    load_semantic_context,
)
from .utils.redaction import mask_database_url


def get_embeddings_dir() -> Path:
    """Get the embeddings directory path from environment variable."""
    embeddings_dir = os.getenv("NLP2SQL_EMBEDDINGS_DIR", "./embeddings")
    return Path(embeddings_dir)


class _StderrHandler(logging.StreamHandler):
    """Writes to the current ``sys.stderr`` (click's test runner swaps it per invocation)."""

    @property
    def stream(self):  # type: ignore[override]
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


_cli_log_handler: Optional[logging.Handler] = None


def setup_logging(verbose: bool = False) -> None:
    """Send nlp2sql logs to stderr, so command output on stdout stays parseable.

    Level: DEBUG with --verbose, else NLP2SQL_LOG_LEVEL when set, else WARNING. Before,
    the CLI logged at INFO to stdout, mixed with the SQL and JSON it prints.
    """
    global _cli_log_handler
    if verbose:
        level = "DEBUG"
    elif "log_level" in settings.model_fields_set:
        level = settings.log_level.value
    else:
        level = "WARNING"

    library_logger = logging.getLogger("nlp2sql")
    if _cli_log_handler is not None:
        library_logger.removeHandler(_cli_log_handler)
    _cli_log_handler = _StderrHandler()
    _cli_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    library_logger.addHandler(_cli_log_handler)
    library_logger.setLevel(level)


PROVIDER_NAMES = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Gemini"}


def provider_api_key(provider: str) -> Optional[str]:
    """API key from the provider's environment variable (ProviderConfig.API_KEY_ENV_VARS)."""
    env_var = ProviderConfig.API_KEY_ENV_VARS.get(provider)
    return os.getenv(env_var) if env_var else None


def configured_providers() -> list[str]:
    return [provider for provider in PROVIDER_NAMES if provider_api_key(provider)]


# One table and one question keep a provider check to a few hundred tokens
_CHECK_SCHEMA = "Table: users\nColumns: id (integer, primary key), name (text)"
_CHECK_QUESTION = "How many users are there?"


async def check_provider(provider: str, api_key: Optional[str]) -> str:
    """Generate SQL for one small question; return "model, latency, tokens". Raises on failure."""
    config = ProviderConfig(provider=provider, api_key=api_key)
    ai_provider = create_ai_provider(config)
    started = time.perf_counter()
    response = await ai_provider.generate_query(
        QueryContext(question=_CHECK_QUESTION, database_type="postgres", schema_context=_CHECK_SCHEMA, examples=[])
    )
    elapsed = time.perf_counter() - started
    return f"{config.resolved_model}, {elapsed:.1f}s, {response.tokens_used} tokens"


def describe_provider_failure(provider: str, error: Exception) -> str:
    """What to do about a failed provider check, from the error type."""
    env_var = ProviderConfig.API_KEY_ENV_VARS[provider]
    status = (getattr(error, "details", None) or {}).get("status_code")
    if isinstance(error, ImportError):
        return f"SDK not installed. Install with: pip install nlp2sql[{provider}]"
    if isinstance(error, ProviderAuthenticationError):
        return f"API key rejected ({status}). Check {env_var}"
    if isinstance(error, ProviderRateLimitError):
        return "rate limited or out of quota (429)"
    if isinstance(error, ProviderUnavailableError):
        return "provider unreachable or unavailable"
    if isinstance(error, ProviderRequestError):
        hint = ". Check the model id" if status == 404 else ""
        return f"request rejected ({status}){hint}"
    return str(error)


async def run_provider_checks(providers: list[str]) -> list[bool]:
    """Check each provider with one real request and print one line per provider."""
    results = []
    for provider in providers:
        name = PROVIDER_NAMES[provider]
        try:
            summary = await check_provider(provider, provider_api_key(provider))
        except Exception as e:
            reason = describe_provider_failure(provider, e)
            click.echo(f"   [ERROR] {name}: {reason}")
            detail = str(e).splitlines()[0] if str(e) else ""
            if detail and detail != reason:
                click.echo(f"      {detail[:200]}")
            results.append(False)
            continue
        click.echo(f"   [OK] {name}: {summary}")
        results.append(True)
    return results


def detect_database_type(database_url: str) -> DatabaseType:
    """Detect database type from connection URL.

    This function delegates to RepositoryFactory.detect_database_type()
    for centralized database type detection logic.

    Args:
        database_url: Database connection URL

    Returns:
        Detected DatabaseType
    """
    from .factories import RepositoryFactory

    return RepositoryFactory.detect_database_type(database_url)


def validate_database_url(ctx, param, value):
    """Validate database URL format."""
    if value and not value.startswith(("postgresql://", "postgres://", "mysql://", "sqlite://", "redshift://")):
        # Never echo the value: a malformed URL can still contain the password
        scheme = value.split("://", 1)[0] if "://" in value else None
        reason = f"unsupported scheme '{scheme}'" if scheme else "missing scheme://"
        click.echo(f"[ERROR] Invalid database URL format: {reason}", err=True)
        click.echo("Hint: Expected format: postgresql://user:pass@host:port/database", err=True)
        click.echo("Note: Examples:", err=True)
        click.echo("   postgresql://testuser:testpass@localhost:5432/testdb", err=True)
        click.echo("   postgres://demo:demo123@localhost:5433/enterprise", err=True)
        click.echo("   redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/database", err=True)
        ctx.exit(1)
    return value


def parse_schema_filters(schema_filters: str | None) -> dict | None:
    """Parse schema filters JSON passed via CLI."""
    if not schema_filters:
        return None
    try:
        return json.loads(schema_filters)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in schema-filters: {exc.msg}.") from exc


def split_names(value: Optional[str]) -> Optional[list[str]]:
    """Parse a comma-separated option into names; None when it names nothing."""
    names = [name.strip() for name in (value or "").split(",") if name.strip()]
    return names or None


_SORT_KEYS = {
    "rows": lambda table: table.row_count or 0,
    "size": lambda table: table.size_bytes or 0,
    "columns": lambda table: len(table.columns),
}


def select_tables(  # noqa: PLR0913 — one keyword per inspect option
    tables: list[TableInfo],
    *,
    include_tables: Optional[list[str]] = None,
    exclude_tables: Optional[list[str]] = None,
    exclude_system: bool = False,
    min_rows: Optional[int] = None,
    sort_by: str = "name",
    max_tables: Optional[int] = None,
) -> list[TableInfo]:
    """Apply the inspect options: filter, keep tables with at least ``min_rows``, sort, then limit."""
    selected = filter_tables(
        tables,
        include_tables=include_tables,
        exclude_tables=exclude_tables,
        exclude_system_tables=exclude_system,
    )
    if min_rows is not None:
        selected = [table for table in selected if (table.row_count or 0) >= min_rows]
    selected.sort(key=lambda table: table.name)
    if sort_by in _SORT_KEYS:
        # Stable sort: ties stay in name order
        selected.sort(key=_SORT_KEYS[sort_by], reverse=True)
    return selected[:max_tables] if max_tables is not None else selected


def table_as_dict(table: TableInfo) -> dict:
    return {
        "name": table.name,
        "schema": table.schema,
        "columns": table.columns,
        "primary_keys": table.primary_keys,
        "foreign_keys": table.foreign_keys,
        "indexes": table.indexes,
        "row_count": table.row_count,
        "size_bytes": table.size_bytes,
        "description": table.description,
    }


def write_tables_csv(tables: list[TableInfo], output: TextIO) -> None:
    """One row per table; columns and foreign_keys are counts."""
    writer = csv.writer(output)
    writer.writerow(["name", "schema", "row_count", "size_bytes", "columns", "foreign_keys", "description"])
    for table in tables:
        writer.writerow(
            [
                table.name,
                table.schema,
                table.row_count if table.row_count is not None else "",
                table.size_bytes if table.size_bytes is not None else "",
                len(table.columns),
                len(table.foreign_keys),
                table.description or "",
            ]
        )


_SIZE_STEP = 1024


def _format_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return "-"
    if size_bytes < _SIZE_STEP:
        return f"{size_bytes} B"
    size = size_bytes / _SIZE_STEP
    for unit in ("KB", "MB", "GB"):
        if size < _SIZE_STEP:
            return f"{size:.1f} {unit}"
        size /= _SIZE_STEP
    return f"{size:.1f} TB"


def render_tables(tables: list[TableInfo]) -> str:
    """Plain-text table: name left-aligned, numbers right-aligned."""
    headers = ["Table", "Rows", "Size", "Columns", "Foreign keys"]
    rows = [
        [
            table.name,
            f"{table.row_count:,}" if table.row_count is not None else "-",
            _format_size(table.size_bytes),
            str(len(table.columns)),
            str(len(table.foreign_keys)),
        ]
        for table in tables
    ]
    widths = [max(len(cell) for cell in column) for column in zip(headers, *rows)]

    def line(cells: list[str]) -> str:
        first = cells[0].ljust(widths[0])
        rest = [cell.rjust(width) for cell, width in zip(cells[1:], widths[1:])]
        return "  ".join([first, *rest]).rstrip()

    return "\n".join([line(headers), "  ".join("-" * width for width in widths), *map(line, rows)])


def write_tables(tables: list[TableInfo], output_format: str, output: TextIO) -> None:
    """Write the selected tables as json, csv or a plain-text table."""
    if output_format == "json":
        json.dump([table_as_dict(table) for table in tables], output, indent=2)
    elif output_format == "csv":
        write_tables_csv(tables, output)
    else:
        click.echo(render_tables(tables), file=output)


def write_schema_summary(tables: list[TableInfo], total: int, database_url: str, schema: str, output: TextIO) -> None:
    shown = f"{len(tables)}" if len(tables) == total else f"{len(tables)} (of {total})"
    click.echo("[STATS] Database Schema Summary", file=output)
    click.echo("=" * 30, file=output)
    click.echo(f"Database URL: {mask_database_url(database_url)}", file=output)
    click.echo(f"Schema: {schema}", file=output)
    click.echo(f"Total tables: {shown}", file=output)
    click.echo(f"Total columns: {sum(len(table.columns) for table in tables):,}", file=output)
    click.echo(f"Tables with foreign keys: {sum(1 for table in tables if table.foreign_keys)}", file=output)


def resolve_execution_mode(validate: bool, repair: bool) -> str:
    """Resolve CLI validate/repair flags into the public execution mode."""
    if repair:
        return ExecutionMode.GENERATE_VALIDATE_REPAIR.value
    if validate:
        return ExecutionMode.GENERATE_AND_VALIDATE.value
    return ExecutionMode.GENERATE_ONLY.value


def echo_runtime_metadata(
    result: dict,
    *,
    show_semantic_context: bool,
    show_sql_intent_plan: bool,
    show_selected_examples: bool,
) -> None:
    """Print optional semantic/runtime metadata sections."""
    metadata = result.get("metadata", {})
    if show_semantic_context and metadata.get("semantic_context"):
        click.echo("\nSemantic Context:")
        click.echo(json.dumps(metadata["semantic_context"], indent=2))
    if show_sql_intent_plan and metadata.get("sql_intent_plan"):
        click.echo("\nSQL Intent Plan:")
        click.echo(json.dumps(metadata["sql_intent_plan"], indent=2))
    if show_selected_examples and metadata.get("selected_examples"):
        click.echo("\nSelected Examples:")
        click.echo(json.dumps(metadata["selected_examples"], indent=2))


@click.group()
@click.version_option()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--config", type=click.Path(), help="Configuration file path")
@click.pass_context
def cli(ctx, verbose, config):
    """nlp2sql - Advanced Natural Language to SQL converter with multiple AI providers."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = config

    setup_logging(verbose)

    if verbose:
        click.echo("[CONFIG] Verbose mode enabled")


@cli.command(name="version")
def version():
    """Show the version of the tool."""
    from . import __version__

    click.echo(f"nlp2sql version {__version__}")


@cli.command(name="config")
@click.pass_context
def config(ctx):
    """Show the current configuration."""
    verbose = ctx.obj.get("verbose", False)
    config_path = ctx.obj.get("config", "Not set")

    click.echo("[CONFIG] Current Configuration")
    click.echo("=" * 25)
    click.echo(f"Verbose mode: {'✅' if verbose else '❌'}")
    click.echo(f"Config file: {config_path}")

    click.echo("\n🔑 API Keys Status:")
    for provider, name in PROVIDER_NAMES.items():
        env_var = ProviderConfig.API_KEY_ENV_VARS[provider]
        if provider_api_key(provider):
            click.echo(f"   [OK] {name} ({env_var}): Set")
        else:
            click.echo(f"   [ERROR] {name} ({env_var}): Not set")

    db_url = os.getenv("DATABASE_URL")
    click.echo("\n[DATABASE] Database Connection:")
    if db_url:
        click.echo(f"   [OK] DATABASE_URL: {mask_database_url(db_url)}")
    else:
        click.echo("   [ERROR] DATABASE_URL: Not set")


@cli.command(name="init")
def init():
    """Create a new configuration file."""
    config_path = Path("nplsql.toml")
    if config_path.exists():
        click.echo("[ERROR] Configuration file already exists.")
        return

    config_content = """# nplsql configuration file

[default]
provider = "openai"
database_url = "postgresql://user:pass@host:port/db"

[providers.openai]
api_key = "$OPENAI_API_KEY"

[providers.anthropic]
api_key = "$ANTHROPIC_API_KEY"

[providers.gemini]
api_key = "$GOOGLE_API_KEY"
"""
    config_path.write_text(config_content)
    click.echo(f"[OK] Created configuration file: {config_path}")


@cli.command()
@click.option("--database-url", required=True, callback=validate_database_url, help="Database connection URL")
@click.option("--schema", default="public", help="Database schema name")
@click.option("--output", type=click.File("w"), default="-", help="Output file (default: stdout)")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table", "summary", "csv"]),
    default="summary",
    help="Output format",
)
@click.option("--include-tables", help="Comma-separated list of tables to include")
@click.option("--exclude-tables", help="Comma-separated list of tables to exclude")
@click.option("--exclude-system", is_flag=True, help="Exclude system tables (pg_, sql_, information_schema, ...)")
@click.option(
    "--min-rows",
    type=int,
    help="Only show tables with at least N rows (PostgreSQL statistics estimate; Redshift reports 0 rows)",
)
@click.option("--max-tables", type=int, help="Limit number of tables shown")
@click.option(
    "--sort-by",
    type=click.Choice(["name", "rows", "size", "columns"]),
    default="name",
    help="Sort tables by field (rows, size and columns: largest first)",
)
@click.pass_context
def inspect(
    ctx,
    database_url: str,
    schema: str,
    output,
    output_format: str,
    include_tables: Optional[str],
    exclude_tables: Optional[str],
    exclude_system: bool,
    min_rows: Optional[int],
    max_tables: Optional[int],
    sort_by: str,
):
    """Inspect database schema with advanced filtering and analysis."""
    verbose = ctx.obj.get("verbose", False)

    async def _inspect():
        try:
            # Detect database type and create appropriate repository using factory
            from .factories import RepositoryFactory

            database_type = detect_database_type(database_url)

            if verbose:
                click.echo(f"[DATABASE] Detected database type: {database_type.value}")

            try:
                repo = await RepositoryFactory.create_and_initialize(database_url, schema, database_type)
            except NotImplementedError as e:
                click.echo(f"[ERROR] {e}", err=True)
                sys.exit(1)

            all_tables = await repo.get_tables()
            if min_rows and database_type == DatabaseType.REDSHIFT:
                click.echo("[WARNING] Redshift tables report 0 rows, so --min-rows leaves no tables", err=True)
            tables = select_tables(
                all_tables,
                include_tables=split_names(include_tables),
                exclude_tables=split_names(exclude_tables),
                exclude_system=exclude_system,
                min_rows=min_rows,
                sort_by=sort_by,
                max_tables=max_tables,
            )

            if output_format == "summary":
                write_schema_summary(tables, len(all_tables), database_url, schema, output)
            else:
                write_tables(tables, output_format, output)

        except NLP2SQLException as e:
            click.echo(f"[ERROR] Application Error: {e!s}", err=True)
            if verbose and hasattr(e, "details"):
                click.echo(f"   Details: {e.details}", err=True)
            sys.exit(1)

        except Exception as e:
            click.echo(f"[ERROR] An unexpected error occurred: {e!s}", err=True)
            if verbose:
                import traceback

                click.echo(traceback.format_exc(), err=True)
            sys.exit(1)

    asyncio.run(_inspect())


@cli.command()
@click.option("--database-url", required=True, callback=validate_database_url, help="Database connection URL")
@click.option("--question", required=True, help="Natural language question")
@click.option("--schema", default="public", help="Database schema name")
@click.option(
    "--provider",
    default="openai",
    type=click.Choice(["openai", "anthropic", "gemini"]),
    help="AI provider to use (default: openai)",
)
@click.option("--api-key", help="API key (or use environment variables)")
@click.option(
    "--model",
    default=None,
    help="AI model name (default depends on provider; e.g., gpt-5.6-terra, claude-sonnet-5, gemini-3.1-flash-lite)",
)
@click.option("--explain", is_flag=True, help="Include detailed explanation")
@click.option("--temperature", type=float, default=0.1, help="Model temperature (0.0-1.0)")
@click.option("--max-tokens", type=int, default=1000, help="Maximum tokens for response")
@click.option("--schema-filters", help="JSON string with schema filters")
@click.option("--semantic-context-file", type=click.Path(exists=True), help="Path to semantic context JSON/YAML")
@click.option("--semantic-context-json", help="Inline semantic context JSON")
@click.option("--examples-file", type=click.Path(exists=True), help="Path to few-shot examples JSON/YAML")
@click.option("--examples-json", help="Inline few-shot examples JSON")
@click.option("--show-semantic-context", is_flag=True, help="Print the semantic context used at runtime")
@click.option("--show-sql-intent-plan", is_flag=True, help="Print the SQL intent plan built for the question")
@click.option("--show-selected-examples", is_flag=True, help="Print metadata for selected few-shot examples")
@click.option("--validate", "run_validation", is_flag=True, help="Execute generated SQL for validation")
@click.option("--repair", is_flag=True, help="Retry with repair on execution or semantic failures")
@click.option(
    "--embedding-provider",
    type=click.Choice(["auto", "local", "openai", "none"]),
    default="auto",
    help="Embedding provider: 'auto' (try local, fallback), 'local', 'openai', or 'none' (disable)",
)
@click.option(
    "--llm-validation",
    is_flag=True,
    help="Also ask the LLM to review the generated SQL (a second call; default: NLP2SQL_LLM_VALIDATION)",
)
@click.pass_context
def query(
    ctx,
    database_url: str,
    question: str,
    schema: str,
    provider: str,
    api_key: Optional[str],
    model: Optional[str],
    explain: bool,
    temperature: float,
    max_tokens: int,
    schema_filters: Optional[str],
    semantic_context_file: Optional[str],
    semantic_context_json: Optional[str],
    examples_file: Optional[str],
    examples_json: Optional[str],
    show_semantic_context: bool,
    show_sql_intent_plan: bool,
    show_selected_examples: bool,
    run_validation: bool,
    repair: bool,
    embedding_provider: str,
    llm_validation: bool,
):
    """Generate SQL from natural language question with advanced options."""
    verbose = ctx.obj.get("verbose", False)

    async def _query():
        try:
            if verbose:
                click.echo(f"[CONFIG] Using provider: {provider}")
                click.echo(f"[CONFIG] Embedding provider: {embedding_provider}")
                click.echo(f"🌡️  Temperature: {temperature}")
                click.echo(f"📏 Max tokens: {max_tokens}")

            filters = parse_schema_filters(schema_filters)

            # Get API key from parameter or environment
            final_api_key = api_key
            if not final_api_key:
                env_var = ProviderConfig.API_KEY_ENV_VARS[provider]
                final_api_key = provider_api_key(provider)
                if not final_api_key:
                    click.echo(f"[ERROR] No API key provided. Set {env_var} or use --api-key", err=True)
                    sys.exit(1)

            # Detect database type from URL
            database_type = detect_database_type(database_url)

            if verbose:
                click.echo(f"[DATABASE] Detected database type: {database_type.value}")

            # Determine embedding provider type
            if embedding_provider == "none":
                embedding_provider_type = None  # Explicitly disable
            elif embedding_provider == "auto":
                embedding_provider_type = None  # Let the function handle auto-detection
            else:
                embedding_provider_type = embedding_provider  # "local" or "openai"

            semantic_context = load_semantic_context(
                file_path=semantic_context_file,
                inline_json=semantic_context_json,
            )
            examples_payload = load_examples_payload(
                file_path=examples_file,
                inline_json=examples_json,
                database_type=database_type,
            )
            example_store = await create_example_store_from_payload(
                examples=examples_payload,
                database_url=database_url,
                schema_name=schema,
                embedding_provider_type=embedding_provider_type,
                api_key=final_api_key,
            )

            # Build unified provider config
            provider_config = ProviderConfig(
                provider=provider,
                api_key=final_api_key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Create service
            service = await create_and_initialize_service(
                database_url=database_url,
                provider_config=provider_config,
                database_type=database_type,
                schema_filters=filters,
                schema_name=schema,
                embedding_provider_type=embedding_provider_type,
                example_store=example_store,
                # Without the flag, NLP2SQL_LLM_VALIDATION decides
                llm_validation=True if llm_validation else None,
            )

            # Generate SQL
            result = await service.generate_sql(
                question=question,
                database_type=database_type,
                temperature=temperature,
                max_tokens=max_tokens,
                include_explanation=explain,
                execution_mode=resolve_execution_mode(run_validation, repair),
                semantic_context=semantic_context,
            )

            # Output results
            click.echo(f"❓ Question: {question}")
            click.echo(f"AI: Provider: {provider.title()}")
            click.echo(f"Note: SQL: {result['sql']}")
            click.echo(f"[STATS] Confidence: {result['confidence']}")
            click.echo(f"[PERF] Tokens used: {result['tokens_used']}")

            if explain and "explanation" in result:
                click.echo(f"Hint: Explanation: {result['explanation']}")

            if "validation" in result:
                validation = result["validation"]
                if validation["is_valid"]:
                    click.echo("[OK] SQL validation: Passed")
                else:
                    click.echo(f"[WARNING] SQL validation issues: {validation.get('issues', [])}")

            echo_runtime_metadata(
                result,
                show_semantic_context=show_semantic_context,
                show_sql_intent_plan=show_sql_intent_plan,
                show_selected_examples=show_selected_examples,
            )

        except ProviderException as e:
            click.echo(f"[ERROR] Provider Error: {e!s}", err=True)
            if hasattr(e, "provider"):
                click.echo(f"   Provider: {e.provider}", err=True)
            if hasattr(e, "status_code"):
                click.echo(f"   Status Code: {e.status_code}", err=True)
            if verbose and hasattr(e, "details"):
                click.echo(f"   Details: {e.details}", err=True)
            sys.exit(1)

        except NLP2SQLException as e:
            click.echo(f"[ERROR] Application Error: {e!s}", err=True)
            if verbose and hasattr(e, "details"):
                click.echo(f"   Details: {e.details}", err=True)
            sys.exit(1)

        except Exception as e:
            click.echo(f"[ERROR] An unexpected error occurred: {e!s}", err=True)
            if verbose:
                import traceback

                click.echo(traceback.format_exc(), err=True)
            sys.exit(1)

    asyncio.run(_query())


@cli.command()
@click.pass_context
def setup(ctx):
    """Interactive setup and configuration for nlp2sql."""
    click.echo("nlp2sql - Interactive Setup")
    click.echo("=" * 40)

    click.echo("\n🔑 API Keys Status:")
    available_providers = []

    for provider, name in PROVIDER_NAMES.items():
        key = provider_api_key(provider)
        if key:
            masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
            click.echo(f"   [OK] {name}: {masked_key}")
            available_providers.append(provider)
        else:
            click.echo(f"   [ERROR] {name}: Not set ({ProviderConfig.API_KEY_ENV_VARS[provider]})")

    if not available_providers:
        click.echo("\n[WARNING] No API keys found!")
        click.echo("Hint: Set at least one API key:")
        click.echo("   export OPENAI_API_KEY=your-openai-key")
        click.echo("   export ANTHROPIC_API_KEY=your-anthropic-key")
        click.echo("   export GOOGLE_API_KEY=your-google-key")
        return

    click.echo(f"\n[OK] Available providers: {', '.join(available_providers)}")

    # Interactive configuration
    if click.confirm("\n[CONFIG] Would you like to test your API keys? (one small request each)"):
        click.echo("\n🧪 Testing API providers...")
        asyncio.run(run_provider_checks(available_providers))

    # Database setup
    if click.confirm("\n[DATABASE] Would you like to configure a database connection?"):
        _setup_database()

    click.echo("\n[SUCCESS] Setup completed!")
    click.echo("Hint: Run 'nlp2sql validate' to verify your configuration")


def _setup_database():
    """Interactive database setup."""
    click.echo("\n[STATS] Database Configuration")
    click.echo("-" * 30)

    # Only the databases nlp2sql has adapters for
    db_type = click.prompt("Select database type", type=click.Choice(["postgresql", "redshift"]), default="postgresql")
    default_port = "5432" if db_type == "postgresql" else "5439"

    host = click.prompt("Host", default="localhost")
    port = click.prompt("Port", default=default_port)
    username = click.prompt("Username")
    password = click.prompt("Password", hide_input=True)
    database = click.prompt("Database name")

    db_url = f"{db_type}://{username}:{password}@{host}:{port}/{database}"

    click.echo(f"\nNote: Connection string: {db_url}")
    click.echo("Hint: Save this to your environment:")
    click.echo(f'   export DATABASE_URL="{db_url}"')


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate nlp2sql configuration and test all components."""
    verbose = ctx.obj.get("verbose", False)

    click.echo("Info: nlp2sql - Configuration Validation")
    click.echo("=" * 45)

    tests = []

    click.echo("\n🔑 Testing API Keys (one small request each)...")
    if verbose:
        for provider, name in PROVIDER_NAMES.items():
            if not provider_api_key(provider):
                click.echo(f"   [WARNING] {name}: Not configured ({ProviderConfig.API_KEY_ENV_VARS[provider]})")
    tests.extend(asyncio.run(run_provider_checks(configured_providers())))

    # Test database connection if provided
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        click.echo("\n[DATABASE] Testing Database Connection...")
        try:
            asyncio.run(_test_database(db_url, verbose))
            click.echo("   [OK] Database connection: Success")
            tests.append(True)
        except Exception as e:
            click.echo(f"   [ERROR] Database connection: {e!s}")
            tests.append(False)
    elif verbose:
        click.echo("\n[WARNING] No DATABASE_URL configured")

    if not _print_validation_summary(tests):
        sys.exit(1)


def _print_validation_summary(tests: list[bool]) -> bool:
    """Print the summary; True only when something was checked and everything passed."""
    passed, total = sum(tests), len(tests)
    click.echo("\n[STATS] Validation Summary:")
    click.echo(f"   Tests passed: {passed}/{total}")
    if total == 0:
        click.echo("[ERROR] Nothing to validate: set an API key or DATABASE_URL.")
    elif passed == total:
        click.echo("[SUCCESS] All tests passed! nlp2sql is ready to use!")
    elif passed > 0:
        click.echo("[WARNING] Some tests passed. Check failures above.")
    else:
        click.echo("[ERROR] All tests failed. Please check your configuration.")
    return total > 0 and passed == total


async def _test_database(db_url: str, verbose: bool = False):
    """Test database connection."""
    from .factories import RepositoryFactory

    if verbose:
        click.echo(f"Info: Connecting to: {mask_database_url(db_url)}")

    await RepositoryFactory.create_and_initialize(db_url)
    if verbose:
        click.echo("   Connection established successfully")


@cli.group()
def providers():
    """Manage AI providers."""
    pass


@providers.command("list")
def providers_list():
    """List all available AI providers."""
    click.echo("AI: Available AI Providers")
    click.echo("=" * 30)

    contexts = {"openai": "1.05M tokens (922K input)", "anthropic": "1M tokens", "gemini": "1M tokens"}
    providers_info = [
        {
            "name": name,
            "provider": provider,
            "env_var": ProviderConfig.API_KEY_ENV_VARS[provider],
            "models": f"default: {ProviderConfig.DEFAULT_MODELS[provider]}",
            "context": contexts[provider],
        }
        for provider, name in PROVIDER_NAMES.items()
    ]

    for provider in providers_info:
        api_key = os.getenv(provider["env_var"])
        status = "[OK] Configured" if api_key else "[ERROR] Not configured"

        click.echo(f"\nAI: {provider['name']}")
        click.echo(f"   Provider: {provider['provider']}")
        click.echo(f"   Models: {provider['models']}")
        click.echo(f"   Context: {provider['context']}")
        click.echo(f"   Status: {status}")
        click.echo(f"   Setup: export {provider['env_var']}=your-key")


@providers.command("test")
@click.option(
    "--provider",
    type=click.Choice(sorted(ProviderConfig.SUPPORTED_PROVIDERS)),
    help="Test one provider (default: every provider with an API key set)",
)
def providers_test(provider):
    """Check AI providers with one small SQL generation request each (exit 1 if any fails)."""
    if provider and not provider_api_key(provider):
        click.echo(f"[ERROR] {PROVIDER_NAMES[provider]}: no API key. Set {ProviderConfig.API_KEY_ENV_VARS[provider]}")
        sys.exit(1)
    providers_to_test = [provider] if provider else configured_providers()
    if not providers_to_test:
        env_vars = ", ".join(ProviderConfig.API_KEY_ENV_VARS.values())
        click.echo(f"[ERROR] No providers configured. Set one of: {env_vars}")
        sys.exit(1)

    click.echo("🧪 Testing AI Providers")
    click.echo("=" * 25)
    results = asyncio.run(run_provider_checks(providers_to_test))
    if not all(results):
        sys.exit(1)


@cli.command()
@click.option("--database-url", required=True, callback=validate_database_url, help="Database connection URL")
@click.option("--schema", default="public", help="Database schema name")
@click.option("--questions", help="File with test questions (one per line)")
@click.option("--providers", help="Comma-separated list of providers to test")
@click.option("--iterations", type=int, default=3, help="Number of iterations per test")
@click.option("--schema-filters", help="JSON string with schema filters")
@click.option("--semantic-context-file", type=click.Path(exists=True), help="Path to semantic context JSON/YAML")
@click.option("--semantic-context-json", help="Inline semantic context JSON")
@click.option("--examples-file", type=click.Path(exists=True), help="Path to few-shot examples JSON/YAML")
@click.option("--examples-json", help="Inline few-shot examples JSON")
@click.option(
    "--embedding-provider",
    type=click.Choice(["auto", "local", "openai", "none"]),
    default="auto",
    help="Embedding provider for schema/examples: 'auto', 'local', 'openai', or 'none'",
)
@click.option("--output-file", type=click.Path(), help="Output file to save benchmark results (JSON format)")
@click.pass_context
def benchmark(
    ctx,
    database_url: str,
    schema: str,
    questions: Optional[str],
    providers: Optional[str],
    iterations: int,
    schema_filters: Optional[str],
    semantic_context_file: Optional[str],
    semantic_context_json: Optional[str],
    examples_file: Optional[str],
    examples_json: Optional[str],
    embedding_provider: str,
    output_file: Optional[str],
):
    """Benchmark different AI providers performance."""
    verbose = ctx.obj.get("verbose", False)

    async def _benchmark():
        filters = parse_schema_filters(schema_filters)
        database_type = detect_database_type(database_url)
        semantic_context = load_semantic_context(
            file_path=semantic_context_file,
            inline_json=semantic_context_json,
        )

        # Default test questions
        default_questions = [
            "Count total users",
            "Show active customers",
            "Find recent orders",
            "Calculate monthly revenue",
            "List top products",
        ]

        # Load questions from file or use defaults
        test_questions = default_questions
        if questions:
            try:
                with open(questions) as f:
                    test_questions = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                click.echo(f"[ERROR] Questions file not found: {questions}", err=True)
                return

        # The listed providers, else every provider with an API key set
        test_providers = providers.split(",") if providers else configured_providers()

        if not test_providers:
            click.echo("[ERROR] No providers configured", err=True)
            return

        click.echo("🏁 nlp2sql Provider Benchmark")
        click.echo("=" * 35)
        click.echo(f"[STATS] Testing {len(test_providers)} providers")
        click.echo(f"❓ {len(test_questions)} questions")
        click.echo(f"🔄 {iterations} iterations each")
        click.echo()

        results = {}

        for provider in test_providers:
            click.echo(f"🧪 Testing {provider.title()}...")
            provider_results = {
                "total_time": 0,
                "total_tokens": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "avg_confidence": 0,
                "confidences": [],
            }

            api_key = provider_api_key(provider)

            try:
                if embedding_provider == "none":
                    embedding_provider_type = None
                elif embedding_provider == "auto":
                    embedding_provider_type = "local"
                else:
                    embedding_provider_type = embedding_provider

                examples_payload = load_examples_payload(
                    file_path=examples_file,
                    inline_json=examples_json,
                    database_type=database_type,
                )
                example_store = await create_example_store_from_payload(
                    examples=examples_payload,
                    database_url=database_url,
                    schema_name=schema,
                    embedding_provider_type=embedding_provider_type,
                    api_key=api_key,
                )
                provider_config = ProviderConfig(
                    provider=provider,
                    api_key=api_key,
                )
                service = await create_and_initialize_service(
                    database_url=database_url,
                    provider_config=provider_config,
                    database_type=database_type,
                    schema_filters=filters,
                    schema_name=schema,
                    embedding_provider_type=embedding_provider_type,
                    example_store=example_store,
                )

                for question in test_questions:
                    for iteration in range(iterations):
                        try:
                            start_time = time.time()
                            result = await service.generate_sql(
                                question=question,
                                database_type=database_type,
                                semantic_context=semantic_context,
                            )
                            end_time = time.time()

                            provider_results["total_time"] += end_time - start_time
                            provider_results["total_tokens"] += result.get("tokens_used", 0)
                            provider_results["successful_queries"] += 1
                            provider_results["confidences"].append(result.get("confidence", 0))

                            if verbose:
                                click.echo(f"   [OK] '{question}' - {end_time - start_time:.2f}s")

                        except Exception as e:
                            provider_results["failed_queries"] += 1
                            if verbose:
                                click.echo(f"   [ERROR] '{question}' - {e!s}")

                # Calculate averages
                if provider_results["confidences"]:
                    provider_results["avg_confidence"] = sum(provider_results["confidences"]) / len(
                        provider_results["confidences"]
                    )

                results[provider] = provider_results
                click.echo(f"   [OK] {provider.title()} completed")

            except Exception as e:
                click.echo(f"   [ERROR] {provider.title()} failed: {e!s}")

        # Display results
        if output_file:
            try:
                with open(output_file, "w") as f:
                    json.dump(results, f, indent=2)
                click.echo(f"[OK] Benchmark results saved to {output_file}")
            except Exception as e:
                click.echo(f"[ERROR] Failed to save results to {output_file}: {e!s}", err=True)
        else:
            click.echo("\n[STATS] Benchmark Results")
            click.echo("=" * 25)

            for provider, stats in results.items():
                total_queries = stats["successful_queries"] + stats["failed_queries"]
                success_rate = (stats["successful_queries"] / total_queries * 100) if total_queries > 0 else 0
                avg_time = stats["total_time"] / stats["successful_queries"] if stats["successful_queries"] > 0 else 0

                click.echo(f"\nAI: {provider.title()}:")
                click.echo(f"   [OK] Success rate: {success_rate:.1f}%")
                click.echo(f"   ⏱️  Avg response time: {avg_time:.2f}s")
                click.echo(f"   🎯 Avg confidence: {stats['avg_confidence']:.2f}")
                click.echo(f"   [PERF] Total tokens: {stats['total_tokens']:,}")

            # Find the best performer
            if results:
                best_provider = max(results.keys(), key=lambda p: results[p]["avg_confidence"])
                click.echo(f"\n[BEST] Best performer: {best_provider.title()}")

    asyncio.run(_benchmark())


@cli.group()
def cache():
    """Manage nlp2sql cache and embeddings."""
    pass


@cache.command("clear")
@click.option("--all", "clear_all", is_flag=True, help="Clear all cache files")
@click.option("--embeddings", is_flag=True, help="Clear embeddings cache")
@click.option("--queries", is_flag=True, help="Clear query cache")
@click.option("--tables", is_flag=True, help="Clear tables cache (forces re-fetch from database)")
def cache_clear(clear_all: bool, embeddings: bool, queries: bool, tables: bool):
    """Clear various cache files.

    Examples:
        nlp2sql cache clear --tables       # Clear tables cache only
        nlp2sql cache clear --embeddings   # Clear embeddings cache only
        nlp2sql cache clear --all          # Clear all caches
    """
    if not any([clear_all, embeddings, queries, tables]):
        click.echo("[ERROR] Specify what to clear: --all, --embeddings, --queries, or --tables")
        return

    # Get embeddings directory from environment variable
    embeddings_dir = get_embeddings_dir()

    cleared = []

    if clear_all:
        embeddings = queries = tables = True

    if embeddings:
        click.echo("Clearing embeddings cache...")
        cache_paths = [str(embeddings_dir) + "/", "schema_embeddings.pkl", "schema_index.faiss"]
        for path in cache_paths:
            if Path(path).exists():
                if Path(path).is_dir():
                    import shutil

                    shutil.rmtree(path)
                else:
                    Path(path).unlink()
                cleared.append(path)

    if queries:
        click.echo("Clearing query cache...")
        cache_paths = ["query_cache.db", ".nlp2sql_cache/"]
        for path in cache_paths:
            if Path(path).exists():
                if Path(path).is_dir():
                    import shutil

                    shutil.rmtree(path)
                else:
                    Path(path).unlink()
                cleared.append(path)

    if tables:
        click.echo("Clearing tables cache...")
        # Tables cache files are stored as tables_cache_*.pkl in embeddings subdirectories
        if embeddings_dir.exists():
            for cache_file in embeddings_dir.rglob("tables_cache_*.pkl"):
                try:
                    cache_file.unlink()
                    cleared.append(str(cache_file))
                    click.echo(f"   Deleted: {cache_file}")
                except Exception as e:
                    click.echo(f"   [ERROR] Failed to delete {cache_file}: {e}", err=True)

    if cleared:
        click.echo(f"[OK] Cleared {len(cleared)} cache file(s)")
    else:
        click.echo("No cache files found to clear")


@cache.command("info")
def cache_info():
    """Show cache information and statistics."""
    import pickle

    click.echo("[STATS] Cache Information")
    click.echo("=" * 25)

    # Check embeddings cache using environment variable
    embeddings_path = get_embeddings_dir()
    if embeddings_path.exists():
        size = sum(f.stat().st_size for f in embeddings_path.rglob("*") if f.is_file())
        files = len([f for f in embeddings_path.rglob("*") if f.is_file()])
        click.echo("Embeddings cache:")
        click.echo(f"   Location: {embeddings_path.absolute()}")
        click.echo(f"   Size: {size / 1024 / 1024:.2f} MB")
        click.echo(f"   Files: {files}")
    else:
        click.echo("Embeddings cache: Not found")

    # Check tables cache
    tables_caches = list(embeddings_path.rglob("tables_cache_*.pkl")) if embeddings_path.exists() else []
    if tables_caches:
        click.echo("\nTables cache:")
        total_tables = 0
        for cache_file in tables_caches:
            try:
                with open(cache_file, "rb") as f:
                    cache_data = pickle.load(f)
                table_count = cache_data.get("table_count", 0)
                created_at = cache_data.get("created_at")
                schema_name = cache_data.get("schema_name", "unknown")
                total_tables += table_count

                age_str = ""
                if created_at:
                    age_hours = (datetime.now() - created_at).total_seconds() / 3600
                    age_str = f", age: {age_hours:.1f}h"

                click.echo(f"   {cache_file.name}: {table_count} tables (schema: {schema_name}{age_str})")
            except Exception as e:
                click.echo(f"   {cache_file.name}: [ERROR] {e}")
        click.echo(f"   Total cached tables: {total_tables}")
    else:
        click.echo("\nTables cache: Not found")

    # Check FAISS index
    faiss_path = Path("schema_index.faiss")
    if faiss_path.exists():
        size = faiss_path.stat().st_size
        click.echo("\nFAISS index:")
        click.echo(f"   Location: {faiss_path.absolute()}")
        click.echo(f"   Size: {size / 1024 / 1024:.2f} MB")
    else:
        click.echo("\nFAISS index: Not found")

    # Check query cache
    query_cache_path = Path("query_cache.db")
    if query_cache_path.exists():
        size = query_cache_path.stat().st_size
        click.echo("\nQuery cache:")
        click.echo(f"   📁 Location: {query_cache_path.absolute()}")
        click.echo(f"   [STATS] Size: {size / 1024:.2f} KB")
    else:
        click.echo("💾 Query cache: Not found")


def main():
    """Main CLI entry point."""
    cli()


if __name__ == "__main__":
    main()
