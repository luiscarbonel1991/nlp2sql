#!/usr/bin/env python3
"""MCP Server for nlp2sql - Natural Language to SQL conversion.

This server exposes 5 simple, idiomatic tools for interacting with databases:
1. ask_database - Ask questions in natural language, get SQL and optional results
2. explore_schema - Discover tables and columns in your database
3. run_sql - Execute SQL queries directly (read-only)
4. list_databases - List available database connections
5. explain_sql - Explain what a SQL query does
"""

import json
import logging
import os
import signal
import sys
import time
from typing import Any, Optional

# Handle SIGPIPE gracefully (prevents BrokenPipeError on closed connections)
# This is common when MCP client closes connection while server is still writing
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# ===== CRITICAL: Configure structlog to stderr BEFORE any nlp2sql imports =====
# MCP protocol uses stdout exclusively for JSON-RPC communication.
# nlp2sql modules use structlog internally, so we MUST configure it globally here first.
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    cache_logger_on_first_use=False,
)

# Also configure standard logging to stderr
logging.basicConfig(
    format="%(message)s",
    stream=sys.stderr,
    level=logging.WARNING,
)

# Suppress verbose third-party loggers
for _lib in ["urllib3", "httpx", "httpcore", "asyncio", "openai", "anthropic", "faiss", "faiss.loader"]:
    logging.getLogger(_lib).setLevel(logging.WARNING)

logger = structlog.get_logger(__name__)

# ===== NOW safe to import external modules =====
from mcp.server.fastmcp import FastMCP

# Add parent directory to path for nlp2sql imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nlp2sql import (
    DatabaseType,
    create_and_initialize_service,
    create_repository,
)
from nlp2sql.exceptions import SecurityException
from nlp2sql.factories import RepositoryFactory

# Create FastMCP server
mcp = FastMCP("nlp2sql")

# Cache for initialized services and repositories
# Key format: "service:{database_url}" or "repo:{database_url}:{schema}"
_service_cache: dict[str, Any] = {}
_repository_cache: dict[str, Any] = {}

# Cache metadata for debugging and potential TTL
_cache_metadata: dict[str, dict] = {}

# Database alias configuration
DATABASE_ALIASES = {
    "default": "NLP2SQL_DEFAULT_DB_URL",
    "demo": "NLP2SQL_DEMO_DB_URL",
    "local": "NLP2SQL_LOCAL_DB_URL",
    "test": "NLP2SQL_TEST_DB_URL",
    "production": "NLP2SQL_PROD_DB_URL",
    "prod": "NLP2SQL_PROD_DB_URL",
}


def _get_api_key(provider: str) -> Optional[str]:
    """Get API key from environment variables."""
    env_mapping = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }
    return os.getenv(env_mapping.get(provider, ""))


def _resolve_database(database: str) -> str:
    """Resolve database alias or validate URL.

    Args:
        database: Database alias (demo, local, etc.) or connection URL

    Returns:
        Database connection URL

    Raises:
        ValueError: If alias is not configured or URL is invalid
    """
    # Check if it's a known alias
    if database in DATABASE_ALIASES:
        url = os.getenv(DATABASE_ALIASES[database])
        if not url:
            configured = [k for k, v in DATABASE_ALIASES.items() if os.getenv(v)]
            raise ValueError(
                f"Database alias '{database}' not configured. "
                f"Set {DATABASE_ALIASES[database]} environment variable. "
                f"Configured aliases: {configured or 'none'}"
            )
        return url

    # Allow direct URLs (PostgreSQL, Redshift)
    if database.startswith(("postgresql://", "postgres://", "redshift://")):
        return database

    raise ValueError(
        f"Invalid database: '{database}'. "
        f"Use a configured alias ({list(DATABASE_ALIASES.keys())}) "
        f"or a connection URL (postgresql://...)"
    )


