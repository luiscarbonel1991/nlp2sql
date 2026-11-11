"""Locks for the default provider models and the model-dependent adapter logic.

No network access: adapters are built with fake keys and SDK clients are mocked.
"""

import asyncio
import logging
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from google.genai import types

from nlp2sql.adapters import anthropic_adapter as anthropic_module
from nlp2sql.adapters import gemini_adapter as gemini_module
from nlp2sql.adapters import openai_adapter as openai_module
from nlp2sql.adapters.anthropic_adapter import AnthropicAdapter
from nlp2sql.adapters.gemini_adapter import GeminiAdapter
from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.config.settings import settings
from nlp2sql.core.provider_config import ProviderConfig
from nlp2sql.exceptions import ProviderException, ProviderRequestError, ProviderResponseFormatError
from nlp2sql.ports.ai_provider import QueryContext

EXPECTED_DEFAULTS = {
    "openai": "gpt-5.6-luna",
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-3.8-flash",
}

SCHEMA = "CREATE TABLE users (id INT PRIMARY KEY, email TEXT, is_active BOOLEAN);"


def _context(**overrides) -> QueryContext:
    params = {
        "question": "How many active users are there?",
        "database_type": "postgres",
        "schema_context": SCHEMA,
        "examples": [],
    }
    params.update(overrides)
    return QueryContext(**params)


