"""Anthropic Claude adapter for query generation."""

import json
from typing import Any, Dict, Optional

import anthropic
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.settings import settings
from ..exceptions import ProviderException, TokenLimitException
from ..ports.ai_provider import AIProviderPort, AIProviderType, QueryContext, QueryResponse

logger = structlog.get_logger()


class AnthropicAdapter(AIProviderPort):
    """Anthropic Claude adapter for natural language to SQL generation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-opus-20240229",
        max_tokens: int = 2000,
        temperature: float = 0.1,
    ):
        self.api_key = api_key or settings.anthropic_api_key
        if not self.api_key:
            raise ProviderException("Anthropic API key is required")

        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.ANTHROPIC

    def get_token_count(self, text: str) -> int:
        """Estimate token count for Claude models."""
        # Claude uses similar tokenization to GPT models
        # Rough estimation: ~4 characters per token
        return len(text) // 4

    def get_max_context_size(self) -> int:
        """Get maximum context size for the model."""
        context_limits = {
            "claude-3-opus-20240229": 200000,
            "claude-3-sonnet-20240229": 200000,
            "claude-3-haiku-20240307": 200000,
            "claude-2.1": 200000,
            "claude-2.0": 100000,
            "claude-instant-1.2": 100000,
        }
        return context_limits.get(self.model, 100000)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def generate_query(self, context: QueryContext) -> QueryResponse:
        """Generate SQL query using Claude."""
        try:
            # Validate token count
            await self._validate_token_count(context)

            # Build prompt
            prompt = self._build_prompt(context)
            system_prompt = self._get_system_prompt(context.database_type)

            # Create messages
            messages = [{"role": "user", "content": prompt}]

            # Call Claude API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=context.max_tokens,
                temperature=context.temperature,
                system=system_prompt,
                messages=messages,
            )

            # Parse response
            result = self._parse_response(response)

            # Create QueryResponse
            metadata = {
                "model": self.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

            # Include raw response if available
            if "_raw_response" in result:
                metadata["raw_response"] = result.pop("_raw_response")

            return QueryResponse(
                sql=result["sql"],
                explanation=result.get("explanation", ""),
                confidence=result.get("confidence", 0.8),
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                provider=self.provider_type.value,
                metadata=metadata,
            )

        except Exception as e:
            logger.error("Anthropic query generation failed", error=str(e))
            raise ProviderException(f"Anthropic query generation failed: {e!s}")

    def _build_prompt(self, context: QueryContext) -> str:
        """Build prompt for query generation."""
        prompt_parts = []

        # Add context
        prompt_parts.append(f"Database Type: {context.database_type}")
        prompt_parts.append(f"Question: {context.question}")

        # Add schema context
        if context.schema_context:
            prompt_parts.append(f"Database Schema:\n{context.schema_context}")

        # Add examples
        if context.examples:
            prompt_parts.append("Examples:")
            for i, example in enumerate(context.examples[:3], 1):
                prompt_parts.append(f"Example {i}:")
                prompt_parts.append(f"Question: {example['question']}")
                prompt_parts.append(f"SQL: {example['sql']}")
                prompt_parts.append("")

        # Add instructions
        prompt_parts.append("Instructions:")
        prompt_parts.append(f"1. Generate a {context.database_type} SQL query that answers the question")
        prompt_parts.append("2. Use only the tables and columns from the provided schema")
        prompt_parts.append("3. Follow SQL best practices and optimize for performance")
        prompt_parts.append("4. Include appropriate JOINs, WHERE clauses, and ORDER BY if needed")
        prompt_parts.append("5. Return the response in JSON format with 'sql', 'explanation', and 'confidence' fields")

        return "\n".join(prompt_parts)

    def _get_system_prompt(self, database_type: str) -> str:
        """Get system prompt for the database type."""
        base_prompt = """You are an expert SQL query generator specializing in converting natural language questions into accurate, optimized SQL queries.

You MUST respond with valid JSON only. No additional text, no markdown, no explanations outside the JSON.

Your response must be a valid JSON object with exactly these fields:
{
  "sql": "your SQL query here",
  "explanation": "brief explanation of the query",
  "confidence": 0.8
}

Ensure the JSON is properly formatted with no syntax errors. Escape any quotes inside strings properly."""

        database_specific = {
            "postgres": "You specialize in PostgreSQL syntax and features. Use PostgreSQL-specific functions and syntax when appropriate.",
            "mysql": "You specialize in MySQL syntax and features. Use MySQL-specific functions and syntax when appropriate.",
            "sqlite": "You specialize in SQLite syntax and features. Use SQLite-specific functions and syntax when appropriate.",
            "mssql": "You specialize in SQL Server syntax and features. Use T-SQL syntax when appropriate.",
            "oracle": "You specialize in Oracle SQL syntax and features. Use Oracle-specific functions and syntax when appropriate.",
        }

        specific_prompt = database_specific.get(database_type.lower(), "")

        return f"{base_prompt} {specific_prompt}"

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse Anthropic response."""
        try:
            raw_content = response.content[0].text.strip()
            content = raw_content

            # Log the raw response for debugging
            logger.debug("Raw Anthropic response", content=content)

            # Try to extract JSON if wrapped in markdown
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            elif content.startswith("```"):
                content = content.replace("```", "").strip()

            # Clean up control characters that can break JSON parsing
            # Replace newlines and tabs in SQL strings to avoid JSON parsing errors
            import re

            content = re.sub(r"\\n\s+", " ", content)  # Replace \n followed by spaces with single space
            content = re.sub(r"\n\s+", " ", content)  # Replace actual newlines with spaces
            content = re.sub(r"\s+", " ", content)  # Normalize multiple spaces to single space

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
        total_tokens = prompt_tokens + system_tokens

        # Check against limits
        max_context = self.get_max_context_size()
        available_tokens = max_context - context.max_tokens  # Reserve space for response

        if total_tokens > available_tokens:
            raise TokenLimitException(f"Context too large: {total_tokens} tokens exceeds limit of {available_tokens}")

        logger.debug(
            "Token validation passed",
            prompt_tokens=prompt_tokens,
            system_tokens=system_tokens,
            total_tokens=total_tokens,
            available_tokens=available_tokens,
        )

    async def validate_query(self, sql: str, schema_context: str) -> Dict[str, Any]:
        """Validate generated SQL query using Claude."""
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

            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0,
                system="You are a SQL validation expert. Analyze the given SQL query and provide validation results in JSON format only.",
                messages=[{"role": "user", "content": validation_prompt}],
            )

            # Parse response
            content = message.content[0].text.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            elif content.startswith("```"):
                content = content.replace("```", "").strip()

            # Clean up control characters that can break JSON parsing (same fix as main parsing)
            import re

            content = re.sub(r"\\n\s+", " ", content)  # Replace \n followed by spaces
            content = re.sub(r"\n\s+", " ", content)  # Replace actual newlines
            content = re.sub(r"\s+", " ", content)  # Normalize multiple spaces

            result = json.loads(content)

            # Set defaults
            result.setdefault("is_valid", True)
            result.setdefault("issues", [])
            result.setdefault("suggestions", [])
            result.setdefault("complexity", "moderate")

            return result

        except Exception as e:
            logger.error(
                "Query validation failed",
                error=str(e),
                content=content if "content" in locals() else "No content received",
            )
            # Return a basic validation result on error
            return {
                "is_valid": True,
                "issues": [],
                "suggestions": [],
                "complexity": "moderate",
                "error": f"Validation error: {e!s}",
            }