async def _get_repository(database_url: str, schema_name: str = "public") -> Any:
    """Get or create a cached repository for the database."""
    cache_key = f"{database_url}:{schema_name}"

    if cache_key not in _repository_cache:
        _repository_cache[cache_key] = await create_repository(database_url, schema_name)

    return _repository_cache[cache_key]


def _format_error(error: Exception, context: str = "") -> str:
    """Format error as JSON response."""
    return json.dumps(
        {
            "error": str(error),
            "error_type": type(error).__name__,
            "context": context,
        },
        indent=2,
    )


def _get_available_provider() -> tuple[str, str]:
    """Get the first available AI provider with a configured API key.

    Returns:
        Tuple of (provider_name, api_key)

    Raises:
        ValueError: If no provider is configured
    """
    providers = [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GOOGLE_API_KEY"),
    ]

    for provider, env_var in providers:
        api_key = os.getenv(env_var)
        if api_key:
            return provider, api_key

    raise ValueError("No AI provider configured. Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY")


async def _get_cached_service(
    database_url: str,
    database_type: DatabaseType,
    provider: Optional[str] = None,
    schema_name: str = "public",
) -> Any:
    """Get or create a cached query generation service.

    The service includes the embedding model and schema index, which are
    expensive to initialize (~30-40s). Caching ensures subsequent calls
    are fast (~3-5s).

    Args:
        database_url: Database connection URL
        database_type: Type of database (postgres, redshift)
        provider: AI provider to use (openai, anthropic, gemini). If None, auto-detect.
        schema_name: Database schema name (default: 'public')

    Returns:
        Initialized QueryGenerationService

    Edge cases handled:
        - Missing API key: Falls back to other providers or raises clear error
        - Service initialization failure: Not cached, will retry
        - Different databases: Separate cache entries
        - Different providers: Separate cache entries
        - Different schemas: Separate cache entries
    """
    # Determine provider and API key
    if provider:
        api_key = _get_api_key(provider)
        if not api_key:
            raise ValueError(f"API key not configured for provider '{provider}'")
    else:
        provider, api_key = _get_available_provider()

    cache_key = f"service:{database_url}:{provider}:{schema_name}"

    if cache_key in _service_cache:
        logger.debug("Using cached service", provider=provider, schema=schema_name)
        return _service_cache[cache_key]

    logger.info(
        "Initializing new service (first call, may take ~30-40s)...",
        provider=provider,
        schema=schema_name,
    )
    start_time = time.time()

    try:
        service = await create_and_initialize_service(
            database_url=database_url,
            ai_provider=provider,
            api_key=api_key,
            database_type=database_type,
            schema_name=schema_name,
        )

        # Only cache on successful initialization
        _service_cache[cache_key] = service
        _cache_metadata[cache_key] = {
            "created_at": time.time(),
            "database_type": database_type.value,
            "provider": provider,
            "schema_name": schema_name,
        }

        elapsed = round(time.time() - start_time, 2)
        logger.info("Service cached successfully", elapsed_seconds=elapsed, provider=provider, schema=schema_name)

        return service

    except Exception as e:
        # Don't cache failed services - allow retry
        logger.error("Service initialization failed", error=str(e), provider=provider, schema=schema_name)
        raise


# =============================================================================
# Tool 1: ask_database - The primary tool
# =============================================================================


