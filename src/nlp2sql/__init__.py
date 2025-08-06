"""nlp2sql - Natural Language to SQL converter with multiple AI providers."""

from typing import Any, Dict

from .adapters.openai_adapter import OpenAIAdapter
from .adapters.postgres_repository import PostgreSQLRepository
from .config.settings import settings
from .core.entities import DatabaseType, Query, SQLQuery
from .exceptions import *
from .services.query_service import QueryGenerationService

__version__ = "0.2.0rc2"
__author__ = "Luis Carbonel"
__email__ = "devhighlevel@gmail.com"

__all__ = [
    # Main service
    "QueryGenerationService",
    # Helper functions
    "create_query_service",
    "create_and_initialize_service",
    "generate_sql_from_db",
    # Adapters
    "OpenAIAdapter",
    "PostgreSQLRepository",
    # Core entities
    "DatabaseType",
    "Query",
    "SQLQuery",
    # Configuration
    "settings",
    # Exceptions
    "NLP2SQLException",
    "SchemaException",
    "ProviderException",
    "TokenLimitException",
    "QueryGenerationException",
    "OptimizationException",
    "CacheException",
    "ValidationException",
    "ConfigurationException",
]


def create_query_service(
    database_url: str,
    ai_provider: str = "openai",
    api_key: str = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Dict[str, Any] = None,
) -> QueryGenerationService:
    """
    Create a configured query service instance.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use ('openai', 'anthropic', 'gemini', etc.)
        api_key: API key for the AI provider
        database_type: Type of database
        schema_filters: Optional filters to limit schema scope

    Returns:
        Configured QueryGenerationService instance
    """
    from .adapters.openai_adapter import OpenAIAdapter
    from .adapters.postgres_repository import PostgreSQLRepository

    # Create repository
    if database_type == DatabaseType.POSTGRES:
        repository = PostgreSQLRepository(database_url)
    else:
        raise NotImplementedError(f"Database type {database_type} not yet supported")

    # Create AI provider
    if ai_provider == "openai":
        from .adapters.openai_adapter import OpenAIAdapter

        provider = OpenAIAdapter(api_key=api_key)
    elif ai_provider == "anthropic":
        from .adapters.anthropic_adapter import AnthropicAdapter

        provider = AnthropicAdapter(api_key=api_key)
    elif ai_provider == "gemini":
        from .adapters.gemini_adapter import GeminiAdapter

        provider = GeminiAdapter(api_key=api_key)
    else:
        available_providers = ["openai", "anthropic", "gemini"]
        raise NotImplementedError(f"AI provider '{ai_provider}' not supported. Available: {available_providers}")

    # Create service
    service = QueryGenerationService(ai_provider=provider, schema_repository=repository, schema_filters=schema_filters)

    return service


async def create_and_initialize_service(
    database_url: str,
    ai_provider: str = "openai",
    api_key: str = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Dict[str, Any] = None,
) -> QueryGenerationService:
    """
    Create and initialize a query service with automatic schema loading.

    This is a convenience function that creates the service and loads the schema
    in one step, ready for immediate use.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use ('openai', 'anthropic', 'gemini', etc.)
        api_key: API key for the AI provider
        database_type: Type of database

    Returns:
        Initialized QueryGenerationService ready for queries

    Example:
        service = await create_and_initialize_service(
            "postgresql://user:pass@localhost/db",
            api_key="your-api-key"
        )
        result = await service.generate_sql("Show all users")
    """
    service = create_query_service(database_url, ai_provider, api_key, database_type, schema_filters)
    await service.initialize(database_type)
    return service


async def generate_sql_from_db(
    database_url: str,
    question: str,
    ai_provider: str = "openai",
    api_key: str = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Dict[str, Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    One-line SQL generation with automatic schema loading.

    This is the simplest way to generate SQL from natural language. It handles
    all the setup, schema loading, and query generation in a single call.

    Args:
        database_url: Database connection URL
        question: Natural language question
        ai_provider: AI provider to use (default: 'openai')
        api_key: API key for the AI provider
        database_type: Type of database (default: POSTGRES)
        **kwargs: Additional arguments passed to generate_sql()

    Returns:
        Dictionary with 'sql', 'confidence', 'explanation', etc.

    Example:
        result = await generate_sql_from_db(
            "postgresql://localhost/mydb",
            "Show me all active users",
            api_key="your-api-key"
        )
        print(result['sql'])
    """
    service = await create_and_initialize_service(database_url, ai_provider, api_key, database_type, schema_filters)
    return await service.generate_sql(question=question, database_type=database_type, **kwargs)
