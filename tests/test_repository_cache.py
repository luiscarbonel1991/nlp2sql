"""Tests for repository disk cache functionality.

Tests the hybrid bulk query + disk cache approach implemented in
PostgreSQLRepository and RedshiftRepository.
"""

import pickle
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from nlp2sql.adapters.postgres_repository import (
    SCHEMA_CACHE_TTL_HOURS,
    SCHEMA_CACHE_VERSION,
    PostgreSQLRepository,
)
from nlp2sql.ports.schema_repository import TableInfo


class TestPostgreSQLCacheDirectory:
    """Test cache directory management."""

    def test_get_cache_dir_creates_directory(self, tmp_path: Path):
        """Test that _get_cache_dir creates the directory if it doesn't exist."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            cache_dir = repo._get_cache_dir()

            assert cache_dir.exists()
            assert cache_dir.is_dir()

    def test_get_cache_dir_uses_url_hash(self):
        """Test that different URLs produce different cache directories."""
        repo1 = PostgreSQLRepository("postgresql://user:pass@localhost/db1")
        repo2 = PostgreSQLRepository("postgresql://user:pass@localhost/db2")

        # They should have different cache directories
        assert repo1._get_cache_dir().name != repo2._get_cache_dir().name

    def test_get_cache_dir_same_url_same_hash(self):
        """Test that same URL produces same cache directory."""
        repo1 = PostgreSQLRepository("postgresql://user:pass@localhost/db")
        repo2 = PostgreSQLRepository("postgresql://user:pass@localhost/db")

        assert repo1._get_cache_dir().name == repo2._get_cache_dir().name

    def test_get_tables_cache_path(self, tmp_path: Path):
        """Test that cache path includes schema name."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            cache_path = repo._get_tables_cache_path("public")

            assert cache_path.name == "tables_cache_public.pkl"


