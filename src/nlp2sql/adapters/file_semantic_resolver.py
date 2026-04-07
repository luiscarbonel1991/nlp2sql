"""Simple semantic resolver backed by a JSON/YAML file."""

from __future__ import annotations

from ..core.entities import DatabaseType, RetrievalPlan, SemanticContext
from ..ports.semantic_resolver import SemanticResolverPort
from ..utils.artifact_loader import load_semantic_context


class FileSemanticResolver(SemanticResolverPort):
    """Resolve semantics from a JSON/YAML semantic context file."""

    def __init__(self, file_path: str):
        self._semantic_context = load_semantic_context(file_path=file_path)

    async def resolve(
        self,
        question: str,
        retrieval_plan: RetrievalPlan,
        database_type: DatabaseType,
        semantic_context: SemanticContext | None = None,
    ) -> SemanticContext:
        del question, retrieval_plan, database_type, semantic_context
        return self._semantic_context or SemanticContext()
