"""Google Gemini adapter for query generation.

Uses the ``google-genai`` SDK and the stateless ``generateContent`` endpoint, pinned to
the stable ``v1`` API version. The SDK's own default depends on its release (``v1beta``
up to 2.x, ``v1`` from 3.0), and pip picks the release by Python version, so without the
pin the same nlp2sql would call different API versions on Python 3.10 and 3.12.

Requests run on the SDK's synchronous client in a worker thread. The asynchronous
client keeps pooled keep-alive connections bound to the event loop that opened them:
reusing one adapter across ``asyncio.run()`` calls failed with "Event loop is closed"
(the same class of bug as issue #35).

Not sent: ``temperature`` (Gemini 3.6 and later ignore it) and ``candidate_count``
(Gemini 3 does not support it). Thinking tokens count against ``max_output_tokens``, so
a too-small response budget surfaces as a truncated or empty answer; the adapter
reports that as an actionable error.
"""

import asyncio
import json
from typing import Any, Dict, NamedTuple, Optional

from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config.settings import settings
from ..core.provider_config import ProviderConfig
from ..exceptions import ProviderException, ProviderRequestError, ProviderResponseFormatError, TokenLimitException
from ..ports.ai_provider import AIProviderPort, AIProviderType, QueryContext, QueryResponse, validation_unavailable
from ..utils.helpers import first_not_none
from ..utils.logger import get_logger
from ..utils.semantic_prompt import format_semantic_context_lines, format_sql_intent_plan_lines
from ._provider_errors import TRANSIENT_PROVIDER_ERRORS, call_with_format_retry, classify_provider_error
from ._provider_validation import validation_from_json

logger = get_logger(__name__)

GEMINI_API_VERSION = "v1"

# Maximum input tokens per model. Legacy rows are kept so users who pin an
# older (or retired) model keep an accurate budget.
CONTEXT_LIMITS: Dict[str, int] = {
    "gemini-3.8-flash": 1_048_576,
    "gemini-3.6-flash": 1_048_576,
    "gemini-3.1-flash-lite": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    "gemini-2.0-pro": 1_048_576,
    "gemini-1.5-pro": 1_048_576,
    "gemini-1.5-flash": 1_048_576,
    "gemini-pro": 30_720,
    "gemini-pro-vision": 16_384,
}
# Every documented Gemini model since 1.5 has at least a 1M input window.
GEMINI_FAMILY_CONTEXT_LIMIT = 1_048_576
# Conservative floor for non-Gemini names served through the same API (gemma,
# tuned models). The previous 30,720 fallback was wrong for every Gemini model.
DEFAULT_CONTEXT_LIMIT = 32_768

# Thinking level sent per model; models not listed keep their own default (medium for
# 3.6 and 3.8). The accepted levels differ by model: gemini-3.8-flash takes low, medium
# and high ("minimal" is an error). gemini-3.6-flash also accepts "low" (live gate G4,
# 2026-11-10), but its SQL was measured only at its default, so it keeps it.
THINKING_LEVELS: Dict[str, types.ThinkingLevel] = {
    "gemini-3.8-flash": types.ThinkingLevel.LOW,
}

# Finish reasons where Gemini withheld the answer; asking again would not help.
_BLOCKED_FINISH_REASONS = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}

VALIDATION_MAX_TOKENS = 1000


class UsageTokens(NamedTuple):
    prompt: int
    output: int
    thinking: int

    @property
    def total(self) -> int:
        return self.prompt + self.output + self.thinking


