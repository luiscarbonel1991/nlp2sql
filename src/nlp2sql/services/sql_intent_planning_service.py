"""Create a structured SQL intent plan from retrieval and semantic signals."""

from __future__ import annotations

from ..core.entities import RetrievalPlan, SemanticContext, SqlIntentPlan


class SqlIntentPlanningService:
    """Build a narrow SQL plan before prompting the LLM."""

    def build(
        self,
        retrieval_plan: RetrievalPlan,
        semantic_context: SemanticContext,
        relevant_tables: list[tuple[str, float]],
        examples: list[dict[str, object]],
    ) -> SqlIntentPlan:
        disallowed_tables = self._unique_ordered(
            [
                *semantic_context.disallowed_tables,
                *[
                    table
                    for rule in semantic_context.rules
                    for table in rule.disallowed_tables
                ],
            ]
        )
        allowed_relevant_tables = [
            (table, score)
            for table, score in relevant_tables
            if table not in disallowed_tables
        ]
        example_tables = []
        for example in examples:
            metadata = example.get("metadata", {})
            if isinstance(metadata, dict):
                example_tables.extend(metadata.get("tables", []))

        preferred_rule_tables = [
            table
            for rule in semantic_context.rules
            for table in rule.preferred_tables
        ]
        fact_table = None
        if semantic_context.canonical_tables:
            fact_table = semantic_context.canonical_tables[0]
        elif preferred_rule_tables:
            fact_table = preferred_rule_tables[0]
        elif allowed_relevant_tables:
            fact_table = allowed_relevant_tables[0][0]
        elif relevant_tables:
            fact_table = relevant_tables[0][0]

        dimensions = self._unique_ordered(
            [
                *retrieval_plan.intent_context.dimensions,
                *[dimension.name for dimension in semantic_context.dimension_definitions],
                *[
                    required_dimension
                    for rule in semantic_context.rules
                    for required_dimension in rule.required_dimensions
                ],
            ]
        )
        metrics = self._unique_ordered(
            [
                *retrieval_plan.intent_context.metrics,
                *[metric.name for metric in semantic_context.metric_definitions],
            ]
        )
        filters = self._unique_ordered(
            [
                *retrieval_plan.intent_context.filters,
                *semantic_context.required_filters,
                *[
                    required_filter
                    for rule in semantic_context.rules
                    for required_filter in rule.required_filters
                ],
                *[
                    mapping.filter_expression
                    for mapping in semantic_context.entity_mappings
                    if mapping.filter_expression
                ],
            ]
        )
        supporting_tables = self._unique_ordered(
            [
                *semantic_context.supporting_tables,
                *preferred_rule_tables,
                *[table for table, _ in allowed_relevant_tables if table != fact_table],
                *example_tables,
            ]
        )
        time_range = retrieval_plan.intent_context.time_grains[0] if retrieval_plan.intent_context.time_grains else None

        group_by = (
            dimensions
            if retrieval_plan.intent_context.requires_aggregation
            or retrieval_plan.intent_context.dimensions
            or any(rule.required_dimensions for rule in semantic_context.rules)
            else []
        )
        order_by = []
        if retrieval_plan.intent_context.requires_ordering and metrics:
            order_by = [f"{metrics[0]} DESC"]
        elif metrics and fact_table:
            order_by = [f"{metrics[0]} DESC"]

        return SqlIntentPlan(
            domain=semantic_context.domain,
            fact_table=fact_table,
            supporting_tables=supporting_tables[:5],
            dimensions=dimensions,
            metrics=metrics,
            filters=filters,
            time_range=time_range,
            group_by=group_by,
            order_by=order_by,
            semantic_context_ref=semantic_context.domain,
            metadata={
                "candidate_tables": [table for table, _ in allowed_relevant_tables],
                "example_tables": example_tables,
            },
        )

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