@mcp.tool()
async def ask_database(
    question: str,
    database: str = "default",
    schema: str = "public",
    execute: bool = False,
    limit: int = 100,
) -> str:
    """Ask a question about your data in natural language.

    This is the main tool for converting natural language questions to SQL.
    Optionally execute the query and return actual results.

    Args:
        question: Your question in plain English (e.g., "How many orders last month?")
        database: Database alias (default, demo, local, test, prod) or connection URL
        schema: Database schema to query (default: "public"). Use this for non-public schemas.
        execute: If True, executes the SQL and returns actual data results
        limit: Maximum rows to return when executing (default: 100, max: 1000)

    Returns:
        JSON with SQL query, explanation, confidence, and optionally results

    Examples:
        - ask_database("Show me top 10 customers by revenue")
        - ask_database("Count orders by status", execute=True)
        - ask_database("How many chats?", schema="alpha_ui", execute=True)
        - ask_database("Average order value", database="prod", schema="sales", execute=True)
    """
    try:
        # Resolve database
        database_url = _resolve_database(database)
        database_type = RepositoryFactory.detect_database_type(database_url)

        # Get cached service (fast after first call)
        service = await _get_cached_service(database_url, database_type, schema_name=schema)

        # Generate SQL from question using cached service
        result = await service.generate_sql(
            question=question,
            database_type=database_type,
        )

        response = {
            "sql": result["sql"],
            "explanation": result.get("explanation", ""),
            "confidence": result.get("confidence", 0.0),
            "schema": schema,
        }

        # Execute query if requested
        if execute:
            try:
                repository = await _get_repository(database_url, schema)
                query_result = await repository.execute_query(
                    sql=result["sql"],
                    limit=min(limit, 1000),
                )
                response["results"] = query_result["results"]
                response["row_count"] = query_result["row_count"]
                response["execution_time_ms"] = query_result["execution_time_ms"]
            except SecurityException as e:
                response["execution_error"] = str(e)
                response["results"] = None
            except Exception as e:
                response["execution_error"] = f"Failed to execute: {e}"
                response["results"] = None

        return json.dumps(response, indent=2, default=str)

    except Exception as e:
        return _format_error(e, f"Question: {question}")


# =============================================================================
# Tool 2: explore_schema - Discover database structure
# =============================================================================


@mcp.tool()
async def explore_schema(
    database: str = "default",
    schema: str = "public",
    table: Optional[str] = None,
    search: Optional[str] = None,
) -> str:
    """Explore the database schema to understand available tables and columns.

    Use this tool to discover what data is available before asking questions.

    Args:
        database: Database alias or connection URL
        schema: Database schema to explore (default: "public")
        table: Get detailed info about a specific table (columns, types, keys)
        search: Search for tables matching a pattern (e.g., "user", "order")

    Returns:
        JSON with schema information - tables list or detailed table info

    Examples:
        - explore_schema()  # List all tables in public schema
        - explore_schema(schema="alpha_ui")  # List tables in alpha_ui schema
        - explore_schema(table="orders")  # See columns in orders table
        - explore_schema(schema="sales", search="customer")  # Find customer tables in sales schema
    """
    try:
        database_url = _resolve_database(database)
        repository = await _get_repository(database_url, schema)

        # Get specific table info
        if table:
            table_info = await repository.get_table_info(table)
            return json.dumps(
                {
                    "table": table_info.name,
                    "schema": table_info.schema,
                    "description": table_info.description or "",
                    "columns": [
                        {
                            "name": col["name"],
                            "type": col["type"],
                            "nullable": col.get("nullable", True),
                            "description": col.get("description", ""),
                        }
                        for col in table_info.columns
                    ],
                    "primary_keys": table_info.primary_keys,
                    "foreign_keys": [
                        {
                            "column": fk["column"],
                            "references": f"{fk['ref_table']}.{fk['ref_column']}",
                        }
                        for fk in table_info.foreign_keys
                    ],
                    "row_count": table_info.row_count,
                },
                indent=2,
                default=str,
            )

        # Search tables by pattern
        if search:
            tables = await repository.search_tables(search)
        else:
            tables = await repository.get_tables()

        return json.dumps(
            {
                "database": database,
                "schema": schema,
                "total_tables": len(tables),
                "tables": [
                    {
                        "name": t.name,
                        "columns": len(t.columns),
                        "description": t.description or "",
                    }
                    for t in tables
                ],
            },
            indent=2,
            default=str,
        )

    except Exception as e:
        return _format_error(e, f"Database: {database}, Schema: {schema}")


