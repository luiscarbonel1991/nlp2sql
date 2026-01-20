"""Tests for RepositoryFactory - centralized repository creation and management."""

from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nlp2sql.core.entities import DatabaseType
from nlp2sql.factories import RepositoryFactory
from nlp2sql.ports.schema_repository import SchemaRepositoryPort


class TestDetectDatabaseType:
    """Test database type detection from connection URLs."""

    def test_postgresql_url(self):
        """Test detection of PostgreSQL from postgresql:// URL."""
        url = "postgresql://user:pass@localhost:5432/testdb"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.POSTGRES

    def test_postgres_url_alias(self):
        """Test detection of PostgreSQL from postgres:// URL (common alias)."""
        url = "postgres://user:pass@localhost:5432/testdb"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.POSTGRES

    def test_postgresql_url_case_insensitive(self):
        """Test case-insensitive URL scheme detection."""
        urls = [
            "POSTGRESQL://user:pass@localhost/db",
            "PostgreSQL://user:pass@localhost/db",
            "postgresql://user:pass@localhost/db",
            "POSTGRES://user:pass@localhost/db",
            "Postgres://user:pass@localhost/db",
        ]
        for url in urls:
            assert RepositoryFactory.detect_database_type(url) == DatabaseType.POSTGRES

    def test_redshift_url(self):
        """Test detection of Redshift from redshift:// URL."""
        url = "redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/db"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.REDSHIFT

    def test_redshift_url_case_insensitive(self):
        """Test case-insensitive Redshift URL detection."""
        url = "REDSHIFT://user:pass@cluster.region.redshift.amazonaws.com:5439/db"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.REDSHIFT

    def test_mysql_url(self):
        """Test detection of MySQL from mysql:// URL."""
        url = "mysql://user:pass@localhost:3306/testdb"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.MYSQL

    def test_sqlite_url(self):
        """Test detection of SQLite from sqlite:// URL."""
        url = "sqlite:///path/to/database.db"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.SQLITE

    def test_mssql_url(self):
        """Test detection of MSSQL from mssql:// URL."""
        url = "mssql://user:pass@localhost:1433/testdb"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.MSSQL

    def test_oracle_url(self):
        """Test detection of Oracle from oracle:// URL."""
        url = "oracle://user:pass@localhost:1521/testdb"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.ORACLE

    def test_unknown_url_defaults_to_postgres(self):
        """Test that unknown URLs default to PostgreSQL for compatibility."""
        url = "unknown://user:pass@localhost/db"
        assert RepositoryFactory.detect_database_type(url) == DatabaseType.POSTGRES


class TestRegistration:
    """Test repository registration and unregistration."""

    def setup_method(self):
        """Store original registry state before each test."""
        # Force registration of defaults
        RepositoryFactory._register_default_repositories()
        self._original_registry = RepositoryFactory._registry.copy()

    def teardown_method(self):
        """Restore original registry state after each test."""
        RepositoryFactory._registry = self._original_registry

    def test_register_custom_repository(self):
        """Test registering a custom repository type."""

        class MockRepository(SchemaRepositoryPort):
            """Mock repository for testing."""

            pass

        RepositoryFactory.register(DatabaseType.MYSQL, MockRepository)
        assert RepositoryFactory.is_registered(DatabaseType.MYSQL)
        assert DatabaseType.MYSQL in RepositoryFactory.get_registered_types()

    def test_unregister_repository(self):
        """Test unregistering a repository type."""

        # First register MySQL
        class MockRepository(SchemaRepositoryPort):
            pass

        RepositoryFactory.register(DatabaseType.MYSQL, MockRepository)
        assert RepositoryFactory.is_registered(DatabaseType.MYSQL)

        # Now unregister
        result = RepositoryFactory.unregister(DatabaseType.MYSQL)
        assert result is True
        assert not RepositoryFactory.is_registered(DatabaseType.MYSQL)

    def test_unregister_nonexistent_returns_false(self):
        """Test unregistering a type that isn't registered returns False."""
        # Ensure MSSQL is not registered
        if DatabaseType.MSSQL in RepositoryFactory._registry:
            RepositoryFactory.unregister(DatabaseType.MSSQL)

        result = RepositoryFactory.unregister(DatabaseType.MSSQL)
        assert result is False

    def test_get_registered_types_includes_defaults(self):
        """Test that default types (Postgres, Redshift) are registered."""
        registered = RepositoryFactory.get_registered_types()
        assert DatabaseType.POSTGRES in registered
        assert DatabaseType.REDSHIFT in registered

    def test_is_registered_for_postgres(self):
        """Test is_registered returns True for Postgres."""
        assert RepositoryFactory.is_registered(DatabaseType.POSTGRES)

    def test_is_registered_for_redshift(self):
        """Test is_registered returns True for Redshift."""
        assert RepositoryFactory.is_registered(DatabaseType.REDSHIFT)

    def test_is_registered_for_unregistered_type(self):
        """Test is_registered returns False for unregistered types."""
        # MSSQL is not registered by default
        if DatabaseType.MSSQL in RepositoryFactory._registry:
            RepositoryFactory.unregister(DatabaseType.MSSQL)
        assert not RepositoryFactory.is_registered(DatabaseType.MSSQL)


