"""Basic unit tests for nlp2sql core functionality."""

from unittest.mock import patch

from nlp2sql.core.entities import DatabaseType
from nlp2sql.core.provider_config import ProviderConfig
from nlp2sql.ports.ai_provider import (
    AIProviderType,
    QueryContext,
    QueryResponse,
)
from nlp2sql.utils.helpers import first_not_none


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


class TestProviderConfig:
    """Test ProviderConfig dataclass."""

    def test_required_provider(self):
        """Provider field is required."""
        import pytest

        with pytest.raises(TypeError):
            ProviderConfig()

    def test_valid_providers(self):
        """All supported providers are accepted."""
        for p in ("openai", "anthropic", "gemini"):
            config = ProviderConfig(provider=p)
            assert config.provider == p

    def test_invalid_provider_raises(self):
        """Unsupported provider raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Unsupported provider"):
            ProviderConfig(provider="invalid_provider")

    def test_optional_fields_default_none(self):
        """Optional fields default to None."""
        config = ProviderConfig(provider="openai")
        assert config.model is None
        assert config.temperature is None
        assert config.max_tokens is None
        assert config.api_key is None

    def test_config_with_values(self):
        """Fields are stored correctly."""
        config = ProviderConfig(
            provider="openai",
            model="gpt-4o",
            temperature=0.5,
            max_tokens=4000,
            api_key="sk-test",
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.temperature == 0.5
        assert config.max_tokens == 4000
        assert config.api_key == "sk-test"

    def test_resolved_model_explicit(self):
        """resolved_model returns explicit model when set."""
        config = ProviderConfig(provider="openai", model="gpt-4o")
        assert config.resolved_model == "gpt-4o"

    def test_resolved_model_default(self):
        """resolved_model returns provider default when model is None."""
        config = ProviderConfig(provider="openai")
        assert config.resolved_model == "gpt-4o-mini"

        config = ProviderConfig(provider="anthropic")
        assert config.resolved_model == "claude-sonnet-4-20250514"

        config = ProviderConfig(provider="gemini")
        assert config.resolved_model == "gemini-2.0-flash"

    def test_temperature_zero_is_preserved(self):
        """0.0 is a valid temperature, must not be treated as None."""
        config = ProviderConfig(provider="openai", temperature=0.0)
        assert config.temperature == 0.0
        assert config.temperature is not None

    def test_max_tokens_zero_is_preserved(self):
        """0 is an edge case that should be preserved."""
        config = ProviderConfig(provider="openai", max_tokens=0)
        assert config.max_tokens == 0
        assert config.max_tokens is not None

    def test_frozen_immutable(self):
        """ProviderConfig instances are immutable."""
        import pytest

        config = ProviderConfig(provider="openai", model="gpt-4o")
        with pytest.raises(AttributeError):
            config.model = "other"


class TestFirstNotNone:
    """Test the first_not_none helper."""

    def test_returns_first_non_none(self):
        assert first_not_none(None, None, 42) == 42

    def test_preserves_zero(self):
        assert first_not_none(0, 100) == 0

    def test_preserves_zero_float(self):
        assert first_not_none(0.0, 0.5) == 0.0

    def test_preserves_empty_string(self):
        assert first_not_none("", "fallback") == ""

    def test_all_none_returns_none(self):
        assert first_not_none(None, None, None) is None

    def test_first_value_wins(self):
        assert first_not_none("a", "b", "c") == "a"


class TestAdapterConfigResolution:
    """Test that adapters resolve config correctly via individual kwargs."""

    def test_openai_with_all_kwargs(self):
        """OpenAI adapter accepts individual kwargs."""
        from nlp2sql.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="sk-test", model="gpt-4o", temperature=0.5)
        assert adapter.model == "gpt-4o"
        assert adapter.temperature == 0.5
        assert adapter.api_key == "sk-test"

    def test_openai_defaults(self):
        """OpenAI adapter uses defaults when no kwargs provided."""
        from nlp2sql.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="sk-test")
        assert adapter.model == "gpt-4o-mini"
        assert adapter.temperature == 0.1
        assert adapter.max_tokens == 2000

    def test_openai_temperature_zero_preserved(self):
        """temperature=0.0 must not fall through to default."""
        from nlp2sql.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="sk-test", temperature=0.0)
        assert adapter.temperature == 0.0

    def test_anthropic_with_model(self):
        """Anthropic adapter accepts model kwarg."""
        from nlp2sql.adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="sk-test", model="claude-opus-4-20250514")
        assert adapter.model == "claude-opus-4-20250514"

    def test_anthropic_defaults(self):
        """Anthropic adapter uses correct defaults."""
        from nlp2sql.adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="sk-test")
        assert adapter.model == "claude-sonnet-4-20250514"

    @patch("nlp2sql.adapters.gemini_adapter.genai")
    def test_gemini_with_model(self, mock_genai):
        """Gemini adapter accepts model kwarg."""
        from nlp2sql.adapters.gemini_adapter import GeminiAdapter

        adapter = GeminiAdapter(api_key="test-key", model="gemini-1.5-pro")
        assert adapter.model_name == "gemini-1.5-pro"

    @patch("nlp2sql.adapters.gemini_adapter.genai")
    def test_gemini_defaults(self, mock_genai):
        """Gemini adapter uses correct defaults."""
        from nlp2sql.adapters.gemini_adapter import GeminiAdapter

        adapter = GeminiAdapter(api_key="test-key")
        assert adapter.model_name == "gemini-2.0-flash"


class TestSettingsBuildProviderConfig:
    """Test settings.build_provider_config() integration."""

    def test_builds_openai_config(self):
        from nlp2sql.config.settings import settings

        config = settings.build_provider_config("openai")
        assert isinstance(config, ProviderConfig)
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.1
        assert config.max_tokens == 2000

    def test_builds_anthropic_config(self):
        from nlp2sql.config.settings import settings

        config = settings.build_provider_config("anthropic")
        assert config.model == "claude-sonnet-4-20250514"

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError from ProviderConfig validation."""
        import pytest

        from nlp2sql.config.settings import settings

        with pytest.raises(ValueError, match="Unsupported provider"):
            settings.build_provider_config("unknown_provider")
