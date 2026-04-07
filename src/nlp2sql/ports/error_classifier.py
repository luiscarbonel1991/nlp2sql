"""Error classifier port for execution failures."""

from abc import ABC, abstractmethod

from ..core.entities import DatabaseType, ExecutionErrorInfo


class ErrorClassifierPort(ABC):
    """Classify execution errors into repair-friendly categories."""

    @abstractmethod
    def classify(
        self,
        error_message: str,
        database_type: DatabaseType,
        sql: str,
    ) -> ExecutionErrorInfo:
        """Return a structured classification for the given execution error."""
        pass