class TestCreate:
    """Test repository creation."""

    def test_create_postgres_repository(self):
        """Test creating a PostgreSQL repository."""
        repo = RepositoryFactory.create(
            "postgresql://user:pass@localhost:5432/testdb",
            schema_name="public",
        )
        # Check it's the right type
        from nlp2sql.adapters.postgres_repository import PostgreSQLRepository

        assert isinstance(repo, PostgreSQLRepository)
        assert repo.schema_name == "public"

    def test_create_redshift_repository(self):
        """Test creating a Redshift repository."""
        repo = RepositoryFactory.create(
            "redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/db",
            schema_name="analytics",
        )
        from nlp2sql.adapters.redshift_adapter import RedshiftRepository

        assert isinstance(repo, RedshiftRepository)
        assert repo.schema_name == "analytics"

    def test_create_with_auto_detect_postgres(self):
        """Test create auto-detects Postgres from URL."""
        repo = RepositoryFactory.create("postgresql://user:pass@localhost/db")
        from nlp2sql.adapters.postgres_repository import PostgreSQLRepository

        assert isinstance(repo, PostgreSQLRepository)

    def test_create_with_auto_detect_redshift(self):
        """Test create auto-detects Redshift from URL."""
        repo = RepositoryFactory.create("redshift://user:pass@cluster/db")
        from nlp2sql.adapters.redshift_adapter import RedshiftRepository

        assert isinstance(repo, RedshiftRepository)

    def test_create_with_explicit_type_overrides_detection(self):
        """Test that explicit database_type overrides URL detection."""
        # URL says postgres, but we explicitly say redshift
        repo = RepositoryFactory.create(
            "postgresql://user:pass@localhost/db",
            database_type=DatabaseType.REDSHIFT,
        )
        from nlp2sql.adapters.redshift_adapter import RedshiftRepository

        assert isinstance(repo, RedshiftRepository)

    def test_create_with_custom_schema_name(self):
        """Test create passes schema_name correctly."""
        repo = RepositoryFactory.create(
            "postgresql://user:pass@localhost/db",
            schema_name="custom_schema",
        )
        assert repo.schema_name == "custom_schema"

    def test_create_unsupported_type_raises_error(self):
        """Test creating an unsupported type raises NotImplementedError."""
        # Remove MySQL if it was registered
        if DatabaseType.MYSQL in RepositoryFactory._registry:
            RepositoryFactory.unregister(DatabaseType.MYSQL)

        with pytest.raises(NotImplementedError) as exc_info:
            RepositoryFactory.create(
                "mysql://user:pass@localhost/db",
                database_type=DatabaseType.MYSQL,
            )

        assert "mysql" in str(exc_info.value).lower()
        assert "not supported" in str(exc_info.value).lower()


class TestCreateAndInitialize:
    """Test async repository creation and initialization."""

    @pytest.mark.asyncio
    async def test_create_and_initialize_calls_initialize(self):
        """Test create_and_initialize calls the repository's initialize method."""
        # Mock the repository class
        mock_repo = MagicMock(spec=SchemaRepositoryPort)
        mock_repo.initialize = AsyncMock()

        # Mock the create method to return our mock
        with patch.object(RepositoryFactory, "create", return_value=mock_repo):
            repo = await RepositoryFactory.create_and_initialize(
                "postgresql://user:pass@localhost/db",
                schema_name="test_schema",
            )

            # Verify initialize was called
            mock_repo.initialize.assert_called_once()
            assert repo == mock_repo


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_import_detect_database_type_from_cli(self):
        """Test that detect_database_type can still be imported from cli."""
        from nlp2sql.cli import detect_database_type

        # Test it works
        result = detect_database_type("postgresql://localhost/db")
        assert result == DatabaseType.POSTGRES

    def test_cli_detect_database_type_supports_postgres_alias(self):
        """Test CLI's detect_database_type supports postgres:// alias."""
        from nlp2sql.cli import detect_database_type

        result = detect_database_type("postgres://localhost/db")
        assert result == DatabaseType.POSTGRES

    def test_import_postgresql_repository_from_nlp2sql(self):
        """Test PostgreSQLRepository can still be imported from nlp2sql."""
        from nlp2sql import PostgreSQLRepository

        assert PostgreSQLRepository is not None

    def test_import_redshift_repository_from_nlp2sql(self):
        """Test RedshiftRepository can still be imported from nlp2sql."""
        from nlp2sql import RedshiftRepository

        assert RedshiftRepository is not None

    def test_import_repository_factory_from_nlp2sql(self):
        """Test RepositoryFactory can be imported from nlp2sql."""
        from nlp2sql import RepositoryFactory

        assert RepositoryFactory is not None

    def test_import_create_repository_from_nlp2sql(self):
        """Test create_repository can be imported from nlp2sql."""
        from nlp2sql import create_repository

        assert create_repository is not None

    def test_import_from_factories_module(self):
        """Test direct import from factories module."""
        from nlp2sql.factories import RepositoryFactory

        assert RepositoryFactory is not None


class TestDefaultRepositoryRegistration:
    """Test default repository registration behavior."""

    def test_defaults_registered_lazily(self):
        """Test that defaults are registered when needed."""
        # After any factory method, defaults should be registered
        RepositoryFactory.get_registered_types()
        assert RepositoryFactory._defaults_registered is True

    def test_postgres_registered_by_default(self):
        """Test PostgreSQL is registered by default."""
        types = RepositoryFactory.get_registered_types()
        assert DatabaseType.POSTGRES in types

    def test_redshift_registered_by_default(self):
        """Test Redshift is registered by default."""
        types = RepositoryFactory.get_registered_types()
        assert DatabaseType.REDSHIFT in types