@contextmanager
def capture_logs():
    """Records emitted through the nlp2sql loggers, as {"log_level", "event"} dicts."""
    records: list[dict] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append({"log_level": record.levelname.lower(), "event": record.getMessage()})

    logger = logging.getLogger("nlp2sql")
    handler, previous_level = _Collect(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _warnings(logs, needle: str):
    return [entry for entry in logs if entry["log_level"] == "warning" and needle in entry["event"]]


# ── Default IDs: one source of truth ────────────────────────────────────────


class TestDefaultModelIds:
    def test_default_model_ids_locked(self):
        assert ProviderConfig.DEFAULT_MODELS == EXPECTED_DEFAULTS

    def test_adapters_read_defaults_from_provider_config(self):
        assert OpenAIAdapter.DEFAULT_MODEL == ProviderConfig.DEFAULT_MODELS["openai"]
        assert AnthropicAdapter.DEFAULT_MODEL == ProviderConfig.DEFAULT_MODELS["anthropic"]
        assert GeminiAdapter.DEFAULT_MODEL == ProviderConfig.DEFAULT_MODELS["gemini"]

    def test_settings_read_defaults_from_provider_config(self):
        for provider, model in EXPECTED_DEFAULTS.items():
            assert settings.get_provider_config(provider)["model"] == model

    def test_readme_defaults_table_matches_code(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        for model in EXPECTED_DEFAULTS.values():
            assert f"`{model}`" in readme, f"README does not mention default model {model}"

    def test_cli_providers_list_shows_current_defaults(self):
        from nlp2sql.cli import cli

        result = CliRunner().invoke(cli, ["providers", "list"])
        assert result.exit_code == 0, result.output
        for model in EXPECTED_DEFAULTS.values():
            assert model in result.output


# ── Context limits and fallbacks ───────────────────────────────────────────


class TestContextLimits:
    def test_openai_default_context_limit(self):
        adapter = OpenAIAdapter(api_key="sk-test")
        assert adapter.get_max_context_size() == 922_000

    def test_anthropic_default_context_limit(self):
        adapter = AnthropicAdapter(api_key="sk-test")
        assert adapter.get_max_context_size() == 1_000_000

    @patch("nlp2sql.adapters.gemini_adapter.genai")
    def test_gemini_default_context_limit(self, mock_genai):
        adapter = GeminiAdapter(api_key="test-key")
        assert adapter.get_max_context_size() == 1_048_576

    def test_openai_unknown_model_falls_back_and_warns(self):
        with capture_logs() as logs:
            adapter = OpenAIAdapter(api_key="sk-test", model="totally-unknown-model")
        assert adapter.get_max_context_size() == openai_module.DEFAULT_CONTEXT_LIMIT == 128_000
        assert len(_warnings(logs, "fallback context limit")) == 1

    def test_openai_dated_snapshot_resolves_by_family(self):
        with capture_logs() as logs:
            adapter = OpenAIAdapter(api_key="sk-test", model="gpt-4o-2024-08-06")
        assert adapter.get_max_context_size() == 128_000
        assert not _warnings(logs, "fallback context limit")

    def test_anthropic_unknown_model_falls_back_and_warns(self):
        with capture_logs() as logs:
            adapter = AnthropicAdapter(api_key="sk-test", model="claude-future-9")
        assert adapter.get_max_context_size() == anthropic_module.DEFAULT_CONTEXT_LIMIT == 200_000
        assert len(_warnings(logs, "fallback context limit")) == 1

    @patch("nlp2sql.adapters.gemini_adapter.genai")
    def test_gemini_family_resolves_without_warning(self, mock_genai):
        with capture_logs() as logs:
            adapter = GeminiAdapter(api_key="test-key", model="gemini-9.9-ultra")
        assert adapter.get_max_context_size() == gemini_module.GEMINI_FAMILY_CONTEXT_LIMIT == 1_048_576
        assert not _warnings(logs, "fallback context limit")

    @patch("nlp2sql.adapters.gemini_adapter.genai")
    def test_gemini_non_gemini_name_falls_back_and_warns(self, mock_genai):
        with capture_logs() as logs:
            adapter = GeminiAdapter(api_key="test-key", model="gemma-3-27b")
        assert adapter.get_max_context_size() == gemini_module.DEFAULT_CONTEXT_LIMIT == 32_768
        assert len(_warnings(logs, "fallback context limit")) == 1

    @patch("nlp2sql.adapters.gemini_adapter.genai")
    def test_gemini_models_prefix_is_normalized(self, mock_genai):
        with capture_logs() as logs:
            adapter = GeminiAdapter(api_key="test-key", model="models/gemini-3.6-flash")
        assert adapter.model_name == "models/gemini-3.6-flash"
        assert adapter.get_max_context_size() == 1_048_576
        assert not _warnings(logs, "fallback context limit")


# ── OpenAI tokenizer ───────────────────────────────────────────────────────


class TestOpenAITokenizer:
    def test_default_model_uses_o200k_without_warning(self):
        with capture_logs() as logs:
            adapter = OpenAIAdapter(api_key="sk-test")
        assert adapter.encoding.name == "o200k_base"
        assert not _warnings(logs, "fallback encoding")

    def test_unknown_model_falls_back_to_o200k_and_warns(self):
        with capture_logs() as logs:
            adapter = OpenAIAdapter(api_key="sk-test", model="totally-unknown-model")
        assert adapter.encoding.name == "o200k_base"
        assert len(_warnings(logs, "fallback encoding")) == 1

    def test_exact_tiktoken_mapping_still_wins(self):
        adapter = OpenAIAdapter(api_key="sk-test", model="gpt-4")
        assert adapter.encoding.name == "cl100k_base"


# ── OpenAI request kwargs ──────────────────────────────────────────────────


class TestOpenAIRequestKwargs:
    def test_reasoning_model_kwargs(self):
        adapter = OpenAIAdapter(api_key="sk-test")
        kwargs = adapter._completion_kwargs(max_tokens=500, temperature=0.2)
        assert kwargs["model"] == ProviderConfig.DEFAULT_MODELS["openai"]
        assert kwargs["max_completion_tokens"] == 500
        assert "max_tokens" not in kwargs
        assert kwargs["reasoning_effort"] == "low"
        assert "temperature" not in kwargs
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_sampling_model_kwargs(self):
        adapter = OpenAIAdapter(api_key="sk-test", model="gpt-4o-mini")
        kwargs = adapter._completion_kwargs(max_tokens=500, temperature=0.2)
        assert kwargs["max_completion_tokens"] == 500
        assert kwargs["temperature"] == 0.2
        assert "reasoning_effort" not in kwargs

    def test_unknown_model_is_treated_as_reasoning_model(self):
        adapter = OpenAIAdapter(api_key="sk-test", model="gpt-7-future")
        kwargs = adapter._completion_kwargs(max_tokens=10, temperature=0.0)
        assert "temperature" not in kwargs
        assert kwargs["reasoning_effort"] == "low"

    def test_explicit_reasoning_effort_is_forwarded(self):
        adapter = OpenAIAdapter(api_key="sk-test", reasoning_effort="none")
        assert adapter._completion_kwargs(max_tokens=10, temperature=0.0)["reasoning_effort"] == "none"

    @pytest.mark.asyncio
    async def test_generate_query_sends_reasoning_kwargs_and_reports_reasoning_tokens(self):
        adapter = OpenAIAdapter(api_key="sk-test")
        fake = MagicMock()
        fake.choices = [
            MagicMock(finish_reason="stop", message=MagicMock(content='{"sql": "SELECT COUNT(*) FROM users"}'))
        ]
        fake.usage.prompt_tokens = 10
        fake.usage.completion_tokens = 5
        fake.usage.total_tokens = 15
        fake.usage.completion_tokens_details.reasoning_tokens = 3
        adapter.client.chat.completions.create = AsyncMock(return_value=fake)

        response = await adapter.generate_query(_context())

        kwargs = adapter.client.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == _context().max_tokens
        assert "max_tokens" not in kwargs
        assert "temperature" not in kwargs
        assert kwargs["reasoning_effort"] == "low"
        assert response.sql == "SELECT COUNT(*) FROM users"
        assert response.metadata["reasoning_tokens"] == 3
        assert response.metadata["reasoning_effort"] == "low"

    def test_empty_completion_is_actionable(self):
        adapter = OpenAIAdapter(api_key="sk-test")
        fake = MagicMock()
        fake.choices = [MagicMock(finish_reason="length", message=MagicMock(content=None))]
        with pytest.raises(ProviderException, match="max_tokens"):
            adapter._parse_response(fake)


# ── Anthropic request kwargs ───────────────────────────────────────────────


class TestAnthropicRequestKwargs:
    @pytest.mark.asyncio
    async def test_never_sends_sampling_params(self):
        adapter = AnthropicAdapter(api_key="sk-test", temperature=0.0)

        generation = MagicMock()
        generation.content = [MagicMock(text='{"sql": "SELECT COUNT(*) FROM users", "confidence": 0.9}')]
        generation.usage.input_tokens = 10
        generation.usage.output_tokens = 5
        adapter.client.messages.create = AsyncMock(return_value=generation)

        response = await adapter.generate_query(_context())
        kwargs = adapter.client.messages.create.call_args.kwargs
        for forbidden in ("temperature", "top_p", "top_k"):
            assert forbidden not in kwargs
        assert kwargs["model"] == ProviderConfig.DEFAULT_MODELS["anthropic"]
        assert kwargs["max_tokens"] == _context().max_tokens
        assert "system" in kwargs
        assert response.sql == "SELECT COUNT(*) FROM users"

        validation = MagicMock()
        validation.content = [MagicMock(text='{"is_valid": true, "issues": []}')]
        adapter.client.messages.create = AsyncMock(return_value=validation)

        result = await adapter.validate_query("SELECT 1", SCHEMA)
        kwargs = adapter.client.messages.create.call_args.kwargs
        assert "temperature" not in kwargs
        assert result["is_valid"] is True

    def test_explicit_temperature_logs_info(self):
        with capture_logs() as logs:
            adapter = AnthropicAdapter(api_key="sk-test", temperature=0.0)
        assert adapter.temperature == 0.0
        assert any(e["log_level"] == "info" and "does not forward temperature" in e["event"] for e in logs)

        with capture_logs() as logs:
            AnthropicAdapter(api_key="sk-test")
        assert not any("does not forward temperature" in e["event"] for e in logs)


# ── Gemini response guards ─────────────────────────────────────────────────


def _gemini_response(parts=None, finish_reason="STOP", block_reason=None) -> types.GenerateContentResponse:
    """A real SDK response object, as ``generate_content`` returns it."""
    if block_reason:
        return types.GenerateContentResponse(
            prompt_feedback=types.GenerateContentResponsePromptFeedback(block_reason=block_reason)
        )
    content = types.Content(role="model", parts=parts) if parts is not None else None
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content, finish_reason=finish_reason)])


