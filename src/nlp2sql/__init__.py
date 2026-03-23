"""nlp2sql - Natural Language to SQL converter with multiple AI providers."""

from typing import Any, Dict, Optional

from .adapters.openai_adapter import OpenAIAdapter
from .adapters.postgres_repository import PostgreSQLRepository
from .adapters.redshift_adapter import RedshiftRepository
from .config.settings import settings
from .client import NLP2SQL, connect
from .core.entities import DatabaseType, Query, SQLQuery
from .core.provider_config import ProviderConfig
from .core.result import QueryResult
from .exceptions import *
from .factories import RepositoryFactory
from .ports.embedding_provider import EmbeddingProviderPort
from .ports.example_repository import ExampleRepositoryPort
from .ports.query_safety import QuerySafetyPort
from .ports.query_validator import QueryValidatorPort
from .ports.schema_repository import SchemaRepositoryPort
from .schema.example_store import ExampleStore
from .services.query_service import QueryGenerationService

__version__ = "0.2.0rc8"
__author__ = "Luis Carbonel"
__email__ = "devhighlevel@gmail.com"

__all__ = [
    # DSL (recommended API)
    "connect",
    "NLP2SQL",
    "QueryResult",
    # Main service (advanced)
    "QueryGenerationService",
    # Legacy helpers (still work, prefer connect())
    "create_query_service",
    "create_and_initialize_service",
    "generate_sql_from_db",
    "create_embedding_provider",
    "create_repository",
    # Factory
    "RepositoryFactory",
    # Adapters
    "OpenAIAdapter",
    "PostgreSQLRepository",
    "RedshiftRepository",
    # Core entities
    "DatabaseType",
    "ProviderConfig",
    "Query",
    "SQLQuery",
    # Embedding Provider
    "EmbeddingProviderPort",
    # Example Repository
    "ExampleRepositoryPort",
    "ExampleStore",
    # Query Safety & Validation
    "QuerySafetyPort",
    "QueryValidatorPort",
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
    "SecurityException",
]


