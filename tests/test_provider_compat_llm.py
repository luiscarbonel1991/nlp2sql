"""Live-key compatibility gate for the default provider models.

Run with real keys before merging a default-model change:

    uv run pytest -m llm tests/test_provider_compat_llm.py -ra

Every test skips when its API key is absent. Tests named ``test_*`` with
assertions are the gate; tests named ``diag_*`` (inside the ``test_`` wrappers)
report observed provider behavior through ``pytest.skip`` so ``-ra`` shows it
without failing the run. Override the OpenAI model under test with
``NLP2SQL_TEST_OPENAI_MODEL``.
"""

import json
import os

import pytest

from nlp2sql.core.provider_config import ProviderConfig
from nlp2sql.ports.ai_provider import QueryContext

pytestmark = pytest.mark.llm

OPENAI_MODEL = os.getenv("NLP2SQL_TEST_OPENAI_MODEL", ProviderConfig.DEFAULT_MODELS["openai"])
ANTHROPIC_MODEL = ProviderConfig.DEFAULT_MODELS["anthropic"]
GEMINI_MODEL = ProviderConfig.DEFAULT_MODELS["gemini"]

SCHEMA = "CREATE TABLE users (id INT PRIMARY KEY, email TEXT, is_active BOOLEAN);"
QUESTION = "How many active users are there?"
JSON_ONLY = 'Reply with exactly this JSON and nothing else: {"ok": true}'


def _require_key(env_var: str) -> str:
    key = os.getenv(env_var)
    if not key:
        pytest.skip(f"{env_var} not set")
    return key


def _context(max_tokens: int = 1000) -> QueryContext:
    return QueryContext(
        question=QUESTION,
        database_type="postgres",
        schema_context=SCHEMA,
        examples=[],
        max_tokens=max_tokens,
    )


def _report(message: str) -> None:
    """Surface a diagnostic outcome in the ``-ra`` summary without failing."""
    pytest.skip(message)


# ── OpenAI ─────────────────────────────────────────────────────────────────


class TestOpenAICompat:
    @pytest.fixture
    def client(self):
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=_require_key("OPENAI_API_KEY"))

    @staticmethod
    def _messages(user: str = JSON_ONLY):
        return [{"role": "system", "content": "You are a JSON-only responder."}, {"role": "user", "content": user}]

    @pytest.mark.asyncio
    async def test_o1_temperature_diagnostic(self, client):
        """Is a non-default temperature accepted on the default model?"""
        try:
            await client.chat.completions.create(
                model=OPENAI_MODEL, messages=self._messages(), max_completion_tokens=64, temperature=0.1
            )
        except Exception as exc:  # BadRequestError expected
            _report(f"O1 {OPENAI_MODEL}: temperature=0.1 REJECTED (expected; adapter omits it): {exc}")
        _report(f"O1 {OPENAI_MODEL}: temperature=0.1 ACCEPTED (adapter still omits it; consider the sampling list)")

    @pytest.mark.asyncio
    async def test_o2_max_tokens_diagnostic(self, client):
        """Does the deprecated max_tokens still work? (adapter uses max_completion_tokens either way)"""
        try:
            await client.chat.completions.create(model=OPENAI_MODEL, messages=self._messages(), max_tokens=64)
        except Exception as exc:
            _report(f"O2 {OPENAI_MODEL}: max_tokens REJECTED (expected): {exc}")
        _report(f"O2 {OPENAI_MODEL}: max_tokens still ACCEPTED")

    @pytest.mark.asyncio
    async def test_o3_reasoning_effort_accepted(self, client):
        """At least one of reasoning_effort none/low must be accepted; report which."""
        accepted = {}
        for effort in ("none", "low"):
            try:
                response = await client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=self._messages(),
                    max_completion_tokens=64,
                    reasoning_effort=effort,
                )
                details = getattr(response.usage, "completion_tokens_details", None)
                accepted[effort] = getattr(details, "reasoning_tokens", None)
            except Exception as exc:
                accepted[effort] = f"rejected: {exc}"
        assert any(not str(v).startswith("rejected") for v in accepted.values()), accepted
        _report(f"O3 {OPENAI_MODEL}: reasoning_effort outcomes (value=reasoning_tokens or rejection): {accepted}")

    @pytest.mark.asyncio
    async def test_o4_adapter_kwargs_accepted(self, client):
        """The exact kwargs the adapter sends must be accepted and yield valid JSON."""
        from nlp2sql.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key=os.environ["OPENAI_API_KEY"], model=OPENAI_MODEL)
        kwargs = adapter._completion_kwargs(max_tokens=64, temperature=0.0)
        response = await client.chat.completions.create(messages=self._messages(), **kwargs)
        content = response.choices[0].message.content
        assert content, f"empty content, finish_reason={response.choices[0].finish_reason}"
        assert json.loads(content) == {"ok": True}

    @pytest.mark.asyncio
    async def test_o6_adapter_generates_sql_within_budget(self):
        """Real prompt, max_tokens=1000: must finish normally with non-empty SQL."""
        from nlp2sql.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key=_require_key("OPENAI_API_KEY"), model=OPENAI_MODEL)
        response = await adapter.generate_query(_context(max_tokens=1000))
        assert response.sql
        assert response.metadata["finish_reason"] == "stop", response.metadata
        _report(
            f"O6 {OPENAI_MODEL}: ok; reasoning_tokens={response.metadata.get('reasoning_tokens')} "
            f"completion_tokens={response.metadata.get('completion_tokens')} sql={response.sql!r}"
        )


