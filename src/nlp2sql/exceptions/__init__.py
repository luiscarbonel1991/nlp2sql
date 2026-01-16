"""Custom exceptions for nlp2sql library."""

from typing import Any, Dict, Optional


class NLP2SQLException(Exception):
    """Base exception for nlp2sql library."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class SchemaException(NLP2SQLException):
    """Exception related to schema operations."""

    pass


class ProviderException(NLP2SQLException):
    """Exception related to AI provider operations."""

    pass


class TokenLimitException(ProviderException):
    """Exception when token limit is exceeded."""

    def __init__(self, message: str, tokens_used: int, max_tokens: int):
        super().__init__(message, {"tokens_used": tokens_used, "max_tokens": max_tokens})
        self.tokens_used = tokens_used
        self.max_tokens = max_tokens


class QueryGenerationException(NLP2SQLException):
    """Exception during query generation."""

    pass


class OptimizationException(NLP2SQLException):
    """Exception during query optimization."""

    pass


class CacheException(NLP2SQLException):
    """Exception related to cache operations."""

    pass


class ValidationException(NLP2SQLException):
    """Exception during validation."""

    pass


class ConfigurationException(NLP2SQLException):
    """Exception related to configuration."""

    pass


class SecurityException(NLP2SQLException):
    """Exception for security-related violations (e.g., unsafe SQL queries)."""

    pass
