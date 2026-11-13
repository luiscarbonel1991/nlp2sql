"""connect() and the service factories take a ready AI provider, not only a ProviderConfig.

A provider built by hand, such as ``OpenAIAdapter(client=...)``, is used as it is: no
adapter is built from a name or a config, and its key and model are its own.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nlp2sql import ProviderConfig, create_query_service
from nlp2sql.client import connect
from nlp2sql.ports.ai_provider import AIProviderPort

DB_URL = "postgresql://user:pass@localhost/db"


async def _service_arguments(provider: object) -> dict[str, Any]:
    """What connect() hands to the service factory for ``provider``."""
    with patch("nlp2sql.create_and_initialize_service", new_callable=AsyncMock) as create_service:
        create_service.return_value = MagicMock()
        await connect(DB_URL, provider=provider, embedding_provider=MagicMock())
    return create_service.await_args.kwargs


class TestConnect:
    @pytest.mark.asyncio
    async def test_a_ready_provider_goes_to_the_service_as_it_is(self, mock_ai_provider: AIProviderPort) -> None:
        arguments = await _service_arguments(mock_ai_provider)

        assert arguments["ai_provider"] is mock_ai_provider
        assert "provider_config" not in arguments

    @pytest.mark.asyncio
    async def test_a_provider_config_is_still_built_by_the_factory(self) -> None:
        config = ProviderConfig(provider="anthropic", api_key="key")

        arguments = await _service_arguments(config)

        assert arguments["provider_config"] is config
        assert "ai_provider" not in arguments

    @pytest.mark.asyncio
    async def test_anything_else_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="ProviderConfig or an AI provider"):
            await connect(DB_URL, provider="openai")


class TestCreateQueryService:
    def test_a_ready_provider_is_the_services_provider(self, mock_ai_provider: AIProviderPort) -> None:
        with patch("nlp2sql.QueryGenerationService") as service, patch("nlp2sql.create_ai_provider") as build:
            create_query_service(DB_URL, ai_provider=mock_ai_provider, embedding_provider=MagicMock())

        assert service.call_args.kwargs["ai_provider"] is mock_ai_provider
        build.assert_not_called()

    @pytest.mark.parametrize(
        "extra",
        [{"api_key": "another-key"}, {"model": "gpt-4o"}, {"provider_config": ProviderConfig(provider="openai")}],
        ids=["api-key", "model", "provider-config"],
    )
    def test_a_ready_provider_has_its_own_key_and_model(
        self, mock_ai_provider: AIProviderPort, extra: dict[str, Any]
    ) -> None:
        with pytest.raises(ValueError, match="ready AI provider"):
            create_query_service(DB_URL, ai_provider=mock_ai_provider, **extra)
