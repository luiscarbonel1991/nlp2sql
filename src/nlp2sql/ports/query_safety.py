"""Query Safety Port - Interface for SQL query safety validation."""

from abc import ABC, abstractmethod


class QuerySafetyPort(ABC):
    """Abstract interface for SQL query safety validation.

    Defines the contract for validating that SQL queries are safe to execute
    (e.g., read-only, no injection). Implementations may use regex patterns,
    sqlglot parsing, or any other validation strategy.
    """

    @abstractmethod
    def validate(self, sql: str) -> tuple[bool, str]:
        """Validate that a SQL query is safe to execute.

        Args:
            sql: The SQL query string to validate.

        Returns:
            Tuple of (is_safe, error_message). If safe, error_message is empty.
        """
        pass

    @abstractmethod
    def apply_row_limit(self, sql: str, limit: int) -> str:
        """Ensure a query has a row limit applied.

        Args:
            sql: The SQL query string.
            limit: Maximum number of rows to return.

        Returns:
            SQL string with LIMIT clause applied.
        """
        pass
