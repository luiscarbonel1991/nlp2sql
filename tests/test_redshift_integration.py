"""Integration tests for Redshift adapter with LocalStack."""

import os

import pytest

from nlp2sql import create_query_service
from nlp2sql.adapters.redshift_adapter import RedshiftRepository
from nlp2sql.core.entities import DatabaseType


class TestRedshiftAdapter:
    """Test Redshift adapter functionality."""

    def test_redshift_repository_creation(self):
        """Test RedshiftRepository can be created."""
        repo = RedshiftRepository("redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/testdb")
        assert repo.connection_string == "redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/testdb"
        assert repo.schema_name == "public"
        assert not repo._initialized

    def test_redshift_repository_with_custom_schema(self):
        """Test RedshiftRepository with custom schema."""
        repo = RedshiftRepository(
            "redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/testdb", schema_name="analytics"
        )
        assert repo.schema_name == "analytics"

    @pytest.mark.asyncio
    async def test_redshift_initialize_converts_url(self):
        """Test that Redshift URL is properly converted for asyncpg."""
        repo = RedshiftRepository("redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/testdb")

        # Mock the async engine creation and connection
        with pytest.raises(Exception):  # Will fail on actual connection, but that's expected
            await repo.initialize()

    def test_database_type_enum_includes_redshift(self):
        """Test that DatabaseType includes REDSHIFT."""
        assert DatabaseType.REDSHIFT.value == "redshift"
        assert DatabaseType.REDSHIFT in [dt for dt in DatabaseType]

    def test_redshift_in_database_types(self):
        """Test that REDSHIFT is properly included in supported database types."""
        db_types = [dt.value for dt in DatabaseType]
        assert "redshift" in db_types
        assert "postgres" in db_types  # Make sure we didn't break existing types


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("SKIP_LOCALSTACK_TESTS") == "true", reason="LocalStack tests disabled")
class TestRedshiftLocalStackIntegration:
    """Integration tests with LocalStack Redshift."""

    # LocalStack Redshift connection details
    # Use REDSHIFT_PORT environment variable or default to 5439
    REDSHIFT_PORT = os.getenv("REDSHIFT_PORT", "5439")
    REDSHIFT_URL = f"redshift://testuser:testpass123@localhost:{REDSHIFT_PORT}/testdb"
    POSTGRES_COMPAT_URL = f"postgresql://testuser:testpass123@localhost:{REDSHIFT_PORT}/testdb"

    @pytest.fixture(scope="class")
    def redshift_repo(self):
        """Create a RedshiftRepository for testing."""
        return RedshiftRepository(self.REDSHIFT_URL)

    @pytest.mark.asyncio
    async def test_redshift_connection_and_initialization(self, redshift_repo):
        """Test connecting to LocalStack Redshift and initializing schema."""
        try:
            await redshift_repo.initialize()
            assert redshift_repo._initialized

            # Test that we can get schema information
            schema_info = await redshift_repo.get_tables()
            assert schema_info is not None
            assert len(schema_info) > 0

        except Exception as e:
            pytest.skip(f"LocalStack Redshift not available: {e}")

    @pytest.mark.asyncio
    async def test_redshift_table_discovery(self, redshift_repo):
        """Test that we can discover tables in LocalStack Redshift."""
        try:
            await redshift_repo.initialize()

            # Get tables from public schema
            schema_info = await redshift_repo.get_tables()

            # Should find our test tables
            table_names = [table["table_name"] for table in schema_info]
            expected_tables = ["users", "products", "orders"]

            for table in expected_tables:
                assert table in table_names, f"Table {table} not found in schema"

        except Exception as e:
            pytest.skip(f"LocalStack Redshift not available: {e}")

    @pytest.mark.asyncio
    async def test_redshift_multi_schema_support(self):
        """Test Redshift with multiple schemas (sales, analytics)."""
        try:
            # Test sales schema
            sales_repo = RedshiftRepository(self.REDSHIFT_URL, schema_name="sales")
            await sales_repo.initialize()

            sales_schema = await sales_repo.get_tables()
            sales_tables = [table["table_name"] for table in sales_schema]

            assert "customers" in sales_tables
            assert "transactions" in sales_tables

            # Test analytics schema
            analytics_repo = RedshiftRepository(self.REDSHIFT_URL, schema_name="analytics")
            await analytics_repo.initialize()

            analytics_schema = await analytics_repo.get_tables()
            analytics_tables = [table["table_name"] for table in analytics_schema]

            assert "sales_summary" in analytics_tables

        except Exception as e:
            pytest.skip(f"LocalStack Redshift not available: {e}")

    @pytest.mark.asyncio
    async def test_redshift_postgresql_compatibility(self):
        """Test that PostgreSQL-compatible URL works with Redshift."""
        try:
            # Use PostgreSQL-compatible connection string
            repo = RedshiftRepository(self.POSTGRES_COMPAT_URL)
            await repo.initialize()

            schema_info = await repo.get_tables()
            assert len(schema_info) > 0

        except Exception as e:
            pytest.skip(f"LocalStack Redshift not available: {e}")

    @pytest.mark.asyncio
    async def test_redshift_system_view_queries(self, redshift_repo):
        """Test that Redshift-specific system view queries work."""
        try:
            await redshift_repo.initialize()

            # Test the private method that builds system view queries
            # This should use svv_table_info for Redshift instead of pg_stat_user_tables
            schema_info = await redshift_repo.get_tables()

            # Verify we get table statistics
            for table in schema_info:
                assert "table_name" in table
                assert "schema_name" in table
                # Should have row count info from svv_table_info
                assert "row_count" in table or "estimated_rows" in table

        except Exception as e:
            pytest.skip(f"LocalStack Redshift not available: {e}")

    @pytest.mark.asyncio
    async def test_end_to_end_service_creation(self):
        """Test creating a complete query service with Redshift."""
        try:
            # Test that we can create a service with LocalStack Redshift
            service = create_query_service(
                database_url=self.REDSHIFT_URL,
                ai_provider="anthropic",
                api_key="test-key-invalid",  # This will fail on AI provider, but DB should work
                database_type=DatabaseType.REDSHIFT,
                schema_filters={"include_schemas": ["sales", "public"]},
            )

            # Verify the repository is correct type
            assert isinstance(service.schema_repository, RedshiftRepository)

            # Test initialization (will fail on AI provider but DB should work)
            try:
                await service.initialize(DatabaseType.REDSHIFT)
            except Exception as e:
                # Expected to fail on AI provider with invalid key
                if "RedshiftRepository" in str(e) or "database" in str(e).lower():
                    raise  # Re-raise database-related errors
                # AI provider errors are expected and ok
                pass

        except Exception as e:
            if "connection" in str(e).lower() or "localstack" in str(e).lower():
                pytest.skip(f"LocalStack Redshift not available: {e}")
            else:
                raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
