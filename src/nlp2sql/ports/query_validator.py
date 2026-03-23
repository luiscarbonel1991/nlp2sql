"""Query Validator Port - Interface for SQL column and structure validation."""

from abc import ABC, abstractmethod
from typing import Any


class QueryValidatorPort(ABC):
    """Abstract interface for SQL query validation.

    Defines the contract for validating that SQL queries reference valid
    columns and structures against a known schema. Implementations may
    use regex parsing, sqlglot AST analysis, or any other strategy.
    """

    @abstractmethod
    async def validate_columns(self, sql: str, tables: list[Any]) -> list[str]:
        """Validate column names in SQL against known table schemas.

        Args:
            sql: The SQL query string to validate.
            tables: List of TableInfo objects with name and columns attributes.

        Returns:
            List of error messages. Empty list if all columns are valid.
        """
        pass
