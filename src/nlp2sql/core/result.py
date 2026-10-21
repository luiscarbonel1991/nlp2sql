"""Query result — typed wrapper over the raw dict returned by generate_sql."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class QueryResult:
    """Immutable result of a natural language to SQL query.

    Provides typed access to the generated SQL and metadata instead of
    requiring dict key access.

    ``validation`` holds the checks behind ``is_valid`` (``errors``, ``warnings``,
    ``column_errors``, ...). ``rows`` and ``columns`` are set when the query was
    executed (``validate=True``) and succeeded: at most 100 rows, with the values
    returned by the database driver. They are ``None`` when nothing was executed.
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
    validation: dict[str, Any] = field(default_factory=dict)
    rows: Optional[list[dict[str, Any]]] = None
    columns: Optional[list[str]] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryResult":
        """Build a QueryResult from the raw dict returned by generate_sql."""
        validation = data.get("validation", {})
        if not isinstance(validation, dict):
            validation = {}
        return cls(
            sql=data.get("sql", ""),
            confidence=data.get("confidence", 0.0),
            explanation=data.get("explanation"),
            is_valid=validation.get("is_valid", False),
            provider=data.get("provider", ""),
            database_type=data.get("database_type", ""),
            tokens_used=data.get("tokens_used", 0),
            generation_time_ms=data.get("generation_time_ms", 0.0),
            examples_used=data.get("examples_used", 0),
            metadata=data.get("metadata", {}),
            validation=validation,
            rows=data.get("rows"),
            columns=data.get("columns"),
        )

    def __str__(self) -> str:
        return self.sql
