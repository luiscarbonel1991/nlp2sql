"""connect() must pick a valid embedding provider for every chat provider.

Regression for the rc15 field test: connect() with ProviderConfig(provider="anthropic")
or "gemini" raised ``Unknown embedding provider``, and the README Quick Start with
OpenAI failed unless OPENAI_API_KEY was exported, because the ProviderConfig key never
reached the embedding adapter.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nlp2sql import ProviderConfig, create_query_service
from nlp2sql.client import connect
from nlp2sql.ports.ai_provider import AIProviderPort

DB_URL = "postgresql://user:pass@localhost/db"
OLLAMA_URL = "http://localhost:11434/v1"


def _fake_create_embedding_provider(local_installed: bool):
    calls: list[dict] = []

    def factory(provider=None, api_key=None, model=None):
        calls.append({"provider": provider, "api_key": api_key})
        if provider == "local" and not local_installed:
            raise ImportError("sentence-transformers is not installed")
        return MagicMock(name=f"{provider}-embeddings")

    return factory, calls


async def _connect(local_installed: bool = True, **kwargs):
    factory, calls = _fake_create_embedding_provider(local_installed)
    with patch("nlp2sql.create_embedding_provider", side_effect=factory):
        with patch("nlp2sql.create_and_initialize_service", new_callable=AsyncMock) as create_service:
            create_service.return_value = MagicMock()
            await connect(DB_URL, **kwargs)
    return create_service.await_args.kwargs, calls


class TestConnectEmbeddingDefaults:
    @pytest.mark.asyncio
    async def test_openai_reuses_provider_config_key(self):
        service_kwargs, calls = await _connect(provider=ProviderConfig(provider="openai", api_key="sk-config"))

        assert calls == [{"provider": "openai", "api_key": "sk-config"}]
        assert service_kwargs["embedding_provider"] is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("chat_provider", ["anthropic", "gemini"])
    async def test_other_providers_use_local_embeddings_when_installed(self, chat_provider):
        service_kwargs, calls = await _connect(provider=ProviderConfig(provider=chat_provider, api_key="key"))

        assert calls == [{"provider": "local", "api_key": None}]
        assert service_kwargs["embedding_provider"] is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("chat_provider", ["anthropic", "gemini"])
    async def test_other_providers_work_without_embeddings(self, chat_provider):
        service_kwargs, calls = await _connect(
            local_installed=False, provider=ProviderConfig(provider=chat_provider, api_key="key")
        )

        assert [call["provider"] for call in calls] == ["local"]
        assert service_kwargs["embedding_provider"] is None
        assert "embedding_provider_type" not in service_kwargs

    @pytest.mark.asyncio
    async def test_explicit_openai_embeddings_never_receive_another_providers_key(self):
        _, calls = await _connect(
            provider=ProviderConfig(provider="anthropic", api_key="sk-ant"),
            embedding_provider_type="openai",
        )

        assert calls == [{"provider": "openai", "api_key": None}]

    @pytest.mark.asyncio
    async def test_explicit_instance_is_used_as_is(self):
        instance = MagicMock(name="custom-embeddings")
        service_kwargs, calls = await _connect(
            provider=ProviderConfig(provider="anthropic", api_key="key"),
            embedding_provider=instance,
        )

        assert calls == []
        assert service_kwargs["embedding_provider"] is instance

    @pytest.mark.asyncio
    async def test_examples_and_schema_share_one_embedding_provider(self):
        with patch("nlp2sql.schema.example_store.ExampleStore") as store_cls:
            store_cls.return_value.add_examples = AsyncMock()
            service_kwargs, calls = await _connect(
                provider=ProviderConfig(provider="openai", api_key="sk-config"),
                examples=[{"question": "q", "sql": "SELECT 1"}],
            )

        assert len(calls) == 1
        assert store_cls.call_args.kwargs["embedding_provider"] is service_kwargs["embedding_provider"]

    @pytest.mark.asyncio
    async def test_examples_without_embeddings_are_skipped_not_fatal(self):
        service_kwargs, _ = await _connect(
            local_installed=False,
            provider=ProviderConfig(provider="anthropic", api_key="key"),
            examples=[{"question": "q", "sql": "SELECT 1"}],
        )

        assert service_kwargs["example_store"] is None


class TestAnotherEndpointKeepsItsKey:
    """A key given for another endpoint, or held by a ready provider, is never sent to OpenAI."""

    @staticmethod
    def _gateway() -> ProviderConfig:
        return ProviderConfig(provider="openai", api_key="gateway-key", base_url=OLLAMA_URL)

    @pytest.mark.asyncio
    async def test_base_url_uses_local_embeddings_when_installed(self) -> None:
        service_kwargs, calls = await _connect(provider=self._gateway())

        assert calls == [{"provider": "local", "api_key": None}]
        assert service_kwargs["embedding_provider"] is not None

    @pytest.mark.asyncio
    async def test_base_url_works_without_embeddings(self) -> None:
        service_kwargs, calls = await _connect(local_installed=False, provider=self._gateway())

        assert [call["provider"] for call in calls] == ["local"]
        assert service_kwargs["embedding_provider"] is None

    @pytest.mark.asyncio
    async def test_explicit_openai_embeddings_never_receive_the_endpoints_key(self) -> None:
        _, calls = await _connect(provider=self._gateway(), embedding_provider_type="openai")

        assert calls == [{"provider": "openai", "api_key": None}]

    @pytest.mark.asyncio
    async def test_a_ready_provider_uses_local_embeddings_when_installed(
        self, mock_ai_provider: AIProviderPort
    ) -> None:
        service_kwargs, calls = await _connect(provider=mock_ai_provider)

        assert calls == [{"provider": "local", "api_key": None}]
        assert service_kwargs["embedding_provider"] is not None

    @pytest.mark.asyncio
    async def test_a_ready_provider_works_without_embeddings(self, mock_ai_provider: AIProviderPort) -> None:
        service_kwargs, calls = await _connect(local_installed=False, provider=mock_ai_provider)

        assert [call["provider"] for call in calls] == ["local"]
        assert service_kwargs["embedding_provider"] is None


class TestCreateQueryServiceEmbeddingKey:
    def test_provider_config_key_reaches_openai_embeddings(self):
        factory, calls = _fake_create_embedding_provider(local_installed=True)
        with patch("nlp2sql.create_embedding_provider", side_effect=factory), patch("nlp2sql.QueryGenerationService"):
            create_query_service(
                DB_URL,
                provider_config=ProviderConfig(provider="openai", api_key="sk-config"),
                embedding_provider_type="openai",
            )

        assert calls == [{"provider": "openai", "api_key": "sk-config"}]

    def test_a_key_for_another_endpoint_stays_out_of_openai_embeddings(self) -> None:
        factory, calls = _fake_create_embedding_provider(local_installed=True)
        with patch("nlp2sql.create_embedding_provider", side_effect=factory), patch("nlp2sql.QueryGenerationService"):
            create_query_service(
                DB_URL,
                provider_config=ProviderConfig(provider="openai", api_key="gateway-key", base_url=OLLAMA_URL),
                embedding_provider_type="openai",
            )

        assert calls == [{"provider": "openai", "api_key": None}]

    def test_a_ready_provider_shares_no_key_with_openai_embeddings(self, mock_ai_provider: AIProviderPort) -> None:
        factory, calls = _fake_create_embedding_provider(local_installed=True)
        with patch("nlp2sql.create_embedding_provider", side_effect=factory), patch("nlp2sql.QueryGenerationService"):
            create_query_service(DB_URL, ai_provider=mock_ai_provider, embedding_provider_type="openai")

        assert calls == [{"provider": "openai", "api_key": None}]
