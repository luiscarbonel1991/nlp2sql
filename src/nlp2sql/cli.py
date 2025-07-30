"""Enhanced command line interface for nlp2sql."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import click
import structlog

from . import create_and_initialize_service, create_query_service
from .adapters.postgres_repository import PostgreSQLRepository
from .core.entities import DatabaseType
from .exceptions import NLP2SQLException, ProviderException


def get_embeddings_dir() -> Path:
    """Get the embeddings directory path from environment variable."""
    embeddings_dir = os.getenv("NLP2SQL_EMBEDDINGS_DIR", "./embeddings")
    return Path(embeddings_dir)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = "DEBUG" if verbose else "INFO"

    processors = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if verbose:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(min_level=level),
    )


def detect_command_confusion(ctx, param, value):
    """Detect common command confusions and provide helpful suggestions."""
    if ctx.info_name == "inspect" and param.name == "question":
        click.echo("❌ Error: 'inspect' command doesn't accept --question option", err=True)
        click.echo('💡 Did you mean: nlp2sql query --database-url [...] --question "..."', err=True)
        click.echo("🔍 Use 'inspect' to analyze database schema", err=True)
        click.echo("🤖 Use 'query' to generate SQL from natural language", err=True)
        ctx.exit(1)
    return value


def validate_database_url(ctx, param, value):
    """Validate database URL format."""
    if value and not value.startswith(("postgresql://", "mysql://", "sqlite://")):
        click.echo(f"❌ Invalid database URL format: {value}", err=True)
        click.echo("💡 Expected format: postgresql://user:pass@host:port/database", err=True)
        click.echo("📝 Examples:", err=True)
        click.echo("   postgresql://testuser:testpass@localhost:5432/testdb", err=True)
        click.echo("   postgresql://demo:demo123@localhost:5433/enterprise", err=True)
        ctx.exit(1)
    return value


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
        click.echo("🔧 Verbose mode enabled")


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

    click.echo("🔧 Current Configuration")
    click.echo("=" * 25)
    click.echo(f"Verbose mode: {'✅' if verbose else '❌'}")
    click.echo(f"Config file: {config_path}")

    click.echo("\n🔑 API Keys Status:")
    api_keys = {
        "OpenAI": os.getenv("OPENAI_API_KEY"),
        "Anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "Google": os.getenv("GOOGLE_API_KEY"),
    }
    for provider, key in api_keys.items():
        if key:
            click.echo(f"   ✅ {provider}: Set")
        else:
            click.echo(f"   ❌ {provider}: Not set")

    db_url = os.getenv("DATABASE_URL")
    click.echo("\n🗄️ Database Connection:")
    if db_url:
        click.echo(f"   ✅ DATABASE_URL: {db_url}")
    else:
        click.echo("   ❌ DATABASE_URL: Not set")


@cli.command(name="init")
def init():
    """Create a new configuration file."""
    config_path = Path("nplsql.toml")
    if config_path.exists():
        click.echo("❌ Configuration file already exists.")
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
    click.echo(f"✅ Created configuration file: {config_path}")


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
@click.option("--exclude-system", is_flag=True, help="Exclude system tables")
@click.option("--min-rows", type=int, help="Only show tables with at least N rows")
@click.option("--max-tables", type=int, help="Limit number of tables shown")
@click.option(
    "--sort-by", type=click.Choice(["name", "rows", "size", "columns"]), default="name", help="Sort tables by field"
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
    if "question" in ctx.params:
        click.echo("❌ Error: 'inspect' command doesn't accept --question option", err=True)
        click.echo('💡 Did you mean: nlp2sql query --database-url [...] --question "..."', err=True)
        click.echo("🔍 Use 'inspect' to analyze database schema", err=True)
        click.echo("🤖 Use 'query' to generate SQL from natural language", err=True)
        ctx.exit(1)

    verbose = ctx.obj.get("verbose", False)

    async def _inspect():
        try:
            # Create repository
            repo = PostgreSQLRepository(database_url, schema)
            await repo.initialize()

            # Get schema information
            tables = await repo.get_tables()

            if output_format == "json":
                # Export full schema as JSON
                schema_data = []
                for table in tables:
                    table_data = {
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
                    schema_data.append(table_data)

                json.dump(schema_data, output, indent=2)

            else:  # summary or table
                total_columns = sum(len(t.columns) for t in tables)
                tables_with_fk = sum(1 for t in tables if t.foreign_keys)

                click.echo("📊 Database Schema Summary", file=output)
                click.echo("=" * 30, file=output)
                click.echo(f"Database URL: {database_url}", file=output)
                click.echo(f"Schema: {schema}", file=output)
                click.echo(f"Total tables: {len(tables)}", file=output)
                click.echo(f"Total columns: {total_columns:,}", file=output)
                click.echo(f"Tables with foreign keys: {tables_with_fk}", file=output)

        except NLP2SQLException as e:
            click.echo(f"❌ Application Error: {e!s}", err=True)
            if verbose and hasattr(e, "details"):
                click.echo(f"   Details: {e.details}", err=True)
            sys.exit(1)

        except Exception as e:
            click.echo(f"❌ An unexpected error occurred: {e!s}", err=True)
            if verbose:
                import traceback

                click.echo(traceback.format_exc(), err=True)
            sys.exit(1)

    asyncio.run(_inspect())


@cli.command()
@click.option("--database-url", required=True, callback=validate_database_url, help="Database connection URL")
@click.option("--question", required=True, help="Natural language question")
@click.option(
    "--provider",
    default="openai",
    type=click.Choice(["openai", "anthropic", "gemini"]),
    help="AI provider to use (default: openai)",
)
@click.option("--api-key", help="API key (or use environment variables)")
@click.option("--explain", is_flag=True, help="Include detailed explanation")
@click.option("--temperature", type=float, default=0.1, help="Model temperature (0.0-1.0)")
@click.option("--max-tokens", type=int, default=1000, help="Maximum tokens for response")
@click.option("--schema-filters", help="JSON string with schema filters")
@click.pass_context
def query(
    ctx,
    database_url: str,
    question: str,
    provider: str,
    api_key: Optional[str],
    explain: bool,
    temperature: float,
    max_tokens: int,
    schema_filters: Optional[str],
):
    """Generate SQL from natural language question with advanced options."""
    verbose = ctx.obj.get("verbose", False)

    async def _query():
        try:
            if verbose:
                click.echo(f"🔧 Using provider: {provider}")
                click.echo(f"🌡️  Temperature: {temperature}")
                click.echo(f"📏 Max tokens: {max_tokens}")

            # Parse schema filters if provided
            filters = None
            if schema_filters:
                try:
                    filters = json.loads(schema_filters)
                except json.JSONDecodeError:
                    click.echo("❌ Invalid JSON in schema-filters", err=True)
                    sys.exit(1)

            # Get API key from parameter or environment
            final_api_key = api_key
            if not final_api_key:
                # Map provider to correct environment variable
                env_var_mapping = {
                    "openai": "OPENAI_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY",
                    "gemini": "GOOGLE_API_KEY",
                }
                env_var = env_var_mapping.get(provider, f"{provider.upper()}_API_KEY")
                final_api_key = os.getenv(env_var)
                if not final_api_key:
                    click.echo(f"❌ No API key provided. Set {env_var} or use --api-key", err=True)
                    sys.exit(1)

            # Create service
            service = await create_and_initialize_service(
                database_url=database_url, ai_provider=provider, api_key=final_api_key, schema_filters=filters
            )

            # Generate SQL
            result = await service.generate_sql(
                question=question,
                database_type=DatabaseType.POSTGRES,
                temperature=temperature,
                max_tokens=max_tokens,
                include_explanation=explain,
            )

            # Output results
            click.echo(f"❓ Question: {question}")
            click.echo(f"🤖 Provider: {provider.title()}")
            click.echo(f"📝 SQL: {result['sql']}")
            click.echo(f"📊 Confidence: {result['confidence']}")
            click.echo(f"⚡ Tokens used: {result['tokens_used']}")

            if explain and "explanation" in result:
                click.echo(f"💡 Explanation: {result['explanation']}")

            if "validation" in result:
                validation = result["validation"]
                if validation["is_valid"]:
                    click.echo("✅ SQL validation: Passed")
                else:
                    click.echo(f"⚠️  SQL validation issues: {validation.get('issues', [])}")

        except ProviderException as e:
            click.echo(f"❌ Provider Error: {e!s}", err=True)
            if hasattr(e, "provider"):
                click.echo(f"   Provider: {e.provider}", err=True)
            if hasattr(e, "status_code"):
                click.echo(f"   Status Code: {e.status_code}", err=True)
            if verbose and hasattr(e, "details"):
                click.echo(f"   Details: {e.details}", err=True)
            sys.exit(1)

        except NLP2SQLException as e:
            click.echo(f"❌ Application Error: {e!s}", err=True)
            if verbose and hasattr(e, "details"):
                click.echo(f"   Details: {e.details}", err=True)
            sys.exit(1)

        except Exception as e:
            click.echo(f"❌ An unexpected error occurred: {e!s}", err=True)
            if verbose:
                import traceback

                click.echo(traceback.format_exc(), err=True)
            sys.exit(1)

    asyncio.run(_query())


@cli.command()
@click.pass_context
def setup(ctx):
    """Interactive setup and configuration for nlp2sql."""
    verbose = ctx.obj.get("verbose", False)

    click.echo("🚀 nlp2sql - Interactive Setup")
    click.echo("=" * 40)

    # Check API keys
    api_keys = {
        "OpenAI": os.getenv("OPENAI_API_KEY"),
        "Anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "Google": os.getenv("GOOGLE_API_KEY"),
    }

    click.echo("\n🔑 API Keys Status:")
    available_providers = []

    for provider, key in api_keys.items():
        if key:
            masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
            click.echo(f"   ✅ {provider}: {masked_key}")
            available_providers.append(provider.lower())
        else:
            click.echo(f"   ❌ {provider}: Not set")

    if not available_providers:
        click.echo("\n⚠️  No API keys found!")
        click.echo("💡 Set at least one API key:")
        click.echo("   export OPENAI_API_KEY=your-openai-key")
        click.echo("   export ANTHROPIC_API_KEY=your-anthropic-key")
        click.echo("   export GOOGLE_API_KEY=your-google-key")
        return

    click.echo(f"\n✅ Available providers: {', '.join(available_providers)}")

    # Interactive configuration
    if click.confirm("\n🔧 Would you like to test your API keys?"):
        asyncio.run(_test_providers(available_providers, verbose))

    # Database setup
    if click.confirm("\n🗄️ Would you like to configure a database connection?"):
        _setup_database()

    click.echo("\n🎉 Setup completed!")
    click.echo("💡 Run 'nlp2sql validate' to verify your configuration")


async def _test_providers(providers: list, verbose: bool = False):
    """Test API providers."""
    click.echo("\n🧪 Testing API providers...")

    for provider in providers:
        if verbose:
            click.echo(f"🔍 Testing {provider}...")

        try:
            # Map provider to correct environment variable
            env_var_mapping = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY"}
            env_var = env_var_mapping.get(provider, f"{provider.upper()}_API_KEY")

            # Create a simple service to test the provider
            service = create_query_service(
                database_url="postgresql://test:test@localhost/test", ai_provider=provider, api_key=os.getenv(env_var)
            )
            click.echo(f"   ✅ {provider.title()}: Connection successful")

        except Exception as e:
            click.echo(f"   ❌ {provider.title()}: {e!s}")


def _setup_database():
    """Interactive database setup."""
    click.echo("\n📊 Database Configuration")
    click.echo("-" * 30)

    db_type = click.choice(["postgresql", "mysql", "sqlite"], prompt="Select database type")

    if db_type == "postgresql":
        host = click.prompt("Host", default="localhost")
        port = click.prompt("Port", default="5432")
        username = click.prompt("Username")
        password = click.prompt("Password", hide_input=True)
        database = click.prompt("Database name")

        db_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"

    elif db_type == "mysql":
        host = click.prompt("Host", default="localhost")
        port = click.prompt("Port", default="3306")
        username = click.prompt("Username")
        password = click.prompt("Password", hide_input=True)
        database = click.prompt("Database name")

        db_url = f"mysql://{username}:{password}@{host}:{port}/{database}"

    else:  # sqlite
        db_path = click.prompt("Database file path")
        db_url = f"sqlite:///{db_path}"

    click.echo(f"\n📝 Connection string: {db_url}")
    click.echo("💡 Save this to your environment:")
    click.echo(f'   export DATABASE_URL="{db_url}"')


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate nlp2sql configuration and test all components."""
    verbose = ctx.obj.get("verbose", False)

    click.echo("🔍 nlp2sql - Configuration Validation")
    click.echo("=" * 45)

    tests = []

    # Test API keys
    api_keys = {
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "gemini": os.getenv("GOOGLE_API_KEY"),
    }

    click.echo("\n🔑 Testing API Keys...")
    working_providers = []

    for provider, key in api_keys.items():
        if not key:
            if verbose:
                click.echo(f"   ⚠️  {provider.title()}: Not configured")
            continue

        try:
            service = create_query_service(
                database_url="postgresql://test:test@localhost/test", ai_provider=provider, api_key=key
            )
            click.echo(f"   ✅ {provider.title()}: Valid")
            working_providers.append(provider)
            tests.append(True)

        except Exception as e:
            click.echo(f"   ❌ {provider.title()}: {e!s}")
            tests.append(False)

    # Test database connection if provided
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        click.echo("\n🗄️ Testing Database Connection...")
        try:
            asyncio.run(_test_database(db_url, verbose))
            click.echo("   ✅ Database connection: Success")
            tests.append(True)
        except Exception as e:
            click.echo(f"   ❌ Database connection: {e!s}")
            tests.append(False)
    elif verbose:
        click.echo("\n⚠️  No DATABASE_URL configured")

    # Summary
    passed = sum(tests)
    total = len(tests)

    click.echo("\n📊 Validation Summary:")
    click.echo(f"   Tests passed: {passed}/{total}")

    if passed == total and total > 0:
        click.echo("🎉 All tests passed! nlp2sql is ready to use!")
    elif passed > 0:
        click.echo("⚠️  Some tests passed. Check failures above.")
    else:
        click.echo("❌ All tests failed. Please check your configuration.")


