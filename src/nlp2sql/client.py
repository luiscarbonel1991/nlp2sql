"""High-level Pythonic client for nlp2sql.

Usage::

    import nlp2sql

    nlp = await nlp2sql.connect(
        "postgresql://user:pass@localhost/mydb",
        provider=ProviderConfig(provider="openai", api_key=key),
    )
    result = await nlp.ask("How many users signed up last month?")
    print(result.sql)
"""

from typing import Any, Optional

import structlog

from .core.entities import DatabaseType, SemanticContext
from .core.provider_config import ProviderConfig
from .core.result import QueryResult
from .core.runtime import ExecutionHooks, ExecutionMode, SemanticHooks
from .ports.embedding_provider import EmbeddingProviderPort
from .ports.error_classifier import ErrorClassifierPort
from .ports.example_repository import ExampleRepositoryPort
from .ports.query_execution import QueryExecutionPort
from .ports.repair_policy import RepairPolicyPort
from .ports.semantic_resolver import SemanticResolverPort
from .ports.semantic_validator import SemanticValidatorPort
from .services.query_service import QueryGenerationService

logger = structlog.get_logger()


class NLP2SQL:
    """Pythonic wrapper around QueryGenerationService.

    Stores database_type at construction time so callers don't have to
    repeat it on every ``ask()`` call.
    """

    def __init__(
        self,
        service: QueryGenerationService,
        database_type: DatabaseType,
        semantic_context: SemanticContext | None = None,
    ) -> None:
        self._service = service
        self._database_type = database_type
        self._semantic_context = semantic_context

    # ------------------------------------------------------------------
    # DSL methods
    # ------------------------------------------------------------------

    async def ask(
        self,
        question: str,
        *,
        explain: bool = True,
        execution_mode: ExecutionMode | str | None = None,
        validate: bool = False,
        repair: bool = False,
        timeout_seconds: int = 30,
        semantic_context: SemanticContext | None = None,
    ) -> QueryResult:
        """Convert a natural language question to SQL.

        Args:
            question: Plain-English question about the database.
            explain: Whether to include an explanation of the SQL.

        Returns:
            A ``QueryResult`` with ``.sql``, ``.confidence``, ``.explanation``, etc.
        """
        raw = await self._service.generate_sql(
            question=question,
            database_type=self._database_type,
            include_explanation=explain,
            execution_mode=self._resolve_execution_mode(execution_mode, validate=validate, repair=repair),
            timeout_seconds=timeout_seconds,
            semantic_context=semantic_context or self._semantic_context,
        )
        return QueryResult.from_dict(raw)

    def _resolve_execution_mode(
        self,
        execution_mode: ExecutionMode | str | None,
        *,
        validate: bool,
        repair: bool,
    ) -> str:
        if execution_mode is not None:
            return execution_mode.value if isinstance(execution_mode, ExecutionMode) else execution_mode
        if repair:
            return ExecutionMode.GENERATE_VALIDATE_REPAIR.value
        if validate:
            return ExecutionMode.GENERATE_AND_VALIDATE.value
        return ExecutionMode.GENERATE_ONLY.value

    async def validate(self, sql: str) -> dict[str, Any]:
        """Validate a SQL query against the loaded schema."""
        return await self._service.validate_sql(sql, self._database_type)

    async def explain(self, sql: str) -> dict[str, Any]:
        """Explain what a SQL query does in plain English."""
        return await self._service.explain_query(sql, self._database_type)

    async def suggest(self, partial: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Get query suggestions from a partial question."""
        return await self._service.get_query_suggestions(partial, self._database_type, limit)

    @property
    def stats(self) -> dict[str, Any]:
        """Get service statistics (sync wrapper)."""
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self._service.get_service_stats())


# ------------------------------------------------------------------
# Factory — the ``connect()`` function
# ------------------------------------------------------------------


def _resolve_embedding_provider(
    provider: Optional[ProviderConfig],
    embedding_provider: Optional[EmbeddingProviderPort],
    embedding_provider_type: Optional[str],
) -> Optional[EmbeddingProviderPort]:
    """Pick the embedding provider ``connect()`` uses for schema search and examples.

    An explicit instance or type always wins. Otherwise OpenAI chat reuses its API key
    for OpenAI embeddings, and any other setup uses local embeddings when
    sentence-transformers is installed, or no embeddings when it is not. The chat
    provider name is never used as an embedding type: Anthropic and Gemini have no
    embedding adapter.
    """
    from . import create_embedding_provider

    if embedding_provider is not None:
        return embedding_provider

    openai_key = provider.api_key if provider is not None and provider.provider == "openai" else None
    if embedding_provider_type is not None:
        return create_embedding_provider(
            provider=embedding_provider_type,
            api_key=openai_key if embedding_provider_type == "openai" else None,
        )
    if provider is not None and provider.provider == "openai":
        return create_embedding_provider(provider="openai", api_key=openai_key)
    try:
        return create_embedding_provider(provider="local")
    except ImportError:
        # create_and_initialize_service logs that table matching falls back to text search
        return None


async def connect(
    database_url: str,
    *,
    provider: Optional[ProviderConfig] = None,
    schema: str = "public",
    database_type: Optional[DatabaseType] = None,
    schema_filters: Optional[dict[str, Any]] = None,
    embedding_provider: Optional[EmbeddingProviderPort] = None,
    embedding_provider_type: Optional[str] = None,
    examples: Optional[ExampleRepositoryPort | list[dict[str, Any]]] = None,
    hooks: ExecutionHooks | None = None,
    semantic_hooks: SemanticHooks | None = None,
    execution_port: Optional[QueryExecutionPort] = None,
    error_classifier: Optional[ErrorClassifierPort] = None,
    repair_policy: Optional[RepairPolicyPort] = None,
    semantic_resolver: Optional[SemanticResolverPort] = None,
    semantic_validator: Optional[SemanticValidatorPort] = None,
    semantic_context: SemanticContext | None = None,
    llm_validation: Optional[bool] = None,
) -> NLP2SQL:
    """Connect to a database and return a ready-to-use NLP2SQL client.

    This is the recommended entry point for the library.

    Args:
        database_url: Database connection URL (postgresql://, redshift://, etc.)
        provider: AI provider configuration. If None, falls back to env vars.
        schema: Database schema name (default: ``"public"``).
        database_type: Database type. Auto-detected from URL if None.
        schema_filters: Optional filters (include_schemas, exclude_tables, etc.)
        embedding_provider: Pre-built embedding provider instance.
        embedding_provider_type: Embedding provider to auto-create (``"local"`` or ``"openai"``).
            If neither this nor ``embedding_provider`` is given, OpenAI chat uses OpenAI
            embeddings with the same API key; other providers use local embeddings when
            ``nlp2sql[embeddings-local]`` is installed, or no embeddings otherwise.
        examples: Few-shot examples. Can be:
            - A list of dicts ``[{"question": ..., "sql": ..., "database_type": ...}]``
              (auto-creates an ExampleStore with the same embedding provider; ignored with a
              warning when no embedding provider is available)
            - A pre-built ``ExampleRepositoryPort`` instance
        hooks: Grouped execution hooks for validation/repair in the public DSL.
        semantic_hooks: Grouped semantic hooks for business-aware retrieval and validation.
        llm_validation: Also ask the LLM to review each generated query, a second call per
            question. If None, uses ``NLP2SQL_LLM_VALIDATION`` (default: off). Column, dialect,
            semantic and read-only checks always run, and execution modes validate against the
            database.

    Returns:
        An initialized ``NLP2SQL`` client ready for ``ask()`` calls.

    Example::

        nlp = await nlp2sql.connect(
            "redshift://user:pass@host:5439/dev",
            provider=ProviderConfig(provider="openai", api_key=key),
            schema="dwh_data_share_llm",
            examples=[
                {"question": "Total sales?", "sql": "SELECT SUM(sales) FROM orders", "database_type": "redshift"},
            ],
        )
        result = await nlp.ask("Total sales by store last month")
        print(result.sql)
    """
    from . import create_and_initialize_service
    from .schema.example_store import ExampleStore

    # Auto-detect database type from URL if not provided
    if database_type is None:
        if "redshift" in database_url.lower():
            database_type = DatabaseType.REDSHIFT
        else:
            database_type = DatabaseType.POSTGRES

    # One embedding provider serves both schema search and few-shot examples
    embedding_provider = _resolve_embedding_provider(provider, embedding_provider, embedding_provider_type)

    # Auto-create ExampleStore from a plain list of dicts
    example_store: Optional[ExampleRepositoryPort] = None
    if isinstance(examples, list):
        if embedding_provider is not None:
            example_store = ExampleStore(
                embedding_provider=embedding_provider,
                database_url=database_url,
                schema_name=schema,
            )
            await example_store.add_examples(examples)
            logger.info("Examples loaded via connect()", count=len(examples))
        else:
            logger.warning(
                "Few-shot examples ignored: no embedding provider is available. "
                "Install nlp2sql[embeddings-local] or pass embedding_provider_type='openai'.",
                count=len(examples),
            )
    elif examples is not None:
        # Already an ExampleRepositoryPort instance
        example_store = examples

    if hooks is not None:
        execution_port = execution_port or hooks.execution_port
        error_classifier = error_classifier or hooks.error_classifier
        repair_policy = repair_policy or hooks.repair_policy
    if semantic_hooks is not None:
        semantic_resolver = semantic_resolver or semantic_hooks.semantic_resolver
        semantic_validator = semantic_validator or semantic_hooks.semantic_validator
        semantic_context = semantic_context or semantic_hooks.semantic_context

    service = await create_and_initialize_service(
        database_url=database_url,
        database_type=database_type,
        schema_name=schema,
        schema_filters=schema_filters,
        embedding_provider=embedding_provider,
        example_store=example_store,
        provider_config=provider,
        execution_port=execution_port,
        error_classifier=error_classifier,
        repair_policy=repair_policy,
        semantic_resolver=semantic_resolver,
        semantic_validator=semantic_validator,
        llm_validation=llm_validation,
    )

    return NLP2SQL(service=service, database_type=database_type, semantic_context=semantic_context)
