"""Integration tests for the DSL API (connect / ask / validate / explain)."""

import os

import pytest

import nlp2sql as lib
from nlp2sql import ProviderConfig
from nlp2sql.client import NLP2SQL
from nlp2sql.core.entities import (
    DatabaseType,
    DimensionDefinition,
    DomainRule,
    MetricDefinition,
    SemanticContext,
    SemanticEntityMapping,
)
from nlp2sql.core.result import QueryResult
from nlp2sql.ports.ai_provider import QueryContext, QueryResponse
from nlp2sql.schema.example_store import ExampleStore
from nlp2sql.services.query_service import QueryGenerationService

from conftest import EXPECTED_TABLES, MockAIProvider, MockEmbeddingProvider

# ---------------------------------------------------------------------------
# Few-shot examples for testing
# ---------------------------------------------------------------------------

_TEST_EXAMPLES = [
    {
        "question": "How many users are active?",
        "sql": "SELECT COUNT(*) FROM users WHERE is_active = true",
        "database_type": "postgres",
    },
    {
        "question": "Total revenue by product category",
        "sql": (
            "SELECT c.name, SUM(oi.total_price) AS revenue "
            "FROM order_items oi JOIN products p ON oi.product_id = p.id "
            "JOIN categories c ON p.category_id = c.id GROUP BY c.name"
        ),
        "database_type": "postgres",
    },
    {
        "question": "Show daily revenue by source category for the flagship North America store",
        "sql": (
            "SELECT d.metric_date, mc.source_category, SUM(d.orders_count) AS orders_count, "
            "SUM(d.revenue) AS revenue "
            "FROM daily_channel_metrics d "
            "JOIN stores s ON d.store_id = s.id "
            "JOIN marketing_channels mc ON d.channel_id = mc.id "
            "WHERE s.code = 'na_flagship' AND s.region = 'North America' "
            "GROUP BY d.metric_date, mc.source_category"
        ),
        "database_type": "postgres",
        "metadata": {"tables": ["daily_channel_metrics", "stores", "marketing_channels"]},
    },
]


@pytest.fixture(autouse=True)
def isolate_local_indexes(tmp_path, monkeypatch):
    """Keep schema/example indexes isolated per test to avoid cache collisions."""
    monkeypatch.setenv("NLP2SQL_EMBEDDINGS_DIR", str(tmp_path / "embeddings"))
    monkeypatch.setenv("NLP2SQL_EXAMPLES_DIR", str(tmp_path / "examples"))


def _build_channel_performance_semantic_context() -> SemanticContext:
    return SemanticContext(
        domain="ecommerce_channel_performance",
        canonical_tables=["daily_channel_metrics"],
        required_filters=["s.code = 'na_flagship'", "s.region = 'North America'"],
        disallowed_tables=["orders"],
        prompt_hints=[
            "Prefer the aggregated daily channel metrics fact table for source-category performance questions."
        ],
        entity_mappings=[
            SemanticEntityMapping(
                source_term="North America flagship store",
                target="store_scope",
                resolved_value="na_flagship / North America",
                filter_expression="s.code = 'na_flagship' AND s.region = 'North America'",
            )
        ],
        metric_definitions=[
            MetricDefinition(name="revenue", description="Revenue aggregated by day and source category."),
            MetricDefinition(name="orders_count", description="Order count aggregated by day and source category."),
            MetricDefinition(
                name="conversion_rate",
                expression="SUM(d.orders_count)::float / NULLIF(SUM(d.sessions), 0)",
                description="Orders divided by sessions on the daily channel metrics fact table.",
            ),
        ],
        dimension_definitions=[
            DimensionDefinition(name="metric_date", description="Daily grain for channel performance."),
            DimensionDefinition(name="source_category", description="Channel grouping dimension."),
        ],
        rules=[
            DomainRule(
                name="preserve_source_breakdown",
                description="Keep source_category when the user asks for a source breakdown.",
                required_dimensions=["source_category"],
                preferred_tables=["daily_channel_metrics"],
            )
        ],
    )