async def _test_database(db_url: str, verbose: bool = False):
    """Test database connection."""
    if verbose:
        click.echo(f"🔍 Connecting to: {db_url[:30]}...")

    repo = PostgreSQLRepository(db_url)
    await repo.connect()
    if verbose:
        click.echo("   Connection established successfully")


@cli.group()
def providers():
    """Manage AI providers."""
    pass


@providers.command("list")
def providers_list():
    """List all available AI providers."""
    click.echo("🤖 Available AI Providers")
    click.echo("=" * 30)

    providers_info = [
        {
            "name": "OpenAI",
            "provider": "openai",
            "env_var": "OPENAI_API_KEY",
            "models": "GPT-4, GPT-3.5",
            "context": "128K tokens",
        },
        {
            "name": "Anthropic",
            "provider": "anthropic",
            "env_var": "ANTHROPIC_API_KEY",
            "models": "Claude-3",
            "context": "200K tokens",
        },
        {
            "name": "Google",
            "provider": "gemini",
            "env_var": "GOOGLE_API_KEY",
            "models": "Gemini Pro",
            "context": "30K tokens",
        },
    ]

    for provider in providers_info:
        api_key = os.getenv(provider["env_var"])
        status = "✅ Configured" if api_key else "❌ Not configured"

        click.echo(f"\n🤖 {provider['name']}")
        click.echo(f"   Provider: {provider['provider']}")
        click.echo(f"   Models: {provider['models']}")
        click.echo(f"   Context: {provider['context']}")
        click.echo(f"   Status: {status}")
        click.echo(f"   Setup: export {provider['env_var']}=your-key")


