"""Which AI provider the MCP server uses, from its environment (mcp_server/provider.py).

The module is loaded by path: it needs no MCP SDK, and the repository root is not on the
import path of the test run.
"""

import importlib.util
import logging
from pathlib import Path
from types import ModuleType

import pytest

from nlp2sql import ProviderConfig

ENDPOINT = "http://localhost:11434/v1"
DB_URL = "postgresql://user:pass@localhost:5432/db"
ENVIRONMENT = (
    *ProviderConfig.API_KEY_ENV_VARS.values(),
    "NLP2SQL_LLM_BASE_URL",
    "NLP2SQL_LLM_MODEL",
    "NLP2SQL_LLM_API_KEY",
)


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "mcp_server" / "provider.py"
    spec = importlib.util.spec_from_file_location("nlp2sql_mcp_provider", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provider = _load()


@pytest.fixture(autouse=True)
def empty_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


class TestEndpoint:
    def test_base_url_selects_the_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NLP2SQL_LLM_BASE_URL", ENDPOINT)
        monkeypatch.setenv("NLP2SQL_LLM_MODEL", "llama3.2")

        config = provider.provider_config()

        assert (config.provider, config.base_url, config.model) == ("openai", ENDPOINT, "llama3.2")
        assert config.targets_openai is False

    def test_it_wins_over_a_hosted_provider_and_does_not_take_its_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-key-for-openai")
        monkeypatch.setenv("NLP2SQL_LLM_BASE_URL", ENDPOINT)

        config = provider.provider_config()

        assert config.base_url == ENDPOINT
        assert config.api_key is None

    def test_its_key_has_its_own_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NLP2SQL_LLM_BASE_URL", ENDPOINT)
        monkeypatch.setenv("NLP2SQL_LLM_API_KEY", "gateway-key")

        assert provider.provider_config().api_key == "gateway-key"

    def test_model_and_key_alone_are_ignored_with_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setenv("NLP2SQL_LLM_MODEL", "llama3.2")

        with caplog.at_level(logging.WARNING):
            config = provider.provider_config()

        assert (config.provider, config.model, config.base_url) == ("anthropic", None, None)
        assert "NLP2SQL_LLM_MODEL ignored" in caplog.text

    def test_a_named_provider_is_not_replaced_by_the_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
        monkeypatch.setenv("NLP2SQL_LLM_BASE_URL", ENDPOINT)

        config = provider.provider_config("gemini")

        assert (config.provider, config.api_key, config.base_url) == ("gemini", "AIza-test", None)


class TestHostedProviders:
    def test_the_first_provider_with_a_key_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")

        config = provider.provider_config()

        assert (config.provider, config.api_key) == ("anthropic", "sk-ant")

    def test_a_named_provider_needs_its_key(self) -> None:
        with pytest.raises(ValueError, match="API key not configured for provider 'openai'"):
            provider.provider_config("openai")

    def test_nothing_configured_names_every_option(self) -> None:
        with pytest.raises(ValueError, match="No AI provider configured") as error:
            provider.provider_config()

        for name in (*ProviderConfig.API_KEY_ENV_VARS.values(), "NLP2SQL_LLM_BASE_URL"):
            assert name in str(error.value)


class TestNames:
    def test_the_label_of_an_endpoint_holds_no_address(self) -> None:
        endpoint = ProviderConfig(provider="openai", base_url="http://user:secret@gateway/v1", model="llama3.2")

        assert provider.provider_label(endpoint) == "openai-compatible"
        assert provider.provider_label(ProviderConfig(provider="gemini")) == "gemini"

    def test_services_are_cached_per_endpoint_and_model(self) -> None:
        small = ProviderConfig(provider="openai", base_url=ENDPOINT, model="llama3.2")
        large = ProviderConfig(provider="openai", base_url=ENDPOINT, model="llama3.2-16k")
        hosted = ProviderConfig(provider="openai")

        keys = {provider.service_cache_key(DB_URL, config, "public") for config in (small, large, hosted)}

        assert len(keys) == len((small, large, hosted))
        assert provider.service_cache_key(DB_URL, hosted, "public") == f"service:{DB_URL}:openai:public"