class TestGeminiResponseGuards:
    def test_empty_candidate_is_actionable(self):
        adapter = GeminiAdapter(api_key="test-key")
        with pytest.raises(ProviderException, match="MAX_TOKENS"):
            adapter._parse_response(_gemini_response(parts=None, finish_reason="MAX_TOKENS"))

    def test_no_candidates_is_actionable(self):
        adapter = GeminiAdapter(api_key="test-key")
        with pytest.raises(ProviderException, match="no response candidates"):
            adapter._parse_response(types.GenerateContentResponse(candidates=[]))

    def test_blocked_prompt_is_a_request_error(self):
        adapter = GeminiAdapter(api_key="test-key")
        with pytest.raises(ProviderRequestError, match="blocked the prompt"):
            adapter._parse_response(_gemini_response(block_reason="SAFETY"))

    def test_thought_parts_are_not_part_of_the_answer(self):
        adapter = GeminiAdapter(api_key="test-key")
        parts = [
            types.Part(text="Let me think about the schema.", thought=True),
            types.Part(text='{"sql": "SELECT 1"}'),
        ]
        assert adapter._parse_response(_gemini_response(parts=parts))["sql"] == "SELECT 1"

    def test_only_thoughts_is_a_format_error(self):
        adapter = GeminiAdapter(api_key="test-key")
        parts = [types.Part(text="Still thinking.", thought=True)]
        with pytest.raises(ProviderResponseFormatError, match="no content"):
            adapter._parse_response(_gemini_response(parts=parts))


