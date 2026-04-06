"""Prompt assembly helpers shared across query generation flows."""

from __future__ import annotations

from typing import Any

from ..core.entities import RetrievalPlan, SemanticContext, SqlIntentPlan
from ..config.settings import settings
from ..ports.ai_provider import QueryContext


class PromptAssemblyService:
    """Build the final QueryContext from retrieval outputs."""

    def build_query_context(
        self,
        question: str,
        database_type: str,
        schema_context: str,
        retrieval_plan: RetrievalPlan,
        examples: list[dict[str, Any]],
        semantic_context: SemanticContext | None,
        sql_intent_plan: SqlIntentPlan | None,
        max_tokens: int,
        temperature: float,
        metadata: dict[str, Any] | None = None,
    ) -> QueryContext:
        """Create a QueryContext with structured metadata for the provider."""
        prompt_examples = examples[: settings.max_prompt_examples]
        base_metadata: dict[str, object] = {
            "intent_context": {
                "intent": retrieval_plan.intent_context.intent.value,
                "business_terms": retrieval_plan.intent_context.business_terms,
                "metrics": retrieval_plan.intent_context.metrics,
                "dimensions": retrieval_plan.intent_context.dimensions,
                "time_grains": retrieval_plan.intent_context.time_grains,
                "filters": retrieval_plan.intent_context.filters,
                "expected_operations": retrieval_plan.intent_context.expected_operations,
                "requires_aggregation": retrieval_plan.intent_context.requires_aggregation,
                "requires_join": retrieval_plan.intent_context.requires_join,
                "requires_ordering": retrieval_plan.intent_context.requires_ordering,
            },
            "retrieval_plan": {
                "retrieval_query": retrieval_plan.retrieval_query,
                "example_query": retrieval_plan.example_query,
                "keyword_hints": retrieval_plan.keyword_hints,
            },
            "semantic_context": semantic_context.to_metadata() if semantic_context else {},
            "sql_intent_plan": sql_intent_plan.to_metadata() if sql_intent_plan else {},
            "retrieved_examples_count": len(examples),
            "prompt_examples_count": len(prompt_examples),
        }
        if metadata:
            base_metadata.update(metadata)

        return QueryContext(
            question=question,
            database_type=database_type,
            schema_context=schema_context,
            examples=prompt_examples,
            max_tokens=max_tokens,
            temperature=temperature,
            metadata=base_metadata,
        )
