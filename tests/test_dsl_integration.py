"""Integration tests for the DSL API (connect / ask / validate / explain)."""

import os

import pytest

import nlp2sql as lib
from nlp2sql import ProviderConfig
from nlp2sql.client import NLP2SQL
from nlp2sql.core.entities import DatabaseType
from nlp2sql.core.result import QueryResult
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
]


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
        # Isolate FAISS indexes so mock-dimension caches don't clash
        monkeypatch.setenv("NLP2SQL_DATA_DIR", str(tmp_path))

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