# ── Gemini request (real google-genai SDK against a local fake API) ─────────


class TestGeminiRequest:
    @pytest.mark.asyncio
    async def test_request_shape(self, fake_gemini):
        adapter = GeminiAdapter(api_key="test-key", model="gemini-3.8-flash")

        response = await adapter.generate_query(_context(max_tokens=1500))

        request = fake_gemini.last()
        assert request["version"] == gemini_module.GEMINI_API_VERSION == "v1"
        assert request["model"] == "gemini-3.8-flash"
        assert request["api_key"] == "test-key"
        config = request["body"]["generationConfig"]
        assert config["maxOutputTokens"] == 1500
        assert config["responseMimeType"] == "application/json"
        assert config["thinkingConfig"] == {"thinking_level": "LOW"}
        for not_sent in ("temperature", "candidateCount", "topP", "topK"):
            assert not_sent not in config
        assert request["body"]["systemInstruction"]["parts"][0]["text"].startswith("You are an expert SQL")
        assert "Question: How many active users are there?" in request["prompt"]
        assert response.sql == fake_gemini.sql
        # Only generateContent: no countTokens round trip before the question
        assert [entry["kind"] for entry in fake_gemini.requests] == ["generate"]

    @pytest.mark.asyncio
    async def test_thinking_tokens_are_counted(self, fake_gemini):
        fake_gemini.thoughts_tokens = 40
        adapter = GeminiAdapter(api_key="test-key")

        response = await adapter.generate_query(_context())

        usage = fake_gemini.last()["usage"]
        assert response.metadata["thinking_tokens"] == 40
        assert response.metadata["prompt_tokens"] == usage["promptTokenCount"]
        assert response.metadata["output_tokens"] == usage["candidatesTokenCount"]
        assert response.tokens_used == usage["totalTokenCount"]
        assert response.metadata["finish_reason"] == "STOP"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("model", ["gemini-3.6-flash", "gemini-2.5-flash", "models/gemini-3.6-flash"])
    async def test_models_without_a_known_level_keep_their_default(self, fake_gemini, model):
        adapter = GeminiAdapter(api_key="test-key", model=model)

        await adapter.generate_query(_context())

        assert "thinkingConfig" not in fake_gemini.last()["body"]["generationConfig"]

    @pytest.mark.asyncio
    async def test_explicit_temperature_is_logged_and_not_sent(self, fake_gemini):
        with capture_logs() as logs:
            adapter = GeminiAdapter(api_key="test-key", temperature=0.0)
        assert adapter.temperature == 0.0
        assert any(e["log_level"] == "info" and "does not forward temperature" in e["event"] for e in logs)

        await adapter.generate_query(_context(temperature=0.0))
        assert "temperature" not in fake_gemini.last()["body"]["generationConfig"]

        with capture_logs() as logs:
            GeminiAdapter(api_key="test-key")
        assert not any("does not forward temperature" in e["event"] for e in logs)

    @pytest.mark.asyncio
    async def test_validate_query_reports_its_tokens(self, fake_gemini):
        adapter = GeminiAdapter(api_key="test-key")

        result = await adapter.validate_query("SELECT COUNT(*) FROM users", SCHEMA)

        assert result["is_valid"] is True
        assert result["_tokens_used"] == fake_gemini.last("validate")["usage"]["totalTokenCount"]
        assert fake_gemini.last("validate")["body"]["generationConfig"]["maxOutputTokens"] == 1000

    def test_one_adapter_works_across_event_loops(self, fake_gemini):
        """Regression: the SDK's async client failed the 2nd asyncio.run() with "Event loop is closed"."""
        adapter = GeminiAdapter(api_key="test-key")

        for _ in range(3):
            assert asyncio.run(adapter.generate_query(_context())).sql == fake_gemini.sql
        assert fake_gemini.calls("generate") == 3
