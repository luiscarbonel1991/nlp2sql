"""The README Quick Start, run the way a new user runs it.

Regression for the rc15 field test, where connect() as documented failed with every
provider. OpenAI goes through the real SDK against tests/fakes/fake_openai.py; Anthropic
and Gemini make no LLM call during connect(), so they need no fake.
"""

import sys
from collections.abc import Callable, Iterator

import pytest
from fakes.fake_openai import FakeOpenAI
from openai import OpenAI

import nlp2sql
from nlp2sql import OpenAIAdapter, ProviderConfig
from nlp2sql.config.settings import settings
from nlp2sql.ports.ai_provider import AIProviderPort

GATEWAY_KEY = "gateway-key"
LOCAL_MODEL = "llama3.1"

pytestmark = pytest.mark.integration


@pytest.fixture
def key_only_in_provider_config(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Quick Start passes the key in ProviderConfig; nothing may fall back to the environment
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", None)


@pytest.fixture
def plain_install(monkeypatch: pytest.MonkeyPatch) -> None:
    # `pip install nlp2sql` without extras has no sentence-transformers
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)


@pytest.mark.asyncio
async def test_readme_quick_start_with_openai(
    postgres_available, fake_openai, isolated_caches, key_only_in_provider_config
):
    nlp = await nlp2sql.connect(
        postgres_available,
        provider=ProviderConfig(provider="openai", api_key="sk-test-not-a-real-key"),
    )

    result = await nlp.ask("How many users are there?")

    assert result.sql == fake_openai.sql
    assert result.is_valid is True
    assert fake_openai.calls("embedding") >= 1
    assert fake_openai.calls("generate") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_provider", ["anthropic", "gemini"])
async def test_connect_with_a_provider_that_has_no_embeddings(
    postgres_available, isolated_caches, plain_install, chat_provider
):
    nlp = await nlp2sql.connect(postgres_available, provider=ProviderConfig(provider=chat_provider, api_key="test-key"))

    assert isinstance(nlp, nlp2sql.NLP2SQL)


@pytest.fixture
def other_endpoint() -> Iterator[FakeOpenAI]:
    """A second OpenAI-compatible server: the one that serves the model, not OpenAI."""
    fake = FakeOpenAI().start()
    yield fake
    fake.stop()


def _provider_config(endpoint: FakeOpenAI) -> ProviderConfig:
    return ProviderConfig(provider="openai", base_url=endpoint.base_url, api_key=GATEWAY_KEY, model=LOCAL_MODEL)


def _ready_adapter(endpoint: FakeOpenAI) -> AIProviderPort:
    return OpenAIAdapter(client=OpenAI(base_url=endpoint.base_url, api_key=GATEWAY_KEY), model=LOCAL_MODEL)


@pytest.mark.asyncio
@pytest.mark.usefixtures("isolated_caches", "plain_install")
@pytest.mark.parametrize("build_provider", [_provider_config, _ready_adapter], ids=["provider-config", "ready-adapter"])
async def test_connect_with_an_openai_compatible_endpoint(
    postgres_available: str,
    fake_openai: FakeOpenAI,
    other_endpoint: FakeOpenAI,
    build_provider: Callable[[FakeOpenAI], ProviderConfig | AIProviderPort],
) -> None:
    # fake_openai stands in for OpenAI itself: nothing goes there, least of all the endpoint's key
    nlp = await nlp2sql.connect(postgres_available, provider=build_provider(other_endpoint))

    result = await nlp.ask("How many users are there?")

    request = other_endpoint.requests[-1]
    assert result.sql == other_endpoint.sql
    assert request["body"]["model"] == LOCAL_MODEL
    assert request["authorization"] == f"Bearer {GATEWAY_KEY}"
    assert fake_openai.requests == []
