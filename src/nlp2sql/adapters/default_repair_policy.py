"""Default repair policy for execution-aware query generation."""

from __future__ import annotations

from ..core.entities import DatabaseType, ExecutionErrorInfo, RepairDecision
from ..ports.repair_policy import RepairPolicyPort


class DefaultRepairPolicy(RepairPolicyPort):
    """Retry only for errors likely to be fixed by regeneration."""

    def __init__(self, max_attempts: int = 2):
        self.max_attempts = max_attempts

    def decide(
        self,
        error: ExecutionErrorInfo,
        database_type: DatabaseType,
        attempt: int,
    ) -> RepairDecision:
        del database_type

        if attempt >= self.max_attempts:
            return RepairDecision(
                should_retry=False,
                max_attempts=self.max_attempts,
                reason="repair_attempt_limit_reached",
            )

        if not error.retryable:
            return RepairDecision(
                should_retry=False,
                max_attempts=self.max_attempts,
                reason=f"non_retryable:{error.category}",
            )

        return RepairDecision(
            should_retry=True,
            max_attempts=self.max_attempts,
            reason=f"retryable:{error.category}",
        )
