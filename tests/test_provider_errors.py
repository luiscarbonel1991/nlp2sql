"""Provider errors are typed, and only transient ones are retried.

Before, every exception in generate_query was retried three times with backoff, so an
invalid API key took about 8 seconds to surface, and Anthropic/Gemini built
TokenLimitException without its required arguments (a TypeError, also retried).

Output that is not the expected JSON is asked for again once, without waiting, and the
tokens of both answers are reported. An answer cut at max_tokens is not asked for again.
"""

import socket
import time
from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
import openai
import pytest
from google.genai import errors as genai_errors
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


def _genai_body(code: int, status: str, message: str, reason: str = "") -> dict:
    """The error body the Gemini API sends."""
    error = {"code": code, "message": message, "status": status}
    if reason:
        error["details"] = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}]
    return {"error": error}


def _genai(error_class, code: int, status: str, message: str, reason: str = "") -> Exception:
    return error_class(code, _genai_body(code, status, message, reason))


API_KEY_INVALID_BODY = _genai_body(
    400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.", "API_KEY_INVALID"
)


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
        (_genai(genai_errors.ClientError, 401, "UNAUTHENTICATED", "bad credentials"), ProviderAuthenticationError),
        (_genai(genai_errors.ClientError, 403, "PERMISSION_DENIED", "no access"), ProviderAuthenticationError),
        (_genai(genai_errors.ClientError, 400, "INVALID_ARGUMENT", "bad request"), ProviderRequestError),
        (_genai(genai_errors.ClientError, 404, "NOT_FOUND", "no such model"), ProviderRequestError),
        # What Gemini answers to an invalid API key (seen with nlp2sql setup)
        (genai_errors.ClientError(400, API_KEY_INVALID_BODY), ProviderAuthenticationError),
        (_genai(genai_errors.ClientError, 429, "RESOURCE_EXHAUSTED", "quota"), ProviderRateLimitError),
        (_genai(genai_errors.ServerError, 503, "UNAVAILABLE", "down"), ProviderUnavailableError),
        (_genai(genai_errors.ServerError, 504, "DEADLINE_EXCEEDED", "slow"), ProviderUnavailableError),
        # google-genai raises httpx transport errors unwrapped
        (httpx.ConnectError("connection refused", request=REQUEST), ProviderUnavailableError),
        (httpx.ReadError("connection reset", request=REQUEST), ProviderUnavailableError),
        (httpx.RemoteProtocolError("server disconnected", request=REQUEST), ProviderUnavailableError),
        (httpx.ReadTimeout("timed out", request=REQUEST), ProviderUnavailableError),
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


@pytest.mark.asyncio
async def test_gemini_asks_again_once_and_counts_both_answers(fake_gemini):
    fake_gemini.contents = ["SELECT COUNT(*) FROM users", '{"sql": "SELECT 1"}']
    adapter = GeminiAdapter(api_key="test-key")

    response = await adapter.generate_query(_context())

    assert response.sql == "SELECT 1"
    assert fake_gemini.calls("generate") == 2
    assert response.tokens_used == sum(request["usage"]["totalTokenCount"] for request in fake_gemini.requests)
    assert response.metadata["format_retries"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "error", "match"),
    [("MAX_TOKENS", ProviderException, "max_tokens"), ("SAFETY", ProviderRequestError, "blocked")],
)
async def test_gemini_truncated_or_blocked_output_is_not_asked_for_again(fake_gemini, finish_reason, error, match):
    fake_gemini.contents = ['{"sql": "SEL']
    fake_gemini.finish_reason = finish_reason
    adapter = GeminiAdapter(api_key="test-key")

    with pytest.raises(error, match=match) as raised:
        await adapter.generate_query(_context())

    assert not isinstance(raised.value, ProviderResponseFormatError)
    assert fake_gemini.calls("generate") == 1


@pytest.mark.asyncio
async def test_gemini_invalid_key_fails_fast_without_retries(fake_gemini):
    fake_gemini.status = 400
    fake_gemini.error_body = API_KEY_INVALID_BODY
    adapter = GeminiAdapter(api_key="not-a-real-key")

    started = time.perf_counter()
    with pytest.raises(ProviderAuthenticationError) as raised:
        await adapter.generate_query(_context())

    assert time.perf_counter() - started < 2
    assert fake_gemini.calls("generate") == 1
    assert isinstance(raised.value.__cause__, genai_errors.ClientError)


@pytest.mark.asyncio
async def test_gemini_transient_errors_are_retried(fake_gemini, monkeypatch):
    monkeypatch.setattr(GeminiAdapter.generate_query.retry, "wait", wait_none())
    fake_gemini.status = 503
    adapter = GeminiAdapter(api_key="test-key")

    with pytest.raises(ProviderUnavailableError):
        await adapter.generate_query(_context())

    assert fake_gemini.calls("generate") == 3


@pytest.mark.asyncio
async def test_gemini_unreachable_api_is_transient(monkeypatch):
    """httpx's ConnectError has no "Connection" in its name; it used to end the question at once."""
    monkeypatch.setattr(GeminiAdapter.generate_query.retry, "wait", wait_none())
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", f"http://127.0.0.1:{closed_port}")
    adapter = GeminiAdapter(api_key="test-key")

    with pytest.raises(ProviderUnavailableError) as raised:
        await adapter.generate_query(_context())

    assert type(raised.value.__cause__).__name__ == "ConnectError"
    assert GeminiAdapter.generate_query.statistics["attempt_number"] == 3
