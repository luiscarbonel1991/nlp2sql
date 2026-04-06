"""Google Gemini adapter for query generation."""

import asyncio
import json
from typing import Any, Dict, Optional

import google.generativeai as genai
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.settings import settings
from ..exceptions import ProviderException, TokenLimitException
from ..ports.ai_provider import AIProviderPort, AIProviderType, QueryContext, QueryResponse
from ..utils.helpers import first_not_none
from ..utils.semantic_prompt import format_semantic_context_lines, format_sql_intent_plan_lines

logger = structlog.get_logger()


class GeminiAdapter(AIProviderPort):
    """Google Gemini adapter for natural language to SQL generation."""

    DEFAULT_MODEL = "gemini-2.0-flash"
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

        resolved_model = model or self.DEFAULT_MODEL
        self.max_tokens = first_not_none(max_tokens, self.DEFAULT_MAX_TOKENS)
        self.temperature = first_not_none(temperature, self.DEFAULT_TEMPERATURE)

        # Configure Gemini
        genai.configure(api_key=self.api_key)
        self.model_name = resolved_model
        self.model = genai.GenerativeModel(resolved_model)

        logger.debug(
            "Provider configured",
            provider="gemini",
            model=self.model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.GEMINI

    def get_token_count(self, text: str) -> int:
        """Estimate token count for Gemini models."""
        try:
            result = self.model.count_tokens(text)
            return result.total_tokens
        except Exception:
            # Fallback estimation
            return len(text) // 4

    def get_max_context_size(self) -> int:
        """Get maximum context size for the model."""
        context_limits = {
            "gemini-2.0-flash": 1048576,
            "gemini-2.0-pro": 1048576,
            "gemini-1.5-pro": 1048576,
            "gemini-1.5-flash": 1048576,
            "gemini-pro": 30720,
            "gemini-pro-vision": 16384,
        }
        return context_limits.get(self.model_name, 30720)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def generate_query(self, context: QueryContext) -> QueryResponse:
        """Generate SQL query using Gemini."""
        try:
            # Validate token count
            await self._validate_token_count(context)

            # Build prompt
            full_prompt = self._build_full_prompt(context)

            # Configure generation
            generation_config = genai.types.GenerationConfig(
                temperature=context.temperature, max_output_tokens=context.max_tokens, candidate_count=1
            )

            # Generate content
            response = await asyncio.to_thread(
                self.model.generate_content, full_prompt, generation_config=generation_config
            )

            # Parse response
            result = self._parse_response(response)

            # Estimate token usage (Gemini doesn't provide exact counts in all cases)
            prompt_tokens = self.get_token_count(full_prompt)
            output_tokens = self.get_token_count(response.text)

            # Create QueryResponse
            metadata = {
                "model": self.model_name,
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "finish_reason": getattr(response.candidates[0], "finish_reason", None),
            }

            # Include raw response if available
            if "_raw_response" in result:
                metadata["raw_response"] = result.pop("_raw_response")

            return QueryResponse(
                sql=result["sql"],
                explanation=result.get("explanation", ""),
                confidence=result.get("confidence", 0.8),
                tokens_used=prompt_tokens + output_tokens,
                provider=self.provider_type.value,
                metadata=metadata,
            )

        except Exception as e:
            logger.error("Gemini query generation failed", error=str(e))
            raise ProviderException(f"Gemini query generation failed: {e!s}")

    def _build_full_prompt(self, context: QueryContext) -> str:
        """Build complete prompt including system instructions."""
        system_prompt = self._get_system_prompt(context.database_type)
        user_prompt = self._build_prompt(context)

        return f"{system_prompt}\n\n{user_prompt}"

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

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse Gemini response."""
        try:
            if not response.candidates:
                raise ProviderException("No response candidates generated")

            raw_content = response.text.strip()
            content = raw_content

            # Log the raw response for debugging
            logger.debug("Raw Gemini response", content=content)

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
        full_prompt = self._build_full_prompt(context)

        # Count tokens
        total_tokens = self.get_token_count(full_prompt)

        # Check against limits
        max_context = self.get_max_context_size()
        available_tokens = max_context - context.max_tokens  # Reserve space for response

        if total_tokens > available_tokens:
            raise TokenLimitException(f"Context too large: {total_tokens} tokens exceeds limit of {available_tokens}")

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

            generation_config = genai.types.GenerationConfig(temperature=0.1, max_output_tokens=1000, candidate_count=1)

            response = await asyncio.to_thread(
                self.model.generate_content, validation_prompt, generation_config=generation_config
            )

            # Parse response
            content = response.text.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            elif content.startswith("```"):
                content = content.replace("```", "").strip()

            result = json.loads(content)

            # Set defaults
            result.setdefault("is_valid", True)
            result.setdefault("issues", [])
            result.setdefault("suggestions", [])
            result.setdefault("complexity", "moderate")

            return result

        except Exception as e:
            logger.error("Query validation failed", error=str(e))
            # Return a basic validation result on error
            return {
                "is_valid": True,
                "issues": [],
                "suggestions": [],
                "complexity": "moderate",
                "error": f"Validation error: {e!s}",
            }
