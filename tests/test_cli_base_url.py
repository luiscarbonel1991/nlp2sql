"""`--base-url` in the CLI: `query`, `providers test` and `benchmark` against another endpoint.

The endpoint is a local fake API. Only a key given with `--api-key` is sent to it: the
OpenAI key of the environment is for OpenAI.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import click
import pytest
from click.testing import CliRunner, Result
from fakes.fake_openai import FakeOpenAI

from nlp2sql import ProviderConfig
from nlp2sql.cli import ENDPOINT_KEY, benchmark_targets, cli, resolve_api_key
from nlp2sql.config.settings import settings

ENVIRONMENT_KEY = "sk-key-from-the-environment"
LOCAL_MODEL = "llama3.2"
DB_URL = "postgresql://user:pass@localhost:5432/db"
EXAMPLES = json.dumps([{"question": "How many users?", "sql": "SELECT COUNT(*) FROM users"}])


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOpenAI]:
    """Another endpoint, and an OpenAI key in the environment that must not reach it."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    for env_var in ProviderConfig.API_KEY_ENV_VARS.values():
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", ENVIRONMENT_KEY)
    monkeypatch.setattr(settings, "openai_api_key", ENVIRONMENT_KEY)
    fake = FakeOpenAI().start()
    yield fake
    fake.stop()


def _run(*args: str) -> Result:
    return CliRunner().invoke(cli, list(args))


def _service() -> MagicMock:
    service = MagicMock()
    service.generate_sql = AsyncMock(
        return_value={"sql": "SELECT 1", "confidence": 0.9, "tokens_used": 42, "validation": {"is_valid": True}}
    )
    return service


def _query(*args: str) -> tuple[Result, dict[str, Any], dict[str, Any]]:
    """Run `query` without a database; return what it built the service and the example store with."""
    with (
        patch("nlp2sql.cli.create_and_initialize_service", new_callable=AsyncMock, return_value=_service()) as service,
        patch("nlp2sql.cli.create_example_store_from_payload", new_callable=AsyncMock) as example_store,
    ):
        result = _run("query", "--database-url", DB_URL, "--question", "How many users are there?", *args)
    service_arguments = service.await_args.kwargs if service.await_args else {}
    store_arguments = example_store.await_args.kwargs if example_store.await_args else {}
    return result, service_arguments, store_arguments


class TestProvidersTest:
    def test_it_checks_the_endpoint_with_one_request(self, endpoint: FakeOpenAI) -> None:
        result = _run("providers", "test", "--base-url", endpoint.base_url, "--model", LOCAL_MODEL)

        request = endpoint.requests[-1]
        assert result.exit_code == 0, result.output
        assert f"[OK] OpenAI-compatible endpoint: {LOCAL_MODEL}" in result.stdout
        assert endpoint.calls("generate") == 1
        assert request["body"]["model"] == LOCAL_MODEL
        assert ENVIRONMENT_KEY not in request["authorization"]

    def test_the_key_of_the_endpoint_comes_from_the_option(self, endpoint: FakeOpenAI) -> None:
        _run("providers", "test", "--base-url", endpoint.base_url, "--api-key", "gateway-key")

        assert endpoint.requests[-1]["authorization"] == "Bearer gateway-key"

    def test_a_rejected_key_points_at_the_option(self, endpoint: FakeOpenAI) -> None:
        endpoint.chat_status = 401

        result = _run("providers", "test", "--base-url", endpoint.base_url, "--api-key", "wrong-key")

        assert result.exit_code == 1
        assert "[ERROR] OpenAI-compatible endpoint: API key rejected (401). Check --api-key" in result.stdout

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            (["--provider", "anthropic", "--base-url", "http://localhost:11434/v1"], "only for --provider openai"),
            (["--model", LOCAL_MODEL], "used with --base-url"),
            (["--api-key", "gateway-key"], "used with --base-url"),
        ],
        ids=["another-provider", "model-alone", "api-key-alone"],
    )
    def test_options_that_do_not_fit_are_a_usage_error(self, args: list[str], message: str) -> None:
        result = _run("providers", "test", *args)

        assert result.exit_code == click.UsageError.exit_code
        assert message in result.output