@providers.command("test")
@click.option("--provider", help="Test specific provider (openai, anthropic, gemini)")
def providers_test(provider):
    """Test AI provider connections."""

    async def _test():
        providers_to_test = []

        if provider:
            providers_to_test = [provider]
        else:
            # Test all configured providers
            all_providers = ["openai", "anthropic", "gemini"]
            env_vars = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]

            for p, env_var in zip(all_providers, env_vars):
                if os.getenv(env_var):
                    providers_to_test.append(p)

        if not providers_to_test:
            click.echo("❌ No providers configured or specified")
            return

        click.echo("🧪 Testing AI Providers")
        click.echo("=" * 25)

        for p in providers_to_test:
            click.echo(f"\n🔍 Testing {p.title()}...")

            try:
                # Map provider to correct environment variable
                env_var_mapping = {
                    "openai": "OPENAI_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY",
                    "gemini": "GOOGLE_API_KEY",
                }
                env_var = env_var_mapping.get(p, f"{p.upper()}_API_KEY")

                service = create_query_service(
                    database_url="postgresql://test:test@localhost/test", ai_provider=p, api_key=os.getenv(env_var)
                )

                click.echo(f"   ✅ {p.title()}: Connection successful")
                click.echo("   📊 Provider initialized and ready")

            except ImportError:
                click.echo(f"   ❌ {p.title()}: Missing dependency")
                click.echo(f"   💡 Install with: pip install nlp2sql[{p}]")
            except Exception as e:
                click.echo(f"   ❌ {p.title()}: {e!s}")

    asyncio.run(_test())


