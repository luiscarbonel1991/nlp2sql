"""Configuration settings for nlp2sql."""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class LogLevel(str, Enum):
    """Log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Application settings."""

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General settings
    app_name: str = "nlp2sql"
    version: str = "0.2.0rc5"
    debug: bool = Field(default=False, validation_alias="NLP2SQL_DEBUG")
    log_level: LogLevel = Field(default=LogLevel.INFO, validation_alias="NLP2SQL_LOG_LEVEL")

    # AI Provider settings
    openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    google_api_key: Optional[str] = Field(default=None)
    azure_openai_api_key: Optional[str] = Field(default=None)
    azure_openai_endpoint: Optional[str] = Field(default=None)
    aws_access_key_id: Optional[str] = Field(default=None)
    aws_secret_access_key: Optional[str] = Field(default=None)
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_DEFAULT_REGION")

    # Database settings
    default_database_type: str = Field(default="postgres", validation_alias="NLP2SQL_DEFAULT_DB_TYPE")
    database_url: Optional[str] = Field(default=None)
    database_pool_size: int = Field(default=10, validation_alias="NLP2SQL_DB_POOL_SIZE")
    database_max_overflow: int = Field(default=20, validation_alias="NLP2SQL_DB_MAX_OVERFLOW")

    # Cache settings
    cache_enabled: bool = Field(default=True, validation_alias="NLP2SQL_CACHE_ENABLED")
    cache_ttl_seconds: int = Field(default=3600, validation_alias="NLP2SQL_CACHE_TTL")
    redis_url: Optional[str] = Field(default=None)

    # Schema settings
    max_schema_tokens: int = Field(default=8000, validation_alias="NLP2SQL_MAX_SCHEMA_TOKENS")
    schema_cache_enabled: bool = Field(default=True, validation_alias="NLP2SQL_SCHEMA_CACHE_ENABLED")
    schema_refresh_interval_hours: int = Field(default=24, validation_alias="NLP2SQL_SCHEMA_REFRESH_HOURS")

    # Query generation settings
    default_temperature: float = Field(default=0.1, validation_alias="NLP2SQL_TEMPERATURE")
    default_max_tokens: int = Field(default=2000, validation_alias="NLP2SQL_MAX_TOKENS")
    retry_attempts: int = Field(default=3, validation_alias="NLP2SQL_RETRY_ATTEMPTS")
    retry_delay_seconds: float = Field(default=1.0, validation_alias="NLP2SQL_RETRY_DELAY")

    # Embedding settings
    # Note: embedding_provider is None by default because sentence-transformers is optional.
    # Set to "local" (requires nlp2sql[embeddings-local]) or "openai" to enable embeddings.
    embedding_provider: Optional[str] = Field(default=None, validation_alias="NLP2SQL_EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", validation_alias="NLP2SQL_EMBEDDING_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", validation_alias="NLP2SQL_OPENAI_EMBEDDING_MODEL"
    )
    embedding_cache_enabled: bool = Field(default=True, validation_alias="NLP2SQL_EMBEDDING_CACHE")

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, validation_alias="NLP2SQL_RATE_LIMIT_ENABLED")
    rate_limit_requests_per_minute: int = Field(default=60, validation_alias="NLP2SQL_RATE_LIMIT_RPM")

    @field_validator("openai_api_key", "anthropic_api_key", "google_api_key", mode="before")
    @classmethod
    def validate_api_keys(cls, v: Optional[str]) -> Optional[str]:
        """Validate API keys are not empty strings."""
        if v == "":
            return None
        return v

    @field_validator("debug", mode="before")
    @classmethod
    def validate_debug(cls, v: Any) -> bool:
        """Validate debug is a boolean, ignore invalid values."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in ("true", "1", "yes", "on"):
                return True
            if v_lower in ("false", "0", "no", "off", ""):
                return False
        # If invalid value, return default
        return False

    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for specific provider."""
        configs = {
            "openai": {
                "api_key": self.openai_api_key,
                "model": "gpt-4-turbo-preview",
                "max_tokens": self.default_max_tokens,
                "temperature": self.default_temperature,
            },
            "anthropic": {
                "api_key": self.anthropic_api_key,
                "model": "claude-3-opus-20240229",
                "max_tokens": self.default_max_tokens,
                "temperature": self.default_temperature,
            },
            "gemini": {
                "api_key": self.google_api_key,
                "model": "gemini-pro",
                "max_tokens": self.default_max_tokens,
                "temperature": self.default_temperature,
            },
            "bedrock": {
                "access_key_id": self.aws_access_key_id,
                "secret_access_key": self.aws_secret_access_key,
                "region": self.aws_region,
                "model": "anthropic.claude-v2",
                "max_tokens": self.default_max_tokens,
                "temperature": self.default_temperature,
            },
            "azure_openai": {
                "api_key": self.azure_openai_api_key,
                "endpoint": self.azure_openai_endpoint,
                "model": "gpt-4",
                "max_tokens": self.default_max_tokens,
                "temperature": self.default_temperature,
            },
        }
        return configs.get(provider, {})


# Global settings instance
settings = Settings()
