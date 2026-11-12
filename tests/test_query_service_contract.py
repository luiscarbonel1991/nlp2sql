"""Contract of QueryGenerationService.generate_sql with fake collaborators (no DB, no LLM)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nlp2sql.adapters.default_error_classifier import DefaultErrorClassifier
from nlp2sql.adapters.default_repair_policy import DefaultRepairPolicy
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


class TestValidity:
    """is_valid must reflect read-only safety and execution, not only the LLM judge."""

    @pytest.mark.asyncio
    async def test_write_query_is_invalid_in_generate_only(self):
        service = _service(sql="DELETE FROM users WHERE is_active = false")

        result = await service.generate_sql("Remove inactive users", DatabaseType.POSTGRES)

        assert result["validation"]["is_valid"] is False
        assert any("Not a read-only query" in error for error in result["validation"]["errors"])

    @pytest.mark.asyncio
    async def test_failed_execution_makes_the_result_invalid(self):
        service = _service()
        service.execution_port = MagicMock()
        service.execution_port.execute_readonly = AsyncMock(side_effect=RuntimeError('relation "users" does not exist'))

        result = await service.generate_sql(
            "How many users are there?", DatabaseType.POSTGRES, execution_mode="generate_and_validate"
        )

        assert result["metadata"]["execution_validation"]["success"] is False
        assert result["validation"]["is_valid"] is False
        assert any("Execution failed" in error for error in result["validation"]["errors"])

    @pytest.mark.asyncio
    async def test_successful_execution_keeps_the_result_valid(self):
        service = _service()
        service.execution_port = MagicMock()
        service.execution_port.execute_readonly = AsyncMock(return_value={"row_count": 1, "execution_time_ms": 2.0})

        result = await service.generate_sql(
            "How many users are there?", DatabaseType.POSTGRES, execution_mode="generate_and_validate"
        )

        assert result["validation"]["is_valid"] is True


# What the Anthropic and Gemini adapters answer when their validation call fails
SWALLOWED_FAILURE = {
    "is_valid": True,
    "issues": [],
    "suggestions": [],
    "complexity": "moderate",
    "error": "Validation error: Connection error.",
}


class TestLlmValidationFailsClosed:
    """A review the provider could not do is never an approval."""

    @staticmethod
    def _reviewing_service(
        answer: object = None, error: Exception | None = None, sql: str = "SELECT COUNT(*) FROM users"
    ) -> QueryGenerationService:
        service = _service(sql=sql)
        service.llm_validation = True
        service.ai_provider.validate_query = AsyncMock(return_value=answer, side_effect=error)
        return service

    @pytest.mark.asyncio
    async def test_a_provider_that_raises_does_not_approve_the_query(self) -> None:
        service = self._reviewing_service(error=RuntimeError("connection refused"))

        result = await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        assert result["sql"] == "SELECT COUNT(*) FROM users"
        assert result["validation"]["is_valid"] is False
        assert result["validation"]["llm_validation_error"] == "connection refused"
        assert result["validation"]["errors"] == ["LLM validation unavailable: connection refused"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "answer",
        [None, "not json", {}, {"errors": []}, {"is_valid": "true"}],
        ids=["none", "text", "empty", "no-verdict", "string-verdict"],
    )
    async def test_an_answer_without_a_verdict_does_not_approve_the_query(self, answer: object) -> None:
        service = self._reviewing_service(answer=answer)

        result = await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        assert result["sql"] == "SELECT COUNT(*) FROM users"
        assert result["validation"]["is_valid"] is False
        assert result["validation"]["llm_validation_error"]

    @pytest.mark.asyncio
    async def test_a_swallowed_failure_does_not_approve_the_query(self) -> None:
        service = self._reviewing_service(answer=dict(SWALLOWED_FAILURE))

        result = await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        assert result["validation"]["is_valid"] is False
        assert result["validation"]["llm_validation_error"] == "Validation error: Connection error."

    @pytest.mark.asyncio
    async def test_an_unreviewed_query_is_not_cached(self) -> None:
        service = self._reviewing_service(answer=dict(SWALLOWED_FAILURE))
        service.cache = MagicMock()
        service.cache.get = AsyncMock(return_value=None)
        service.cache.set = AsyncMock()

        await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        service.cache.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_errors_is_there_whatever_the_provider_calls_it(self) -> None:
        service = self._reviewing_service(answer={"is_valid": True, "issues": [], "suggestions": []})

        result = await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        assert result["validation"]["is_valid"] is True
        assert result["validation"]["errors"] == []
        assert "llm_validation_error" not in result["validation"]

    @pytest.mark.asyncio
    async def test_the_providers_issues_and_the_service_checks_share_errors(self) -> None:
        service = self._reviewing_service(
            answer={"is_valid": False, "issues": ["users has no column deleted_at"]},
            sql="DELETE FROM users WHERE is_active = false",
        )

        result = await service.generate_sql("Remove inactive users", DatabaseType.POSTGRES)

        errors = result["validation"]["errors"]
        assert errors[0] == "users has no column deleted_at"
        assert any("Not a read-only query" in error for error in errors)
        assert "issues" not in result["validation"]

    @pytest.mark.asyncio
    async def test_validate_reports_a_failed_review_instead_of_raising(self) -> None:
        service = _service()
        service.ai_provider.validate_query = AsyncMock(side_effect=RuntimeError("connection refused"))

        result = await service.validate_sql("SELECT COUNT(*) FROM users", DatabaseType.POSTGRES)

        assert result["is_valid"] is False
        assert result["llm_validation_error"] == "connection refused"
        assert result["tokens_used"] == 0

    @pytest.mark.asyncio
    async def test_validate_does_not_trust_a_swallowed_failure(self) -> None:
        service = _service()
        service.ai_provider.validate_query = AsyncMock(return_value=dict(SWALLOWED_FAILURE))

        result = await service.validate_sql("SELECT COUNT(*) FROM users", DatabaseType.POSTGRES)

        assert result["is_valid"] is False
        assert result["errors"] == ["LLM validation unavailable: Validation error: Connection error."]


class TestLlmValidationAndTokenUsage:
    """LLM validation is opt-in, and tokens_used covers every LLM call of a question."""

    @pytest.mark.asyncio
    async def test_llm_validation_is_off_by_default(self):
        service = _service()

        result = await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        service.ai_provider.validate_query.assert_not_awaited()
        assert result["validation"]["is_valid"] is True
        assert result["validation"]["llm_validation"] is False
        assert result["tokens_used"] == 10
        assert result["metadata"]["token_usage"] == {"total": 10, "generation": 10, "validation": 0, "llm_calls": 1}

    @pytest.mark.asyncio
    async def test_llm_validation_on_request_counts_its_tokens(self):
        service = _service()
        service.llm_validation = True
        service.ai_provider.validate_query = AsyncMock(
            return_value={"is_valid": True, "errors": [], "warnings": [], "_tokens_used": 7}
        )

        result = await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        service.ai_provider.validate_query.assert_awaited_once()
        assert result["tokens_used"] == 17
        assert result["metadata"]["token_usage"] == {"total": 17, "generation": 10, "validation": 7, "llm_calls": 2}
        assert "_tokens_used" not in result["validation"]

    @pytest.mark.asyncio
    async def test_llm_validation_verdict_still_applies_when_enabled(self):
        service = _service()
        service.llm_validation = True
        service.ai_provider.validate_query = AsyncMock(
            return_value={"is_valid": False, "errors": ["wrong join"], "warnings": [], "_tokens_used": 7}
        )

        result = await service.generate_sql("How many users are there?", DatabaseType.POSTGRES)

        assert result["validation"]["is_valid"] is False

    @pytest.mark.asyncio
    async def test_repair_calls_are_counted(self):
        service = _service()
        service.error_classifier = DefaultErrorClassifier()
        service.repair_policy = DefaultRepairPolicy(max_attempts=2)
        service.execution_port = MagicMock()
        service.execution_port.execute_readonly = AsyncMock(
            side_effect=[RuntimeError('column "user_name" does not exist'), {"row_count": 1, "execution_time_ms": 1.0}]
        )

        result = await service.generate_sql(
            "How many users are there?", DatabaseType.POSTGRES, execution_mode="generate_validate_repair"
        )

        assert result["metadata"]["execution_validation"]["success"] is True
        assert result["tokens_used"] == 20
        assert result["metadata"]["token_usage"]["llm_calls"] == 2
