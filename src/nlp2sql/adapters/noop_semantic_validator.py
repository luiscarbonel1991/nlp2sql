"""No-op semantic validator used when no custom validator is configured."""

from __future__ import annotations

from ..core.entities import SemanticContext, SemanticValidationResult, SqlIntentPlan
from ..ports.semantic_validator import SemanticValidatorPort


class NoOpSemanticValidator(SemanticValidatorPort):
    """Always returns a valid semantic validation result."""

    async def validate(
        self,
        sql: str,
        semantic_context: SemanticContext,
        sql_intent_plan: SqlIntentPlan | None = None,
    ) -> SemanticValidationResult:
        del sql, semantic_context, sql_intent_plan
        return SemanticValidationResult(is_valid=True)
