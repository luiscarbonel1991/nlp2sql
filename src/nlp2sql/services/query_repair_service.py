"""Execution-aware query repair helpers."""

from __future__ import annotations

from ..core.entities import DatabaseType, RepairContext
from ..ports.ai_provider import AIProviderPort, QueryContext, QueryResponse


class QueryRepairService:
    """Regenerate SQL using structured execution feedback."""

    def __init__(self, ai_provider: AIProviderPort):
        self.ai_provider = ai_provider

    async def repair(
        self,
        question: str,
        database_type: DatabaseType,
        schema_context: str,
        examples: list[dict[str, object]],
        repair_context: RepairContext,
        max_tokens: int,
        temperature: float,
        metadata: dict[str, object],
    ) -> QueryResponse:
        """Generate a corrected query informed by the previous execution failure."""
        retry_prompt = self._build_retry_question(question, repair_context)
        retry_context = QueryContext(
            question=retry_prompt,
            database_type=database_type.value,
            schema_context=schema_context,
            examples=examples,
            max_tokens=max_tokens,
            temperature=temperature,
            metadata={**metadata, "repair_context": self._serialize_repair_context(repair_context)},
        )
        return await self.ai_provider.generate_query(retry_context)

    def _build_retry_question(self, question: str, repair_context: RepairContext) -> str:
        hints = "\n".join(f"- {hint}" for hint in repair_context.error.hints)
        hint_block = f"\nExecution Hints:\n{hints}\n" if hints else ""
        return (
            f"{question}\n\n"
            f"PREVIOUS SQL:\n{repair_context.previous_sql}\n\n"
            f"EXECUTION ERROR CATEGORY: {repair_context.error.category}\n"
            f"EXECUTION ERROR MESSAGE: {repair_context.error.message}\n"
            f"{hint_block}"
            "Regenerate the SQL so it answers the original question, keeps read-only semantics, "
            "uses only the available schema, and avoids the previous execution error."
        )

    def _serialize_repair_context(self, repair_context: RepairContext) -> dict[str, object]:
        return {
            "attempt": repair_context.attempt,
            "previous_sql": repair_context.previous_sql,
            "error": {
                "category": repair_context.error.category,
                "message": repair_context.error.message,
                "retryable": repair_context.error.retryable,
                "hints": repair_context.error.hints,
            },
        }
