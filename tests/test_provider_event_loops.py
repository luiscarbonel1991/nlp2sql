"""One provider adapter used from several event loops (issue #66).

With ``openai`` 3.x and ``anthropic`` 2.x, the SDKs' async clients keep keep-alive
connections bound to the event loop that opened them. An adapter reused from a second
``asyncio.run()`` failed with "Event loop is closed": the OpenAI adapters on every other
call, the Anthropic adapter on its first attempt, hidden by the SDK's own retry. The
fakes keep connections alive like the real APIs, and both the SDK retries and the
adapters' own retries are off, so a failed first attempt cannot pass unnoticed.
"""

import asyncio

import pytest
from fakes.fake_anthropic import FakeAnthropic
from fakes.fake_openai import FakeOpenAI
from tenacity import stop_after_attempt

from nlp2sql.adapters.anthropic_adapter import AnthropicAdapter
from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.adapters.openai_embedding_adapter import OpenAIEmbeddingAdapter
from nlp2sql.ports.ai_provider import QueryContext, QueryResponse

RUNS = 3


@pytest.fixture(autouse=True)
def no_adapter_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """One attempt per question: a retried "Event loop is closed" would otherwise pass after a wait."""
    for adapter in (OpenAIAdapter, AnthropicAdapter):
        monkeypatch.setattr(adapter.generate_query.retry, "stop", stop_after_attempt(1))


def _context() -> QueryContext:
    return QueryContext(
        question="How many users are there?",
        database_type="postgres",
        schema_context="Table: users | Columns: id, email",
        examples=[],
    )


def test_openai_adapter_works_across_event_loops(fake_openai: FakeOpenAI) -> None:
    adapter = OpenAIAdapter(api_key="sk-test-not-a-real-key")
    adapter.client = adapter.client.with_options(max_retries=0)

    for _ in range(RUNS):
        assert asyncio.run(adapter.generate_query(_context())).sql == fake_openai.sql
    for _ in range(RUNS):
        assert asyncio.run(adapter.validate_query("SELECT 1", "Table: users"))["is_valid"] is True


def test_openai_adapter_handles_concurrent_questions(fake_openai: FakeOpenAI) -> None:
    adapter = OpenAIAdapter(api_key="sk-test-not-a-real-key")
    adapter.client = adapter.client.with_options(max_retries=0)

    async def ask_many() -> list[QueryResponse]:
        return await asyncio.gather(*(adapter.generate_query(_context()) for _ in range(8)))

    responses = asyncio.run(ask_many())

    assert [response.sql for response in responses] == [fake_openai.sql] * 8


def test_openai_embedding_adapter_works_across_event_loops(fake_openai: FakeOpenAI) -> None:
    adapter = OpenAIEmbeddingAdapter(api_key="sk-test-not-a-real-key")
    adapter.client = adapter.client.with_options(max_retries=0)

    for _ in range(RUNS):
        assert asyncio.run(adapter.encode(["users table"])).shape == (1, 1536)


def test_anthropic_adapter_works_across_event_loops(fake_anthropic: FakeAnthropic) -> None:
    adapter = AnthropicAdapter(api_key="sk-ant-test-not-a-real-key")
    adapter.client = adapter.client.with_options(max_retries=0)

    for _ in range(RUNS):
        assert asyncio.run(adapter.generate_query(_context())).sql == fake_anthropic.sql
    for _ in range(RUNS):
        result = asyncio.run(adapter.validate_query("SELECT 1", "Table: users"))
        # Anthropic's validate_query returns is_valid=True on errors too, with an "error" key
        assert "error" not in result
        assert result["is_valid"] is True
