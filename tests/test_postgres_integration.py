"""Integration tests against Docker PostgreSQL (no API keys required)."""

import pytest

from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.core.entities import DatabaseType
from nlp2sql.core.sql_safety import is_safe_query
from nlp2sql.schema.embedding_manager import SchemaEmbeddingManager
from nlp2sql.schema.manager import SchemaManager

from conftest import EXPECTED_TABLES


@pytest.mark.integration
@pytest.mark.asyncio
class TestPostgresRepository:
    """Verify schema discovery against a real PostgreSQL database."""

    async def test_connect_and_discover_tables(self, postgres_available):
        repo = PostgreSQLRepository(postgres_available)
        await repo.initialize()

        tables = await repo.get_tables()
        table_names = {t.name.lower() for t in tables}

        assert EXPECTED_TABLES.issubset(table_names), f"Missing tables: {EXPECTED_TABLES - table_names}"

    async def test_column_discovery(self, postgres_available):
        repo = PostgreSQLRepository(postgres_available)
        await repo.initialize()

        tables = await repo.get_tables()
        users_table = next((t for t in tables if t.name.lower() == "users"), None)
        assert users_table is not None

        column_names = {c["name"].lower() for c in users_table.columns}
        expected = {"id", "email", "first_name", "last_name", "city", "country", "is_active"}
        assert expected.issubset(column_names), f"Missing columns: {expected - column_names}"

    async def test_returns_only_tables_not_views(self, postgres_available):
        repo = PostgreSQLRepository(postgres_available)
        await repo.initialize()

        tables = await repo.get_tables()
        names = {t.name.lower() for t in tables}
        assert EXPECTED_TABLES.issubset(names)
        assert "order_summaries" not in names  # views are excluded

    async def test_safe_query_check(self, postgres_available):
        safe, _ = is_safe_query("SELECT COUNT(*) FROM users")
        assert safe

        safe, _ = is_safe_query("DROP TABLE users")
        assert not safe

        safe, _ = is_safe_query("DELETE FROM orders")
        assert not safe

        safe, _ = is_safe_query("TRUNCATE users")
        assert not safe


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchemaManagerWithPostgres:
    """Test SchemaManager pipeline with a real PostgreSQL backend."""

    async def test_schema_filters_exclude_tables(self, postgres_available, mock_embedding_provider):
        repo = PostgreSQLRepository(postgres_available)
        manager = SchemaManager(
            repository=repo,
            embedding_provider=mock_embedding_provider,
            schema_filters={"exclude_tables": ["reviews"]},
        )
        await repo.initialize()
        await manager.initialize(DatabaseType.POSTGRES)

        context = await manager.get_optimal_schema_context("How many users?", DatabaseType.POSTGRES, max_tokens=4000)
        assert "reviews" not in context.lower()

    async def test_schema_filters_include_tables(self, postgres_available, mock_embedding_provider):
        repo = PostgreSQLRepository(postgres_available)
        manager = SchemaManager(
            repository=repo,
            embedding_provider=mock_embedding_provider,
            schema_filters={"include_tables": ["users", "orders"]},
        )
        await repo.initialize()
        await manager.initialize(DatabaseType.POSTGRES)

        context = await manager.get_optimal_schema_context("How many users?", DatabaseType.POSTGRES, max_tokens=4000)
        assert "users" in context.lower()

    async def test_embedding_search_against_real_schema(self, postgres_available, mock_embedding_provider, tmp_path):
        repo = PostgreSQLRepository(postgres_available)
        await repo.initialize()

        tables = await repo.get_tables()
        emb_manager = SchemaEmbeddingManager(
            database_url=postgres_available,
            embedding_provider=mock_embedding_provider,
            index_path=tmp_path,
        )

        elements = []
        for table in tables:
            elements.append(
                {"type": "table", "name": table.name, "columns": [{"name": c["name"]} for c in table.columns]}
            )
            for col in table.columns:
                elements.append(
                    {
                        "type": "column",
                        "name": col["name"],
                        "table_name": table.name,
                        "data_type": col.get("data_type", "unknown"),
                    }
                )

        await emb_manager.add_schema_elements(elements, DatabaseType.POSTGRES)
        results = await emb_manager.search_similar("customer email", top_k=5, min_score=0.0)

        assert len(results) > 0