class GeminiAdapter(AIProviderPort):
    """Google Gemini adapter for natural language to SQL generation.

    A ``temperature`` passed to the constructor is kept for backward compatibility but
    not forwarded: Gemini 3.6 and later models ignore it.
    """

    DEFAULT_MODEL = ProviderConfig.DEFAULT_MODELS["gemini"]
    DEFAULT_MAX_TOKENS = 2000
    DEFAULT_TEMPERATURE = 0.1

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        self.api_key = api_key or settings.google_api_key
        if not self.api_key:
            raise ProviderException("Google API key is required")

        self.model_name = model or self.DEFAULT_MODEL
        self.max_tokens = first_not_none(max_tokens, self.DEFAULT_MAX_TOKENS)
        self.temperature = first_not_none(temperature, self.DEFAULT_TEMPERATURE)
        self._max_context_size = self._resolve_context_limit(self.model_name)
        self._thinking_level = THINKING_LEVELS.get(self._normalize_model_name(self.model_name))

        if temperature is not None:
            # INFO, not WARNING: the CLI always forwards its --temperature default.
            logger.info(
                "Gemini adapter does not forward temperature (ignored by Gemini 3.6+ models)",
                model=self.model_name,
                temperature=temperature,
            )

        self.client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(api_version=GEMINI_API_VERSION))

        logger.debug(
            "Provider configured",
            provider="gemini",
            model=self.model_name,
            api_version=GEMINI_API_VERSION,
            max_tokens=self.max_tokens,
            thinking_level=self._thinking_level.value if self._thinking_level else None,
            context_limit=self._max_context_size,
        )

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.GEMINI

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        """The API accepts both ``gemini-x`` and ``models/gemini-x``; look up the bare name."""
        return model_name[len("models/") :] if model_name.startswith("models/") else model_name

    @classmethod
    def _resolve_context_limit(cls, model_name: str) -> int:
        """Exact match, then the Gemini family limit, then a logged fallback."""
        name = cls._normalize_model_name(model_name)
        if name in CONTEXT_LIMITS:
            return CONTEXT_LIMITS[name]
        if name.startswith("gemini-"):
            logger.debug(
                "Resolved context limit by model family",
                model=model_name,
                context_limit=GEMINI_FAMILY_CONTEXT_LIMIT,
            )
            return GEMINI_FAMILY_CONTEXT_LIMIT
        logger.warning(
            "Unknown Gemini model; using fallback context limit",
            model=model_name,
            context_limit=DEFAULT_CONTEXT_LIMIT,
            hint="pin a model listed in gemini_adapter.CONTEXT_LIMITS or add it",
        )
        return DEFAULT_CONTEXT_LIMIT

    def get_token_count(self, text: str) -> int:
        """Estimate token count for Gemini models (about 4 characters per token).

        A local estimate, like the Anthropic adapter: the API's countTokens would add a
        network round trip to every question, and the API enforces the real limit.
        """
        return len(text) // 4

    def get_max_context_size(self) -> int:
        """Get maximum input context size for the model."""
        return self._max_context_size

    def _generation_config(self, system_instruction: str, max_output_tokens: int) -> types.GenerateContentConfig:
        thinking_config = types.ThinkingConfig(thinking_level=self._thinking_level) if self._thinking_level else None
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            thinking_config=thinking_config,
        )

    async def _generate(self, prompt: str, config: types.GenerateContentConfig) -> types.GenerateContentResponse:
        return await asyncio.to_thread(
            self.client.models.generate_content, model=self.model_name, contents=prompt, config=config
        )

    @staticmethod
    def _finish_name(candidate: types.Candidate) -> Optional[str]:
        finish_reason = getattr(candidate, "finish_reason", None)
        return getattr(finish_reason, "name", finish_reason)

    @classmethod
    def _extract_text(cls, response: types.GenerateContentResponse) -> str:
        """Return the first candidate's answer text, or raise an actionable error.

        Thought parts are skipped. A candidate has no text when thinking tokens exhaust
        ``max_output_tokens`` or a safety filter fires.
        """
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            feedback = getattr(response, "prompt_feedback", None)
            block_reason = getattr(feedback, "block_reason", None)
            if block_reason:
                block_name = getattr(block_reason, "name", block_reason)
                raise ProviderRequestError(f"Gemini blocked the prompt (block_reason={block_name})")
            raise ProviderException("Gemini returned no response candidates")
        candidate = candidates[0]
        finish_name = cls._finish_name(candidate)
        if finish_name == "MAX_TOKENS":
            # An answer cut at max_tokens would be cut again, so it is not retried.
            raise ProviderException(
                "Gemini response truncated at max_tokens (finish_reason=MAX_TOKENS); "
                "raise max_tokens (thinking tokens count against the output budget)"
            )
        if finish_name in _BLOCKED_FINISH_REASONS:
            raise ProviderRequestError(f"Gemini blocked the response (finish_reason={finish_name})")
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        text = "".join(part.text for part in parts if part.text and not part.thought)
        if not text.strip():
            raise ProviderResponseFormatError(f"Gemini returned no content (finish_reason={finish_name})")
        return text.strip()

    def _usage_tokens(self, response: types.GenerateContentResponse, prompt: str) -> UsageTokens:
        """Prompt, answer and thinking tokens: the usage reported by the API, else estimates.

        Thinking tokens are billed as output but not included in ``candidates_token_count``.
        """
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        thinking_tokens = getattr(usage, "thoughts_token_count", None) or 0
        if prompt_tokens is None:
            prompt_tokens = self.get_token_count(prompt)
        if output_tokens is None:
            try:
                output_tokens = self.get_token_count(self._extract_text(response))
            except ProviderException:
                output_tokens = 0
        return UsageTokens(prompt_tokens, output_tokens, thinking_tokens)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(TRANSIENT_PROVIDER_ERRORS),
        reraise=True,
    )
    async def generate_query(self, context: QueryContext) -> QueryResponse:
        """Generate SQL query using Gemini."""
        try:
            # Validate token count
            await self._validate_token_count(context)

            system_prompt = self._get_system_prompt(context.database_type)
            prompt = self._build_prompt(context)
            config = self._generation_config(system_prompt, context.max_tokens)

            # Generate content; malformed output is asked for again once
            generation = await call_with_format_retry(
                lambda: self._generate(prompt, config),
                self._parse_response,
                lambda response: self._usage_tokens(response, system_prompt + prompt).total,
                provider=self.provider_type.value,
            )
            response, result = generation.response, generation.result
            usage = self._usage_tokens(response, system_prompt + prompt)

            # Create QueryResponse
            metadata = {
                "model": self.model_name,
                "prompt_tokens": usage.prompt,
                "output_tokens": usage.output,
                "thinking_tokens": usage.thinking,
                "finish_reason": self._finish_name(response.candidates[0]),
                "format_retries": generation.format_retries,
            }

            # Include raw response if available
            if "_raw_response" in result:
                metadata["raw_response"] = result.pop("_raw_response")

            return QueryResponse(
                sql=result["sql"],
                explanation=result.get("explanation", ""),
                confidence=result.get("confidence", 0.8),
                tokens_used=generation.tokens_used,
                provider=self.provider_type.value,
                metadata=metadata,
            )

        except Exception as e:
            logger.error("Gemini query generation failed", error=str(e), error_type=type(e).__name__)
            error = classify_provider_error(e, f"Gemini query generation failed: {e!s}")
            if error is e:
                raise
            raise error from e

    def _build_prompt(self, context: QueryContext) -> str:
        """Build prompt for query generation."""
        prompt_parts = []
        metadata = context.metadata or {}

        # Add context
        prompt_parts.append(f"Database Type: {context.database_type}")
        prompt_parts.append(f"Question: {context.question}")

        intent_context = metadata.get("intent_context")
        if isinstance(intent_context, dict):
            prompt_parts.append("Intent Context:")
            prompt_parts.append(f"- Intent: {intent_context.get('intent', 'unknown')}")
            if intent_context.get("metrics"):
                prompt_parts.append(f"- Metrics: {', '.join(intent_context['metrics'])}")
            if intent_context.get("dimensions"):
                prompt_parts.append(f"- Dimensions: {', '.join(intent_context['dimensions'])}")
            if intent_context.get("time_grains"):
                prompt_parts.append(f"- Time grains: {', '.join(intent_context['time_grains'])}")
            if intent_context.get("filters"):
                prompt_parts.append(f"- Filters: {', '.join(intent_context['filters'])}")
            if intent_context.get("expected_operations"):
                prompt_parts.append(f"- Expected operations: {', '.join(intent_context['expected_operations'])}")

        semantic_context = metadata.get("semantic_context")
        if isinstance(semantic_context, dict) and semantic_context:
            prompt_parts.extend(format_semantic_context_lines(semantic_context))

        sql_intent_plan = metadata.get("sql_intent_plan")
        if isinstance(sql_intent_plan, dict) and sql_intent_plan:
            prompt_parts.extend(format_sql_intent_plan_lines(sql_intent_plan))

        # Add schema context
        if context.schema_context:
            prompt_parts.append(f"Database Schema:\n{context.schema_context}")

        # Add examples
        if context.examples:
            prompt_parts.append("Examples:")
            for i, example in enumerate(context.examples[: settings.max_prompt_examples], 1):
                prompt_parts.append(f"Example {i}:")
                prompt_parts.append(f"Question: {example['question']}")
                prompt_parts.append(f"SQL: {example['sql']}")
                example_metadata = example.get("metadata", {})
                if isinstance(example_metadata, dict):
                    tables = example_metadata.get("tables")
                    if tables:
                        prompt_parts.append(f"Tables: {', '.join(tables)}")
                prompt_parts.append("")

        # Add instructions
        prompt_parts.append("Instructions:")
        prompt_parts.append(f"1. Generate a {context.database_type} SQL query that answers the question")
        prompt_parts.append(
            "2. Use EXACT column names as listed in the schema above. "
            "NEVER abbreviate, shorten, or infer column names. "
            "If a column is not explicitly listed in the schema, DO NOT use it."
        )
        prompt_parts.append("3. Follow SQL best practices and optimize for performance")
        prompt_parts.append("4. Include appropriate JOINs, WHERE clauses, and ORDER BY if needed")
        prompt_parts.append("5. Return the response in JSON format with 'sql', 'explanation', and 'confidence' fields")

        return "\n".join(prompt_parts)

    def _get_system_prompt(self, database_type: str) -> str:
        """Get system prompt for the database type."""
        base_prompt = """You are an expert SQL query generator specializing in converting natural language questions into accurate, optimized SQL queries.

CRITICAL: You MUST respond with valid JSON only. No additional text, no markdown, no explanations outside the JSON.

Your response must be a valid JSON object with exactly these fields:
{
  "sql": "your SQL query here",
  "explanation": "brief explanation of the query",
  "confidence": 0.8
}

Ensure the JSON is properly formatted with no syntax errors. Escape any quotes inside strings properly."""

        from ..core.database_prompts import get_database_hint

        specific_prompt = get_database_hint(database_type)

        return f"{base_prompt} {specific_prompt}"

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        if content.startswith("```json"):
            return content.replace("```json", "").replace("```", "").strip()
        if content.startswith("```"):
            return content.replace("```", "").strip()
        return content

    def _parse_response(self, response: types.GenerateContentResponse) -> Dict[str, Any]:
        """Parse Gemini response."""
        content = ""
        try:
            raw_content = self._extract_text(response)

            # The model output can quote user data: DEBUG only
            logger.debug("Raw Gemini response", content=raw_content)

            content = self._strip_code_fence(raw_content)
            result = json.loads(content)

            # Validate required fields
            if not isinstance(result, dict) or "sql" not in result:
                raise ProviderResponseFormatError("Response missing required 'sql' field")

            # Set defaults
            result.setdefault("explanation", "")
            result.setdefault("confidence", 0.8)

            # Store raw response for debugging/display
            result["_raw_response"] = raw_content

            return result

        except ProviderException:
            raise
        except json.JSONDecodeError as e:
            # The model output can quote user data: DEBUG only
            logger.debug("JSON parsing failed", content=content, error=str(e))
            raise ProviderResponseFormatError(f"Invalid JSON response: {e!s}") from e
        except Exception as e:
            logger.error("Response parsing failed", error=str(e))
            raise ProviderException(f"Failed to parse response: {e!s}")

    async def _validate_token_count(self, context: QueryContext) -> None:
        """Validate that context doesn't exceed token limits."""
        prompt_tokens = self.get_token_count(self._build_prompt(context))
        system_tokens = self.get_token_count(self._get_system_prompt(context.database_type))
        total_tokens = prompt_tokens + system_tokens

        # Check against limits
        max_context = self.get_max_context_size()
        available_tokens = max_context - context.max_tokens  # Reserve space for response

        if total_tokens > available_tokens:
            raise TokenLimitException(
                f"Context too large: {total_tokens} tokens exceeds limit of {available_tokens}",
                tokens_used=total_tokens,
                max_tokens=available_tokens,
            )

        logger.debug("Token validation passed", total_tokens=total_tokens, available_tokens=available_tokens)

    async def validate_query(self, sql: str, schema_context: str) -> Dict[str, Any]:
        """Validate generated SQL query using Gemini."""
        try:
            validation_prompt = f"""Validate this SQL query against the provided schema.

SQL Query:
{sql}

Database Schema:
{schema_context}

Analyze the query and return a JSON response with:
{{
  "is_valid": true/false,
  "issues": ["list of any issues found"],
  "suggestions": ["list of improvement suggestions"],
  "complexity": "simple/moderate/complex"
}}

Check for:
1. Table and column existence
2. Correct JOIN conditions
3. Valid WHERE clause syntax
4. Appropriate GROUP BY usage
5. Proper aggregate function usage"""

            config = self._generation_config(
                "You are a SQL validation expert. Respond with valid JSON only.", VALIDATION_MAX_TOKENS
            )
            response = await self._generate(validation_prompt, config)

            # The tokens are reported so the service can account for every LLM call of a question
            usage = getattr(response, "usage_metadata", None)
            return validation_from_json(
                self._strip_code_fence(self._extract_text(response)), getattr(usage, "total_token_count", 0) or 0
            )

        except Exception as e:
            logger.error("Query validation failed", error=str(e))
            return validation_unavailable(str(e))
