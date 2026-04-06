"""Heuristic query analysis shared across retrieval and prompting."""

from __future__ import annotations

import re

from ..core.entities import QueryIntent, QueryIntentContext, RetrievalPlan

_STOP_WORDS = {
    "a",
    "all",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "last",
    "me",
    "of",
    "on",
    "or",
    "show",
    "the",
    "this",
    "to",
    "was",
    "what",
    "which",
    "with",
}

_METRIC_KEYWORDS = {
    "amount",
    "avg",
    "average",
    "clicks",
    "count",
    "cost",
    "cpa",
    "cpc",
    "cvr",
    "margin",
    "orders",
    "profit",
    "rate",
    "revenue",
    "roas",
    "sales",
    "sessions",
    "spend",
    "sum",
    "total",
    "users",
}

_DIMENSION_KEYWORDS = {
    "campaign",
    "campaigns",
    "category",
    "channel",
    "country",
    "date",
    "day",
    "layer",
    "month",
    "product",
    "region",
    "source",
    "status",
    "store",
    "strategy",
    "week",
    "year",
}

_TIME_KEYWORDS = {
    "daily",
    "day",
    "days",
    "monthly",
    "month",
    "months",
    "weekly",
    "week",
    "weeks",
    "year",
    "yearly",
    "ytd",
}


class QueryAnalysisService:
    """Analyze a natural-language question before retrieval and prompting."""

    def analyze(self, question: str) -> RetrievalPlan:
        """Create a retrieval plan from a natural-language question."""
        normalized_question = self._normalize_question(question)
        tokens = self._tokenize(normalized_question)
        filtered_tokens = [token for token in tokens if token not in _STOP_WORDS]

        intent_context = QueryIntentContext(
            intent=self._infer_intent(normalized_question),
            business_terms=filtered_tokens[:12],
            metrics=self._extract_keywords(filtered_tokens, _METRIC_KEYWORDS),
            dimensions=self._extract_keywords(filtered_tokens, _DIMENSION_KEYWORDS),
            time_grains=self._extract_keywords(filtered_tokens, _TIME_KEYWORDS),
            filters=self._extract_filters(normalized_question),
            expected_operations=self._extract_expected_operations(normalized_question),
            requires_aggregation=self._requires_aggregation(normalized_question),
            requires_join=self._requires_join(normalized_question),
            requires_ordering=self._requires_ordering(normalized_question),
            metadata={"token_count": len(filtered_tokens)},
        )

        retrieval_terms = self._unique_ordered(
            [
                *intent_context.metrics,
                *intent_context.dimensions,
                *intent_context.time_grains,
                *intent_context.business_terms,
            ]
        )
        retrieval_query = " ".join([question.strip(), *retrieval_terms]).strip()

        example_terms = self._unique_ordered(
            [
                intent_context.intent.value,
                *intent_context.expected_operations,
                *intent_context.metrics,
                *intent_context.dimensions,
                *intent_context.time_grains,
                *intent_context.filters,
                *intent_context.business_terms[:8],
            ]
        )
        example_query = " ".join([question.strip(), *example_terms]).strip()

        return RetrievalPlan(
            original_question=question,
            normalized_question=normalized_question,
            intent_context=intent_context,
            retrieval_query=retrieval_query,
            example_query=example_query,
            keyword_hints=retrieval_terms[:10],
            metadata={
                "business_terms": intent_context.business_terms,
                "metrics": intent_context.metrics,
                "dimensions": intent_context.dimensions,
                "time_grains": intent_context.time_grains,
            },
        )

    def _normalize_question(self, question: str) -> str:
        return re.sub(r"\s+", " ", question.strip().lower())

    def _tokenize(self, question: str) -> list[str]:
        return re.findall(r"[a-z0-9_]+", question)

    def _infer_intent(self, question: str) -> QueryIntent:
        if any(keyword in question for keyword in ("compare", "versus", "vs")):
            return QueryIntent.COMPLEX
        if any(keyword in question for keyword in ("top", "highest", "lowest", "best", "worst")):
            return QueryIntent.ORDER
        if any(keyword in question for keyword in ("break down", "group by", "per ", "by ")) and any(
            keyword in question for keyword in ("sum", "count", "avg", "average", "total", "revenue", "spend")
        ):
            return QueryIntent.GROUP
        if any(keyword in question for keyword in ("sum", "count", "avg", "average", "total")):
            return QueryIntent.AGGREGATE
        if "join" in question or "across" in question:
            return QueryIntent.JOIN
        if any(keyword in question for keyword in ("where", "filter", "only", "last", "between")):
            return QueryIntent.FILTER
        return QueryIntent.SELECT

    def _extract_keywords(self, tokens: list[str], candidates: set[str]) -> list[str]:
        return [token for token in tokens if token in candidates]

    def _extract_filters(self, question: str) -> list[str]:
        filters = []
        if "last " in question:
            filters.append("relative_time_window")
        if "between " in question:
            filters.append("between_clause")
        if "top " in question:
            filters.append("limit_ranking")
        if " by " in question:
            filters.append("grouping_dimension")
        return filters

    def _extract_expected_operations(self, question: str) -> list[str]:
        operations: list[str] = []
        if self._requires_aggregation(question):
            operations.append("aggregation")
        if self._requires_join(question):
            operations.append("join")
        if self._requires_ordering(question):
            operations.append("order_by")
        if "distinct" in question:
            operations.append("distinct")
        if any(keyword in question for keyword in ("trend", "daily", "weekly", "monthly")):
            operations.append("time_series")
        return operations

    def _requires_aggregation(self, question: str) -> bool:
        return any(keyword in question for keyword in ("sum", "count", "avg", "average", "total", "trend", "rate"))

    def _requires_join(self, question: str) -> bool:
        return any(keyword in question for keyword in (" by ", "across", "per ", "compare", "with "))

    def _requires_ordering(self, question: str) -> bool:
        return any(keyword in question for keyword in ("top", "highest", "lowest", "best", "worst", "rank"))

    def _unique_ordered(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
