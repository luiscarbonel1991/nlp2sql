"""Provider checks in the CLI send a real request and fail with exit 1.

Before, `providers test`, `validate` and `setup` only built a query service: an invalid
key reported "Connection successful" with exit 0, no request was sent, and `setup`
checked Gemini under the name "google", which the library rejects.
"""

from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

import nlp2sql
from nlp2sql import ProviderConfig, create_ai_provider, create_query_service
from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.cli import cli, describe_provider_failure
from nlp2sql.exceptions import ProviderRateLimitError, ProviderUnavailableError


@pytest.fixture(autouse=True)
def no_keys_or_database(monkeypatch: pytest.MonkeyPatch):
    for env_var in (*ProviderConfig.API_KEY_ENV_VARS.values(), "DATABASE_URL"):
        monkeypatch.delenv(env_var, raising=False)


def _run(*args: str, stdin: Optional[str] = None, **env: str):
    return CliRunner().invoke(cli, list(args), input=stdin, env=env)


def test_providers_test_sends_one_request(fake_openai):
    result = _run("providers", "test", OPENAI_API_KEY="sk-test")

    assert result.exit_code == 0, result.output
    assert fake_openai.calls("generate") == 1
    assert f"[OK] OpenAI: {ProviderConfig.DEFAULT_MODELS['openai']}" in result.stdout
    assert f"{fake_openai.chat_tokens()} tokens" in result.stdout


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "API key rejected (401). Check OPENAI_API_KEY"), (404, "request rejected (404). Check the model id")],
)
def test_providers_test_explains_a_failure_and_exits_1(fake_openai, status, message):
    fake_openai.chat_status = status

    result = _run("providers", "test", "--provider", "openai", OPENAI_API_KEY="sk-invalid")

    assert result.exit_code == 1
    assert f"[ERROR] OpenAI: {message}" in result.stdout
    assert "[OK]" not in result.stdout


def test_providers_test_without_a_key_exits_1():
    assert _run("providers", "test").exit_code == 1
    assert "ANTHROPIC_API_KEY" in _run("providers", "test", "--provider", "anthropic").stdout


def test_validate_fails_when_the_key_is_rejected(fake_openai):
    fake_openai.chat_status = 401

    result = _run("validate", OPENAI_API_KEY="sk-invalid")

    assert result.exit_code == 1
    assert "API key rejected" in result.stdout
    assert "Tests passed: 0/1" in result.stdout


def test_validate_passes_after_a_real_request(fake_openai):
    result = _run("validate", OPENAI_API_KEY="sk-test")

    assert result.exit_code == 0, result.output
    assert fake_openai.calls("generate") == 1
    assert "Tests passed: 1/1" in result.stdout


def test_validate_with_nothing_configured_exits_1():
    result = _run("validate")

    assert result.exit_code == 1
    assert "Nothing to validate" in result.stdout


def test_setup_checks_gemini_under_its_provider_name():
    with patch("nlp2sql.cli.check_provider", new=AsyncMock(return_value="gemini-x, 0.4s, 120 tokens")) as check:
        result = _run("setup", stdin="y\nn\n", GOOGLE_API_KEY="AIza-test-key")

    assert result.exit_code == 0, result.output
    check.assert_awaited_once_with("gemini", "AIza-test-key")
    assert "[OK] Gemini: gemini-x, 0.4s, 120 tokens" in result.stdout


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ImportError("No module named 'anthropic'"), "pip install nlp2sql[anthropic]"),
        (ProviderRateLimitError("slow down", {"status_code": 429}), "rate limited or out of quota"),
        (ProviderUnavailableError("connection refused"), "unreachable or unavailable"),
    ],
)
def test_failures_are_described_by_type(error, message):
    assert message in describe_provider_failure("anthropic", error)


def test_create_ai_provider_builds_only_the_adapter(isolated_caches):
    provider = create_ai_provider(ProviderConfig(provider="openai", api_key="sk-test", model="gpt-x", max_tokens=99))

    assert isinstance(provider, OpenAIAdapter)
    assert (provider.model, provider.max_tokens) == ("gpt-x", 99)
    assert list(isolated_caches.iterdir()) == []


def test_create_query_service_still_rejects_unknown_providers():
    with pytest.raises(NotImplementedError, match="'google' not supported"):
        create_query_service("postgresql://u:p@localhost/db", ai_provider="google", api_key="x")


def test_create_ai_provider_is_exported():
    assert "create_ai_provider" in nlp2sql.__all__
