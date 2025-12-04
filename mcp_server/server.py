#!/usr/bin/env python3
"""MCP Server for nlp2sql - Natural Language to SQL conversion."""

import os
import sys

# CRITICAL: Set working directory and environment variables BEFORE any nlp2sql imports
# This ensures the embedding manager uses the correct directories and paths
os.chdir("/tmp")  # Change to /tmp to avoid read-only filesystem issues

os.environ.setdefault("TMPDIR", "/tmp/nlp2sql_tmp")
os.environ.setdefault("NLP2SQL_CACHE_DIR", "/tmp/nlp2sql_cache")
os.environ.setdefault("NLP2SQL_EMBEDDINGS_DIR", "/tmp/nlp2sql_embeddings")

# Create temp directories if they don't exist
for dir_name in ["TMPDIR", "NLP2SQL_CACHE_DIR", "NLP2SQL_EMBEDDINGS_DIR"]:
    dir_path = os.environ.get(dir_name, f"/tmp/{dir_name.lower()}")
    os.makedirs(dir_path, exist_ok=True)

# Now safe to import other modules
import json
import time
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# Import nlp2sql after environment setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nlp2sql import (
    DatabaseType,
    create_and_initialize_service,
    generate_sql_from_db,
)
from nlp2sql.cli import detect_database_type

# Create FastMCP server
mcp = FastMCP("nlp2sql")

# Cache for initialized services
service_cache: Dict[str, Any] = {}


def get_api_key(provider: str) -> Optional[str]:
    """Get API key from environment variables."""
    env_mapping = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }
    return os.getenv(env_mapping.get(provider, ""))


def _create_cache_key(
    database_url: str,
    ai_provider: str,
    schema_name: Optional[str] = None,
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider_type: Optional[str] = None,
) -> str:
    """Create a cache key including all relevant parameters."""
    parts = [database_url, ai_provider]
    if schema_name:
        parts.append(f"schema:{schema_name}")
    if schema_filters:
        parts.append(f"filters:{json.dumps(schema_filters, sort_keys=True)}")
    if embedding_provider_type:
        parts.append(f"embedding:{embedding_provider_type}")
    return ":".join(parts)


def get_safe_database_url(alias: str = "demo") -> str:
    """Get database URL from environment variables using aliases for security.

    Args:
        alias: Database alias (demo, local, test)

    Returns:
        Database URL or raises error if not found
    """
    env_mapping = {
        "demo": "NLP2SQL_DEMO_DB_URL",
        "local": "NLP2SQL_LOCAL_DB_URL",
        "test": "NLP2SQL_TEST_DB_URL",
    }

    db_url = os.getenv(env_mapping.get(alias, ""))
    if not db_url:
        available = list(env_mapping.keys())
        raise ValueError(f"Database alias '{alias}' not configured. Available aliases: {available}")

    return db_url


@mcp.tool()
async def nlp_to_sql_with_database_url(
    database_url: str,
    question: str,
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider_type: str = "local",
) -> str:
    """Convert natural language query to SQL.

    Args:
        database_url: Database connection URL (e.g., postgresql://user:pass@host/db)
        question: Natural language question to convert to SQL
        ai_provider: AI provider to use (openai, anthropic, gemini)
        api_key: API key for the AI provider (optional, uses env vars if not provided)
        schema_filters: Optional filters to limit schema scope
        embedding_provider_type: Embedding provider type ('local' or 'openai', default: 'local')

    Returns:
        JSON string with SQL query, confidence, explanation, provider, and metadata

    Example:
        {
            "sql": "SELECT COUNT(*) FROM users",
            "confidence": 0.95,
            "explanation": "Counts all users in the database",
            "provider": "openai",
            "database_type": "postgres",
            "metadata": {
                "model": "gpt-4o-mini",
                "finish_reason": "stop",
                "prompt_tokens": 1150,
                "completion_tokens": 93,
                "raw_response": "{\"sql\": \"SELECT COUNT(*) FROM users\", \"explanation\": \"...\", \"confidence\": 0.95}"
            }
        }
    """
    try:
        # Detect database type automatically
        database_type = detect_database_type(database_url)

        result = await generate_sql_from_db(
            database_url=database_url,
            question=question,
            ai_provider=ai_provider,
            api_key=api_key or get_api_key(ai_provider),
            database_type=database_type,
            schema_filters=schema_filters,
            embedding_provider_type=embedding_provider_type,
        )

        response = {
            "sql": result["sql"],
            "confidence": result.get("confidence", 0.0),
            "explanation": result.get("explanation", ""),
            "provider": result.get("provider", ai_provider),
            "database_type": database_type.value,
            "metadata": result.get("metadata", {}),
        }

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error generating SQL: {e!s}", "error_type": type(e).__name__}, indent=2)


