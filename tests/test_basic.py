"""Basic unit tests for nlp2sql core functionality."""

from nlp2sql.core.entities import DatabaseType
from nlp2sql.ports.ai_provider import (
    AIProviderType,
    QueryContext,
    QueryResponse,
)


class TestBasicFunctionality:
    """Test basic functionality of the library."""

    def test_database_types(self):
        """Test database type enumeration."""
        assert DatabaseType.POSTGRES.value == "postgres"
        assert DatabaseType.MYSQL.value == "mysql"
        assert DatabaseType.SQLITE.value == "sqlite"
        assert DatabaseType.REDSHIFT.value == "redshift"

    def test_ai_provider_types(self):
        """Test AI provider type enumeration."""
        assert AIProviderType.OPENAI.value == "openai"
        assert AIProviderType.ANTHROPIC.value == "anthropic"
        assert AIProviderType.GEMINI.value == "gemini"

    def test_query_context_creation(self):
        """Test query context creation."""
        context = QueryContext(
            question="Show me all users",
            database_type="postgres",
            schema_context="CREATE TABLE users (id INT, name VARCHAR(255))",
            examples=[],
            max_tokens=1000,
        )

        assert context.question == "Show me all users"
        assert context.database_type == "postgres"
        assert context.max_tokens == 1000

    def test_query_response_creation(self):
        """Test query response creation."""
        response = QueryResponse(
            sql="SELECT * FROM users",
            explanation="This query selects all users",
            confidence=0.95,
            tokens_used=150,
            provider="openai",
        )

        assert response.sql == "SELECT * FROM users"
        assert response.confidence == 0.95
        assert response.provider == "openai"
