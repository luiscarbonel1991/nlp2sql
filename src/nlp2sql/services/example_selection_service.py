"""Selection and reranking for few-shot examples."""

from __future__ import annotations

from collections.abc import Sequence
import re
from typing import Any

from ..core.entities import DatabaseType, ExampleCandidate, QueryIntent, RetrievalPlan, SemanticContext
from ..ports.example_repository import ExampleRepositoryPort


class ExampleSelectionService:
    """Select examples using schema-aware reranking while preserving the existing port."""

    def __init__(self, example_store: ExampleRepositoryPort | None, max_examples: int, max_prompt_examples: int):
        self.example_store = example_store
        self.max_examples = max_examples
        self.max_prompt_examples = max_prompt_examples

    async def select_examples(
        self,
        question: str,
        database_type: DatabaseType,
        retrieval_plan: RetrievalPlan,
        relevant_tables: Sequence[tuple[str, float]],
        semantic_context: SemanticContext | None = None,
    ) -> list[dict[str, Any]]:
        """Return reranked examples for prompting."""
        if self.example_store is None:
            return []

        table_names = [table_name for table_name, _ in relevant_tables[:5]]
        retrieval_query = " ".join([retrieval_plan.example_query, *table_names]).strip()

        candidates = await self.example_store.search_similar(
            question=retrieval_query,
            top_k=max(self.max_examples * 3, self.max_examples + 2),
            database_type=database_type.value,
            min_score=0.2,
        )

        if not candidates:
            return []

        reranked = [
            self._build_candidate(candidate, retrieval_plan, table_names, semantic_context)
            for candidate in candidates
        ]
        reranked.sort(key=lambda candidate: candidate.score, reverse=True)

        selected: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        for candidate in reranked:
            signature = self._build_diversity_signature(candidate)
            if signature in seen_signatures and len(selected) >= self.max_prompt_examples:
                continue

            seen_signatures.add(signature)
            selected.append(
                {
                    "question": candidate.question,
                    "sql": candidate.sql,
                    "metadata": {
                        **candidate.metadata,
                        "tables": candidate.tables,
                        "intent": candidate.intent.value if candidate.intent else None,
                        "rerank_score": round(candidate.score, 4),
                    },
                }
            )
            if len(selected) >= self.max_examples:
                break

        return selected

    def _build_candidate(
        self,
        example: dict[str, Any],
        retrieval_plan: RetrievalPlan,
        relevant_tables: Sequence[str],
        semantic_context: SemanticContext | None,
    ) -> ExampleCandidate:
        metadata = dict(example.get("metadata", {}))
        similarity_score = float(example.get("similarity_score", 0.0))
        tables = metadata.get("tables") or self._extract_sql_tables(example.get("sql", ""))
        intent = self._resolve_intent(metadata, example)

        table_overlap = 0.0
        if relevant_tables and tables:
            shared = len(set(tables) & set(relevant_tables))
            table_overlap = shared / max(len(set(relevant_tables)), 1)

        business_terms = set(retrieval_plan.intent_context.business_terms)
        example_terms = set(self._tokenize(example.get("question", "")))
        business_overlap = len(business_terms & example_terms) / max(len(business_terms), 1) if business_terms else 0.0

        intent_match = 1.0 if intent == retrieval_plan.intent_context.intent else 0.0
        canonical_table_bonus = 0.0
        semantic_filter_bonus = 0.0
        if semantic_context and not semantic_context.is_empty():
            if set(tables) & set(semantic_context.canonical_tables):
                canonical_table_bonus = 1.0
            required_filters = {
                filter_text.lower()
                for filter_text in semantic_context.required_filters
            }
            mapping_filters = {
                mapping.filter_expression.lower()
                for mapping in semantic_context.entity_mappings
                if mapping.filter_expression
            }
            sql_lower = example.get("sql", "").lower()
            expected_filters = required_filters | mapping_filters
            if expected_filters:
                matched_filters = sum(1 for filter_text in expected_filters if filter_text in sql_lower)
                semantic_filter_bonus = matched_filters / max(len(expected_filters), 1)

        score = (
            similarity_score * 0.45
            + table_overlap * 0.25
            + intent_match * 0.15
            + business_overlap * 0.05
            + canonical_table_bonus * 0.07
            + semantic_filter_bonus * 0.03
        )

        metadata.setdefault("similarity_score", similarity_score)
        metadata.setdefault("table_overlap", round(table_overlap, 4))
        metadata.setdefault("intent_match", intent_match)
        metadata.setdefault("canonical_table_bonus", canonical_table_bonus)
        metadata.setdefault("semantic_filter_bonus", round(semantic_filter_bonus, 4))

        return ExampleCandidate(
            question=example.get("question", ""),
            sql=example.get("sql", ""),
            score=score,
            tables=tables,
            intent=intent,
            metadata=metadata,
        )

    def _resolve_intent(self, metadata: dict[str, Any], example: dict[str, Any]) -> QueryIntent | None:
        raw_intent = metadata.get("intent")
        if isinstance(raw_intent, str):
            for value in QueryIntent:
                if raw_intent.lower() == value.value:
                    return value
        return self._infer_intent_from_text(" ".join([example.get("question", ""), example.get("sql", "")]))

    def _infer_intent_from_text(self, text: str) -> QueryIntent:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ("group by", "sum(", "count(", "avg(", "total")):
            return QueryIntent.AGGREGATE
        if any(keyword in lowered for keyword in ("join", " left ", " right ", " inner ")):
            return QueryIntent.JOIN
        if any(keyword in lowered for keyword in ("order by", "top", "limit")):
            return QueryIntent.ORDER
        if "where" in lowered:
            return QueryIntent.FILTER
        return QueryIntent.SELECT

    def _extract_sql_tables(self, sql: str) -> list[str]:
        matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z0-9_.\"]+)", sql, flags=re.IGNORECASE)
        tables = []
        for match in matches:
            table_name = match.strip('"')
            table_name = table_name.split(".")[-1]
            tables.append(table_name)
        return self._unique_ordered(tables)

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9_]+", text.lower())

    def _build_diversity_signature(self, candidate: ExampleCandidate) -> str:
        table_part = ",".join(candidate.tables[:3]) if candidate.tables else "no-table"
        intent_part = candidate.intent.value if candidate.intent else "unknown"
        return f"{intent_part}:{table_part}"

    def _unique_ordered(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