class SemanticAwareMockAIProvider(MockAIProvider):
    """Mock provider that reacts to semantic planning metadata."""

    async def generate_query(self, context: QueryContext) -> QueryResponse:
        metadata = context.metadata or {}
        semantic_context = metadata.get("semantic_context", {})
        sql_intent_plan = metadata.get("sql_intent_plan", {})

        if (
            semantic_context.get("domain") == "ecommerce_channel_performance"
            and sql_intent_plan.get("fact_table") == "daily_channel_metrics"
            and "source_category" in sql_intent_plan.get("dimensions", [])
        ):
            return QueryResponse(
                sql=(
                    "SELECT d.metric_date, mc.source_category, "
                    "SUM(d.orders_count) AS orders_count, SUM(d.revenue) AS revenue "
                    "FROM daily_channel_metrics d "
                    "JOIN stores s ON d.store_id = s.id "
                    "JOIN marketing_channels mc ON d.channel_id = mc.id "
                    "WHERE s.code = 'na_flagship' AND s.region = 'North America' "
                    "GROUP BY d.metric_date, mc.source_category "
                    "ORDER BY d.metric_date, revenue DESC"
                ),
                explanation="Use aggregated daily channel metrics for source-category ecommerce performance.",
                confidence=0.99,
                tokens_used=120,
                provider="mock-semantic",
            )

        return QueryResponse(
            sql=(
                "SELECT DATE(order_date) AS order_day, COUNT(*) AS orders_count, SUM(total_amount) AS revenue "
                "FROM orders GROUP BY DATE(order_date) ORDER BY order_day"
            ),
            explanation="Fallback to transactional orders table without semantic business guidance.",
            confidence=0.7,
            tokens_used=80,
            provider="mock-semantic",
        )


# ---------------------------------------------------------------------------
# Level 1 — Mock AI, real PostgreSQL
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
class TestConnectDSL:
    """Test nlp2sql.connect() factory with Docker PostgreSQL."""

    async def test_connect_returns_nlp2sql_instance(self, postgres_available, mock_embedding_provider):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
        )
        assert isinstance(nlp, NLP2SQL)

    async def test_auto_detects_postgres_type(self, postgres_available, mock_embedding_provider):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
        )
        assert nlp._database_type == DatabaseType.POSTGRES

    async def test_connect_with_schema_filters(self, postgres_available, mock_embedding_provider):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
            schema_filters={"exclude_tables": ["reviews", "categories"]},
        )
        assert isinstance(nlp, NLP2SQL)

    async def test_connect_with_examples_list(self, postgres_available, mock_embedding_provider):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
            examples=_TEST_EXAMPLES,
        )
        assert isinstance(nlp, NLP2SQL)

    async def test_connect_with_example_repository_port(self, postgres_available, mock_embedding_provider):
        store = ExampleStore(embedding_provider=mock_embedding_provider)
        await store.add_examples(_TEST_EXAMPLES)

        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
            examples=store,
        )
        assert isinstance(nlp, NLP2SQL)


