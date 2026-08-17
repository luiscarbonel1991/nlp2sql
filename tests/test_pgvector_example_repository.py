"""Integration tests for ``PgvectorExampleRepository``.

Requires a PostgreSQL instance with the ``pgvector`` extension available
(e.g. the ``pgvector/pgvector:pg16`` Docker image). Tests are gated by the
same ``postgres_available`` fixture used by other integration suites, and
skip gracefully when pgvector is not installed.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import psycopg2
import pytest
import pytest_asyncio

from nlp2sql.exceptions import SchemaException

from conftest import require_integration

pgvector = pytest.importorskip("pgvector.psycopg2")

from nlp2sql.adapters.pgvector_example_repository import PgvectorExampleRepository  # noqa: E402

# Integration marks are applied per-class below so the pure-helper tests in
# ``TestHelpersNoDB`` still run under ``pytest -m "not integration"``.


def _pgvector_extension_installed(url: str) -> bool:
    """Return True when the ``vector`` extension can be loaded."""
    try:
        conn = psycopg2.connect(url)
        try:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.close()
            return True
        finally:
            conn.close()
    except Exception:
        return False


@pytest_asyncio.fixture
async def pgvector_available(postgres_available: str) -> str:
    """Skip (or, in CI, fail) unless both Postgres and the ``vector`` extension are reachable."""
    installed = await asyncio.to_thread(_pgvector_extension_installed, postgres_available)
    if not installed:
        message = "pgvector extension not available on the test database"
        if require_integration():
            pytest.fail(f"{message} (NLP2SQL_REQUIRE_INTEGRATION set — refusing to skip)")
        pytest.skip(message)
    return postgres_available


@pytest.fixture
def unique_table_name() -> str:
    """Return a unique table name so parallel tests never collide."""
    return f"nlp2sql_examples_test_{uuid.uuid4().hex[:12]}"


@pytest_asyncio.fixture
async def pgvector_repo(
    pgvector_available: str,
    unique_table_name: str,
    mock_embedding_provider,
):
    """Build a repository pointed at a throwaway table; drop the table on teardown."""
    repo = PgvectorExampleRepository(
        connection_string=pgvector_available,
        embedding_provider=mock_embedding_provider,
        namespace="test-default",
        table_name=unique_table_name,
    )
    try:
        yield repo
    finally:
        await asyncio.to_thread(_drop_table, pgvector_available, unique_table_name)


def _drop_table(url: str, table_name: str) -> None:
    conn = psycopg2.connect(url)
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        cur.close()
    finally:
        conn.close()


def _sample_examples() -> list[dict[str, Any]]:
    return [
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
            "question": "Monthly order count",
            "sql": "SELECT DATE_TRUNC('month', created_at) AS m, COUNT(*) FROM orders GROUP BY m",
            "database_type": "redshift",
        },
    ]


# ── Unit-level checks that don't need a real DB ─────────────────────────────


class TestHelpersNoDB:
    """Pure-function helpers we want behavior-compatible with ExampleStore."""

    def test_extract_sql_tables_simple(self, mock_embedding_provider):
        # auto_migrate=False would need the table; we only reach helper methods,
        # so construct manually and skip __init__ DB work by monkeypatching
        repo = PgvectorExampleRepository.__new__(PgvectorExampleRepository)
        repo.embedding_provider = mock_embedding_provider  # type: ignore[attr-defined]
        tables = repo._extract_sql_tables("SELECT * FROM users u JOIN orders o ON u.id = o.user_id")
        assert tables == ["users", "orders"]

    def test_extract_sql_tables_schema_qualified(self, mock_embedding_provider):
        repo = PgvectorExampleRepository.__new__(PgvectorExampleRepository)
        repo.embedding_provider = mock_embedding_provider  # type: ignore[attr-defined]
        tables = repo._extract_sql_tables("SELECT * FROM public.users")
        assert tables == ["users"]

    def test_content_hash_matches_example_store(self, mock_embedding_provider):
        """Content hash must be byte-identical to ExampleStore's so the two
        adapters can share dedup keys when migrating data across backends."""
        from nlp2sql.schema.example_store import ExampleStore

        repo = PgvectorExampleRepository.__new__(PgvectorExampleRepository)
        example = {"question": "q1", "sql": "SELECT 1"}

        faiss_store = ExampleStore.__new__(ExampleStore)
        assert repo._create_content_hash(example) == faiss_store._create_example_key(example)

    def test_embedding_text_uses_all_metadata(self, mock_embedding_provider):
        repo = PgvectorExampleRepository.__new__(PgvectorExampleRepository)
        example = {
            "question": "Q",
            "sql": "SELECT 1",
            "metadata": {
                "tables": ["users"],
                "metrics": ["count"],
                "dimensions": ["day"],
                "intent": "aggregate",
            },
        }
        text = repo._create_example_embedding_text(example)
        assert "Question: Q" in text
        assert "SQL: SELECT 1" in text
        assert "Tables: users" in text
        assert "Metrics: count" in text
        assert "Dimensions: day" in text
        assert "Intent: aggregate" in text

    def test_rejects_invalid_table_name(self, mock_embedding_provider):
        with pytest.raises(ValueError, match="Invalid table_name"):
            PgvectorExampleRepository(
                connection_string="postgresql://user:pass@localhost/db",
                embedding_provider=mock_embedding_provider,
                table_name="DROP TABLE users; --",
            )


# ── DB-backed tests ─────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
class TestAddExamples:
    async def test_add_examples_inserts_rows(self, pgvector_repo):
        await pgvector_repo.add_examples(_sample_examples())
        stats = pgvector_repo.get_stats()
        assert stats["total_examples"] == 3
        assert set(stats["database_types"]) == {"postgres", "redshift"}

    async def test_add_examples_dedup_on_conflict(self, pgvector_repo):
        examples = _sample_examples()[:1]
        await pgvector_repo.add_examples(examples)
        await pgvector_repo.add_examples(examples)  # same rows — must no-op
        assert pgvector_repo.get_stats()["total_examples"] == 1

    async def test_add_examples_noop_for_empty_list(self, pgvector_repo):
        await pgvector_repo.add_examples([])
        assert pgvector_repo.get_stats()["total_examples"] == 0

    async def test_add_examples_handles_metadata_none(self, pgvector_repo):
        """Examples that explicitly pass ``metadata=None`` (common in ETL
        pipelines that emit null for optional fields) must not crash."""
        await pgvector_repo.add_examples(
            [
                {
                    "question": "How many products?",
                    "sql": "SELECT COUNT(*) FROM products",
                    "database_type": "postgres",
                    "metadata": None,
                },
            ]
        )
        assert pgvector_repo.get_stats()["total_examples"] == 1

    async def test_add_examples_handles_missing_database_type(self, pgvector_repo):
        """Missing ``database_type`` is stored as NULL (parity with ExampleStore)."""
        await pgvector_repo.add_examples(
            [{"question": "Q", "sql": "SELECT 1"}],
        )
        assert pgvector_repo.get_stats()["total_examples"] == 1

    async def test_concurrent_add_is_safe(self, pgvector_repo):
        """``ON CONFLICT (namespace, content_hash) DO NOTHING`` must protect
        against concurrent inserts of the same examples."""
        examples = _sample_examples()
        await asyncio.gather(*[pgvector_repo.add_examples(examples) for _ in range(5)])
        # 3 unique examples, regardless of how many writers raced.
        assert pgvector_repo.get_stats()["total_examples"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestSearchSimilar:
    async def test_returns_ranked_results(self, pgvector_repo):
        await pgvector_repo.add_examples(_sample_examples())
        results = await pgvector_repo.search_similar("how many active users", top_k=3, min_score=0.0)
        assert len(results) > 0
        assert all("similarity_score" in r for r in results)
        scores = [r["similarity_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_filters_by_database_type(self, pgvector_repo):
        await pgvector_repo.add_examples(_sample_examples())
        # min_score=-1 so the score threshold doesn't interact with random mock
        # embeddings — this test only exercises the database_type filter.
        results = await pgvector_repo.search_similar(
            "monthly", top_k=5, database_type="redshift", min_score=-1.0
        )
        assert {r["database_type"] for r in results} == {"redshift"}

    async def test_respects_min_score(self, pgvector_repo):
        await pgvector_repo.add_examples(_sample_examples())
        # min_score=2.0 means similarity must be >=2.0 (impossible with cosine).
        results = await pgvector_repo.search_similar("anything", top_k=5, min_score=2.0)
        assert results == []

    async def test_empty_when_no_rows(self, pgvector_repo):
        results = await pgvector_repo.search_similar("anything", top_k=5, min_score=0.0)
        assert results == []

    async def test_top_k_zero_returns_empty(self, pgvector_repo):
        await pgvector_repo.add_examples(_sample_examples())
        assert await pgvector_repo.search_similar("q", top_k=0) == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestNamespaceIsolation:
    async def test_clear_only_current_namespace(self, pgvector_available, mock_embedding_provider, unique_table_name):
        repo_a = PgvectorExampleRepository(
            connection_string=pgvector_available,
            embedding_provider=mock_embedding_provider,
            namespace="ns-a",
            table_name=unique_table_name,
        )
        repo_b = PgvectorExampleRepository(
            connection_string=pgvector_available,
            embedding_provider=mock_embedding_provider,
            namespace="ns-b",
            table_name=unique_table_name,
            auto_migrate=False,  # table already exists from repo_a
        )
        try:
            await repo_a.add_examples(_sample_examples()[:2])
            await repo_b.add_examples(_sample_examples()[2:])

            assert repo_a.get_stats()["total_examples"] == 2
            assert repo_b.get_stats()["total_examples"] == 1

            await repo_a.clear()
            assert repo_a.get_stats()["total_examples"] == 0
            assert repo_b.get_stats()["total_examples"] == 1
        finally:
            await asyncio.to_thread(_drop_table, pgvector_available, unique_table_name)

    async def test_search_does_not_cross_namespaces(
        self, pgvector_available, mock_embedding_provider, unique_table_name
    ):
        repo_a = PgvectorExampleRepository(
            connection_string=pgvector_available,
            embedding_provider=mock_embedding_provider,
            namespace="iso-a",
            table_name=unique_table_name,
        )
        repo_b = PgvectorExampleRepository(
            connection_string=pgvector_available,
            embedding_provider=mock_embedding_provider,
            namespace="iso-b",
            table_name=unique_table_name,
            auto_migrate=False,
        )
        try:
            await repo_a.add_examples(_sample_examples())
            results = await repo_b.search_similar("anything", top_k=10, min_score=0.0)
            assert results == []
        finally:
            await asyncio.to_thread(_drop_table, pgvector_available, unique_table_name)

    async def test_namespace_from_database_url_matches_example_store(
        self, pgvector_available, mock_embedding_provider, unique_table_name
    ):
        """The md5(url:schema) hashing must match the FAISS adapter so both
        backends address the same logical tenant for a given connection."""
        import hashlib

        repo = PgvectorExampleRepository(
            connection_string=pgvector_available,
            embedding_provider=mock_embedding_provider,
            database_url="postgresql://host/db",
            schema_name="analytics",
            table_name=unique_table_name,
        )
        try:
            expected = hashlib.md5(b"postgresql://host/db:analytics").hexdigest()
            assert repo.namespace == expected
        finally:
            await asyncio.to_thread(_drop_table, pgvector_available, unique_table_name)


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchemaValidation:
    async def test_dimension_mismatch_raises(self, pgvector_available, mock_embedding_provider, unique_table_name):
        from conftest import MockEmbeddingProvider

        # Create the table with 384 dims
        PgvectorExampleRepository(
            connection_string=pgvector_available,
            embedding_provider=mock_embedding_provider,
            table_name=unique_table_name,
        )
        try:
            wrong = MockEmbeddingProvider(dimension=768)
            with pytest.raises(SchemaException, match="dimension mismatch"):
                PgvectorExampleRepository(
                    connection_string=pgvector_available,
                    embedding_provider=wrong,
                    table_name=unique_table_name,
                )
        finally:
            await asyncio.to_thread(_drop_table, pgvector_available, unique_table_name)

    async def test_auto_migrate_false_fails_when_table_missing(
        self, pgvector_available, mock_embedding_provider, unique_table_name
    ):
        with pytest.raises(SchemaException, match="not found"):
            PgvectorExampleRepository(
                connection_string=pgvector_available,
                embedding_provider=mock_embedding_provider,
                table_name=unique_table_name,
                auto_migrate=False,
            )



@pytest.mark.integration
@pytest.mark.asyncio
class TestGetStats:
    async def test_stats_reflect_current_namespace(self, pgvector_repo, mock_embedding_provider):
        await pgvector_repo.add_examples(_sample_examples())
        stats = pgvector_repo.get_stats()
        assert stats["embedding_dimension"] == mock_embedding_provider.get_embedding_dimension()
        assert stats["provider_type"] == mock_embedding_provider.provider_type
        assert stats["namespace"] == "test-default"
        assert stats["total_examples"] == 3