# =============================================================================
# Tool 3: run_sql - Execute SQL directly
# =============================================================================


@mcp.tool()
async def run_sql(
    sql: str,
    database: str = "default",
    schema: str = "public",
    limit: int = 100,
) -> str:
    """Execute a SQL query and return results.

    Use this tool when you have a specific SQL query to run.
    Only SELECT queries are allowed for safety.

    Args:
        sql: The SQL query to execute (SELECT only)
        database: Database alias or connection URL
        schema: Database schema context (default: "public")
        limit: Maximum rows to return (default: 100, max: 1000)

    Returns:
        JSON with query results, columns, and execution time

    Examples:
        - run_sql("SELECT * FROM users WHERE active = true LIMIT 10")
        - run_sql("SELECT COUNT(*) FROM alpha_ui.chat", schema="alpha_ui")
        - run_sql("SELECT name, email FROM customers", database="prod")
    """
    try:
        database_url = _resolve_database(database)
        repository = await _get_repository(database_url, schema)

        result = await repository.execute_query(
            sql=sql,
            limit=min(limit, 1000),
        )

        return json.dumps(
            {
                "results": result["results"],
                "columns": result["columns"],
                "row_count": result["row_count"],
                "execution_time_ms": result["execution_time_ms"],
            },
            indent=2,
            default=str,
        )

    except SecurityException as e:
        return json.dumps(
            {
                "error": str(e),
                "error_type": "SecurityException",
                "hint": "Only SELECT, WITH, and EXPLAIN queries are allowed. "
                "INSERT, UPDATE, DELETE, DROP and other write operations are blocked.",
            },
            indent=2,
        )
    except Exception as e:
        return _format_error(e, f"SQL: {sql[:100]}...")


# =============================================================================
# Tool 4: list_databases - Show available connections
# =============================================================================


@mcp.tool()
async def list_databases() -> str:
    """List all configured database connections.

    Returns:
        JSON with available database aliases and their configuration status

    Example:
        list_databases()
    """
    databases = []

    for alias, env_var in DATABASE_ALIASES.items():
        url = os.getenv(env_var)
        if url:
            # Detect database type without exposing the URL
            try:
                db_type = RepositoryFactory.detect_database_type(url)
                status = "configured"
                database_type = db_type.value
            except Exception:
                status = "configured"
                database_type = "unknown"
        else:
            status = "not_configured"
            database_type = None

        databases.append(
            {
                "alias": alias,
                "status": status,
                "type": database_type,
                "env_var": env_var,
            }
        )

    # Determine default
    default_alias = None
    for alias in ["default", "demo", "local"]:
        if os.getenv(DATABASE_ALIASES.get(alias, "")):
            default_alias = alias
            break

    return json.dumps(
        {
            "databases": databases,
            "default": default_alias,
            "hint": "Use database alias in other tools, e.g., ask_database(..., database='demo')",
        },
        indent=2,
    )


# =============================================================================
# Tool 5: explain_sql - Explain what a query does
# =============================================================================


@mcp.tool()
async def explain_sql(
    sql: str,
    database: str = "default",
    schema: str = "public",
) -> str:
    """Explain what a SQL query does in plain English.

    Use this tool to understand complex queries or verify generated SQL.

    Args:
        sql: The SQL query to explain
        database: Database context for accurate explanations
        schema: Database schema context (default: "public")

    Returns:
        JSON with plain English explanation of the query

    Example:
        explain_sql("SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.name")
    """
    try:
        database_url = _resolve_database(database)
        database_type = RepositoryFactory.detect_database_type(database_url)

        # Get cached service (fast after first call)
        service = await _get_cached_service(database_url, database_type, schema_name=schema)

        # Get explanation
        explanation = await service.explain_query(sql, database_type)

        return json.dumps(explanation, indent=2, default=str)

    except Exception as e:
        return _format_error(e, f"SQL: {sql[:100]}...")


if __name__ == "__main__":
    mcp.run()
