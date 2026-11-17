"""OpenAIAdapter against an endpoint that is not api.openai.com (a local fake API).

``base_url``, or a ready-made client, points the adapter at any server that speaks the
Chat Completions API, such as Ollama, vLLM or a gateway. ``ProviderConfig(base_url=...)``
is the same option where a provider is created from a config.
"""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fakes.fake_openai import FakeOpenAI
from openai import AsyncOpenAI, OpenAI

from nlp2sql import ProviderConfig, create_ai_provider
from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.config.settings import settings
from nlp2sql.exceptions import ProviderException
from nlp2sql.ports.ai_provider import QueryContext

ENVIRONMENT_KEY = "sk-key-from-the-environment"
LOCAL_MODEL = "llama3.1"
OLLAMA_URL = "http://localhost:11434/v1"


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOpenAI]:
    """A compatible endpoint the SDK cannot find in the environment, and an OpenAI key that must not reach it."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", ENVIRONMENT_KEY)
    fake = FakeOpenAI().start()
    yield fake
    fake.stop()


def _context() -> QueryContext:
    return QueryContext(
        question="How many users are there?",
        database_type="postgres",
        schema_context="Table: users\nColumns:\n  - id integer NOT NULL",
        examples=[],
    )


def _last_request(fake: FakeOpenAI) -> dict[str, Any]:
    return fake.requests[-1]


class TestBaseUrl:
    @pytest.mark.asyncio
    async def test_requests_go_to_that_endpoint(self, endpoint: FakeOpenAI) -> None:
        adapter = OpenAIAdapter(base_url=endpoint.base_url, model=LOCAL_MODEL)

        response = await adapter.generate_query(_context())

        assert response.sql == endpoint.sql
        assert _last_request(endpoint)["body"]["model"] == LOCAL_MODEL

    @pytest.mark.asyncio
    async def test_the_environment_key_is_not_sent_to_it(self, endpoint: FakeOpenAI) -> None:
        adapter = OpenAIAdapter(base_url=endpoint.base_url, model=LOCAL_MODEL)

        await adapter.generate_query(_context())

        assert ENVIRONMENT_KEY not in _last_request(endpoint)["authorization"]
        assert adapter.api_key != ENVIRONMENT_KEY

    @pytest.mark.asyncio
    async def test_a_key_given_for_it_is_sent(self, endpoint: FakeOpenAI) -> None:
        adapter = OpenAIAdapter(base_url=endpoint.base_url, api_key="gateway-key", model=LOCAL_MODEL)

        await adapter.generate_query(_context())

        assert _last_request(endpoint)["authorization"] == "Bearer gateway-key"

    @pytest.mark.asyncio
    async def test_validation_goes_there_too(self, endpoint: FakeOpenAI) -> None:
        adapter = OpenAIAdapter(base_url=endpoint.base_url, model=LOCAL_MODEL)

        result = await adapter.validate_query("SELECT COUNT(*) FROM users", "Table: users")

        assert result["is_valid"] is True
        assert endpoint.calls("validate") == 1

    def test_openai_itself_still_needs_a_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "openai_api_key", None)

        with pytest.raises(ProviderException, match="API key is required"):
            OpenAIAdapter()


class TestRequestParameters:
    """Which optional parameters a model is sent depends on what the adapter knows about it."""

    @pytest.mark.asyncio
    async def test_an_open_model_gets_the_parameters_every_server_takes(self, endpoint: FakeOpenAI) -> None:
        adapter = OpenAIAdapter(base_url=endpoint.base_url, model=LOCAL_MODEL)

        response = await adapter.generate_query(_context())

        body = _last_request(endpoint)["body"]
        assert body["temperature"] == _context().temperature
        assert body["max_tokens"] == _context().max_tokens
        assert "max_completion_tokens" not in body
        assert "reasoning_effort" not in body
        assert body["response_format"] == {"type": "json_object"}
        assert response.metadata["reasoning_effort"] is None

    @pytest.mark.asyncio
    async def test_reasoning_effort_marks_an_unknown_model_as_a_reasoning_model(self, endpoint: FakeOpenAI) -> None:
        adapter = OpenAIAdapter(base_url=endpoint.base_url, model="my-deployment", reasoning_effort="medium")

        await adapter.generate_query(_context())

        body = _last_request(endpoint)["body"]
        assert body["reasoning_effort"] == "medium"
        assert body["max_completion_tokens"] == _context().max_tokens
        assert "temperature" not in body
        assert "max_tokens" not in body

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("model", "sent", "not_sent"),
        [("gpt-5.6-luna", "reasoning_effort", "temperature"), ("gpt-4o", "temperature", "reasoning_effort")],
    )
    async def test_an_openai_model_keeps_its_parameters_on_another_endpoint(
        self, endpoint: FakeOpenAI, model: str, sent: str, not_sent: str
    ) -> None:
        adapter = OpenAIAdapter(base_url=endpoint.base_url, model=model)

        await adapter.generate_query(_context())

        body = _last_request(endpoint)["body"]
        assert sent in body
        assert not_sent not in body
        assert body["max_completion_tokens"] == _context().max_tokens

    @pytest.mark.asyncio
    async def test_an_unknown_model_on_openai_is_a_reasoning_model(self, fake_openai: FakeOpenAI) -> None:
        # OPENAI_BASE_URL only redirects the SDK: for the adapter this is still OpenAI
        adapter = OpenAIAdapter(api_key="test-key", model="some-future-model")

        await adapter.generate_query(_context())

        body = _last_request(fake_openai)["body"]
        assert body["reasoning_effort"] == "low"
        assert body["max_completion_tokens"] == _context().max_tokens
        assert "temperature" not in body

    def test_an_unknown_model_on_another_endpoint_is_not_a_warning(
        self, endpoint: FakeOpenAI, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="nlp2sql"):
            adapter = OpenAIAdapter(base_url=endpoint.base_url, model=LOCAL_MODEL)

        assert adapter.get_max_context_size() > 0
        assert [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING] == []


class TestReadyClient:
    @pytest.mark.asyncio
    async def test_the_adapter_uses_the_client_it_is_given(self, endpoint: FakeOpenAI) -> None:
        client = OpenAI(api_key="client-key", base_url=endpoint.base_url, max_retries=0)

        adapter = OpenAIAdapter(client=client, model=LOCAL_MODEL)
        response = await adapter.generate_query(_context())

        assert adapter.client is client
        assert response.sql == endpoint.sql
        assert _last_request(endpoint)["authorization"] == "Bearer client-key"

    def test_no_key_is_needed_besides_the_clients(self, endpoint: FakeOpenAI, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "openai_api_key", None)

        adapter = OpenAIAdapter(client=OpenAI(api_key="client-key", base_url=endpoint.base_url))

        assert adapter.api_key is None

    def test_an_async_client_is_rejected(self) -> None:
        with pytest.raises(ProviderException, match="synchronous"):
            OpenAIAdapter(client=AsyncOpenAI(api_key="client-key"))

    @pytest.mark.parametrize("extra", [{"base_url": OLLAMA_URL}, {"api_key": "another-key"}])
    def test_a_client_already_has_its_endpoint_and_key(self, extra: dict[str, str]) -> None:
        with pytest.raises(ProviderException, match="client"):
            OpenAIAdapter(client=OpenAI(api_key="client-key"), **extra)


class TestProviderConfig:
    """``base_url`` in a ``ProviderConfig`` reaches the adapter that ``create_ai_provider`` builds."""

    @pytest.mark.asyncio
    async def test_base_url_reaches_the_adapter(self, endpoint: FakeOpenAI) -> None:
        config = ProviderConfig(provider="openai", base_url=endpoint.base_url, model=LOCAL_MODEL)

        response = await create_ai_provider(config).generate_query(_context())

        request = _last_request(endpoint)
        assert response.sql == endpoint.sql
        assert request["body"]["model"] == LOCAL_MODEL
        assert request["body"]["max_tokens"] == _context().max_tokens
        assert ENVIRONMENT_KEY not in request["authorization"]

    @pytest.mark.asyncio
    async def test_its_api_key_is_the_key_of_that_endpoint(self, endpoint: FakeOpenAI) -> None:
        config = ProviderConfig(provider="openai", base_url=endpoint.base_url, api_key="gateway-key", model=LOCAL_MODEL)

        await create_ai_provider(config).generate_query(_context())

        assert _last_request(endpoint)["authorization"] == "Bearer gateway-key"

    @pytest.mark.parametrize("provider", ["anthropic", "gemini"])
    def test_base_url_is_only_for_openai(self, provider: str) -> None:
        with pytest.raises(ValueError, match="only supported for provider 'openai'"):
            ProviderConfig(provider=provider, base_url=OLLAMA_URL)

    def test_only_openai_without_base_url_targets_openai(self) -> None:
        assert ProviderConfig(provider="openai").targets_openai is True
        assert ProviderConfig(provider="openai", base_url=OLLAMA_URL).targets_openai is False
        assert ProviderConfig(provider="anthropic").targets_openai is False
