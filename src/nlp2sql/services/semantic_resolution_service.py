"""Business semantic resolution and retrieval-plan enrichment."""

from __future__ import annotations

from typing import Any

from ..core.entities import (
    DatabaseType,
    QueryIntentContext,
    RetrievalPlan,
    SemanticContext,
)
from ..ports.semantic_resolver import SemanticResolverPort


class SemanticResolutionService:
    """Resolve semantic context and inject it into retrieval signals."""

    def __init__(self, semantic_resolver: SemanticResolverPort | None = None) -> None:
        self.semantic_resolver = semantic_resolver

    @property
    def is_configured(self) -> bool:
        return self.semantic_resolver is not None

    async def resolve(
        self,
        question: str,
        retrieval_plan: RetrievalPlan,
        database_type: DatabaseType,
        semantic_context: SemanticContext | None = None,
    ) -> tuple[SemanticContext, RetrievalPlan]:
        base_context = semantic_context or SemanticContext()
        resolved_context = base_context

        if self.semantic_resolver is not None:
            resolved_context = await self.semantic_resolver.resolve(
                question=question,
                retrieval_plan=retrieval_plan,
                database_type=database_type,
                semantic_context=base_context,
            )

        merged_context = self._merge_contexts(base_context, resolved_context)
        enriched_plan = self._enrich_retrieval_plan(retrieval_plan, merged_context)
        return merged_context, enriched_plan

    def _enrich_retrieval_plan(self, retrieval_plan: RetrievalPlan, semantic_context: SemanticContext) -> RetrievalPlan:
        if semantic_context.is_empty():
            return retrieval_plan

        semantic_terms = self._semantic_terms(semantic_context)
        intent_context = retrieval_plan.intent_context
        enriched_intent = QueryIntentContext(
            intent=intent_context.intent,
            business_terms=self._unique_ordered([*intent_context.business_terms, *semantic_terms]),
            metrics=self._unique_ordered(
                [*intent_context.metrics, *[metric.name for metric in semantic_context.metric_definitions]]
            ),
            dimensions=self._unique_ordered(
                [*intent_context.dimensions, *[dimension.name for dimension in semantic_context.dimension_definitions]]
            ),
            time_grains=self._unique_ordered(
                [*intent_context.time_grains, *semantic_context.preferred_time_logic]
            ),
            filters=self._unique_ordered(
                [
                    *intent_context.filters,
                    *semantic_context.required_filters,
                    *[
                        mapping.filter_expression
                        for mapping in semantic_context.entity_mappings
                        if mapping.filter_expression
                    ],
                ]
            ),
            expected_operations=intent_context.expected_operations,
            requires_aggregation=intent_context.requires_aggregation,
            requires_join=intent_context.requires_join,
            requires_ordering=intent_context.requires_ordering,
            metadata={
                **intent_context.metadata,
                "semantic_domain": semantic_context.domain,
            },
        )

        retrieval_query = " ".join(
            self._unique_ordered(
                [
                    retrieval_plan.retrieval_query,
                    semantic_context.domain or "",
                    *semantic_context.canonical_tables,
                    *semantic_context.supporting_tables[:3],
                    *semantic_context.required_filters[:3],
                    *semantic_terms[:6],
                ]
            )
        ).strip()
        example_query = " ".join(
            self._unique_ordered(
                [
                    retrieval_plan.example_query,
                    semantic_context.domain or "",
                    *semantic_context.canonical_tables[:3],
                    *[metric.name for metric in semantic_context.metric_definitions[:3]],
                    *[dimension.name for dimension in semantic_context.dimension_definitions[:3]],
                ]
            )
        ).strip()

        metadata: dict[str, Any] = {
            **retrieval_plan.metadata,
            "semantic_context": semantic_context.to_metadata(),
        }

        return RetrievalPlan(
            original_question=retrieval_plan.original_question,
            normalized_question=retrieval_plan.normalized_question,
            intent_context=enriched_intent,
            retrieval_query=retrieval_query or retrieval_plan.retrieval_query,
            example_query=example_query or retrieval_plan.example_query,
            keyword_hints=self._unique_ordered([*retrieval_plan.keyword_hints, *semantic_terms]),
            metadata=metadata,
        )

    def _merge_contexts(self, base_context: SemanticContext, resolved_context: SemanticContext) -> SemanticContext:
        if base_context.is_empty():
            return resolved_context
        if resolved_context.is_empty():
            return base_context

        return SemanticContext(
            domain=resolved_context.domain or base_context.domain,
            entity_mappings=self._merge_objects(
                base_context.entity_mappings,
                resolved_context.entity_mappings,
                key=lambda mapping: mapping.to_prompt_text(),
            ),
            metric_definitions=self._merge_objects(
                base_context.metric_definitions,
                resolved_context.metric_definitions,
                key=lambda metric: metric.name,
            ),
            dimension_definitions=self._merge_objects(
                base_context.dimension_definitions,
                resolved_context.dimension_definitions,
                key=lambda dimension: dimension.name,
            ),
            canonical_tables=self._unique_ordered([*base_context.canonical_tables, *resolved_context.canonical_tables]),
            supporting_tables=self._unique_ordered([*base_context.supporting_tables, *resolved_context.supporting_tables]),
            required_filters=self._unique_ordered([*base_context.required_filters, *resolved_context.required_filters]),
            preferred_time_logic=self._unique_ordered(
                [*base_context.preferred_time_logic, *resolved_context.preferred_time_logic]
            ),
            disallowed_tables=self._unique_ordered([*base_context.disallowed_tables, *resolved_context.disallowed_tables]),
            prompt_hints=self._unique_ordered([*base_context.prompt_hints, *resolved_context.prompt_hints]),
            rules=self._merge_objects(base_context.rules, resolved_context.rules, key=lambda rule: rule.name),
            patterns=self._merge_objects(base_context.patterns, resolved_context.patterns, key=lambda pattern: pattern.name),
            confidence=max(base_context.confidence, resolved_context.confidence),
            metadata={**base_context.metadata, **resolved_context.metadata},
        )

    def _semantic_terms(self, semantic_context: SemanticContext) -> list[str]:
        terms = []
        if semantic_context.domain:
            terms.append(semantic_context.domain)
        terms.extend(semantic_context.canonical_tables)
        terms.extend(mapping.source_term for mapping in semantic_context.entity_mappings)
        terms.extend(mapping.resolved_value for mapping in semantic_context.entity_mappings)
        terms.extend(metric.name for metric in semantic_context.metric_definitions)
        terms.extend(dimension.name for dimension in semantic_context.dimension_definitions)
        terms.extend(semantic_context.prompt_hints)
        return self._unique_ordered([term for term in terms if term])

    def _merge_objects(self, left: list[Any], right: list[Any], key) -> list[Any]:
        seen: set[str] = set()
        merged: list[Any] = []
        for value in [*left, *right]:
            signature = key(value)
            if not signature or signature in seen:
                continue
            seen.add(signature)
            merged.append(value)
        return merged

    def _unique_ordered(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result
