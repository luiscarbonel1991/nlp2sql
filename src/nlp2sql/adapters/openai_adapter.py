"""OpenAI adapter for query generation."""

import json
from typing import Any, Dict, Optional

import structlog
import tiktoken
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.settings import settings
from ..exceptions import ProviderException, TokenLimitException
from ..ports.ai_provider import AIProviderPort, AIProviderType, QueryContext, QueryResponse
from ..utils.helpers import first_not_none
from ..utils.semantic_prompt import format_semantic_context_lines, format_sql_intent_plan_lines

logger = structlog.get_logger()


class OpenAIAdapter(AIProviderPort):
    """OpenAI adapter for natural language to SQL generation."""

    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_MAX_TOKENS = 2000
    DEFAULT_TEMPERATURE = 0.1

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ProviderException("OpenAI API key is required")

        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = first_not_none(max_tokens, self.DEFAULT_MAX_TOKENS)
        self.temperature = first_not_none(temperature, self.DEFAULT_TEMPERATURE)

        self.client = AsyncOpenAI(api_key=self.api_key)

        # Token encoding
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")

        logger.debug(
            "Provider configured",
            provider="openai",
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.OPENAI

    def get_token_count(self, text: str) -> int:
        """Count tokens for OpenAI models."""
        return len(self.encoding.encode(text))

    def get_max_context_size(self) -> int:
        """Get maximum context size for the model."""
        context_limits = {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4-turbo": 128000,
            "gpt-4-turbo-preview": 128000,
            "gpt-4": 8192,
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-16k": 16385,
        }
        return context_limits.get(self.model, 8192)

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
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=context.max_tokens,
                temperature=context.temperature,
                response_format={"type": "json_object"},
            )

            # Parse response
            result = self._parse_response(response)

            # Create QueryResponse
            metadata = {
                "model": self.model,
                "finish_reason": response.choices[0].finish_reason,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }

            # Include raw response if available
            if "_raw_response" in result:
                metadata["raw_response"] = result.pop("_raw_response")

            return QueryResponse(
                sql=result["sql"],
                explanation=result.get("explanation", ""),
                confidence=result.get("confidence", 0.8),
                tokens_used=response.usage.total_tokens,
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
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a SQL validation expert. Analyze the given SQL query and provide validation results in JSON format.",
                    },
                    {"role": "user", "content": validation_prompt},
                ],
                max_tokens=1000,
                temperature=0,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
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
            raw_content = response.choices[0].message.content.strip()
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
