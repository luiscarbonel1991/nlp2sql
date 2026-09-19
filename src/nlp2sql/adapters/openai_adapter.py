"""OpenAI adapter for query generation."""

import json
from typing import Any, Dict, Optional, Tuple

import structlog
import tiktoken
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.settings import settings
from ..core.provider_config import ProviderConfig
from ..exceptions import ProviderException, TokenLimitException
from ..ports.ai_provider import AIProviderPort, AIProviderType, QueryContext, QueryResponse
from ..utils.helpers import first_not_none
from ..utils.semantic_prompt import format_semantic_context_lines, format_sql_intent_plan_lines

logger = structlog.get_logger()

# Maximum input tokens per model. The gpt-5.6 entries hold the documented
# max-input cap (922K) rather than the 1.05M context window, because this table
# gates prompt size, not the total window. Legacy rows are kept so users who pin
# an older model keep an accurate budget.
CONTEXT_LIMITS: Dict[str, int] = {
    "gpt-5.6-luna": 922_000,
    "gpt-5.6-terra": 922_000,
    "gpt-4.1": 1_047_576,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4-turbo-preview": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "gpt-3.5-turbo-16k": 16_385,
}
# Every OpenAI chat model still served has at least a 128K window; the previous
# 8,192 fallback made any unknown model fail token validation before the first
# request.
DEFAULT_CONTEXT_LIMIT = 128_000

# Models that accept sampling parameters (temperature) and do not accept
# reasoning_effort. Everything else, including unknown or future IDs, is treated
# as a reasoning model, which is what every OpenAI chat model since gpt-5 is.
SAMPLING_MODEL_PREFIXES: Tuple[str, ...] = ("gpt-3.5", "gpt-4", "chatgpt-4o", "ft:gpt-3.5", "ft:gpt-4")

# tiktoken has no mapping for several current IDs (its prefix rule is "gpt-5-"
# while the IDs are "gpt-5."). All post-2024 OpenAI models use o200k_base.
ENCODING_BY_PREFIX: Tuple[Tuple[str, str], ...] = (
    ("gpt-5", "o200k_base"),
    ("gpt-4.1", "o200k_base"),
    ("gpt-4o", "o200k_base"),
    ("chatgpt-4o", "o200k_base"),
    ("o1", "o200k_base"),
    ("o3", "o200k_base"),
    ("o4", "o200k_base"),
)
FALLBACK_ENCODING = "o200k_base"


