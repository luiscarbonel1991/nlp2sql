"""validate_query of the three provider adapters, against the local fake APIs.

Every adapter answers by the contract of AIProviderPort.validate_query: the same keys
for all of them, and a review that could not be done is never an approval.
"""

import json

import pytest

from nlp2sql.adapters._provider_validation import validation_from_json
from nlp2sql.adapters.anthropic_adapter import AnthropicAdapter
from nlp2sql.adapters.gemini_adapter import GeminiAdapter
from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.ports.ai_provider import AIProviderPort

SQL = "SELECT COUNT(*) FROM users"
SCHEMA = "Table: users\nColumns:\n  - id integer NOT NULL"
TOKENS = 5


@pytest.fixture(params=["openai", "anthropic", "gemini"])
def provider(request: pytest.FixtureRequest) -> tuple[AIProviderPort, object]:
    """One adapter and the fake API it talks to. The SDK retries are off: one call, one answer."""
    fake = request.getfixturevalue(f"fake_{request.param}")
    if request.param == "gemini":
        return GeminiAdapter(api_key="test-key"), fake
    adapter = (OpenAIAdapter if request.param == "openai" else AnthropicAdapter)(api_key="test-key")
    adapter.client = adapter.client.with_options(max_retries=0)
    return adapter, fake


def _fail_every_call(fake: object) -> None:
    setattr(fake, "chat_status" if hasattr(fake, "chat_status") else "status", 500)


@pytest.mark.asyncio
async def test_an_approval_has_the_keys_of_the_contract(provider: tuple[AIProviderPort, object]) -> None:
    adapter, _ = provider

    result = await adapter.validate_query(SQL, SCHEMA)

    assert result["is_valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == []
    assert result["_tokens_used"] > 0
    assert "issues" not in result
    assert "llm_validation_error" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["errors", "issues"])
async def test_what_the_model_finds_is_reported_as_errors(provider: tuple[AIProviderPort, object], name: str) -> None:
    adapter, fake = provider
    fake.validation_content = json.dumps({"is_valid": False, name: ["users has no column deleted_at"]})

    result = await adapter.validate_query(SQL, SCHEMA)

    assert result["is_valid"] is False
    assert result["errors"] == ["users has no column deleted_at"]
    assert "issues" not in result
    assert "llm_validation_error" not in result


@pytest.mark.asyncio
async def test_a_failed_call_is_not_an_approval(provider: tuple[AIProviderPort, object]) -> None:
    adapter, fake = provider
    _fail_every_call(fake)

    result = await adapter.validate_query(SQL, SCHEMA)

    assert result["is_valid"] is False
    assert result["llm_validation_error"]
    assert result["errors"] == [f"LLM validation unavailable: {result['llm_validation_error']}"]


@pytest.mark.asyncio
async def test_an_answer_that_is_not_json_is_not_an_approval(provider: tuple[AIProviderPort, object]) -> None:
    adapter, fake = provider
    fake.validation_content = "The query looks fine to me."

    result = await adapter.validate_query(SQL, SCHEMA)

    assert result["is_valid"] is False
    assert "not JSON" in result["llm_validation_error"]
    # The call was made: its tokens still count
    assert result["_tokens_used"] > 0


@pytest.mark.asyncio
async def test_an_answer_without_a_verdict_is_not_an_approval(provider: tuple[AIProviderPort, object]) -> None:
    adapter, fake = provider
    fake.validation_content = json.dumps({"issues": [], "suggestions": []})

    result = await adapter.validate_query(SQL, SCHEMA)

    assert result["is_valid"] is False
    assert result["llm_validation_error"]


@pytest.mark.parametrize(
    "text", ["", "[1, 2]", '"valid"', '{"is_valid": "yes"}'], ids=["empty", "list", "text", "no-bool"]
)
def test_json_that_is_not_a_verdict_keeps_its_tokens(text: str) -> None:
    result = validation_from_json(text, TOKENS)

    assert result["is_valid"] is False
    assert result["llm_validation_error"]
    assert result["_tokens_used"] == TOKENS
