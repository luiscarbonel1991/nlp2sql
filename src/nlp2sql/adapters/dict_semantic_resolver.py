"""Simple semantic resolver backed by a dictionary or SemanticContext."""

from __future__ import annotations

from ..core.entities import DatabaseType, RetrievalPlan, SemanticContext
from ..ports.semantic_resolver import SemanticResolverPort
from ..utils.artifact_loader import semantic_context_from_dict


class DictSemanticResolver(SemanticResolverPort):
    """Resolve semantics from a preloaded dict or SemanticContext."""

    def __init__(self, semantic_definition: SemanticContext | dict[str, object]):
        if isinstance(semantic_definition, SemanticContext):
            self._semantic_context = semantic_definition
        else:
            self._semantic_context = semantic_context_from_dict(semantic_definition)

    async def resolve(
        self,
        question: str,
        retrieval_plan: RetrievalPlan,
        database_type: DatabaseType,
        semantic_context: SemanticContext | None = None,
    ) -> SemanticContext:
        del question, retrieval_plan, database_type, semantic_context
        return self._semantic_context
