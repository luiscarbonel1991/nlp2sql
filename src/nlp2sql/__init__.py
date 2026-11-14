"""nlp2sql - Natural Language to SQL converter with multiple AI providers."""

import logging as _logging
from typing import Any, Optional

from .adapters.openai_adapter import OpenAIAdapter
from .adapters.postgres_repository import PostgreSQLRepository
from .adapters.redshift_adapter import RedshiftRepository
from .adapters.default_error_classifier import DefaultErrorClassifier
from .adapters.default_repair_policy import DefaultRepairPolicy
from .adapters.dict_semantic_resolver import DictSemanticResolver
from .adapters.file_semantic_resolver import FileSemanticResolver
from .adapters.noop_semantic_resolver import NoOpSemanticResolver
from .adapters.noop_semantic_validator import NoOpSemanticValidator
from .adapters.schema_repository_execution_adapter import SchemaRepositoryExecutionAdapter
from .config.settings import settings
from .client import NLP2SQL, connect
from .core.entities import (
    CanonicalQueryPattern,
    DatabaseType,
    DimensionDefinition,
    DomainRule,
    MetricDefinition,
    Query,
    SQLQuery,
    SemanticContext,
    SemanticEntityMapping,
    SemanticIssue,
    SemanticValidationResult,
    SqlIntentPlan,
)
from .core.provider_config import ProviderConfig
from .core.result import QueryResult
from .core.runtime import ExecutionHooks, ExecutionMode, SemanticHooks
from .exceptions import *
from .factories import RepositoryFactory
from .ports.ai_provider import AIProviderPort
from .ports.embedding_provider import EmbeddingProviderPort
from .ports.example_repository import ExampleRepositoryPort
from .ports.error_classifier import ErrorClassifierPort
from .ports.query_execution import QueryExecutionPort
from .ports.query_safety import QuerySafetyPort
from .ports.query_validator import QueryValidatorPort
from .ports.repair_policy import RepairPolicyPort
from .ports.schema_repository import SchemaRepositoryPort
from .ports.semantic_resolver import SemanticResolverPort
from .ports.semantic_validator import SemanticValidatorPort
from .schema.example_store import ExampleStore
from .services.query_service import QueryGenerationService
from .utils.logger import get_logger

__version__ = "0.2.0rc20"

# Silent unless the application configures logging (the logging HOWTO's advice for libraries)
_logging.getLogger(__name__).addHandler(_logging.NullHandler())
__author__ = "Luis Carbonel"
__email__ = "devhighlevel@gmail.com"