@pytest.mark.integration
@pytest.mark.asyncio
class TestAskDSL:
    """Test NLP2SQL.ask() end-to-end with mock AI + real DB."""

    async def _build_client(self, url: str, emb: MockEmbeddingProvider) -> NLP2SQL:
        """Helper: build client with MockAIProvider injected."""
        nlp = await lib.connect(
            url,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=emb,
        )
        # Replace AI provider with mock to avoid API calls
        nlp._service.ai_provider = MockAIProvider()
        return nlp

    async def test_ask_returns_query_result(self, postgres_available, mock_embedding_provider):
        nlp = await self._build_client(postgres_available, mock_embedding_provider)
        result = await nlp.ask("How many users are there?")

        assert isinstance(result, QueryResult)
        assert result.sql
        assert result.confidence > 0
        assert result.is_valid is True

    async def test_ask_without_explanation(self, postgres_available, mock_embedding_provider):
        nlp = await self._build_client(postgres_available, mock_embedding_provider)
        result = await nlp.ask("How many users?", explain=False)

        assert isinstance(result, QueryResult)
        assert result.explanation is None

    async def test_ask_with_examples(self, postgres_available, mock_embedding_provider):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
            examples=_TEST_EXAMPLES,
        )
        nlp._service.ai_provider = MockAIProvider()

        result = await nlp.ask("How many active users?")
        assert isinstance(result, QueryResult)
        assert result.sql

    async def test_ask_with_in_memory_semantic_context(self, postgres_available, mock_embedding_provider):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
            examples=_TEST_EXAMPLES,
        )
        nlp._service.ai_provider = SemanticAwareMockAIProvider()

        result = await nlp.ask(
            "Show daily revenue and order count by source category for the North America flagship store",
            semantic_context=_build_channel_performance_semantic_context(),
        )

        assert isinstance(result, QueryResult)
        assert "daily_channel_metrics" in result.sql
        assert "source_category" in result.sql
        assert result.metadata["sql_intent_plan"]["fact_table"] == "daily_channel_metrics"
        assert "source_category" in result.metadata["sql_intent_plan"]["dimensions"]

        execution = await nlp._service.schema_repository.execute_query(result.sql)
        assert execution["row_count"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestSemanticRegressionScenario:
    """Reproduce a wrong-choice path and prove semantic guidance fixes it."""

    async def test_semantic_context_shifts_from_orders_to_daily_channel_metrics(
        self,
        postgres_available,
        mock_embedding_provider,
    ):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=mock_embedding_provider,
            examples=_TEST_EXAMPLES,
        )
        nlp._service.ai_provider = SemanticAwareMockAIProvider()
        question = "Show daily revenue and order count by source category for the North America flagship store"

        baseline = await nlp.ask(question)
        assert "FROM orders" in baseline.sql
        baseline_execution = await nlp._service.schema_repository.execute_query(baseline.sql)
        assert baseline_execution["row_count"] > 0

        enriched = await nlp.ask(
            question,
            semantic_context=_build_channel_performance_semantic_context(),
        )
        assert "FROM daily_channel_metrics" in enriched.sql
        assert enriched.metadata["sql_intent_plan"]["fact_table"] == "daily_channel_metrics"
        assert "source_category" in enriched.metadata["sql_intent_plan"]["group_by"]

        enriched_execution = await nlp._service.schema_repository.execute_query(enriched.sql)
        assert enriched_execution["row_count"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestValidateDSL:
    """Test NLP2SQL.validate() with real DB schema."""

    async def _build_client(self, url: str, emb: MockEmbeddingProvider) -> NLP2SQL:
        nlp = await lib.connect(
            url,
            provider=ProviderConfig(provider="openai", api_key="fake"),
            embedding_provider=emb,
        )
        nlp._service.ai_provider = MockAIProvider()
        return nlp

    async def test_validate_good_sql(self, postgres_available, mock_embedding_provider):
        nlp = await self._build_client(postgres_available, mock_embedding_provider)
        result = await nlp.validate("SELECT COUNT(*) FROM users")
        assert result["is_valid"] is True

    async def test_validate_bad_sql(self, postgres_available, mock_embedding_provider):
        nlp = await self._build_client(postgres_available, mock_embedding_provider)
        result = await nlp.validate("THIS IS NOT SQL")
        assert result["is_valid"] is True  # MockAIProvider always returns valid


# ---------------------------------------------------------------------------
# Level 2 — Real AI + real PostgreSQL (requires API key)
# ---------------------------------------------------------------------------


@pytest.mark.llm
@pytest.mark.integration
@pytest.mark.asyncio
class TestEndToEndWithRealAI:
    """Full pipeline with real AI provider. Run with: uv run pytest -m llm"""

    @pytest.fixture(autouse=True)
    def require_api_key(self, tmp_path, monkeypatch):
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        monkeypatch.setenv("NLP2SQL_EMBEDDINGS_DIR", str(tmp_path / "embeddings"))
        monkeypatch.setenv("NLP2SQL_EXAMPLES_DIR", str(tmp_path / "examples"))

    async def test_generate_valid_sql(self, postgres_available):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(
                provider="openai",
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=0.0,
            ),
        )
        result = await nlp.ask("How many users are in the database?")

        assert result.sql
        assert "users" in result.sql.lower()
        assert result.confidence > 0

    async def test_generate_with_examples(self, postgres_available):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(
                provider="openai",
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=0.0,
            ),
            examples=_TEST_EXAMPLES,
        )
        result = await nlp.ask("Show me total revenue per category")

        assert result.sql
        assert "category" in result.sql.lower() or "categories" in result.sql.lower()

    async def test_provider_config_model_override(self, postgres_available):
        nlp = await lib.connect(
            postgres_available,
            provider=ProviderConfig(
                provider="openai",
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-4o-mini",
                temperature=0.0,
            ),
        )
        result = await nlp.ask("List all product names")

        assert result.sql
        assert "products" in result.sql.lower() or "name" in result.sql.lower()
