"""No-op semantic resolver used when no business context source is configured."""

from __future__ import annotations

from ..core.entities import DatabaseType, RetrievalPlan, SemanticContext
from ..ports.semantic_resolver import SemanticResolverPort


class NoOpSemanticResolver(SemanticResolverPort):
    """Return the provided semantic context unchanged."""

    async def resolve(
        self,
        question: str,
        retrieval_plan: RetrievalPlan,
        database_type: DatabaseType,
        semantic_context: SemanticContext | None = None,
    ) -> SemanticContext:
        del question, retrieval_plan, database_type
        return semantic_context or SemanticContext()
