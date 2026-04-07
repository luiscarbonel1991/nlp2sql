"""Query execution port for optional execution-time validation and repair."""

from abc import ABC, abstractmethod


class QueryExecutionPort(ABC):
    """Execute generated SQL in read-only mode."""

    @abstractmethod
    async def execute_readonly(
        self,
        sql: str,
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        """Execute a read-only SQL statement and return execution metadata."""
        pass
