"""Helpers to render rich semantic context into LLM prompts."""

from __future__ import annotations

from typing import Any


def format_semantic_context_lines(semantic_context: dict[str, Any]) -> list[str]:
    """Render semantic context metadata into concise prompt lines."""
    lines: list[str] = ["Business Context:"]

    if semantic_context.get("domain"):
        lines.append(f"- Domain: {semantic_context['domain']}")
    if semantic_context.get("canonical_tables"):
        lines.append(f"- Preferred tables: {', '.join(semantic_context['canonical_tables'])}")
    if semantic_context.get("supporting_tables"):
        lines.append(f"- Supporting tables: {', '.join(semantic_context['supporting_tables'][:5])}")
    if semantic_context.get("required_filters"):
        lines.append(f"- Required filters: {', '.join(semantic_context['required_filters'])}")
    if semantic_context.get("disallowed_tables"):
        lines.append(f"- Avoid tables: {', '.join(semantic_context['disallowed_tables'])}")
    if semantic_context.get("preferred_time_logic"):
        lines.append(f"- Time logic: {', '.join(semantic_context['preferred_time_logic'])}")
    if semantic_context.get("prompt_hints"):
        lines.append(f"- Hints: {', '.join(semantic_context['prompt_hints'])}")

    entity_mapping_lines = _format_entity_mappings(semantic_context.get("entity_mappings"))
    if entity_mapping_lines:
        lines.append("- Entity mappings:")
        lines.extend(entity_mapping_lines)

    metric_lines = _format_metric_definitions(semantic_context.get("metric_definitions"))
    if metric_lines:
        lines.append("- Metric definitions:")
        lines.extend(metric_lines)

    dimension_lines = _format_dimension_definitions(semantic_context.get("dimension_definitions"))
    if dimension_lines:
        lines.append("- Dimension definitions:")
        lines.extend(dimension_lines)

    rule_lines = _format_rules(semantic_context.get("rules"))
    if rule_lines:
        lines.append("- Business rules:")
        lines.extend(rule_lines)

    pattern_lines = _format_patterns(semantic_context.get("patterns"))
    if pattern_lines:
        lines.append("- Canonical query patterns:")
        lines.extend(pattern_lines)

    return lines


def format_sql_intent_plan_lines(sql_intent_plan: dict[str, Any]) -> list[str]:
    """Render structured SQL intent metadata into concise prompt lines."""
    lines: list[str] = ["SQL Intent Plan:"]

    if sql_intent_plan.get("fact_table"):
        lines.append(f"- Fact table: {sql_intent_plan['fact_table']}")
    if sql_intent_plan.get("supporting_tables"):
        lines.append(f"- Supporting tables: {', '.join(sql_intent_plan['supporting_tables'])}")
    if sql_intent_plan.get("dimensions"):
        lines.append(f"- Dimensions: {', '.join(sql_intent_plan['dimensions'])}")
    if sql_intent_plan.get("metrics"):
        lines.append(f"- Metrics: {', '.join(sql_intent_plan['metrics'])}")
    if sql_intent_plan.get("filters"):
        lines.append(f"- Filters: {', '.join(sql_intent_plan['filters'])}")
    if sql_intent_plan.get("group_by"):
        lines.append(f"- Group by: {', '.join(sql_intent_plan['group_by'])}")
    if sql_intent_plan.get("order_by"):
        lines.append(f"- Order by: {', '.join(sql_intent_plan['order_by'])}")
    if sql_intent_plan.get("time_range"):
        lines.append(f"- Time range: {sql_intent_plan['time_range']}")

    return lines


def _format_entity_mappings(entity_mappings: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(entity_mappings, list):
        return lines

    for mapping in entity_mappings[:5]:
        if isinstance(mapping, dict):
            prompt_text = mapping.get("prompt_text")
            if prompt_text:
                lines.append(f"  - {prompt_text}")
                continue

            source_term = mapping.get("source_term", "unknown")
            target = mapping.get("target", "unknown")
            resolved_value = mapping.get("resolved_value", "unknown")
            lines.append(f"  - {source_term} -> {target} = {resolved_value}")
        elif isinstance(mapping, str) and mapping.strip():
            lines.append(f"  - {mapping}")

    return lines


def _format_metric_definitions(metric_definitions: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(metric_definitions, list):
        return lines

    for metric in metric_definitions[:8]:
        if isinstance(metric, dict):
            parts = [str(metric.get("name", "unknown"))]
            if metric.get("description"):
                parts.append(str(metric["description"]))
            if metric.get("expression"):
                parts.append(f"expr={metric['expression']}")
            if metric.get("synonyms"):
                parts.append(f"synonyms={', '.join(metric['synonyms'][:5])}")
            lines.append(f"  - {' | '.join(parts)}")
        elif isinstance(metric, str) and metric.strip():
            lines.append(f"  - {metric}")

    return lines


def _format_dimension_definitions(dimension_definitions: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(dimension_definitions, list):
        return lines

    for dimension in dimension_definitions[:8]:
        if isinstance(dimension, dict):
            parts = [str(dimension.get("name", "unknown"))]
            if dimension.get("description"):
                parts.append(str(dimension["description"]))
            if dimension.get("allowed_values"):
                parts.append(f"values={', '.join(dimension['allowed_values'][:5])}")
            if dimension.get("synonyms"):
                parts.append(f"synonyms={', '.join(dimension['synonyms'][:5])}")
            lines.append(f"  - {' | '.join(parts)}")
        elif isinstance(dimension, str) and dimension.strip():
            lines.append(f"  - {dimension}")

    return lines


def _format_rules(rules: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(rules, list):
        return lines

    for rule in rules[:5]:
        if not isinstance(rule, dict):
            continue

        parts = [str(rule.get("name", "rule"))]
        if rule.get("description"):
            parts.append(str(rule["description"]))
        if rule.get("required_dimensions"):
            parts.append(f"requires_dimensions={', '.join(rule['required_dimensions'])}")
        if rule.get("required_filters"):
            parts.append(f"requires_filters={', '.join(rule['required_filters'])}")
        if rule.get("preferred_tables"):
            parts.append(f"preferred_tables={', '.join(rule['preferred_tables'])}")
        lines.append(f"  - {' | '.join(parts)}")

    return lines


def _format_patterns(patterns: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(patterns, list):
        return lines

    for pattern in patterns[:5]:
        if not isinstance(pattern, dict):
            continue

        parts = [str(pattern.get("name", "pattern"))]
        if pattern.get("description"):
            parts.append(str(pattern["description"]))
        if pattern.get("metric_names"):
            parts.append(f"metrics={', '.join(pattern['metric_names'])}")
        if pattern.get("dimension_names"):
            parts.append(f"dimensions={', '.join(pattern['dimension_names'])}")
        if pattern.get("preferred_tables"):
            parts.append(f"tables={', '.join(pattern['preferred_tables'])}")
        lines.append(f"  - {' | '.join(parts)}")

    return lines
