"""Tests for the high-level DSL execution hooks and modes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nlp2sql.client import NLP2SQL, connect
from nlp2sql.core.entities import DatabaseType, DimensionDefinition, MetricDefinition, SemanticContext
from nlp2sql.core.runtime import ExecutionHooks, ExecutionMode, SemanticHooks


class TestNLP2SQLAskModes:
    """Ensure the public DSL resolves execution mode idiomatically."""

    @pytest.mark.asyncio
    async def test_ask_defaults_to_generate_only(self):
        service = MagicMock()
        service.generate_sql = AsyncMock(
            return_value={
                "sql": "SELECT 1",
                "confidence": 1.0,
                "provider": "openai",
                "database_type": "postgres",
                "validation": {"is_valid": True},
                "metadata": {},
            }
        )
        client = NLP2SQL(service=service, database_type=DatabaseType.POSTGRES)

        await client.ask("test question")

        assert service.generate_sql.await_args.kwargs["execution_mode"] == ExecutionMode.GENERATE_ONLY.value

    @pytest.mark.asyncio
    async def test_ask_validate_and_repair_flags_map_to_mode(self):
        service = MagicMock()
        service.generate_sql = AsyncMock(
            return_value={
                "sql": "SELECT 1",
                "confidence": 1.0,
                "provider": "openai",
                "database_type": "postgres",
                "validation": {"is_valid": True},
                "metadata": {},
            }
        )
        client = NLP2SQL(service=service, database_type=DatabaseType.POSTGRES)

        await client.ask("test question", validate=True, repair=True)

        assert service.generate_sql.await_args.kwargs["execution_mode"] == ExecutionMode.GENERATE_VALIDATE_REPAIR.value

    @pytest.mark.asyncio
    async def test_explicit_execution_mode_wins_over_flags(self):
        service = MagicMock()
        service.generate_sql = AsyncMock(
            return_value={
                "sql": "SELECT 1",
                "confidence": 1.0,
                "provider": "openai",
                "database_type": "postgres",
                "validation": {"is_valid": True},
                "metadata": {},
            }
        )
        client = NLP2SQL(service=service, database_type=DatabaseType.POSTGRES)

        await client.ask("test question", execution_mode=ExecutionMode.GENERATE_AND_VALIDATE, repair=True)

        assert service.generate_sql.await_args.kwargs["execution_mode"] == ExecutionMode.GENERATE_AND_VALIDATE.value

    @pytest.mark.asyncio
    async def test_ask_forwards_default_semantic_context(self):
        service = MagicMock()
        service.generate_sql = AsyncMock(
            return_value={
                "sql": "SELECT 1",
                "confidence": 1.0,
                "provider": "openai",
                "database_type": "postgres",
                "validation": {"is_valid": True},
                "metadata": {},
            }
        )
        semantic_context = SemanticContext(domain="non_paid")
        client = NLP2SQL(service=service, database_type=DatabaseType.POSTGRES, semantic_context=semantic_context)

        await client.ask("test question")

        assert service.generate_sql.await_args.kwargs["semantic_context"] is semantic_context

    @pytest.mark.asyncio
    async def test_ask_accepts_rich_per_request_funnel_context(self):
        service = MagicMock()
        service.generate_sql = AsyncMock(
            return_value={
                "sql": "SELECT 1",
                "confidence": 1.0,
                "provider": "openai",
                "database_type": "postgres",
                "validation": {"is_valid": True},
                "metadata": {},
            }
        )
        client = NLP2SQL(service=service, database_type=DatabaseType.POSTGRES)
        semantic_context = SemanticContext(
            domain="funnel",
            canonical_tables=["conversion_funnel"],
            metric_definitions=[
                MetricDefinition(name="sessions"),
                MetricDefinition(name="cvr", expression="SUM(conversions)::float / NULLIF(SUM(sessions), 0)"),
            ],
            dimension_definitions=[DimensionDefinition(name="source_category")],
        )

        await client.ask(
            "show sessions and cvr by source category",
            semantic_context=semantic_context,
        )

        assert service.generate_sql.await_args.kwargs["semantic_context"] is semantic_context


class TestConnectHooks:
    """Ensure grouped hooks are forwarded by the public `connect()` API."""

    @pytest.mark.asyncio
    async def test_connect_accepts_grouped_hooks(self):
        fake_service = MagicMock()
        execution_port = MagicMock()
        error_classifier = MagicMock()
        repair_policy = MagicMock()
        semantic_resolver = MagicMock()
        semantic_validator = MagicMock()
        semantic_context = SemanticContext(domain="funnel")

        with patch("nlp2sql.create_and_initialize_service", new_callable=AsyncMock) as create_service:
            create_service.return_value = fake_service

            client = await connect(
                "postgresql://user:pass@localhost/db",
                hooks=ExecutionHooks(
                    execution_port=execution_port,
                    error_classifier=error_classifier,
                    repair_policy=repair_policy,
                ),
                semantic_hooks=SemanticHooks(
                    semantic_resolver=semantic_resolver,
                    semantic_validator=semantic_validator,
                    semantic_context=semantic_context,
                ),
            )

        assert isinstance(client, NLP2SQL)
        assert create_service.await_args.kwargs["execution_port"] is execution_port
        assert create_service.await_args.kwargs["error_classifier"] is error_classifier
        assert create_service.await_args.kwargs["repair_policy"] is repair_policy
        assert create_service.await_args.kwargs["semantic_resolver"] is semantic_resolver
        assert create_service.await_args.kwargs["semantic_validator"] is semantic_validator
        assert client._semantic_context is semantic_context
