"""Configuration settings for nlp2sql."""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import Field, validator
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

    # General settings
    app_name: str = "nlp2sql"
    version: str = "0.2.0rc2"
    debug: bool = Field(default=False, env="NLP2SQL_DEBUG")
    log_level: LogLevel = Field(default=LogLevel.INFO, env="NLP2SQL_LOG_LEVEL")

    # AI Provider settings
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    google_api_key: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")
    azure_openai_api_key: Optional[str] = Field(default=None, env="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: Optional[str] = Field(default=None, env="AZURE_OPENAI_ENDPOINT")
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-east-1", env="AWS_DEFAULT_REGION")

    # Database settings
    default_database_type: str = Field(default="postgres", env="NLP2SQL_DEFAULT_DB_TYPE")
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")
    database_pool_size: int = Field(default=10, env="NLP2SQL_DB_POOL_SIZE")
    database_max_overflow: int = Field(default=20, env="NLP2SQL_DB_MAX_OVERFLOW")

    # Cache settings
    cache_enabled: bool = Field(default=True, env="NLP2SQL_CACHE_ENABLED")
    cache_ttl_seconds: int = Field(default=3600, env="NLP2SQL_CACHE_TTL")
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")

    # Schema settings
    max_schema_tokens: int = Field(default=8000, env="NLP2SQL_MAX_SCHEMA_TOKENS")
    schema_cache_enabled: bool = Field(default=True, env="NLP2SQL_SCHEMA_CACHE_ENABLED")
    schema_refresh_interval_hours: int = Field(default=24, env="NLP2SQL_SCHEMA_REFRESH_HOURS")

    # Query generation settings
    default_temperature: float = Field(default=0.1, env="NLP2SQL_TEMPERATURE")
    default_max_tokens: int = Field(default=2000, env="NLP2SQL_MAX_TOKENS")
    retry_attempts: int = Field(default=3, env="NLP2SQL_RETRY_ATTEMPTS")
    retry_delay_seconds: float = Field(default=1.0, env="NLP2SQL_RETRY_DELAY")

    # Embedding settings
    embedding_model: str = Field(default="all-MiniLM-L6-v2", env="NLP2SQL_EMBEDDING_MODEL")
    embedding_cache_enabled: bool = Field(default=True, env="NLP2SQL_EMBEDDING_CACHE")

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, env="NLP2SQL_RATE_LIMIT_ENABLED")
    rate_limit_requests_per_minute: int = Field(default=60, env="NLP2SQL_RATE_LIMIT_RPM")

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator("openai_api_key", "anthropic_api_key", "google_api_key", pre=True)
    def validate_api_keys(cls, v: Optional[str]) -> Optional[str]:
        """Validate API keys are not empty strings."""
        if v == "":
            return None
        return v

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