@cli.command()
@click.option("--database-url", required=True, help="Database connection URL")
@click.option("--questions", help="File with test questions (one per line)")
@click.option("--providers", help="Comma-separated list of providers to test")
@click.option("--iterations", type=int, default=3, help="Number of iterations per test")
@click.option("--schema-filters", help="JSON string with schema filters")
@click.option("--output-file", type=click.Path(), help="Output file to save benchmark results (JSON format)")
@click.pass_context
def benchmark(
    ctx,
    database_url: str,
    questions: Optional[str],
    providers: Optional[str],
    iterations: int,
    schema_filters: Optional[str],
    output_file: Optional[str],
):
    """Benchmark different AI providers performance."""
    verbose = ctx.obj.get("verbose", False)

    async def _benchmark():
        # Parse schema filters if provided
        filters = None
        if schema_filters:
            try:
                filters = json.loads(schema_filters)
            except json.JSONDecodeError:
                click.echo("❌ Invalid JSON in schema-filters", err=True)
                sys.exit(1)

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
                click.echo(f"❌ Questions file not found: {questions}", err=True)
                return

        # Determine providers to test
        if providers:
            test_providers = providers.split(",")
        else:
            # Test all configured providers
            test_providers = []
            for p, env_var in [
                ("openai", "OPENAI_API_KEY"),
                ("anthropic", "ANTHROPIC_API_KEY"),
                ("gemini", "GOOGLE_API_KEY"),
            ]:
                if os.getenv(env_var):
                    test_providers.append(p)

        if not test_providers:
            click.echo("❌ No providers configured", err=True)
            return

        click.echo("🏁 nlp2sql Provider Benchmark")
        click.echo("=" * 35)
        click.echo(f"📊 Testing {len(test_providers)} providers")
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

            # Map provider to correct environment variable
            env_var_mapping = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY"}
            env_var = env_var_mapping.get(provider, f"{provider.upper()}_API_KEY")
            api_key = os.getenv(env_var)

            try:
                service = await create_and_initialize_service(
                    database_url=database_url, ai_provider=provider, api_key=api_key, schema_filters=filters
                )

                for question in test_questions:
                    for iteration in range(iterations):
                        try:
                            start_time = time.time()
                            result = await service.generate_sql(question=question, database_type=DatabaseType.POSTGRES)
                            end_time = time.time()

                            provider_results["total_time"] += end_time - start_time
                            provider_results["total_tokens"] += result.get("tokens_used", 0)
                            provider_results["successful_queries"] += 1
                            provider_results["confidences"].append(result.get("confidence", 0))

                            if verbose:
                                click.echo(f"   ✅ '{question}' - {end_time - start_time:.2f}s")

                        except Exception as e:
                            provider_results["failed_queries"] += 1
                            if verbose:
                                click.echo(f"   ❌ '{question}' - {e!s}")

                # Calculate averages
                if provider_results["confidences"]:
                    provider_results["avg_confidence"] = sum(provider_results["confidences"]) / len(
                        provider_results["confidences"]
                    )

                results[provider] = provider_results
                click.echo(f"   ✅ {provider.title()} completed")

            except Exception as e:
                click.echo(f"   ❌ {provider.title()} failed: {e!s}")

        # Display results
        if output_file:
            try:
                with open(output_file, "w") as f:
                    json.dump(results, f, indent=2)
                click.echo(f"✅ Benchmark results saved to {output_file}")
            except Exception as e:
                click.echo(f"❌ Failed to save results to {output_file}: {e!s}", err=True)
        else:
            click.echo("\n📊 Benchmark Results")
            click.echo("=" * 25)

            for provider, stats in results.items():
                total_queries = stats["successful_queries"] + stats["failed_queries"]
                success_rate = (stats["successful_queries"] / total_queries * 100) if total_queries > 0 else 0
                avg_time = stats["total_time"] / stats["successful_queries"] if stats["successful_queries"] > 0 else 0

                click.echo(f"\n🤖 {provider.title()}:")
                click.echo(f"   ✅ Success rate: {success_rate:.1f}%")
                click.echo(f"   ⏱️  Avg response time: {avg_time:.2f}s")
                click.echo(f"   🎯 Avg confidence: {stats['avg_confidence']:.2f}")
                click.echo(f"   ⚡ Total tokens: {stats['total_tokens']:,}")

            # Find the best performer
            if results:
                best_provider = max(results.keys(), key=lambda p: results[p]["avg_confidence"])
                click.echo(f"\n🏆 Best performer: {best_provider.title()}")

    asyncio.run(_benchmark())


