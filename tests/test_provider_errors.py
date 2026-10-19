"""Provider errors are typed, and only transient ones are retried.

Before, every exception in generate_query was retried three times with backoff, so an
invalid API key took about 8 seconds to surface, and Anthropic/Gemini built
TokenLimitException without its required arguments (a TypeError, also retried).
"""

import time

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
