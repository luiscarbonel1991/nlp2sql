"""Query result — typed wrapper over the raw dict returned by generate_sql."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class QueryResult:
    """Immutable result of a natural language to SQL query.

    Provides typed access to the generated SQL and metadata instead of
    requiring dict key access.
    """

    sql: str
    confidence: float
    explanation: Optional[str] = None
    is_valid: bool = False
    provider: str = ""
    database_type: str = ""
    tokens_used: int = 0
    generation_time_ms: float = 0.0
    examples_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryResult":
        """Build a QueryResult from the raw dict returned by generate_sql."""
        validation = data.get("validation", {})
        return cls(
            sql=data.get("sql", ""),
            confidence=data.get("confidence", 0.0),
            explanation=data.get("explanation"),
            is_valid=validation.get("is_valid", False) if isinstance(validation, dict) else False,
            provider=data.get("provider", ""),
            database_type=data.get("database_type", ""),
            tokens_used=data.get("tokens_used", 0),
            generation_time_ms=data.get("generation_time_ms", 0.0),
            examples_used=data.get("examples_used", 0),
            metadata=data.get("metadata", {}),
        )

    def __str__(self) -> str:
        return self.sql
