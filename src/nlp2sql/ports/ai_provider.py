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
    examples: List[Dict[str, Any]]
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


def validation_unavailable(reason: str) -> dict[str, Any]:
    """The ``validate_query`` answer for a review that could not be done.

    It is never valid: a provider that could not be asked, or whose answer could not be
    read, has not approved the query.
    """
    return {
        "is_valid": False,
        "errors": [f"LLM validation unavailable: {reason}"],
        "warnings": [],
        "llm_validation_error": reason,
    }


def checked_validation(answer: object) -> dict[str, Any]:
    """``answer`` held to the ``validate_query`` contract.

    An answer without a boolean ``is_valid``, or one that reports its own failure, becomes
    ``validation_unavailable``. Two older names are still read: ``issues`` for ``errors``,
    and ``error`` for ``llm_validation_error``.
    """
    if not isinstance(answer, dict):
        return validation_unavailable("the provider did not answer with a JSON object")

    failure = answer.get("llm_validation_error") or answer.get("error")
    if not failure and not isinstance(answer.get("is_valid"), bool):
        failure = "the provider's answer has no boolean is_valid"
    if failure:
        unavailable = validation_unavailable(str(failure))
        if "_tokens_used" in answer:
            unavailable["_tokens_used"] = answer["_tokens_used"]
        return unavailable

    checked = {key: value for key, value in answer.items() if key not in ("issues", "error")}
    checked["errors"] = _messages(answer.get("errors")) + _messages(answer.get("issues"))
    checked["warnings"] = _messages(answer.get("warnings"))
    return checked


def _messages(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


class AIProviderPort(ABC):
    """Abstract interface for AI providers."""

    @abstractmethod
    async def generate_query(self, context: QueryContext) -> QueryResponse:
        """Generate SQL query from natural language."""
        pass

    @abstractmethod
    async def validate_query(self, sql: str, schema_context: str) -> Dict[str, Any]:
        """Ask the model to review a SQL query against the schema.

        Returns a dict with:

        - ``is_valid`` (bool): True only when the model reviewed the query and approved it.
        - ``errors`` (list of str): what the model found wrong.
        - ``warnings`` (list of str).
        - ``llm_validation_error`` (str): only when the review could not be done (the call
          failed, or the answer could not be read). ``is_valid`` is then False. Build that
          answer with ``validation_unavailable``.
        - ``_tokens_used`` (int, optional): tokens the review spent.

        Other keys are passed on to the caller. A provider must never report a query as
        valid because the review failed. Callers hold every answer to this contract with
        ``checked_validation``.
        """
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