__all__ = [
    # DSL (recommended API)
    "connect",
    "NLP2SQL",
    "QueryResult",
    "ExecutionHooks",
    "ExecutionMode",
    "SemanticHooks",
    # Main service (advanced)
    "QueryGenerationService",
    # Legacy helpers (still work, prefer connect())
    "create_query_service",
    "create_and_initialize_service",
    "generate_sql_from_db",
    "create_ai_provider",
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
    "SemanticContext",
    "SemanticEntityMapping",
    "MetricDefinition",
    "DimensionDefinition",
    "DomainRule",
    "CanonicalQueryPattern",
    "SqlIntentPlan",
    "SemanticIssue",
    "SemanticValidationResult",
    # Embedding Provider
    "EmbeddingProviderPort",
    # Example Repository
    "ExampleRepositoryPort",
    "ExampleStore",
    "QueryExecutionPort",
    "ErrorClassifierPort",
    "RepairPolicyPort",
    "SemanticResolverPort",
    "SemanticValidatorPort",
    # Query Safety & Validation
    "QuerySafetyPort",
    "QueryValidatorPort",
    "SchemaRepositoryExecutionAdapter",
    "DefaultErrorClassifier",
    "DefaultRepairPolicy",
    "NoOpSemanticResolver",
    "NoOpSemanticValidator",
    "DictSemanticResolver",
    "FileSemanticResolver",
    # Configuration
    "settings",
    # Exceptions
    "NLP2SQLException",
    "SchemaException",
    "ProviderException",
    "ProviderAuthenticationError",
    "ProviderRequestError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
    "ProviderResponseFormatError",
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


def create_ai_provider(provider_config: ProviderConfig) -> AIProviderPort:
    """Create the AI provider adapter for ``provider_config``.

    Builds only the adapter: no database connection, embedding model or cache directory,
    so it is cheap enough to check a provider and API key. Fields left as None use the
    adapter's defaults.

    Raises:
        ImportError: If the provider's SDK is not installed (``pip install nlp2sql[anthropic]``
            or ``nlp2sql[gemini]``).

    Example:
        provider = create_ai_provider(ProviderConfig(provider="anthropic", api_key=key))

        # A local model served by Ollama, through its OpenAI-compatible API
        provider = create_ai_provider(
            ProviderConfig(provider="openai", base_url="http://localhost:11434/v1", model="llama3.2")
        )
    """
    adapter_kwargs: dict[str, Any] = {"api_key": provider_config.api_key}
    for field_name in ("model", "temperature", "max_tokens"):
        value = getattr(provider_config, field_name)
        if value is not None:
            adapter_kwargs[field_name] = value

    if provider_config.provider == "openai":
        return OpenAIAdapter(**adapter_kwargs, base_url=provider_config.base_url)
    if provider_config.provider == "anthropic":
        from .adapters.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(**adapter_kwargs)
    if provider_config.provider == "gemini":
        from .adapters.gemini_adapter import GeminiAdapter

        return GeminiAdapter(**adapter_kwargs)
    available_providers = sorted(ProviderConfig.SUPPORTED_PROVIDERS)
    raise NotImplementedError(
        f"AI provider '{provider_config.provider}' not supported. Available: {available_providers}"
    )


def _resolve_ai_provider(
    ai_provider: str | AIProviderPort,
    api_key: str | None,
    model: str | None,
    provider_config: ProviderConfig | None,
) -> tuple[AIProviderPort, ProviderConfig | None]:
    """The AI provider of a service, and the config it was built from (None for a ready one).

    ``ai_provider`` is a ready provider, or a name. A name is read, with ``api_key`` and
    ``model``, only when there is no ``provider_config``.
    """
    if isinstance(ai_provider, AIProviderPort):
        if provider_config is not None or api_key or model:
            raise ValueError(
                "Pass a ready AI provider, or provider_config, or a provider name with api_key and model: "
                "a ready provider has its own key and model"
            )
        return ai_provider, None
    if provider_config is None:
        if ai_provider not in ProviderConfig.SUPPORTED_PROVIDERS:
            available_providers = sorted(ProviderConfig.SUPPORTED_PROVIDERS)
            raise NotImplementedError(f"AI provider '{ai_provider}' not supported. Available: {available_providers}")
        provider_config = ProviderConfig(provider=ai_provider, api_key=api_key, model=model)
    return create_ai_provider(provider_config), provider_config


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
    ai_provider: str | AIProviderPort = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: dict[str, Any] | None = None,
    embedding_provider: EmbeddingProviderPort | None = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
    example_store: ExampleRepositoryPort | None = None,
    execution_port: QueryExecutionPort | None = None,
    error_classifier: ErrorClassifierPort | None = None,
    repair_policy: RepairPolicyPort | None = None,
    semantic_resolver: SemanticResolverPort | None = None,
    semantic_validator: SemanticValidatorPort | None = None,
    *,
    provider_config: Optional[ProviderConfig] = None,
    llm_validation: Optional[bool] = None,
) -> QueryGenerationService:
    """
    Create a configured query service instance.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use: a name ('openai', 'anthropic', 'gemini'), or a ready
            provider such as ``OpenAIAdapter(client=...)``. A ready provider has its own key
            and model, so it cannot be combined with api_key, model or provider_config.
        api_key: API key for the AI provider
        model: Optional model name for the AI provider (e.g., 'gpt-5.6-luna', 'claude-sonnet-5',
            'gemini-3.6-flash'). If None, uses the provider's default model.
        database_type: Type of database
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create.
            If None (default), no embedding provider is created (embeddings are optional).
        schema_name: Database schema name (default: 'public')
        example_store: Optional pre-loaded few-shot examples for better SQL generation
        provider_config: Optional ProviderConfig for full control over provider settings
            (model, temperature, max_tokens, base_url). When given, the ai_provider name,
            api_key and model arguments are not read.
        llm_validation: Also ask the LLM to review each generated query (a second call per
            question). If None, uses NLP2SQL_LLM_VALIDATION (default: off).

    Returns:
        Configured QueryGenerationService instance

    Note:
        Embedding providers are optional. The service works without them but may have
        reduced accuracy for table selection. To enable embeddings, either:
        - Pass embedding_provider_type='local' (requires pip install nlp2sql[embeddings-local])
        - Pass embedding_provider_type='openai' (uses OpenAI embeddings API)
        - Pass a custom embedding_provider instance

        OpenAI embeddings reuse the chat key only when chat goes to OpenAI itself. A key given
        for another endpoint (``base_url``), or held by a ready provider, is not sent to
        OpenAI: those embeddings use OPENAI_API_KEY.

    Raises:
        ValueError: If a ready provider is combined with api_key, model or provider_config.
    """
    _logger = get_logger(__name__)

    # Create repository using factory
    repository = RepositoryFactory.create(database_url, schema_name, database_type)

    # A ready provider, a ProviderConfig, or a name with api_key and model
    provider, provider_config = _resolve_ai_provider(ai_provider, api_key, model, provider_config)

    # Create embedding provider
    # If embedding_provider_type is explicitly set, create that provider (raises if deps missing)
    # If embedding_provider_type is None, try to create local provider (graceful fallback if deps missing)
    if embedding_provider is None:
        if embedding_provider_type is not None:
            # Explicit provider requested - raise error if dependencies missing
            # Reuse the chat key only when it is a key for OpenAI itself: one given for another
            # endpoint (base_url), or held by a ready provider, is never sent to OpenAI
            reuse_chat_key = (
                embedding_provider_type == "openai" and provider_config is not None and provider_config.targets_openai
            )
            embedding_provider = create_embedding_provider(
                provider=embedding_provider_type,
                api_key=provider_config.api_key if reuse_chat_key else None,
            )
        else:
            # No explicit provider - try local silently, fallback to None if deps missing
            try:
                from .adapters.local_embedding_adapter import LocalEmbeddingAdapter

                embedding_provider = LocalEmbeddingAdapter()
            except ImportError:
                # sentence-transformers not installed - continue without embeddings
                _logger = get_logger(__name__)
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
    if execution_port is None:
        execution_port = SchemaRepositoryExecutionAdapter(repository)
    if error_classifier is None:
        error_classifier = DefaultErrorClassifier()
    if repair_policy is None:
        repair_policy = DefaultRepairPolicy(max_attempts=settings.retry_attempts)

    return QueryGenerationService(
        ai_provider=provider,
        schema_repository=repository,
        schema_filters=schema_filters,
        embedding_provider=embedding_provider,
        schema_name=schema_name,
        example_store=example_store,
        query_validator=query_validator,
        execution_port=execution_port,
        error_classifier=error_classifier,
        repair_policy=repair_policy,
        semantic_resolver=semantic_resolver,
        semantic_validator=semantic_validator,
        llm_validation=llm_validation,
    )


