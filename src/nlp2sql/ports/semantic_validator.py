"""Port for validating SQL against business semantic rules."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.entities import SemanticContext, SemanticValidationResult, SqlIntentPlan


class SemanticValidatorPort(ABC):
    """Validate generated SQL against business semantics."""

    @abstractmethod
    async def validate(
        self,
        sql: str,
        semantic_context: SemanticContext,
        sql_intent_plan: SqlIntentPlan | None = None,
    ) -> SemanticValidationResult:
        """Return semantic validation results for a generated SQL statement."""
        raise NotImplementedError
