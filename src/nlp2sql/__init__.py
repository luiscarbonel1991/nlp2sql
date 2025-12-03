"""nlp2sql - Natural Language to SQL converter with multiple AI providers."""

from typing import Any, Dict, Optional

from .adapters.openai_adapter import OpenAIAdapter
from .adapters.postgres_repository import PostgreSQLRepository
from .adapters.redshift_adapter import RedshiftRepository
from .config.settings import settings
from .core.entities import DatabaseType, Query, SQLQuery
from .exceptions import *
from .ports.embedding_provider import EmbeddingProviderPort
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
    "create_embedding_provider",
    # Adapters
    "OpenAIAdapter",
    "PostgreSQLRepository",
    "RedshiftRepository",
    # Core entities
    "DatabaseType",
    "Query",
    "SQLQuery",
    # Embedding Provider
    "EmbeddingProviderPort",
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


def create_embedding_provider(
    provider: str = "local",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> EmbeddingProviderPort:
    """
    Create an embedding provider instance.

    Args:
        provider: Embedding provider type ('local', 'openai')
        model: Model name (for local provider, default from settings)
        api_key: API key (for OpenAI provider, default from settings)

    Returns:
        EmbeddingProviderPort instance

    Raises:
        ValueError: If provider is not supported
        ImportError: If required dependencies are not installed
    """
    if provider == "local":
        from .adapters.local_embedding_adapter import LocalEmbeddingAdapter

        model_name = model or settings.embedding_model
        return LocalEmbeddingAdapter(model_name=model_name)

    elif provider == "openai":
        from .adapters.openai_embedding_adapter import OpenAIEmbeddingAdapter

        api_key = api_key or settings.openai_api_key
        model_name = model or settings.openai_embedding_model
        return OpenAIEmbeddingAdapter(api_key=api_key, model=model_name)

    else:
        available_providers = ["local", "openai"]
        raise ValueError(
            f"Unknown embedding provider: {provider}. Available providers: {available_providers}"
        )


def create_query_service(
    database_url: str,
    ai_provider: str = "openai",
    api_key: str = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Dict[str, Any] = None,
    embedding_provider: Optional[EmbeddingProviderPort] = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
) -> QueryGenerationService:
    """
    Create a configured query service instance.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use ('openai', 'anthropic', 'gemini', etc.)
        api_key: API key for the AI provider
        database_type: Type of database
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create
        schema_name: Database schema name (default: 'public')

    Returns:
        Configured QueryGenerationService instance
    """
    from .adapters.openai_adapter import OpenAIAdapter
    from .adapters.postgres_repository import PostgreSQLRepository
    from .adapters.redshift_adapter import RedshiftRepository

    # Create repository
    if database_type == DatabaseType.POSTGRES:
        repository = PostgreSQLRepository(database_url, schema_name)
    elif database_type == DatabaseType.REDSHIFT:
        repository = RedshiftRepository(database_url, schema_name)
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

    # Create embedding provider if not provided
    if embedding_provider is None:
        provider_type = embedding_provider_type or "local"
        embedding_provider = create_embedding_provider(
            provider=provider_type,
            api_key=api_key if provider_type == "openai" else None,
        )

    # Create service
    service = QueryGenerationService(
        ai_provider=provider,
        schema_repository=repository,
        schema_filters=schema_filters,
        embedding_provider=embedding_provider,
    )

    return service


async def create_and_initialize_service(
    database_url: str,
    ai_provider: str = "openai",
    api_key: str = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Dict[str, Any] = None,
    embedding_provider: Optional[EmbeddingProviderPort] = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
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
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create
        schema_name: Database schema name (default: 'public')

    Returns:
        Initialized QueryGenerationService ready for queries

    Example:
        service = await create_and_initialize_service(
            "postgresql://user:pass@localhost/db",
            api_key="your-api-key"
        )
        result = await service.generate_sql("Show all users")
    """
    service = create_query_service(
        database_url,
        ai_provider,
        api_key,
        database_type,
        schema_filters,
        embedding_provider,
        embedding_provider_type,
        schema_name,
    )
    await service.initialize(database_type)
    return service


async def generate_sql_from_db(
    database_url: str,
    question: str,
    ai_provider: str = "openai",
    api_key: str = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Dict[str, Any] = None,
    embedding_provider: Optional[EmbeddingProviderPort] = None,
    embedding_provider_type: Optional[str] = None,
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
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance for schema search.
            If None, defaults to local embeddings if available.
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create.
            Only used if embedding_provider is None.
        **kwargs: Additional arguments passed to generate_sql()

    Returns:
        Dictionary with 'sql', 'confidence', 'explanation', etc.

    Example:
        # Basic usage (uses default local embeddings if available)
        result = await generate_sql_from_db(
            "postgresql://localhost/mydb",
            "Show me all active users",
            api_key="your-api-key"
        )

        # Using OpenAI embeddings
        result = await generate_sql_from_db(
            "postgresql://localhost/mydb",
            "Show me all active users",
            api_key="your-api-key",
            embedding_provider_type="openai"
        )
    """
    service = await create_and_initialize_service(
        database_url,
        ai_provider,
        api_key,
        database_type,
        schema_filters,
        embedding_provider,
        embedding_provider_type,
    )
    return await service.generate_sql(question=question, database_type=database_type, **kwargs)
