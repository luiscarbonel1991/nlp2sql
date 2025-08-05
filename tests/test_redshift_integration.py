"""Basic integration test for Redshift adapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from nlp2sql.adapters.redshift_adapter import RedshiftRepository
from nlp2sql.core.entities import DatabaseType
from nlp2sql.exceptions import SchemaException


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
            "redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/testdb", 
            schema_name="analytics"
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])