class OpenAIAdapter(AIProviderPort):
    """OpenAI adapter for natural language to SQL generation.

    Reasoning models (the default family) receive ``max_completion_tokens`` and
    ``reasoning_effort`` and never ``temperature``; the legacy sampling families
    (``gpt-3.5``, ``gpt-4``, ``chatgpt-4o``) keep receiving ``temperature``.
    """

    DEFAULT_MODEL = ProviderConfig.DEFAULT_MODELS["openai"]
    DEFAULT_MAX_TOKENS = 2000
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_REASONING_EFFORT: Optional[str] = "low"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
    ):
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ProviderException("OpenAI API key is required")

        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = first_not_none(max_tokens, self.DEFAULT_MAX_TOKENS)
        self.temperature = first_not_none(temperature, self.DEFAULT_TEMPERATURE)
        self.reasoning_effort = first_not_none(reasoning_effort, self.DEFAULT_REASONING_EFFORT)

        self.client = AsyncOpenAI(api_key=self.api_key)

        self.encoding = self._resolve_encoding(self.model)
        self._max_context_size = self._resolve_context_limit(self.model)

        logger.debug(
            "Provider configured",
            provider="openai",
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            reasoning_effort=self.reasoning_effort,
            uses_sampling_params=self._uses_sampling_params(),
            encoding=self.encoding.name,
            context_limit=self._max_context_size,
        )

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.OPENAI

    # ── Model capability resolution ────────────────────────────────────

    def _uses_sampling_params(self) -> bool:
        """Whether the model accepts temperature (and rejects reasoning_effort)."""
        return self.model.startswith(SAMPLING_MODEL_PREFIXES)

    @staticmethod
    def _resolve_encoding(model: str) -> tiktoken.Encoding:
        """Pick the tokenizer for a model, never silently using cl100k_base."""
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            pass
        for prefix, encoding_name in ENCODING_BY_PREFIX:
            if model.startswith(prefix):
                logger.debug(
                    "tiktoken has no exact mapping for model; using family encoding",
                    model=model,
                    encoding=encoding_name,
                )
                return tiktoken.get_encoding(encoding_name)
        logger.warning(
            "tiktoken has no mapping for model; using fallback encoding",
            model=model,
            encoding=FALLBACK_ENCODING,
        )
        return tiktoken.get_encoding(FALLBACK_ENCODING)

    @staticmethod
    def _resolve_context_limit(model: str) -> int:
        """Exact match, then longest model-family prefix, then a logged fallback."""
        if model in CONTEXT_LIMITS:
            return CONTEXT_LIMITS[model]
        matches = [key for key in CONTEXT_LIMITS if model.startswith(key)]
        if matches:
            family = max(matches, key=len)
            logger.debug(
                "Resolved context limit by model family",
                model=model,
                family=family,
                context_limit=CONTEXT_LIMITS[family],
            )
            return CONTEXT_LIMITS[family]
        logger.warning(
            "Unknown OpenAI model; using fallback context limit",
            model=model,
            context_limit=DEFAULT_CONTEXT_LIMIT,
            hint="pin a model listed in openai_adapter.CONTEXT_LIMITS or add it",
        )
        return DEFAULT_CONTEXT_LIMIT

    def get_token_count(self, text: str) -> int:
        """Count tokens for OpenAI models."""
        return len(self.encoding.encode(text))

    def get_max_context_size(self) -> int:
        """Get maximum input context size for the model."""
        return self._max_context_size

    def _completion_kwargs(self, *, max_tokens: int, temperature: float) -> Dict[str, Any]:
        """Build the model-family-appropriate kwargs for ``chat.completions.create``.

        ``max_completion_tokens`` replaced the deprecated ``max_tokens`` and is
        accepted by every Chat Completions model. Reasoning models reject
        non-default ``temperature`` values and take ``reasoning_effort`` instead.
        Built as a plain dict because the SDK types ``reasoning_effort`` as a
        Literal that lags behind the API.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self._uses_sampling_params():
            kwargs["temperature"] = temperature
        elif self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    # ── Generation ─────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), reraise=True)
    async def generate_query(self, context: QueryContext) -> QueryResponse:
        """Generate SQL query from natural language."""
        try:
            # Validate token count
            await self._validate_token_count(context)

            # Build prompt
            prompt = self._build_prompt(context)
            system_prompt = self._get_system_prompt(context.database_type)

            # Make API call
            response = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                **self._completion_kwargs(max_tokens=context.max_tokens, temperature=context.temperature),
            )

            # Parse response
            result = self._parse_response(response)

            usage = response.usage
            reasoning_tokens = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)

            # Create QueryResponse
            metadata = {
                "model": self.model,
                "finish_reason": response.choices[0].finish_reason,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "reasoning_effort": None if self._uses_sampling_params() else self.reasoning_effort,
                "reasoning_tokens": reasoning_tokens,
            }

            # Include raw response if available
            if "_raw_response" in result:
                metadata["raw_response"] = result.pop("_raw_response")

            return QueryResponse(
                sql=result["sql"],
                explanation=result.get("explanation", ""),
                confidence=result.get("confidence", 0.8),
                tokens_used=usage.total_tokens,
                provider=self.provider_type.value,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                "OpenAI query generation failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ProviderException(f"OpenAI query generation failed: {e!s}") from e

    async def validate_query(self, sql: str, schema_context: str) -> Dict[str, Any]:
        """Validate generated SQL query."""
        try:
            validation_prompt = self._build_validation_prompt(sql, schema_context)

            response = await self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a SQL validation expert. Analyze the given SQL query and provide validation results in JSON format.",
                    },
                    {"role": "user", "content": validation_prompt},
                ],
                **self._completion_kwargs(max_tokens=1000, temperature=0),
            )

            content = response.choices[0].message.content or ""
            result = json.loads(content)
            return result

        except Exception as e:
            logger.error("OpenAI query validation failed", error=str(e))
            return {"is_valid": False, "errors": [f"Validation failed: {e!s}"], "warnings": []}

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

    def _build_validation_prompt(self, sql: str, schema_context: str) -> str:
        """Build prompt for query validation."""
        return f"""
        Validate the following SQL query against the provided schema:

        SQL Query:
        {sql}

        Schema Context:
        {schema_context}

        Please analyze the query and return a JSON response with:
        - is_valid: boolean indicating if the query is valid
        - errors: array of error messages if any
        - warnings: array of warning messages if any
        - suggestions: array of optimization suggestions if any
        - estimated_performance: string indicating expected performance (fast/medium/slow)
        """

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

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse OpenAI response."""
        try:
            choice = response.choices[0]
            message_content = choice.message.content
            if not message_content:
                # Reasoning models can spend the whole budget on reasoning tokens
                # and return no content with finish_reason="length".
                raise ProviderException(
                    f"Empty completion (finish_reason={choice.finish_reason}); "
                    "raise max_tokens or lower reasoning_effort (reasoning tokens count toward max_tokens)"
                )

            raw_content = message_content.strip()
            content = raw_content

            # Log the raw response for debugging
            logger.debug("Raw OpenAI response", content=content)

            # Try to extract JSON if wrapped in markdown
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            elif content.startswith("```"):
                content = content.replace("```", "").strip()

            result = json.loads(content)

            # Validate required fields
            if "sql" not in result:
                raise ProviderException("Response missing required 'sql' field")

            # Set defaults
            result.setdefault("explanation", "")
            result.setdefault("confidence", 0.8)

            # Store raw response for debugging/display
            result["_raw_response"] = raw_content

            return result

        except ProviderException:
            raise
        except json.JSONDecodeError as e:
            # Log the problematic content
            logger.error("JSON parsing failed", content=content, error=str(e))
            raise ProviderException(f"Invalid JSON response: {e!s}")
        except Exception as e:
            logger.error("Response parsing failed", error=str(e))
            raise ProviderException(f"Failed to parse response: {e!s}")

    async def _validate_token_count(self, context: QueryContext) -> None:
        """Validate that context doesn't exceed token limits."""
        # Build prompt to count tokens
        prompt = self._build_prompt(context)
        system_prompt = self._get_system_prompt(context.database_type)

        # Count tokens
        prompt_tokens = self.get_token_count(prompt)
        system_tokens = self.get_token_count(system_prompt)
        total_input_tokens = prompt_tokens + system_tokens

        # Check against limits
        max_context = self.get_max_context_size()
        available_tokens = max_context - context.max_tokens - 100  # Buffer

        if total_input_tokens > available_tokens:
            raise TokenLimitException(
                f"Input tokens ({total_input_tokens}) exceed available context ({available_tokens})",
                tokens_used=total_input_tokens,
                max_tokens=available_tokens,
            )

        logger.debug(
            "Token validation passed",
            prompt_tokens=prompt_tokens,
            system_tokens=system_tokens,
            total_tokens=total_input_tokens,
            available_tokens=available_tokens,
        )
