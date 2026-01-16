"""Main service for natural language to SQL conversion."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from ..config.settings import settings
from ..core.entities import DatabaseType, Query
from ..exceptions import QueryGenerationException, ValidationException
from ..ports.ai_provider import AIProviderPort, QueryContext
from ..ports.cache import CachePort
from ..ports.embedding_provider import EmbeddingProviderPort
from ..ports.query_optimizer import QueryOptimizerPort
from ..ports.schema_repository import SchemaRepositoryPort
from ..schema.example_store import ExampleStore
from ..schema.manager import SchemaManager

logger = structlog.get_logger()


class QueryGenerationService:
    """Service for converting natural language to SQL."""

    def __init__(
        self,
        ai_provider: AIProviderPort,
        schema_repository: SchemaRepositoryPort,
        cache: Optional[CachePort] = None,
        query_optimizer: Optional[QueryOptimizerPort] = None,
        schema_filters: Optional[Dict[str, Any]] = None,
        embedding_provider: Optional[EmbeddingProviderPort] = None,
        example_store: Optional[ExampleStore] = None,
        schema_name: str = "public",
    ):
        self.ai_provider = ai_provider
        self.schema_repository = schema_repository
        self.cache = cache
        self.query_optimizer = query_optimizer
        self.schema_name = schema_name

        # Initialize schema manager with embedding provider
        self.schema_manager = SchemaManager(
            repository=schema_repository,
            cache=cache,
            embedding_provider=embedding_provider,
            schema_filters=schema_filters,
            schema_name=schema_name,
        )

        # Initialize example store
        self.example_store = example_store

        # Configuration
        self.max_examples = 5
        self.cache_ttl_hours = 24
        self.enable_query_optimization = True

    async def initialize(self, database_type: DatabaseType) -> None:
        """Initialize the service."""
        try:
            # Initialize schema repository first
            if hasattr(self.schema_repository, "initialize"):
                await self.schema_repository.initialize()

            # Initialize schema manager
            await self.schema_manager.initialize(database_type)

            logger.info(
                "Query generation service initialized",
                provider=self.ai_provider.provider_type.value,
                database_type=database_type.value,
            )

        except Exception as e:
            logger.error("Failed to initialize query service", error=str(e))
            raise QueryGenerationException(f"Service initialization failed: {e!s}")

    async def generate_sql(
        self,
        question: str,
        database_type: DatabaseType,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        include_explanation: bool = True,
    ) -> Dict[str, Any]:
        """Generate SQL query from natural language question."""
        try:
            start_time = datetime.now()

            # Create query object
            query = Query(text=question)

            # Check cache first
            cache_key = f"query:{question}:{database_type.value}:{self.ai_provider.provider_type.value}"
            if self.cache:
                cached_result = await self.cache.get(cache_key)
                if cached_result:
                    logger.info("Query served from cache", question=question[:50])
                    return cached_result

            # Get optimal schema context
            schema_context = await self.schema_manager.get_optimal_schema_context(
                question, database_type, max_tokens or settings.max_schema_tokens
            )

            # Find relevant examples
            examples = await self._find_relevant_examples(question, database_type)

            # Create query context
            query_context = QueryContext(
                question=question,
                database_type=database_type.value,
                schema_context=schema_context,
                examples=examples,
                max_tokens=max_tokens or settings.default_max_tokens,
                temperature=temperature or settings.default_temperature,
                metadata={"service_version": "1.0", "timestamp": start_time.isoformat()},
            )

            # Generate SQL
            response = await self.ai_provider.generate_query(query_context)

            # Optimize query if enabled
            if self.enable_query_optimization and self.query_optimizer:
                optimization_result = await self.query_optimizer.optimize(response.sql)
                response.sql = optimization_result.optimized_query
                response.metadata["optimization"] = {
                    "applied": optimization_result.optimizations_applied,
                    "improvement": optimization_result.estimated_improvement,
                }

            # Validate query
            validation_result = await self.ai_provider.validate_query(response.sql, schema_context)

            # Build result
            result = {
                "sql": response.sql,
                "explanation": response.explanation if include_explanation else None,
                "confidence": response.confidence,
                "provider": response.provider,
                "database_type": database_type.value,
                "tokens_used": response.tokens_used,
                "generation_time_ms": (datetime.now() - start_time).total_seconds() * 1000,
                "validation": validation_result,
                "schema_context_length": len(schema_context),
                "examples_used": len(examples),
                "metadata": response.metadata,
            }

            # Cache result
            if self.cache and validation_result.get("is_valid", False):
                await self.cache.set(cache_key, result)

            logger.info(
                "SQL generated successfully",
                question=question[:50],
                confidence=response.confidence,
                tokens_used=response.tokens_used,
                valid=validation_result.get("is_valid", False),
            )

            return result

        except Exception as e:
            logger.error(
                "SQL generation failed",
                question=question[:50],
                error=str(e),
                error_type=type(e).__name__,
            )
            raise QueryGenerationException(f"SQL generation failed: {e!s}") from e

    async def validate_sql(self, sql: str, database_type: DatabaseType) -> Dict[str, Any]:
        """Validate SQL query."""
        try:
            # Get schema context for validation
            schema_context = await self.schema_manager.get_optimal_schema_context(
                sql, database_type, settings.max_schema_tokens
            )

            # Validate with AI provider
            validation_result = await self.ai_provider.validate_query(sql, schema_context)

            # Additional validation with query optimizer if available
            if self.query_optimizer:
                analysis = await self.query_optimizer.analyze(sql)
                validation_result["analysis"] = {
                    "tables_used": analysis.tables_used,
                    "estimated_cost": analysis.estimated_cost,
                    "potential_issues": analysis.potential_issues,
                }

            return validation_result

        except Exception as e:
            logger.error("SQL validation failed", sql=sql[:100], error=str(e))
            raise ValidationException(f"SQL validation failed: {e!s}")

    async def get_query_suggestions(
        self, partial_question: str, database_type: DatabaseType, max_suggestions: int = 5
    ) -> List[Dict[str, Any]]:
        """Get query suggestions based on partial input."""
        try:
            # Find relevant tables
            relevant_tables = await self.schema_manager.find_relevant_tables(
                partial_question, database_type, max_suggestions * 2
            )

            # Generate suggestions based on tables
            suggestions = []
            for table_name, relevance in relevant_tables:
                table_info = await self.schema_repository.get_table_info(table_name)

                # Create basic suggestions
                suggestions.append(
                    {
                        "type": "table_exploration",
                        "text": f"Show me all data from {table_name}",
                        "relevance": relevance,
                        "table": table_name,
                        "description": f"Explore the {table_name} table",
                    }
                )

                # Add column-specific suggestions
                for column in table_info.columns[:3]:  # Top 3 columns
                    if any(keyword in column["name"].lower() for keyword in ["name", "title", "description"]):
                        suggestions.append(
                            {
                                "type": "column_query",
                                "text": f"Show me {column['name']} from {table_name}",
                                "relevance": relevance * 0.8,
                                "table": table_name,
                                "column": column["name"],
                                "description": f"Query {column['name']} from {table_name}",
                            }
                        )

            # Sort by relevance and limit
            suggestions.sort(key=lambda x: x["relevance"], reverse=True)
            return suggestions[:max_suggestions]

        except Exception as e:
            logger.error("Failed to get query suggestions", partial_question=partial_question, error=str(e))
            return []

    async def explain_query(self, sql: str, database_type: DatabaseType) -> Dict[str, Any]:
        """Explain what an SQL query does."""
        try:
            # Get schema context
            schema_context = await self.schema_manager.get_optimal_schema_context(
                sql, database_type, settings.max_schema_tokens
            )

            # Use AI provider to explain
            explanation_context = QueryContext(
                question=f"Explain this SQL query: {sql}",
                database_type=database_type.value,
                schema_context=schema_context,
                examples=[],
                max_tokens=1000,
                temperature=0.1,
            )

            response = await self.ai_provider.generate_query(explanation_context)

            # Analyze query structure
            analysis = {}
            if self.query_optimizer:
                analysis = await self.query_optimizer.analyze(sql)

            return {
                "explanation": response.explanation,
                "sql": sql,
                "analysis": analysis,
                "provider": response.provider,
            }

        except Exception as e:
            logger.error("Failed to explain query", sql=sql[:100], error=str(e))
            raise QueryGenerationException(f"Query explanation failed: {e!s}")

    async def _find_relevant_examples(self, question: str, database_type: DatabaseType) -> List[Dict[str, str]]:
        """Find relevant example queries using vector similarity."""
        # If example store is available, use it for dynamic retrieval
        if self.example_store:
            try:
                examples = await self.example_store.search_similar(
                    question=question,
                    top_k=self.max_examples,
                    database_type=database_type.value,
                    min_score=0.3,
                )
                # Format for compatibility with existing code
                return [{"question": ex["question"], "sql": ex["sql"]} for ex in examples]
            except Exception as e:
                logger.warning("Failed to retrieve examples from store, using fallback", error=str(e))

        # Fallback to hardcoded examples if store is not available
        examples = [
            {"question": "Show me all customers", "sql": "SELECT * FROM customers"},
            {"question": "Count total orders", "sql": "SELECT COUNT(*) FROM orders"},
            {
                "question": "Find customers with orders",
                "sql": "SELECT c.* FROM customers c JOIN orders o ON c.id = o.customer_id",
            },
        ]

        # Simple keyword matching fallback
        relevant_examples = []
        question_lower = question.lower()

        for example in examples:
            if any(word in question_lower for word in example["question"].lower().split()):
                relevant_examples.append(example)

        return relevant_examples[: self.max_examples]

    async def get_service_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        stats = {
            "provider": self.ai_provider.provider_type.value,
            "provider_context_size": self.ai_provider.get_max_context_size(),
            "cache_enabled": self.cache is not None,
            "optimizer_enabled": self.query_optimizer is not None,
            "timestamp": datetime.now().isoformat(),
        }

        # Add cache stats if available
        if self.cache:
            cache_stats = await self.cache.get_stats()
            stats["cache_stats"] = cache_stats

        return stats