async def create_and_initialize_service(
    database_url: str,
    ai_provider: str | AIProviderPort = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: dict[str, Any] | None = None,
    embedding_provider: EmbeddingProviderPort | None = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
    example_store: ExampleRepositoryPort | None = None,
    execution_port: QueryExecutionPort | None = None,
    error_classifier: ErrorClassifierPort | None = None,
    repair_policy: RepairPolicyPort | None = None,
    semantic_resolver: SemanticResolverPort | None = None,
    semantic_validator: SemanticValidatorPort | None = None,
    *,
    provider_config: Optional[ProviderConfig] = None,
    llm_validation: Optional[bool] = None,
) -> QueryGenerationService:
    """
    Create and initialize a query service with automatic schema loading.

    This is a convenience function that creates the service and loads the schema
    in one step, ready for immediate use.

    Args:
        database_url: Database connection URL
        ai_provider: AI provider to use: a name ('openai', 'anthropic', 'gemini'), or a ready
            provider such as ``OpenAIAdapter(client=...)``
        api_key: API key for the AI provider
        model: Optional model name for the AI provider (e.g., 'gpt-5.6-luna', 'claude-sonnet-5').
            If None, uses the provider's default model.
        database_type: Type of database
        schema_filters: Optional filters to limit schema scope
        embedding_provider: Optional embedding provider instance
        embedding_provider_type: Optional embedding provider type ('local', 'openai') to auto-create
        schema_name: Database schema name (default: 'public')
        example_store: Optional pre-loaded few-shot examples for better SQL generation
        provider_config: Optional ProviderConfig for full control over provider settings
        llm_validation: Also ask the LLM to review each generated query. If None, uses
            NLP2SQL_LLM_VALIDATION (default: off).

    Returns:
        Initialized QueryGenerationService ready for queries

    Example:
        service = await create_and_initialize_service(
            "postgresql://user:pass@localhost/db",
            ai_provider="anthropic",
            api_key="your-api-key",
            model="claude-sonnet-5"
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
        execution_port,
        error_classifier,
        repair_policy,
        semantic_resolver,
        semantic_validator,
        provider_config=provider_config,
        llm_validation=llm_validation,
    )
    await service.initialize(database_type)
    return service


async def generate_sql_from_db(
    database_url: str,
    question: str,
    ai_provider: str | AIProviderPort = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    database_type: DatabaseType = DatabaseType.POSTGRES,
    schema_filters: dict[str, Any] | None = None,
    embedding_provider: EmbeddingProviderPort | None = None,
    embedding_provider_type: Optional[str] = None,
    schema_name: str = "public",
    example_store: ExampleRepositoryPort | None = None,
    execution_port: QueryExecutionPort | None = None,
    error_classifier: ErrorClassifierPort | None = None,
    repair_policy: RepairPolicyPort | None = None,
    semantic_resolver: SemanticResolverPort | None = None,
    semantic_validator: SemanticValidatorPort | None = None,
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
        ai_provider: AI provider to use: a name (default: 'openai') or a ready provider
        api_key: API key for the AI provider
        model: Optional model name for the AI provider (e.g., 'gpt-5.6-luna').
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
            model="gpt-5.6-luna"
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
        execution_port,
        error_classifier,
        repair_policy,
        semantic_resolver,
        semantic_validator,
        provider_config=provider_config,
    )
    return await service.generate_sql(question=question, database_type=database_type, **kwargs)
