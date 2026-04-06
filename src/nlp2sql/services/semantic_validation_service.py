"""Semantic validation for executable but business-incorrect SQL."""

from __future__ import annotations

import re

from ..core.entities import SemanticContext, SemanticIssue, SemanticValidationResult, SqlIntentPlan
from ..ports.semantic_validator import SemanticValidatorPort


class SemanticValidationService:
    """Validate SQL against resolved business semantics."""

    def __init__(self, semantic_validator: SemanticValidatorPort | None = None) -> None:
        self.semantic_validator = semantic_validator

    async def validate(
        self,
        sql: str,
        semantic_context: SemanticContext | None,
        sql_intent_plan: SqlIntentPlan | None = None,
    ) -> SemanticValidationResult:
        normalized_context = semantic_context or SemanticContext()
        built_in_result = self._run_builtin_checks(sql, normalized_context, sql_intent_plan)

        if self.semantic_validator is None:
            return built_in_result

        custom_result = await self.semantic_validator.validate(sql, normalized_context, sql_intent_plan)
        merged_issues = [*built_in_result.issues, *custom_result.issues]
        merged_warnings = [*built_in_result.warnings, *custom_result.warnings]

        return SemanticValidationResult(
            is_valid=not any(issue.severity == "error" for issue in merged_issues),
            issues=merged_issues,
            warnings=merged_warnings,
            metadata={**built_in_result.metadata, **custom_result.metadata},
        )

    def _run_builtin_checks(
        self,
        sql: str,
        semantic_context: SemanticContext,
        sql_intent_plan: SqlIntentPlan | None,
    ) -> SemanticValidationResult:
        if semantic_context.is_empty() and sql_intent_plan is None:
            return SemanticValidationResult(is_valid=True)

        issues: list[SemanticIssue] = []
        warnings: list[str] = []
        normalized_sql = self._normalize(sql)
        tables_used = self._extract_tables(sql)

        expected_tables = semantic_context.canonical_tables or []
        if sql_intent_plan and sql_intent_plan.fact_table and not expected_tables:
            expected_tables = [sql_intent_plan.fact_table]
        if expected_tables and not set(expected_tables) & set(tables_used):
            issues.append(
                SemanticIssue(
                    category="semantic_table_mismatch",
                    message=f"Expected one of the canonical tables {expected_tables}, but SQL used {tables_used or ['none']}.",
                    metadata={"expected_tables": expected_tables, "tables_used": tables_used},
                )
            )

        disallowed_tables = self._unique_ordered(
            [*semantic_context.disallowed_tables, *[table for rule in semantic_context.rules for table in rule.disallowed_tables]]
        )
        forbidden_hits = sorted(set(disallowed_tables) & set(tables_used))
        if forbidden_hits:
            issues.append(
                SemanticIssue(
                    category="disallowed_table",
                    message=f"SQL uses disallowed tables for this business context: {', '.join(forbidden_hits)}.",
                    metadata={"tables": forbidden_hits},
                )
            )

        required_filters = self._unique_ordered(
            [
                *semantic_context.required_filters,
                *[
                    mapping.filter_expression
                    for mapping in semantic_context.entity_mappings
                    if mapping.filter_expression
                ],
                *[rule_filter for rule in semantic_context.rules for rule_filter in rule.required_filters],
            ]
        )
        missing_filters = [
            required_filter
            for required_filter in required_filters
            if self._normalize(required_filter) not in normalized_sql
        ]
        if missing_filters:
            issues.append(
                SemanticIssue(
                    category="missing_required_filter",
                    message=f"SQL is missing required business filters: {', '.join(missing_filters)}.",
                    metadata={"filters": missing_filters},
                )
            )

        required_dimensions = self._unique_ordered(
            [
                *[rule_dimension for rule in semantic_context.rules for rule_dimension in rule.required_dimensions],
                *(
                    sql_intent_plan.group_by
                    if sql_intent_plan is not None
                    else []
                ),
            ]
        )
        missing_dimensions = [
            required_dimension
            for required_dimension in required_dimensions
            if self._normalize(required_dimension) not in normalized_sql
        ]
        if missing_dimensions:
            issues.append(
                SemanticIssue(
                    category="missing_required_dimension",
                    message=f"SQL is missing required business dimensions: {', '.join(missing_dimensions)}.",
                    metadata={"dimensions": missing_dimensions},
                )
            )

        if sql_intent_plan and sql_intent_plan.group_by and "group by" not in normalized_sql:
            warnings.append(
                "Structured plan expects grouped output but the generated SQL does not include GROUP BY."
            )

        return SemanticValidationResult(
            is_valid=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            warnings=warnings,
            metadata={"tables_used": tables_used},
        )

    def _extract_tables(self, sql: str) -> list[str]:
        matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z0-9_.\"]+)", sql, flags=re.IGNORECASE)
        tables: list[str] = []
        for match in matches:
            table_name = match.strip('"').split(".")[-1]
            if table_name not in tables:
                tables.append(table_name)
        return tables

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

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
