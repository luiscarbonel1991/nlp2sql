"""Provider errors are typed, and only transient ones are retried.

Before, every exception in generate_query was retried three times with backoff, so an
invalid API key took about 8 seconds to surface, and Anthropic/Gemini built
TokenLimitException without its required arguments (a TypeError, also retried).

Output that is not the expected JSON is asked for again once, without waiting, and the
tokens of both answers are reported. An answer cut at max_tokens is not asked for again.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import openai
import pytest
from google.api_core import exceptions as google_exceptions
from tenacity import wait_none

from nlp2sql.adapters._provider_errors import TRANSIENT_PROVIDER_ERRORS, classify_provider_error
from nlp2sql.adapters.anthropic_adapter import AnthropicAdapter
from nlp2sql.adapters.gemini_adapter import GeminiAdapter
from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.exceptions import (
    ProviderAuthenticationError,
    ProviderException,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseFormatError,
    ProviderUnavailableError,
    TokenLimitException,
)
from nlp2sql.ports.ai_provider import QueryContext

REQUEST = httpx.Request("POST", "https://provider.test/v1")


def _status(sdk, error_class: str, status: int) -> Exception:
    return getattr(sdk, error_class)("provider error", response=httpx.Response(status, request=REQUEST), body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status(openai, "AuthenticationError", 401), ProviderAuthenticationError),
        (_status(openai, "PermissionDeniedError", 403), ProviderAuthenticationError),
        (_status(openai, "BadRequestError", 400), ProviderRequestError),
        (_status(openai, "NotFoundError", 404), ProviderRequestError),
        (_status(openai, "RateLimitError", 429), ProviderRateLimitError),
        (_status(openai, "InternalServerError", 500), ProviderUnavailableError),
        (openai.APIConnectionError(request=REQUEST), ProviderUnavailableError),
        (openai.APITimeoutError(request=REQUEST), ProviderUnavailableError),
        (_status(anthropic, "AuthenticationError", 401), ProviderAuthenticationError),
        (_status(anthropic, "RateLimitError", 429), ProviderRateLimitError),
        (_status(anthropic, "InternalServerError", 529), ProviderUnavailableError),
        (google_exceptions.Unauthenticated("bad key"), ProviderAuthenticationError),
        (google_exceptions.InvalidArgument("bad model"), ProviderRequestError),
        (google_exceptions.ResourceExhausted("quota"), ProviderRateLimitError),
        (google_exceptions.ServiceUnavailable("down"), ProviderUnavailableError),
        (google_exceptions.DeadlineExceeded("slow"), ProviderUnavailableError),
        (ValueError("unexpected"), ProviderException),
    ],
)
def test_sdk_errors_are_classified(error, expected):
    classified = classify_provider_error(error, "generation failed")

    assert type(classified) is expected
    assert isinstance(classified, ProviderException)


def test_nlp2sql_errors_pass_through_unchanged():
    error = TokenLimitException("too large", tokens_used=10, max_tokens=5)

    assert classify_provider_error(error, "generation failed") is error
    assert not isinstance(error, TRANSIENT_PROVIDER_ERRORS)


def _context() -> QueryContext:
    return QueryContext(
        question="How many users are there?",
        database_type="postgres",
        schema_context="Table: users\nColumns:\n  - id integer NOT NULL",
        examples=[],
    )


@pytest.mark.asyncio
async def test_invalid_key_fails_fast_without_retries(fake_openai):
    fake_openai.chat_status = 401
    adapter = OpenAIAdapter(api_key="sk-test-not-a-real-key")

    started = time.perf_counter()
    with pytest.raises(ProviderAuthenticationError) as raised:
        await adapter.generate_query(_context())

    assert time.perf_counter() - started < 2
    assert fake_openai.calls("generate") == 1
    assert isinstance(raised.value.__cause__, openai.AuthenticationError)


@pytest.mark.asyncio
async def test_transient_errors_are_still_retried(fake_openai, monkeypatch):
    monkeypatch.setattr(OpenAIAdapter.generate_query.retry, "wait", wait_none())
    fake_openai.chat_status = 503
    adapter = OpenAIAdapter(api_key="sk-test-not-a-real-key")
    # Count only the adapter's own retries; the SDK also retries 5xx by itself
    adapter.client = adapter.client.with_options(max_retries=0)

    with pytest.raises(ProviderUnavailableError):
        await adapter.generate_query(_context())

    assert fake_openai.calls("generate") == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_class", [AnthropicAdapter, GeminiAdapter])
async def test_token_limit_exception_carries_its_numbers(adapter_class, monkeypatch):
    adapter = adapter_class(api_key="test-key")
    monkeypatch.setattr(adapter, "get_max_context_size", lambda: 100)
    monkeypatch.setattr(adapter, "get_token_count", lambda text: len(text))

    with pytest.raises(TokenLimitException) as raised:
        await adapter._validate_token_count(_context())

    assert raised.value.tokens_used > raised.value.max_tokens


# ── Malformed model output ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_output_is_asked_for_again_once(fake_openai):
    fake_openai.chat_contents = ["Sure! Here is the query: SELECT COUNT(*) FROM users"]
    adapter = OpenAIAdapter(api_key="sk-test-not-a-real-key")

    response = await adapter.generate_query(_context())

    assert response.sql == fake_openai.sql
    assert fake_openai.calls("generate") == 2
    assert response.tokens_used == fake_openai.chat_tokens()
    assert response.metadata["format_retries"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not json", '{"query": "SELECT 1"}', '["SELECT 1"]', ""])
async def test_malformed_output_twice_raises_a_format_error(fake_openai, content):
    fake_openai.chat_contents = [content, content]
    adapter = OpenAIAdapter(api_key="sk-test-not-a-real-key")

    started = time.perf_counter()
    with pytest.raises(ProviderResponseFormatError) as raised:
        await adapter.generate_query(_context())

    assert time.perf_counter() - started < 2
    assert fake_openai.calls("generate") == 2
    assert raised.value.details["tokens_used"] == fake_openai.chat_tokens()
    assert not isinstance(raised.value, TRANSIENT_PROVIDER_ERRORS)


@pytest.mark.asyncio
async def test_output_truncated_at_max_tokens_is_not_asked_for_again(fake_openai):
    fake_openai.chat_contents = ['{"sql": "SELECT COUNT(*) FROM us']
    fake_openai.finish_reason = "length"
    adapter = OpenAIAdapter(api_key="sk-test-not-a-real-key")

    with pytest.raises(ProviderException, match="max_tokens") as raised:
        await adapter.generate_query(_context())

    assert not isinstance(raised.value, ProviderResponseFormatError)
    assert fake_openai.calls("generate") == 1


def _anthropic_message(text: str, stop_reason: str = "end_turn") -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=text)]
    message.stop_reason = stop_reason
    message.usage.input_tokens = 10
    message.usage.output_tokens = 5
    return message


@pytest.mark.asyncio
async def test_anthropic_asks_again_once_and_counts_both_answers():
    adapter = AnthropicAdapter(api_key="test-key")
    adapter.client.messages.create = AsyncMock(
        side_effect=[_anthropic_message("SELECT COUNT(*) FROM users"), _anthropic_message('{"sql": "SELECT 1"}')]
    )

    response = await adapter.generate_query(_context())

    assert response.sql == "SELECT 1"
    assert adapter.client.messages.create.await_count == 2
    assert response.tokens_used == 30
    assert response.metadata["format_retries"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stop_reason", "error", "match"),
    [("max_tokens", ProviderException, "max_tokens"), ("refusal", ProviderRequestError, "declined")],
)
async def test_anthropic_truncated_or_refused_output_is_not_asked_for_again(stop_reason, error, match):
    adapter = AnthropicAdapter(api_key="test-key")
    adapter.client.messages.create = AsyncMock(return_value=_anthropic_message('{"sql": "SELECT', stop_reason))

    with pytest.raises(error, match=match) as raised:
        await adapter.generate_query(_context())

    assert not isinstance(raised.value, ProviderResponseFormatError)
    assert adapter.client.messages.create.await_count == 1


def test_anthropic_missing_sql_is_a_format_error_with_its_own_message():
    adapter = AnthropicAdapter(api_key="test-key")

    with pytest.raises(ProviderResponseFormatError, match="^Response missing required 'sql' field$"):
        adapter._parse_response(_anthropic_message('{"query": "SELECT 1"}'))


def _gemini_response(text: str, finish_reason: str = "STOP") -> MagicMock:
    candidate = MagicMock()
    candidate.finish_reason.name = finish_reason
    candidate.content.parts = [MagicMock()]
    response = MagicMock()
    response.candidates = [candidate]
    response.text = text
    response.usage_metadata.prompt_token_count = 10
    response.usage_metadata.candidates_token_count = 5
    return response


@pytest.fixture
def gemini_adapter(monkeypatch):
    with patch("nlp2sql.adapters.gemini_adapter.genai"):
        adapter = GeminiAdapter(api_key="test-key")
    monkeypatch.setattr(adapter, "get_token_count", lambda text: len(text) // 4)
    return adapter


@pytest.mark.asyncio
async def test_gemini_asks_again_once_and_counts_both_answers(gemini_adapter):
    gemini_adapter.model.generate_content = MagicMock(
        side_effect=[_gemini_response("SELECT COUNT(*) FROM users"), _gemini_response('{"sql": "SELECT 1"}')]
    )

    response = await gemini_adapter.generate_query(_context())

    assert response.sql == "SELECT 1"
    assert gemini_adapter.model.generate_content.call_count == 2
    assert response.tokens_used == 30
    assert response.metadata["format_retries"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "error", "match"),
    [("MAX_TOKENS", ProviderException, "max_tokens"), ("SAFETY", ProviderRequestError, "blocked")],
)
async def test_gemini_truncated_or_blocked_output_is_not_asked_for_again(gemini_adapter, finish_reason, error, match):
    gemini_adapter.model.generate_content = MagicMock(return_value=_gemini_response('{"sql": "SEL', finish_reason))

    with pytest.raises(error, match=match) as raised:
        await gemini_adapter.generate_query(_context())

    assert not isinstance(raised.value, ProviderResponseFormatError)
    assert gemini_adapter.model.generate_content.call_count == 1