# ── Anthropic ──────────────────────────────────────────────────────────────


class TestAnthropicCompat:
    @pytest.fixture
    def client(self):
        import anthropic

        return anthropic.AsyncAnthropic(api_key=_require_key("ANTHROPIC_API_KEY"))

    @pytest.mark.asyncio
    async def test_a1_temperature_diagnostic(self, client):
        """Documents why the adapter omits temperature (400 expected on Claude 4.7+)."""
        try:
            await client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=64,
                system="You are a JSON-only responder.",
                messages=[{"role": "user", "content": JSON_ONLY}],
                temperature=0.1,
            )
        except TypeError as exc:
            _report(f"A1 {ANTHROPIC_MODEL}: SDK removed the temperature kwarg (SDK >= 1.0): {exc}")
        except Exception as exc:
            _report(f"A1 {ANTHROPIC_MODEL}: temperature=0.1 REJECTED by the API (expected): {exc}")
        _report(f"A1 {ANTHROPIC_MODEL}: temperature=0.1 still ACCEPTED (deprecation not enforced yet)")

    @pytest.mark.asyncio
    async def test_a2_baseline_without_temperature(self, client):
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=64,
            system="You are a JSON-only responder.",
            messages=[{"role": "user", "content": JSON_ONLY}],
        )
        text = response.content[0].text
        assert text
        assert json.loads(text) == {"ok": True}
        assert response.usage.output_tokens < 64

    @pytest.mark.asyncio
    async def test_a5_adapter_generates_sql(self):
        from nlp2sql.adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key=_require_key("ANTHROPIC_API_KEY"))
        response = await adapter.generate_query(_context(max_tokens=1000))
        assert response.sql
        _report(f"A5 {ANTHROPIC_MODEL}: ok; output_tokens={response.metadata['output_tokens']} sql={response.sql!r}")


# ── Gemini (legacy google-generativeai SDK, v1beta) ────────────────────────


class TestGeminiCompat:
    @pytest.fixture
    def model(self):
        import google.generativeai as genai

        genai.configure(api_key=_require_key("GOOGLE_API_KEY"))
        return genai.GenerativeModel(GEMINI_MODEL)

    def test_g1_model_available_on_legacy_sdk(self, model):
        """404/400 here means the legacy SDK cannot use the default model: migrate to google-genai."""
        import google.generativeai as genai

        response = model.generate_content(
            JSON_ONLY, generation_config=genai.types.GenerationConfig(max_output_tokens=256, temperature=0.1)
        )
        assert response.candidates and response.candidates[0].content.parts, "empty candidate"
        assert json.loads(response.text.strip()) == {"ok": True}

    def test_g4_count_tokens(self, model):
        assert model.count_tokens("hello").total_tokens > 0

    @pytest.mark.asyncio
    async def test_g2_adapter_generates_sql_within_budget(self):
        """Thinking cannot be capped on the legacy SDK; the budget must still leave room for the answer."""
        from nlp2sql.adapters.gemini_adapter import GeminiAdapter

        adapter = GeminiAdapter(api_key=_require_key("GOOGLE_API_KEY"))
        outcomes = {}
        for budget in (1000, 2000):
            response = await adapter.generate_query(_context(max_tokens=budget))
            assert response.sql, f"empty SQL at max_tokens={budget}"
            outcomes[budget] = {
                "finish_reason": str(response.metadata.get("finish_reason")),
                "prompt_tokens": response.metadata.get("prompt_tokens"),
                "output_tokens": response.metadata.get("output_tokens"),
            }
        _report(f"G2 {GEMINI_MODEL}: ok; {outcomes}")

    def test_g3_json_mode_diagnostic(self, model):
        """Is response_mime_type=application/json accepted? (optional adapter improvement)"""
        import google.generativeai as genai

        try:
            response = model.generate_content(
                JSON_ONLY,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=256, temperature=0.1, response_mime_type="application/json"
                ),
            )
            json.loads(response.text.strip())
        except Exception as exc:
            _report(f"G3 {GEMINI_MODEL}: response_mime_type REJECTED: {exc}")
        _report(f"G3 {GEMINI_MODEL}: response_mime_type=application/json ACCEPTED")