@mcp.tool()
async def analyze_database_schema(
    database_url: str,
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    embedding_provider_type: str = "local",
    schema_filters: Optional[Dict[str, Any]] = None,
) -> str:
    """Analyze database schema and return statistics.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use
        api_key: API key for the AI provider
        embedding_provider_type: Embedding provider type ('local' or 'openai', default: 'local')
        schema_filters: Optional filters to limit schema scope

    Returns:
        JSON string with schema statistics

    Example:
        {
            "total_tables": 25,
            "total_columns": 150,
            "total_relationships": 30,
            "schemas": ["public"],
            "provider": "openai"
        }
    """
    try:
        # Detect database type automatically
        database_type = detect_database_type(database_url)

        # Get or create cached service with complete cache key
        cache_key = _create_cache_key(
            database_url=database_url,
            ai_provider=ai_provider,
            schema_filters=schema_filters,
            embedding_provider_type=embedding_provider_type,
        )
        if cache_key not in service_cache:
            service = await create_and_initialize_service(
                database_url=database_url,
                ai_provider=ai_provider,
                api_key=api_key or get_api_key(ai_provider),
                database_type=database_type,
                schema_filters=schema_filters,
                embedding_provider_type=embedding_provider_type,
            )
            service_cache[cache_key] = service
        else:
            service = service_cache[cache_key]

        # Get schema statistics from repository
        repo = service.schema_repository
        tables = await repo.get_tables()

        total_tables = len(tables)
        total_columns = sum(len(table.columns) for table in tables)
        total_relationships = sum(len(table.foreign_keys) for table in tables if table.foreign_keys)

        schema_info = {
            "total_tables": total_tables,
            "total_columns": total_columns,
            "total_relationships": total_relationships,
            "provider": ai_provider,
            "database_type": database_type.value,
        }

        return json.dumps(schema_info, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error analyzing schema: {e!s}", "error_type": type(e).__name__}, indent=2)


@mcp.tool()
async def explain_sql_query(
    database_url: str,
    sql: str,
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    embedding_provider_type: str = "local",
    schema_filters: Optional[Dict[str, Any]] = None,
) -> str:
    """Explain what a SQL query does in natural language.

    Args:
        database_url: Database connection URL
        sql: SQL query to explain
        ai_provider: AI provider to use
        api_key: API key for the AI provider
        embedding_provider_type: Embedding provider type ('local' or 'openai', default: 'local')
        schema_filters: Optional filters to limit schema scope

    Returns:
        JSON string with query explanation

    Example:
        {
            "explanation": "This query counts all active users...",
            "sql": "SELECT COUNT(*) FROM users WHERE active = true",
            "provider": "openai"
        }
    """
    try:
        # Detect database type automatically
        database_type = detect_database_type(database_url)

        # Get or create cached service with complete cache key
        cache_key = _create_cache_key(
            database_url=database_url,
            ai_provider=ai_provider,
            schema_filters=schema_filters,
            embedding_provider_type=embedding_provider_type,
        )
        if cache_key not in service_cache:
            service = await create_and_initialize_service(
                database_url=database_url,
                ai_provider=ai_provider,
                api_key=api_key or get_api_key(ai_provider),
                database_type=database_type,
                schema_filters=schema_filters,
                embedding_provider_type=embedding_provider_type,
            )
            service_cache[cache_key] = service
        else:
            service = service_cache[cache_key]

        # Explain the query
        explanation = await service.explain_query(sql, database_type)

        return json.dumps(explanation, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error explaining query: {e!s}", "error_type": type(e).__name__}, indent=2)


@mcp.tool()
async def nlp_to_sql(
    database_alias: str,
    question: str,
    ai_provider: str = "openai",
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider_type: str = "local",
) -> str:
    """Convert natural language query to SQL using secure database aliases.

    Args:
        database_alias: Secure database alias (demo, local, test)
        question: Natural language question to convert to SQL
        ai_provider: AI provider to use (openai, anthropic, gemini)
        schema_filters: Optional filters to limit schema scope
        embedding_provider_type: Embedding provider type ('local' or 'openai', default: 'local')

    Returns:
        JSON string with SQL query, confidence, explanation, provider, and metadata

    Example:
        {
            "sql": "SELECT COUNT(*) FROM users WHERE active = true",
            "confidence": 0.92,
            "explanation": "Counts active users",
            "provider": "openai",
            "database_alias": "demo",
            "database_type": "postgres",
            "metadata": {
                "model": "gpt-4o-mini",
                "finish_reason": "stop",
                "prompt_tokens": 1150,
                "completion_tokens": 93,
                "raw_response": "{\"sql\": \"SELECT COUNT(*) FROM users WHERE active = true\", \"explanation\": \"...\", \"confidence\": 0.92}"
            }
        }
    """
    try:
        database_url = get_safe_database_url(database_alias)

        # Detect database type automatically
        database_type = detect_database_type(database_url)

        result = await generate_sql_from_db(
            database_url=database_url,
            question=question,
            ai_provider=ai_provider,
            api_key=get_api_key(ai_provider),
            database_type=database_type,
            schema_filters=schema_filters,
            embedding_provider_type=embedding_provider_type,
        )

        response = {
            "sql": result["sql"],
            "confidence": result.get("confidence", 0.0),
            "explanation": result.get("explanation", ""),
            "provider": result.get("provider", ai_provider),
            "database_alias": database_alias,
            "database_type": database_type.value,
            "metadata": result.get("metadata", {}),
        }

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error generating SQL: {e!s}", "error_type": type(e).__name__}, indent=2)


@mcp.tool()
async def list_database_aliases() -> str:
    """List configured database aliases.

    Returns:
        JSON string with available database aliases
    """
    try:
        env_mapping = {
            "demo": "NLP2SQL_DEMO_DB_URL",
            "local": "NLP2SQL_LOCAL_DB_URL",
            "test": "NLP2SQL_TEST_DB_URL",
        }

        configured_aliases = []
        for alias, env_var in env_mapping.items():
            if os.getenv(env_var):
                configured_aliases.append(alias)

        response = {
            "configured_aliases": configured_aliases,
            "all_possible_aliases": list(env_mapping.keys()),
        }

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error listing databases: {e!s}"}, indent=2)


@mcp.tool()
async def analyze_schema(
    database_alias: str,
    ai_provider: str = "openai",
    schema_name: str = "public",
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider_type: str = "local",
) -> str:
    """Analyze database schema using secure database aliases.

    Args:
        database_alias: Secure database alias (demo, local, test)
        ai_provider: AI provider to use
        schema_name: Database schema name to analyze (default: public)
        schema_filters: Optional filters to limit schema scope
        embedding_provider_type: Embedding provider type ('local' or 'openai', default: 'local')

    Returns:
        JSON string with schema statistics

    Example:
        {
            "total_tables": 25,
            "total_columns": 150,
            "total_relationships": 30,
            "table_names": ["users", "orders", "products"],
            "schemas": ["public"],
            "provider": "openai",
            "database_alias": "demo",
            "schema_name": "public"
        }
    """
    try:
        database_url = get_safe_database_url(database_alias)

        # Detect database type automatically
        database_type = detect_database_type(database_url)

        # Get or create cached service with complete cache key
        cache_key = _create_cache_key(
            database_url=database_url,
            ai_provider=ai_provider,
            schema_name=schema_name,
            schema_filters=schema_filters,
            embedding_provider_type=embedding_provider_type,
        )
        if cache_key not in service_cache:
            # For PostgreSQL, create repository with specific schema
            if database_type == DatabaseType.POSTGRES:
                from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
                from nlp2sql import create_query_service

                repository = PostgreSQLRepository(database_url, schema_name=schema_name)
                await repository.initialize()

                # Create service with custom repository
                service = create_query_service(
                    database_url=database_url,
                    ai_provider=ai_provider,
                    api_key=get_api_key(ai_provider),
                    database_type=database_type,
                    schema_filters=schema_filters,
                    embedding_provider_type=embedding_provider_type,
                )
                # Replace repository with schema-specific one
                service.schema_repository = repository
                await service.initialize(database_type)
            else:
                # For other database types, use standard helper
                service = await create_and_initialize_service(
                    database_url=database_url,
                    ai_provider=ai_provider,
                    api_key=get_api_key(ai_provider),
                    database_type=database_type,
                    schema_filters=schema_filters,
                    embedding_provider_type=embedding_provider_type,
                )
            service_cache[cache_key] = service
        else:
            service = service_cache[cache_key]

        # Get basic table information from repository
        repo = service.schema_repository
        tables = await repo.get_tables()

        # Extract table names and statistics
        table_names = [table.name for table in tables]
        total_tables = len(tables)
        total_columns = sum(len(table.columns) for table in tables)
        total_relationships = sum(len(table.foreign_keys) for table in tables if table.foreign_keys)

        schema_info = {
            "total_tables": total_tables,
            "total_columns": total_columns,
            "total_relationships": total_relationships,
            "table_names": table_names,
            "schemas": [schema_name],
            "provider": ai_provider,
            "database_alias": database_alias,
            "schema_name": schema_name,
            "database_type": database_type.value,
        }

        return json.dumps(schema_info, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error analyzing schema: {e!s}", "error_type": type(e).__name__}, indent=2)


@mcp.tool()
async def benchmark_ai_providers(
    database_alias: str,
    questions: Optional[List[str]] = None,
    providers: Optional[List[str]] = None,
    iterations: int = 1,
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider_type: str = "local",
) -> str:
    """Benchmark different AI providers performance.

    Args:
        database_alias: Secure database alias (demo, local, test)
        questions: List of questions to test (optional, uses defaults if not provided)
        providers: List of providers to test (optional, tests all configured if not provided)
        iterations: Number of iterations per question (default: 1)
        schema_filters: Optional filters to limit schema scope
        embedding_provider_type: Embedding provider type ('local' or 'openai', default: 'local')

    Returns:
        JSON string with benchmark results

    Example:
        {
            "database_alias": "demo",
            "total_questions": 5,
            "iterations_per_question": 1,
            "providers_tested": 2,
            "best_performer": "openai",
            "results": {...}
        }
    """
    try:
        database_url = get_safe_database_url(database_alias)

        # Default test questions
        default_questions = [
            "Count total users",
            "Show active customers",
            "Find recent orders",
            "Calculate monthly revenue",
            "List top products",
        ]

        test_questions = questions or default_questions

        # Determine providers to test
        if providers:
            test_providers = providers
        else:
            # Test all configured providers
            test_providers = []
            for p in ["openai", "anthropic", "gemini"]:
                if get_api_key(p):
                    test_providers.append(p)

        if not test_providers:
            return json.dumps({"error": "No providers configured"}, indent=2)

        results = {}

        for provider in test_providers:
            provider_results = {
                "total_time": 0,
                "total_tokens": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "avg_confidence": 0,
                "confidences": [],
                "errors": [],
            }

            api_key = get_api_key(provider)
            if not api_key:
                provider_results["errors"].append(f"API key not configured for {provider}")
                results[provider] = provider_results
                continue

            try:
                # Detect database type automatically
                database_type = detect_database_type(database_url)

                service = await create_and_initialize_service(
                    database_url=database_url,
                    ai_provider=provider,
                    api_key=api_key,
                    database_type=database_type,
                    schema_filters=schema_filters,
                    embedding_provider_type=embedding_provider_type,
                )

                for question in test_questions:
                    for iteration in range(iterations):
                        try:
                            start_time = time.time()
                            result = await service.generate_sql(question=question, database_type=database_type)
                            end_time = time.time()

                            provider_results["total_time"] += end_time - start_time
                            provider_results["total_tokens"] += result.get("tokens_used", 0)
                            provider_results["successful_queries"] += 1
                            provider_results["confidences"].append(result.get("confidence", 0))

                        except Exception as e:
                            provider_results["failed_queries"] += 1
                            provider_results["errors"].append(f"'{question}': {e!s}")

                # Calculate averages
                if provider_results["confidences"]:
                    provider_results["avg_confidence"] = sum(provider_results["confidences"]) / len(
                        provider_results["confidences"]
                    )

                results[provider] = provider_results

            except Exception as e:
                provider_results["errors"].append(f"Service initialization failed: {e!s}")
                results[provider] = provider_results

        # Add summary statistics
        summary = {
            "database_alias": database_alias,
            "total_questions": len(test_questions),
            "iterations_per_question": iterations,
            "providers_tested": len(test_providers),
            "results": results,
        }

        # Find best performer
        if results:
            best_provider = None
            best_score = -1
            for provider, stats in results.items():
                if stats["successful_queries"] > 0:
                    # Score based on success rate and confidence
                    total_queries = stats["successful_queries"] + stats["failed_queries"]
                    success_rate = stats["successful_queries"] / total_queries
                    score = success_rate * stats["avg_confidence"]
                    if score > best_score:
                        best_score = score
                        best_provider = provider

            if best_provider:
                summary["best_performer"] = best_provider

        return json.dumps(summary, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error running benchmark: {e!s}", "error_type": type(e).__name__}, indent=2)


@mcp.tool()
async def generate_example_queries(
    database_url: str,
    topic: Optional[str] = None,
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    embedding_provider_type: str = "local",
    schema_filters: Optional[Dict[str, Any]] = None,
) -> str:
    """Get example queries for a database.

    Args:
        database_url: Database connection URL
        topic: Topic or area to get examples for (optional)
        ai_provider: AI provider to use
        api_key: API key for the AI provider
        embedding_provider_type: Embedding provider type ('local' or 'openai', default: 'local')
        schema_filters: Optional filters to limit schema scope

    Returns:
        JSON string with example queries

    Example:
        {
            "examples": [
                {
                    "question": "Show me all records from the main table",
                    "sql": "SELECT * FROM users",
                    "explanation": "Retrieves all user records"
                }
            ]
        }
    """
    try:
        # Generate example queries based on schema
        examples = []

        # Common query patterns
        base_examples = [
            "Show me all records from the main table",
            "Count the total number of records",
            "Find the most recent entries",
        ]

        # If topic is provided, customize examples
        if topic:
            base_examples = [f"{ex} related to {topic}" for ex in base_examples]

        # Detect database type automatically
        database_type = detect_database_type(database_url)

        # Generate SQL for each example
        for example in base_examples:
            try:
                result = await generate_sql_from_db(
                    database_url=database_url,
                    question=example,
                    ai_provider=ai_provider,
                    api_key=api_key or get_api_key(ai_provider),
                    database_type=database_type,
                    schema_filters=schema_filters,
                    embedding_provider_type=embedding_provider_type,
                )
                examples.append(
                    {
                        "question": example,
                        "sql": result["sql"],
                        "explanation": result.get("explanation", ""),
                    }
                )
            except Exception:
                continue

        return json.dumps({"examples": examples}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Error generating examples: {e!s}", "error_type": type(e).__name__}, indent=2)


if __name__ == "__main__":
    mcp.run()