@cli.group()
def cache():
    """Manage nlp2sql cache and embeddings."""
    pass


@cache.command("clear")
@click.option("--all", "clear_all", is_flag=True, help="Clear all cache files")
@click.option("--embeddings", is_flag=True, help="Clear embeddings cache")
@click.option("--queries", is_flag=True, help="Clear query cache")
def cache_clear(clear_all: bool, embeddings: bool, queries: bool):
    """Clear various cache files."""

    if not any([clear_all, embeddings, queries]):
        click.echo("❌ Specify what to clear: --all, --embeddings, or --queries")
        return

    # Get embeddings directory from environment variable
    embeddings_dir = get_embeddings_dir()

    cache_paths = {
        "embeddings": [str(embeddings_dir) + "/", "schema_embeddings.pkl", "schema_index.faiss"],
        "queries": ["query_cache.db", ".nlp2sql_cache/"],
    }

    cleared = []

    if clear_all:
        embeddings = queries = True

    if embeddings:
        click.echo("🗑️  Clearing embeddings cache...")
        for path in cache_paths["embeddings"]:
            if Path(path).exists():
                if Path(path).is_dir():
                    import shutil

                    shutil.rmtree(path)
                else:
                    Path(path).unlink()
                cleared.append(path)

    if queries:
        click.echo("🗑️  Clearing query cache...")
        for path in cache_paths["queries"]:
            if Path(path).exists():
                if Path(path).is_dir():
                    import shutil

                    shutil.rmtree(path)
                else:
                    Path(path).unlink()
                cleared.append(path)

    if cleared:
        click.echo(f"✅ Cleared: {', '.join(cleared)}")
    else:
        click.echo("ℹ️  No cache files found to clear")


