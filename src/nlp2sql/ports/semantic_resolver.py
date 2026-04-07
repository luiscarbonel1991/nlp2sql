"""Port for resolving business semantic context."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.entities import DatabaseType, RetrievalPlan, SemanticContext


class SemanticResolverPort(ABC):
    """Resolve business semantics for a question from any backing store."""

    @abstractmethod
    async def resolve(
        self,
        question: str,
        retrieval_plan: RetrievalPlan,
        database_type: DatabaseType,
        semantic_context: SemanticContext | None = None,
    ) -> SemanticContext:
        """Return a semantic context for the current question."""
        raise NotImplementedError