class TestQuery:
    def test_base_url_reaches_the_provider_config(self, endpoint: FakeOpenAI) -> None:
        result, service_arguments, _ = _query("--base-url", endpoint.base_url, "--model", LOCAL_MODEL)

        config = service_arguments["provider_config"]
        assert result.exit_code == 0, result.output
        assert (config.provider, config.base_url, config.model) == ("openai", endpoint.base_url, LOCAL_MODEL)

    def test_no_key_is_needed_and_the_environment_key_is_not_used(self, endpoint: FakeOpenAI) -> None:
        result, service_arguments, _ = _query("--base-url", endpoint.base_url)

        assert result.exit_code == 0, result.output
        assert service_arguments["provider_config"].api_key is None

    def test_without_base_url_the_environment_key_is_used(self, endpoint: FakeOpenAI) -> None:
        _, service_arguments, _ = _query()

        assert service_arguments["provider_config"].api_key == ENVIRONMENT_KEY

    def test_another_provider_with_base_url_is_a_usage_error(self) -> None:
        result, service_arguments, _ = _query("--provider", "gemini", "--base-url", "http://localhost:11434/v1")

        assert result.exit_code == click.UsageError.exit_code
        assert service_arguments == {}

    @pytest.mark.parametrize(
        ("provider_args", "key_for_embeddings"),
        [
            (["--api-key", "sk-openai"], "sk-openai"),
            (["--api-key", "gateway-key", "--base-url", "http://localhost:11434/v1"], None),
            (["--provider", "anthropic", "--api-key", "sk-ant"], None),
        ],
        ids=["openai", "another-endpoint", "anthropic"],
    )
    def test_openai_embeddings_only_reuse_a_key_for_openai(
        self, provider_args: list[str], key_for_embeddings: str | None
    ) -> None:
        _, _, store_arguments = _query(*provider_args, "--embedding-provider", "openai", "--examples-json", EXAMPLES)

        assert store_arguments["api_key"] == key_for_embeddings


class TestBenchmark:
    def test_the_endpoint_alone_is_the_only_target(self, endpoint: FakeOpenAI) -> None:
        # OPENAI_API_KEY is set, but no hosted provider is called without being asked for
        targets = benchmark_targets(None, endpoint.base_url, LOCAL_MODEL, None)

        assert targets == {
            ENDPOINT_KEY: {"provider": "openai", "api_key": None, "model": LOCAL_MODEL, "base_url": endpoint.base_url}
        }

    def test_the_endpoint_is_measured_next_to_the_listed_providers(self, endpoint: FakeOpenAI) -> None:
        targets = benchmark_targets("openai, anthropic", endpoint.base_url, LOCAL_MODEL, "gateway-key")

        assert list(targets) == ["openai", "anthropic", ENDPOINT_KEY]
        assert targets["openai"] == {"provider": "openai", "api_key": ENVIRONMENT_KEY}
        assert targets[ENDPOINT_KEY]["api_key"] == "gateway-key"

    def test_without_base_url_every_configured_provider_is_a_target(self, endpoint: FakeOpenAI) -> None:
        assert list(benchmark_targets(None, None, None, None)) == ["openai"]

    def test_the_command_measures_the_endpoint(self, endpoint: FakeOpenAI, tmp_path: Path) -> None:
        output = tmp_path / "results.json"
        with patch(
            "nlp2sql.cli.create_and_initialize_service", new_callable=AsyncMock, return_value=_service()
        ) as service:
            result = _run(
                "benchmark", "--database-url", DB_URL, "--base-url", endpoint.base_url, "--model", LOCAL_MODEL,
                "--iterations", "1", "--embedding-provider", "none", "--output-file", str(output),
            )  # fmt: skip

        config = service.await_args.kwargs["provider_config"]
        assert result.exit_code == 0, result.output
        assert service.await_count == 1
        assert (config.base_url, config.model, config.api_key) == (endpoint.base_url, LOCAL_MODEL, None)
        assert "[OK] OpenAI-compatible endpoint completed" in result.output
        assert list(json.loads(output.read_text())) == [ENDPOINT_KEY]

    def test_model_without_base_url_is_a_usage_error(self) -> None:
        result = _run("benchmark", "--database-url", DB_URL, "--model", LOCAL_MODEL)

        assert result.exit_code == click.UsageError.exit_code


def test_only_the_option_gives_the_key_of_another_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", ENVIRONMENT_KEY)

    assert resolve_api_key("openai", None, None) == ENVIRONMENT_KEY
    assert resolve_api_key("openai", "sk-given", None) == "sk-given"
    assert resolve_api_key("openai", None, "http://localhost:11434/v1") is None
    assert resolve_api_key("openai", "gateway-key", "http://localhost:11434/v1") == "gateway-key"