@cache.command("info")
def cache_info():
    """Show cache information and statistics."""
    click.echo("📊 Cache Information")
    click.echo("=" * 25)

    # Check embeddings cache using environment variable
    embeddings_path = get_embeddings_dir()
    if embeddings_path.exists():
        size = sum(f.stat().st_size for f in embeddings_path.rglob("*") if f.is_file())
        files = len([f for f in embeddings_path.rglob("*") if f.is_file()])
        click.echo("🧠 Embeddings cache:")
        click.echo(f"   📁 Location: {embeddings_path.absolute()}")
        click.echo(f"   📊 Size: {size / 1024 / 1024:.2f} MB")
        click.echo(f"   📄 Files: {files}")
    else:
        click.echo("🧠 Embeddings cache: Not found")

    # Check FAISS index
    faiss_path = Path("schema_index.faiss")
    if faiss_path.exists():
        size = faiss_path.stat().st_size
        click.echo("🔍 FAISS index:")
        click.echo(f"   📁 Location: {faiss_path.absolute()}")
        click.echo(f"   📊 Size: {size / 1024 / 1024:.2f} MB")
    else:
        click.echo("🔍 FAISS index: Not found")

    # Check query cache
    query_cache_path = Path("query_cache.db")
    if query_cache_path.exists():
        size = query_cache_path.stat().st_size
        click.echo("💾 Query cache:")
        click.echo(f"   📁 Location: {query_cache_path.absolute()}")
        click.echo(f"   📊 Size: {size / 1024:.2f} KB")
    else:
        click.echo("💾 Query cache: Not found")


def main():
    """Main CLI entry point."""
    cli()


if __name__ == "__main__":
    main()