class TestCacheValidation:
    """Test cache validity checking."""

    def test_is_cache_valid_missing_file(self, tmp_path: Path):
        """Test that missing cache file returns False."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            assert repo._is_cache_valid("public") is False

    def test_is_cache_valid_version_mismatch(self, tmp_path: Path):
        """Test that version mismatch invalidates cache."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            cache_path = repo._get_tables_cache_path("public")
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Write cache with old version
            cache_data = {
                "version": "0.9",  # Old version
                "created_at": datetime.now(),
                "schema_name": "public",
                "tables": [],
            }
            with open(cache_path, "wb") as f:
                pickle.dump(cache_data, f)

            assert repo._is_cache_valid("public") is False

    def test_is_cache_valid_expired_ttl(self, tmp_path: Path):
        """Test that expired TTL invalidates cache."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            cache_path = repo._get_tables_cache_path("public")
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Write cache with old timestamp
            old_time = datetime.now() - timedelta(hours=SCHEMA_CACHE_TTL_HOURS + 1)
            cache_data = {
                "version": SCHEMA_CACHE_VERSION,
                "created_at": old_time,
                "schema_name": "public",
                "tables": [],
            }
            with open(cache_path, "wb") as f:
                pickle.dump(cache_data, f)

            assert repo._is_cache_valid("public") is False

    def test_is_cache_valid_schema_mismatch(self, tmp_path: Path):
        """Test that schema mismatch invalidates cache."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            cache_path = repo._get_tables_cache_path("public")
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Write cache with different schema
            cache_data = {
                "version": SCHEMA_CACHE_VERSION,
                "created_at": datetime.now(),
                "schema_name": "other_schema",  # Wrong schema
                "tables": [],
            }
            with open(cache_path, "wb") as f:
                pickle.dump(cache_data, f)

            assert repo._is_cache_valid("public") is False

    def test_is_cache_valid_success(self, tmp_path: Path):
        """Test that valid cache returns True."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            cache_path = repo._get_tables_cache_path("public")
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Write valid cache
            cache_data = {
                "version": SCHEMA_CACHE_VERSION,
                "created_at": datetime.now(),
                "schema_name": "public",
                "tables": [],
            }
            with open(cache_path, "wb") as f:
                pickle.dump(cache_data, f)

            assert repo._is_cache_valid("public") is True


class TestCacheOperations:
    """Test cache save and load operations."""

    def test_save_and_load_tables(self, tmp_path: Path):
        """Test round-trip save and load of tables."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")

            # Create sample tables
            tables = [
                TableInfo(
                    name="users",
                    schema="public",
                    columns=[{"name": "id", "type": "integer"}],
                    primary_keys=["id"],
                    foreign_keys=[],
                    indexes=[],
                    row_count=100,
                    size_bytes=1024,
                ),
                TableInfo(
                    name="orders",
                    schema="public",
                    columns=[{"name": "id", "type": "integer"}, {"name": "user_id", "type": "integer"}],
                    primary_keys=["id"],
                    foreign_keys=[{"column": "user_id", "ref_table": "users", "ref_column": "id"}],
                    indexes=[],
                    row_count=500,
                    size_bytes=2048,
                ),
            ]

            # Save to cache
            repo._save_tables_to_cache(tables, "public")

            # Load from cache
            loaded_tables = repo._load_tables_from_cache("public")

            assert loaded_tables is not None
            assert len(loaded_tables) == 2
            assert loaded_tables[0].name == "users"
            assert loaded_tables[1].name == "orders"
            assert loaded_tables[0].row_count == 100
            assert loaded_tables[1].foreign_keys[0]["ref_table"] == "users"

    def test_load_from_cache_returns_none_when_invalid(self, tmp_path: Path):
        """Test that load returns None for invalid cache."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")

            # No cache exists
            result = repo._load_tables_from_cache("public")
            assert result is None


class TestClearCache:
    """Test cache clearing functionality."""

    def test_clear_cache_removes_files(self, tmp_path: Path):
        """Test that clear_cache removes cache files."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")

            # Create some cache files
            cache_dir = repo._get_cache_dir()
            (cache_dir / "tables_cache_public.pkl").touch()
            (cache_dir / "tables_cache_analytics.pkl").touch()
            (cache_dir / "other_file.txt").touch()

            # Clear cache
            repo.clear_cache()

            # Cache files should be gone, other files remain
            assert not (cache_dir / "tables_cache_public.pkl").exists()
            assert not (cache_dir / "tables_cache_analytics.pkl").exists()
            assert (cache_dir / "other_file.txt").exists()

    def test_clear_cache_handles_empty_dir(self, tmp_path: Path):
        """Test that clear_cache handles empty directory gracefully."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            repo._get_cache_dir()  # Ensure directory exists

            # Should not raise
            repo.clear_cache()


class TestGetTablesHybrid:
    """Test the hybrid get_tables approach."""

    @pytest.mark.asyncio
    async def test_get_tables_uses_cache_when_valid(self, tmp_path: Path):
        """Test that get_tables returns cached data when valid."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            repo._initialized = True  # Skip initialization

            # Pre-populate cache
            tables = [
                TableInfo(
                    name="cached_table",
                    schema="public",
                    columns=[],
                    primary_keys=[],
                    foreign_keys=[],
                    indexes=[],
                )
            ]
            repo._save_tables_to_cache(tables, "public")

            # Mock bulk query to verify it's not called
            repo._get_tables_bulk = AsyncMock(return_value=[])

            result = await repo.get_tables("public")

            assert len(result) == 1
            assert result[0].name == "cached_table"
            repo._get_tables_bulk.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_tables_force_refresh_bypasses_cache(self, tmp_path: Path):
        """Test that force_refresh=True bypasses cache."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            repo._initialized = True

            # Pre-populate cache
            cached_tables = [
                TableInfo(
                    name="cached_table",
                    schema="public",
                    columns=[],
                    primary_keys=[],
                    foreign_keys=[],
                    indexes=[],
                )
            ]
            repo._save_tables_to_cache(cached_tables, "public")

            # Mock bulk query to return fresh data
            fresh_tables = [
                TableInfo(
                    name="fresh_table",
                    schema="public",
                    columns=[],
                    primary_keys=[],
                    foreign_keys=[],
                    indexes=[],
                )
            ]
            repo._get_tables_bulk = AsyncMock(return_value=fresh_tables)

            result = await repo.get_tables("public", force_refresh=True)

            assert len(result) == 1
            assert result[0].name == "fresh_table"
            repo._get_tables_bulk.assert_called_once_with("public")

    @pytest.mark.asyncio
    async def test_get_tables_queries_db_when_cache_invalid(self, tmp_path: Path):
        """Test that get_tables queries database when cache is invalid."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            repo._initialized = True

            # No cache exists
            fresh_tables = [
                TableInfo(
                    name="db_table",
                    schema="public",
                    columns=[],
                    primary_keys=[],
                    foreign_keys=[],
                    indexes=[],
                )
            ]
            repo._get_tables_bulk = AsyncMock(return_value=fresh_tables)

            result = await repo.get_tables("public")

            assert len(result) == 1
            assert result[0].name == "db_table"
            repo._get_tables_bulk.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tables_saves_to_cache_after_query(self, tmp_path: Path):
        """Test that get_tables saves results to cache after querying."""
        with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
            repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
            repo._initialized = True

            # Mock bulk query
            fresh_tables = [
                TableInfo(
                    name="new_table",
                    schema="public",
                    columns=[{"name": "id", "type": "int"}],
                    primary_keys=["id"],
                    foreign_keys=[],
                    indexes=[],
                )
            ]
            repo._get_tables_bulk = AsyncMock(return_value=fresh_tables)

            await repo.get_tables("public")

            # Verify cache was saved
            loaded = repo._load_tables_from_cache("public")
            assert loaded is not None
            assert len(loaded) == 1
            assert loaded[0].name == "new_table"


class TestSchemaRepositoryPortInterface:
    """Test that clear_cache() method is properly exposed in interface."""

    def test_clear_cache_method_exists(self):
        """Test that clear_cache method exists on repository."""
        from nlp2sql.ports.schema_repository import SchemaRepositoryPort

        # The method should exist (even if no-op by default)
        assert hasattr(SchemaRepositoryPort, "clear_cache")

    def test_postgres_repository_implements_clear_cache(self):
        """Test that PostgreSQLRepository implements clear_cache."""
        repo = PostgreSQLRepository("postgresql://user:pass@localhost/db")
        assert hasattr(repo, "clear_cache")
        assert callable(repo.clear_cache)

    def test_redshift_repository_implements_clear_cache(self):
        """Test that RedshiftRepository implements clear_cache."""
        from nlp2sql.adapters.redshift_adapter import RedshiftRepository

        repo = RedshiftRepository("redshift://user:pass@cluster/db")
        assert hasattr(repo, "clear_cache")
        assert callable(repo.clear_cache)
