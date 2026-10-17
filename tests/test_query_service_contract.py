"""Contract of QueryGenerationService.generate_sql with fake collaborators (no DB, no LLM)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nlp2sql.config.settings import settings
from nlp2sql.core.entities import DatabaseType
from nlp2sql.ports.ai_provider import QueryResponse
from nlp2sql.services.query_service import QueryGenerationService

SCHEMA_CONTEXT = "Table: users\nColumns:\n  - id integer NOT NULL\n  - is_active boolean NULL"


def _service(sql: str = "SELECT COUNT(*) FROM users") -> QueryGenerationService:
    ai_provider = MagicMock()
    ai_provider.generate_query = AsyncMock(
        return_value=QueryResponse(sql=sql, explanation="", confidence=0.9, tokens_used=10, provider="fake")
    )
    ai_provider.validate_query = AsyncMock(return_value={"is_valid": True, "errors": [], "warnings": []})

    service = QueryGenerationService(ai_provider=ai_provider, schema_repository=MagicMock())
    service.schema_manager = MagicMock()
    service.schema_manager.find_relevant_tables = AsyncMock(return_value=[("users", 0.9)])
    service.schema_manager.get_optimal_schema_context = AsyncMock(return_value=SCHEMA_CONTEXT)
    service._validate_column_names = AsyncMock(return_value=[])
    return service


class TestSchemaBudget:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("max_tokens", [None, 300, 1000, 4000])
    async def test_schema_budget_ignores_response_max_tokens(self, max_tokens):
        service = _service()

        await service.generate_sql("How many users are there?", DatabaseType.POSTGRES, max_tokens=max_tokens)

        schema_budget = service.schema_manager.get_optimal_schema_context.await_args.args[2]
        assert schema_budget == settings.max_schema_tokens

    @pytest.mark.asyncio
    async def test_max_tokens_still_caps_the_response(self):
        service = _service()

        await service.generate_sql("How many users are there?", DatabaseType.POSTGRES, max_tokens=300)

        context = service.ai_provider.generate_query.await_args.args[0]
        assert context.max_tokens == 300
