"""AI Provider Port - Interface for all AI providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class AIProviderType(Enum):
    """Supported AI providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    GEMINI = "gemini"
    AZURE_OPENAI = "azure_openai"


@dataclass
class QueryContext:
    """Context for query generation."""

    question: str
    database_type: str  # postgres, mysql, etc.
    schema_context: str
    examples: List[Dict[str, str]]
    max_tokens: int = 4096
    temperature: float = 0.1
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class QueryResponse:
    """Response from AI provider."""

    sql: str
    explanation: str
    confidence: float
    tokens_used: int
    provider: str
    metadata: Optional[Dict[str, Any]] = None


class AIProviderPort(ABC):
    """Abstract interface for AI providers."""

    @abstractmethod
    async def generate_query(self, context: QueryContext) -> QueryResponse:
        """Generate SQL query from natural language."""
        pass

    @abstractmethod
    async def validate_query(self, sql: str, schema_context: str) -> Dict[str, Any]:
        """Validate generated SQL query."""
        pass

    @abstractmethod
    def get_token_count(self, text: str) -> int:
        """Count tokens for the provider's model."""
        pass

    @abstractmethod
    def get_max_context_size(self) -> int:
        """Get maximum context size for the provider."""
        pass

    @property
    @abstractmethod
    def provider_type(self) -> AIProviderType:
        """Get the provider type."""
        pass
