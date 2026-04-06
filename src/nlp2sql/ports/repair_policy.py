"""Repair policy port for execution-aware query generation."""

from abc import ABC, abstractmethod

from ..core.entities import DatabaseType, ExecutionErrorInfo, RepairDecision


class RepairPolicyPort(ABC):
    """Decide whether a failed query should be repaired and retried."""

    @abstractmethod
    def decide(
        self,
        error: ExecutionErrorInfo,
        database_type: DatabaseType,
        attempt: int,
    ) -> RepairDecision:
        """Return the repair decision for a classified execution error."""
        pass
