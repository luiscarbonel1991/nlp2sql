"""Tests for the new retrieval pipeline and execution-aware repair flow."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nlp2sql.adapters.default_error_classifier import DefaultErrorClassifier
from nlp2sql.adapters.default_repair_policy import DefaultRepairPolicy
from nlp2sql.core.entities import (
    CanonicalQueryPattern,
    DatabaseType,
    DimensionDefinition,
    DomainRule,
    MetricDefinition,
    SemanticContext,
    SemanticEntityMapping,
)
from nlp2sql.ports.ai_provider import QueryContext, QueryResponse
from nlp2sql.services.example_selection_service import ExampleSelectionService
from nlp2sql.services.prompt_assembly_service import PromptAssemblyService
from nlp2sql.services.query_analysis_service import QueryAnalysisService
from nlp2sql.services.query_repair_service import QueryRepairService
from nlp2sql.services.query_service import QueryGenerationService
from nlp2sql.services.semantic_resolution_service import SemanticResolutionService
from nlp2sql.services.semantic_validation_service import SemanticValidationService
from nlp2sql.services.sql_intent_planning_service import SqlIntentPlanningService
from nlp2sql.utils.semantic_prompt import format_semantic_context_lines


def _build_generic_funnel_semantic_context() -> SemanticContext:
    return SemanticContext(
        domain="funnel",
        canonical_tables=["conversion_funnel"],
        supporting_tables=["channel_summary"],
        required_filters=["store = 'demo_store'", "region = 'north_america'"],
        preferred_time_logic=["Use the date column for time windows."],
        disallowed_tables=["legacy_channel_rollup"],
        prompt_hints=["Preserve funnel groupings when the question asks for a breakdown."],
        entity_mappings=[
            SemanticEntityMapping(
                source_term="Demo Store North America",
                target="store_region",
                resolved_value="demo_store / north_america",
                filter_expression="store = 'demo_store' AND region = 'north_america'",
            )
        ],
        metric_definitions=[
            MetricDefinition(
                name="sessions",
                description="Top-of-funnel visits.",
                source_columns=["sessions"],
                synonyms=["visitors", "traffic"],
            ),
            MetricDefinition(
                name="atc_rate",
                expression="SUM(atc_users)::float / NULLIF(SUM(sessions), 0)",
                description="Add-to-cart rate.",
                source_columns=["atc_users", "sessions"],
                synonyms=["add_to_cart_rate"],
            ),
            MetricDefinition(
                name="cvr",
                expression="SUM(conversions)::float / NULLIF(SUM(sessions), 0)",
                description="Conversion rate.",
                source_columns=["conversions", "sessions"],
                synonyms=["conversion_rate"],
            ),
        ],
        dimension_definitions=[
            DimensionDefinition(
                name="source_category",
                description="Traffic source grouping.",
                synonyms=["channel_group", "traffic_source"],
                allowed_values=["Email", "Paid Social", "Organic Search"],
            ),
            DimensionDefinition(
                name="date",
                description="Daily reporting grain.",
                synonyms=["day"],
            ),
        ],
        rules=[
            DomainRule(
                name="preserve_source_breakdown",
                description="Keep source_category grouping when the user asks for a source breakdown.",
                required_dimensions=["source_category"],
                required_filters=["store = 'demo_store'"],
                preferred_tables=["conversion_funnel"],
            )
        ],
        patterns=[
            CanonicalQueryPattern(
                name="daily_funnel_by_source",
                description="Daily funnel trend by source category.",
                preferred_tables=["conversion_funnel"],
                metric_names=["sessions", "atc_rate", "cvr"],
                dimension_names=["date", "source_category"],
            )
        ],
    )


class TestQueryAnalysisService:
    """Tests for the query analysis and retrieval plan step."""

    def test_analysis_extracts_intent_and_keywords(self):
        service = QueryAnalysisService()

        plan = service.analyze("Show daily revenue by channel for the last 7 days")

        assert plan.intent_context.intent.value in {"group", "aggregate"}
        assert "revenue" in plan.intent_context.metrics
        assert "channel" in plan.intent_context.dimensions
        assert any(token in plan.intent_context.time_grains for token in ("daily", "days"))
        assert "revenue" in plan.example_query


class _FakeExampleRepository:
    async def add_examples(self, examples):  # pragma: no cover - unused in test
        del examples

    async def search_similar(self, question, top_k=5, database_type=None, min_score=0.3):
        del question, top_k, database_type, min_score
        return [
            {
                "question": "Top products by revenue",
                "sql": "SELECT product, SUM(revenue) FROM product_metrics GROUP BY product ORDER BY SUM(revenue) DESC",
                "database_type": "postgres",
                "similarity_score": 0.92,
                "metadata": {"tables": ["product_metrics"], "intent": "aggregate"},
            },
            {
                "question": "Revenue by channel for the last 7 days",
                "sql": "SELECT channel, SUM(revenue) FROM channel_metrics WHERE date >= CURRENT_DATE - INTERVAL '7 days' GROUP BY channel",
                "database_type": "postgres",
                "similarity_score": 0.55,
                "metadata": {"tables": ["channel_metrics"], "intent": "aggregate"},
            },
        ]

    async def clear(self):  # pragma: no cover - unused in test
        return None

    def get_stats(self):  # pragma: no cover - unused in test
        return {"total_examples": 2}


class TestExampleSelectionService:
    """Tests for schema-aware example reranking."""

    @pytest.mark.asyncio
    async def test_prefers_schema_aligned_example_over_higher_semantic_score(self):
        query_analysis = QueryAnalysisService()
        retrieval_plan = query_analysis.analyze("Revenue by channel for the last 7 days")
        service = ExampleSelectionService(
            example_store=_FakeExampleRepository(),
            max_examples=2,
            max_prompt_examples=2,
        )

        selected = await service.select_examples(
            question="Revenue by channel for the last 7 days",
            database_type=DatabaseType.POSTGRES,
            retrieval_plan=retrieval_plan,
            relevant_tables=[("channel_metrics", 0.95)],
        )

        assert selected[0]["metadata"]["tables"] == ["channel_metrics"]
        assert selected[0]["metadata"]["rerank_score"] > selected[1]["metadata"]["rerank_score"]


class TestPromptAssemblyService:
    """Tests for final query context assembly."""

    def test_prompt_assembly_keeps_analysis_metadata(self):
        query_analysis = QueryAnalysisService()
        retrieval_plan = query_analysis.analyze("Revenue by channel for the last 7 days")
        service = PromptAssemblyService()
        semantic_context = SemanticContext(
            domain="sales",
            canonical_tables=["channel_performance"],
            required_filters=["segment = 'growth'"],
            entity_mappings=[
                SemanticEntityMapping(
                    source_term="North America growth",
                    target="sales_segment",
                    resolved_value="north_america / growth",
                    filter_expression="region = 'north_america' AND segment = 'growth'",
                )
            ],
        )

        query_context = service.build_query_context(
            question="Revenue by channel for the last 7 days",
            database_type="postgres",
            schema_context="Table: channel_metrics",
            retrieval_plan=retrieval_plan,
            examples=[],
            semantic_context=semantic_context,
            sql_intent_plan=SqlIntentPlanningService().build(
                retrieval_plan=retrieval_plan,
                semantic_context=semantic_context,
                relevant_tables=[("channel_performance", 0.9)],
                examples=[],
            ),
            max_tokens=1000,
            temperature=0.1,
        )

        assert query_context.metadata["intent_context"]["metrics"] == ["revenue"]
        assert "example_query" in query_context.metadata["retrieval_plan"]
        assert query_context.metadata["semantic_context"]["domain"] == "sales"
        assert query_context.metadata["sql_intent_plan"]["fact_table"] == "channel_performance"

    def test_prompt_assembly_keeps_rich_funnel_semantic_metadata(self):
        query_analysis = QueryAnalysisService()
        retrieval_plan = query_analysis.analyze("Show funnel sessions and CVR by source category")
        semantic_context = _build_generic_funnel_semantic_context()

        query_context = PromptAssemblyService().build_query_context(
            question="Show funnel sessions and CVR by source category",
            database_type="postgres",
            schema_context="Table: conversion_funnel",
            retrieval_plan=retrieval_plan,
            examples=[],
            semantic_context=semantic_context,
            sql_intent_plan=SqlIntentPlanningService().build(
                retrieval_plan=retrieval_plan,
                semantic_context=semantic_context,
                relevant_tables=[("conversion_funnel", 0.95), ("legacy_channel_rollup", 0.60)],
                examples=[],
            ),
            max_tokens=1000,
            temperature=0.1,
        )

        semantic_metadata = query_context.metadata["semantic_context"]
        assert semantic_metadata["metric_definitions"][1]["name"] == "atc_rate"
        assert "SUM(atc_users)" in semantic_metadata["metric_definitions"][1]["expression"]
        assert semantic_metadata["dimension_definitions"][0]["name"] == "source_category"
        assert semantic_metadata["rules"][0]["required_dimensions"] == ["source_category"]
        assert semantic_metadata["patterns"][0]["dimension_names"] == ["date", "source_category"]
        assert query_context.metadata["sql_intent_plan"]["metadata"]["candidate_tables"] == ["conversion_funnel"]


class TestSemanticPromptFormatting:
    def test_formats_rich_semantic_context_for_prompt(self):
        lines = format_semantic_context_lines(_build_generic_funnel_semantic_context().to_metadata())

        assert "Business Context:" in lines
        assert any("Metric definitions:" in line for line in lines)
        assert any("atc_rate" in line and "expr=" in line for line in lines)
        assert any("Dimension definitions:" in line for line in lines)
        assert any("source_category" in line and "Traffic source grouping." in line for line in lines)
        assert any("Business rules:" in line for line in lines)
        assert any("preserve_source_breakdown" in line for line in lines)
        assert any("Canonical query patterns:" in line for line in lines)
        assert any("daily_funnel_by_source" in line for line in lines)


class TestSemanticResolutionService:
    @pytest.mark.asyncio
    async def test_semantic_resolution_enriches_retrieval_plan(self):
        query_analysis = QueryAnalysisService()
        retrieval_plan = query_analysis.analyze("Revenue by channel for the north america growth segment")
        semantic_context = SemanticContext(
            domain="sales",
            canonical_tables=["channel_performance"],
            required_filters=["segment = 'growth'"],
            metric_definitions=[MetricDefinition(name="net_revenue")],
            entity_mappings=[
                SemanticEntityMapping(
                    source_term="north america growth",
                    target="sales_segment",
                    resolved_value="north_america / growth",
                    filter_expression="region = 'north_america' AND segment = 'growth'",
                )
            ],
        )
        service = SemanticResolutionService()

        resolved_context, enriched_plan = await service.resolve(
            question="Revenue by channel for the north america growth segment",
            retrieval_plan=retrieval_plan,
            database_type=DatabaseType.POSTGRES,
            semantic_context=semantic_context,
        )

        assert resolved_context.domain == "sales"
        assert "channel_performance" in enriched_plan.retrieval_query
        assert "net_revenue" in enriched_plan.example_query


class TestSemanticValidationService:
    @pytest.mark.asyncio
    async def test_semantic_validation_flags_missing_required_filters(self):
        service = SemanticValidationService()
        semantic_context = SemanticContext(
            domain="sales",
            canonical_tables=["channel_performance"],
            required_filters=["segment = 'growth'"],
        )
        sql_intent_plan = SqlIntentPlanningService().build(
            retrieval_plan=QueryAnalysisService().analyze("Revenue by channel"),
            semantic_context=semantic_context,
            relevant_tables=[("channel_performance", 0.95)],
            examples=[],
        )

        result = await service.validate(
            "SELECT channel, SUM(net_revenue) FROM channel_performance GROUP BY channel",
            semantic_context,
            sql_intent_plan,
        )

        assert result.is_valid is False
        assert any(issue.category == "missing_required_filter" for issue in result.issues)

    @pytest.mark.asyncio
    async def test_semantic_validation_flags_missing_required_dimensions(self):
        service = SemanticValidationService()
        semantic_context = _build_generic_funnel_semantic_context()
        sql_intent_plan = SqlIntentPlanningService().build(
            retrieval_plan=QueryAnalysisService().analyze("Show sessions by source category"),
            semantic_context=semantic_context,
            relevant_tables=[("conversion_funnel", 0.95)],
            examples=[],
        )

        result = await service.validate(
            "SELECT SUM(sessions) FROM conversion_funnel WHERE store = 'demo_store' AND region = 'north_america'",
            semantic_context,
            sql_intent_plan,
        )

        assert result.is_valid is False
        assert any(issue.category == "missing_required_dimension" for issue in result.issues)


class TestRepairLoop:
    """Tests for execution-aware repair without a real database."""

    @pytest.mark.asyncio
    async def test_generate_response_pipeline_repairs_execution_failure(self):
        provider = MagicMock()
        provider.generate_query = AsyncMock(
            side_effect=[
                QueryResponse(
                    sql="SELECT bad_column FROM orders",
                    explanation="first attempt",
                    confidence=0.4,
                    tokens_used=10,
                    provider="openai",
                    metadata={},
                ),
                QueryResponse(
                    sql="SELECT total_amount FROM orders",
                    explanation="repaired",
                    confidence=0.8,
                    tokens_used=12,
                    provider="openai",
                    metadata={},
                ),
            ]
        )
        provider.validate_query = AsyncMock(return_value={"is_valid": True, "errors": [], "warnings": []})

        service = object.__new__(QueryGenerationService)
        service.ai_provider = provider
        service.query_optimizer = None
        service.enable_query_optimization = True
        service.query_validator = None
        service.execution_port = MagicMock()
        service.execution_port.execute_readonly = AsyncMock(
            side_effect=[Exception("column bad_column does not exist"), {"row_count": 1, "execution_time_ms": 3.2}]
        )
        service.error_classifier = DefaultErrorClassifier()
        service.repair_policy = DefaultRepairPolicy(max_attempts=2)
        service.query_repair_service = QueryRepairService(provider)
        service.semantic_validation_service = SemanticValidationService()

        query_context = QueryContext(
            question="Total revenue",
            database_type="postgres",
            schema_context="Table: orders (total_amount)",
            examples=[],
            max_tokens=1000,
            temperature=0.1,
            metadata={},
        )

        response, validation, execution_validation, repair_attempts = await service._generate_response_pipeline(
            query_context=query_context,
            database_type=DatabaseType.POSTGRES,
            execution_mode="generate_validate_repair",
            timeout_seconds=5,
        )

        assert response.sql == "SELECT total_amount FROM orders"
        assert validation["is_valid"] is True
        assert execution_validation["success"] is True
        assert len(repair_attempts) == 1

    @pytest.mark.asyncio
    async def test_generate_response_pipeline_repairs_semantic_failure_before_execution(self):
        provider = MagicMock()
        provider.generate_query = AsyncMock(
            side_effect=[
                QueryResponse(
                    sql="SELECT channel, SUM(net_revenue) FROM channel_performance GROUP BY channel",
                    explanation="first attempt",
                    confidence=0.5,
                    tokens_used=9,
                    provider="openai",
                    metadata={},
                ),
                QueryResponse(
                    sql="SELECT channel, SUM(net_revenue) FROM channel_performance WHERE segment = 'growth' GROUP BY channel",
                    explanation="semantic retry",
                    confidence=0.8,
                    tokens_used=12,
                    provider="openai",
                    metadata={},
                ),
            ]
        )
        provider.validate_query = AsyncMock(return_value={"is_valid": True, "errors": [], "warnings": []})

        service = object.__new__(QueryGenerationService)
        service.ai_provider = provider
        service.query_optimizer = None
        service.enable_query_optimization = True
        service.query_validator = None
        service.execution_port = MagicMock()
        service.execution_port.execute_readonly = AsyncMock(return_value={"row_count": 1, "execution_time_ms": 1.2})
        service.error_classifier = DefaultErrorClassifier()
        service.repair_policy = DefaultRepairPolicy(max_attempts=2)
        service.query_repair_service = QueryRepairService(provider)
        service.semantic_validation_service = SemanticValidationService()

        semantic_context = SemanticContext(
            domain="sales",
            canonical_tables=["channel_performance"],
            required_filters=["segment = 'growth'"],
        )
        sql_intent_plan = SqlIntentPlanningService().build(
            retrieval_plan=QueryAnalysisService().analyze("Revenue by channel"),
            semantic_context=semantic_context,
            relevant_tables=[("channel_performance", 0.95)],
            examples=[],
        )
        query_context = QueryContext(
            question="Revenue by channel",
            database_type="postgres",
            schema_context="Table: channel_performance (channel, net_revenue, segment)",
            examples=[],
            max_tokens=1000,
            temperature=0.1,
            metadata={
                "semantic_context": semantic_context.to_metadata(),
                "sql_intent_plan": sql_intent_plan.to_metadata(),
            },
        )

        response, validation, execution_validation, repair_attempts = await service._generate_response_pipeline(
            query_context=query_context,
            database_type=DatabaseType.POSTGRES,
            execution_mode="generate_validate_repair",
            timeout_seconds=5,
            semantic_context=semantic_context,
            sql_intent_plan=sql_intent_plan,
        )

        assert response.sql.endswith("GROUP BY channel")
        assert validation["semantic_validation"]["is_valid"] is True
        assert execution_validation["success"] is True
        assert any(attempt["type"] == "semantic_retry" for attempt in repair_attempts)

    def test_redshift_dialect_validation_flags_known_issues(self):
        service = object.__new__(QueryGenerationService)

        issues = service._validate_dialect_rules(
            "SELECT DISTINCT ON (user_id) STRING_AGG(name, ',') FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'",
            DatabaseType.REDSHIFT,
        )

        assert any("DISTINCT ON" in issue for issue in issues)
        assert any("LISTAGG" in issue for issue in issues)
        assert any("DATEADD" in issue for issue in issues)