def create_embedding_provider(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> EmbeddingProviderPort:
    """
    Create an embedding provider instance.

    Args:
        provider: Embedding provider type ('local', 'openai'). Required.
        model: Model name (for local provider, default from settings)
        api_key: API key (for OpenAI provider, default from settings)

    Returns:
        EmbeddingProviderPort instance

    Raises:
        ValueError: If provider is None or not supported
        ImportError: If required dependencies are not installed

    Example:
        # Using local embeddings (requires sentence-transformers)
        provider = create_embedding_provider(provider="local")

        # Using OpenAI embeddings
        provider = create_embedding_provider(provider="openai", api_key="sk-...")
    """
    if provider is None:
        raise ValueError(
            "Embedding provider must be explicitly specified. "
            "Available options: 'local' (requires pip install nlp2sql[embeddings-local]) "
            "or 'openai' (requires OPENAI_API_KEY)"
        )

    if provider == "local":
        from .adapters.local_embedding_adapter import LocalEmbeddingAdapter

        model_name = model or settings.embedding_model
        return LocalEmbeddingAdapter(model_name=model_name)

    if provider == "openai":
        from .adapters.openai_embedding_adapter import OpenAIEmbeddingAdapter

        api_key = api_key or settings.openai_api_key
        model_name = model or settings.openai_embedding_model
        return OpenAIEmbeddingAdapter(api_key=api_key, model=model_name)

    available_providers = ["local", "openai"]
    raise ValueError(f"Unknown embedding provider: {provider}. Available providers: {available_providers}")


async def create_repository(
    database_url: str,
    schema_name: str = "public",
    database_type: Optional[DatabaseType] = None,
) -> SchemaRepositoryPort:
    """Create and initialize a schema repository instance.

    This is a convenience function that creates the repository and initializes
    it in one step, ready for immediate use.

    Args:
        database_url: Database connection URL
        schema_name: Database schema name (default: 'public')
        database_type: Type of database. If None, auto-detected from URL.

    Returns:
        Initialized SchemaRepositoryPort instance ready for queries

    Raises:
        NotImplementedError: If the database type is not supported

    Example:
        repo = await create_repository("postgresql://user:pass@localhost/db")
        tables = await repo.get_tables()
    """
    return await RepositoryFactory.create_and_initialize(database_url, schema_name, database_type)


def create_query_service(
    database_url: str,
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider: Optional[EmbeddingProviderPort] = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
    example_store: Optional[ExampleRepositoryPort] = None,
    *,
    provider_config: Optional[ProviderConfig] = None,
) -> QueryGenerationService:
    """
    Create a configured query service instance.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use ('openai', 'anthropic', 'gemini', etc.)
        api_key: API key for the AI provider
        model: Optional model name for the AI provider (e.g., 'gpt-4o', 'claude-sonnet-4-20250514',
            'gemini-2.0-flash'). If None, uses the provider's default model.
        database_type: Type of database
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create.
            If None (default), no embedding provider is created (embeddings are optional).
        schema_name: Database schema name (default: 'public')
        example_store: Optional pre-loaded few-shot examples for better SQL generation
        provider_config: Optional ProviderConfig for full control over provider settings
            (model, temperature, max_tokens, extra_kwargs). Individual kwargs like api_key
            and model take precedence over values in provider_config.

    Returns:
        Configured QueryGenerationService instance

    Note:
        Embedding providers are optional. The service works without them but may have
        reduced accuracy for table selection. To enable embeddings, either:
        - Pass embedding_provider_type='local' (requires pip install nlp2sql[embeddings-local])
        - Pass embedding_provider_type='openai' (uses OpenAI embeddings API)
        - Pass a custom embedding_provider instance
    """
    import structlog

    _logger = structlog.get_logger()

    # Create repository using factory
    repository = RepositoryFactory.create(database_url, schema_name, database_type)

    # Resolve provider configuration
    if provider_config is not None:
        _provider_name = provider_config.provider
        _api_key = provider_config.api_key
        _model = provider_config.model
        _temperature = provider_config.temperature
        _max_tokens = provider_config.max_tokens
    else:
        _provider_name = ai_provider
        _api_key = api_key
        _model = model
        _temperature = None
        _max_tokens = None

    # Build adapter kwargs — only pass non-None values so adapters use their own defaults
    adapter_kwargs: Dict[str, Any] = {"api_key": _api_key}
    if _model is not None:
        adapter_kwargs["model"] = _model
    if _temperature is not None:
        adapter_kwargs["temperature"] = _temperature
    if _max_tokens is not None:
        adapter_kwargs["max_tokens"] = _max_tokens

    # Create AI provider adapter
    if _provider_name == "openai":
        from .adapters.openai_adapter import OpenAIAdapter

        provider = OpenAIAdapter(**adapter_kwargs)
    elif _provider_name == "anthropic":
        from .adapters.anthropic_adapter import AnthropicAdapter

        provider = AnthropicAdapter(**adapter_kwargs)
    elif _provider_name == "gemini":
        from .adapters.gemini_adapter import GeminiAdapter

        provider = GeminiAdapter(**adapter_kwargs)
    else:
        available_providers = sorted(ProviderConfig.SUPPORTED_PROVIDERS)
        raise NotImplementedError(f"AI provider '{_provider_name}' not supported. Available: {available_providers}")

    # Create embedding provider
    # If embedding_provider_type is explicitly set, create that provider (raises if deps missing)
    # If embedding_provider_type is None, try to create local provider (graceful fallback if deps missing)
    if embedding_provider is None:
        if embedding_provider_type is not None:
            # Explicit provider requested - raise error if dependencies missing
            embedding_provider = create_embedding_provider(
                provider=embedding_provider_type,
                api_key=api_key if embedding_provider_type == "openai" else None,
            )
        else:
            # No explicit provider - try local silently, fallback to None if deps missing
            try:
                from .adapters.local_embedding_adapter import LocalEmbeddingAdapter

                embedding_provider = LocalEmbeddingAdapter()
            except ImportError:
                # sentence-transformers not installed - continue without embeddings
                import structlog

                _logger = structlog.get_logger()
                _logger.info(
                    "Local embedding provider not available (sentence-transformers not installed). "
                    "Table matching will use text-based methods only. For better accuracy, install with: "
                    "pip install nlp2sql[embeddings-local]"
                )
                embedding_provider = None

    # Create query validator (default: regex-based column validation)
    from .adapters.regex_query_validator import RegexQueryValidator

    query_validator = RegexQueryValidator()

    # Create service
    service = QueryGenerationService(
        ai_provider=provider,
        schema_repository=repository,
        schema_filters=schema_filters,
        embedding_provider=embedding_provider,
        schema_name=schema_name,
        example_store=example_store,
        query_validator=query_validator,
    )

    return service


async def create_and_initialize_service(
    database_url: str,
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider: Optional[EmbeddingProviderPort] = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
    example_store: Optional[ExampleRepositoryPort] = None,
    *,
    provider_config: Optional[ProviderConfig] = None,
) -> QueryGenerationService:
    """
    Create and initialize a query service with automatic schema loading.

    This is a convenience function that creates the service and loads the schema
    in one step, ready for immediate use.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use ('openai', 'anthropic', 'gemini', etc.)
        api_key: API key for the AI provider
        model: Optional model name for the AI provider (e.g., 'gpt-4o', 'claude-sonnet-4-20250514').
            If None, uses the provider's default model.
        database_type: Type of database
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create
        schema_name: Database schema name (default: 'public')
        example_store: Optional pre-loaded few-shot examples for better SQL generation
        provider_config: Optional ProviderConfig for full control over provider settings

    Returns:
        Initialized QueryGenerationService ready for queries

    Example:
        service = await create_and_initialize_service(
            "postgresql://user:pass@localhost/db",
            ai_provider="anthropic",
            api_key="your-api-key",
            model="claude-sonnet-4-20250514"
        )
        result = await service.generate_sql("Show all users")
    """
    service = create_query_service(
        database_url,
        ai_provider,
        api_key,
        model,
        database_type,
        schema_filters,
        embedding_provider,
        embedding_provider_type,
        schema_name,
        example_store,
        provider_config=provider_config,
    )
    await service.initialize(database_type)
    return service


async def generate_sql_from_db(
    database_url: str,
    question: str,
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: Optional[Dict[str, Any]] = None,
    embedding_provider: Optional[EmbeddingProviderPort] = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
    example_store: Optional[ExampleRepositoryPort] = None,
    *,
    provider_config: Optional[ProviderConfig] = None,
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
        model: Optional model name for the AI provider (e.g., 'gpt-4o-mini').
            If None, uses the provider's default model.
        database_type: Type of database (default: POSTGRES)
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance for schema search.
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create.
            If None (default), no embedding provider is used (embeddings are optional).
        schema_name: Database schema name (default: 'public')
        example_store: Optional pre-loaded few-shot examples for better SQL generation
        provider_config: Optional ProviderConfig for full control over provider settings
        **kwargs: Additional arguments passed to generate_sql()

    Returns:
        Dictionary with 'sql', 'confidence', 'explanation', etc.

    Example:
        result = await generate_sql_from_db(
            "postgresql://localhost/mydb",
            "Show me all active users",
            ai_provider="openai",
            api_key="your-api-key",
            model="gpt-4o-mini"
        )
    """
    service = await create_and_initialize_service(
        database_url,
        ai_provider,
        api_key,
        model,
        database_type,
        schema_filters,
        embedding_provider,
        embedding_provider_type,
        schema_name,
        example_store,
        provider_config=provider_config,
    )
    return await service.generate_sql(question=question, database_type=database_type, **kwargs)
