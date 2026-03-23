"""Shared fixtures for nlp2sql tests."""

import os
from typing import Any

import numpy as np
import pytest
import pytest_asyncio

from nlp2sql.core.entities import DatabaseType
from nlp2sql.ports.ai_provider import AIProviderPort, AIProviderType, QueryContext, QueryResponse
from nlp2sql.ports.embedding_provider import EmbeddingProviderPort

# ---------------------------------------------------------------------------
# Configuration — override via env vars
# ---------------------------------------------------------------------------

POSTGRES_HOST = os.getenv("NLP2SQL_TEST_POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("NLP2SQL_TEST_POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("NLP2SQL_TEST_POSTGRES_USER", "testuser")
POSTGRES_PASS = os.getenv("NLP2SQL_TEST_POSTGRES_PASS", "testpass")
POSTGRES_DB = os.getenv("NLP2SQL_TEST_POSTGRES_DB", "testdb")

POSTGRES_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASS}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Expected tables from docker/init-schema.sql
EXPECTED_TABLES = {"users", "categories", "products", "orders", "order_items", "reviews"}


# ---------------------------------------------------------------------------
# Mock providers — no external API calls
# ---------------------------------------------------------------------------


class MockEmbeddingProvider(EmbeddingProviderPort):
    """Deterministic embedding provider for testing (384-dim)."""

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension
        self._provider_type = "mock"

    @property
    def provider_type(self) -> str:
        return self._provider_type

    def get_embedding_dimension(self) -> int:
        return self._dimension

    async def encode(self, texts: list[str]) -> np.ndarray:
        rng = np.random.default_rng(seed=42)
        embeddings = rng.standard_normal((len(texts), self._dimension)).astype(np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / norms


class MockAIProvider(AIProviderPort):
    """AI provider that returns deterministic SQL without API calls."""

    def __init__(self, default_sql: str = "SELECT COUNT(*) FROM users") -> None:
        self._default_sql = default_sql

    async def generate_query(self, context: QueryContext) -> QueryResponse:
        return QueryResponse(
            sql=self._default_sql,
            explanation="Mock explanation for testing.",
            confidence=0.95,
            tokens_used=100,
            provider="mock",
        )

    async def validate_query(self, sql: str, schema_context: str) -> dict[str, Any]:
        return {"is_valid": True, "issues": []}

    def get_token_count(self, text: str) -> int:
        return len(text.split())

    def get_max_context_size(self) -> int:
        return 128_000

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.OPENAI


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def postgres_url() -> str:
    return POSTGRES_URL


@pytest.fixture
def mock_embedding_provider() -> MockEmbeddingProvider:
    return MockEmbeddingProvider()


@pytest.fixture
def mock_ai_provider() -> MockAIProvider:
    return MockAIProvider()


async def _postgres_is_reachable(url: str) -> bool:
    """Return True if the Docker postgres is accepting connections."""
    try:
        from nlp2sql.adapters.postgres_repository import PostgreSQLRepository

        repo = PostgreSQLRepository(url)
        await repo.initialize()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def postgres_available(postgres_url: str) -> str:
    """Skip the test if Docker postgres is not running."""
    reachable = await _postgres_is_reachable(postgres_url)
    if not reachable:
        pytest.skip(f"PostgreSQL not reachable at {postgres_url}")
    return postgres_url
