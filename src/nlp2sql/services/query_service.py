"""Main service for natural language to SQL conversion."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
import hashlib
import json
import re
from datetime import datetime
from typing import Any

import structlog

from ..config.settings import settings
from ..core.entities import (
    DatabaseType,
    RepairContext,
    SemanticContext,
    SqlIntentPlan,
)
from ..exceptions import QueryGenerationException, ValidationException
from ..ports.ai_provider import AIProviderPort, QueryContext, QueryResponse
from ..ports.cache import CachePort
from ..ports.embedding_provider import EmbeddingProviderPort
from ..ports.error_classifier import ErrorClassifierPort
from ..ports.example_repository import ExampleRepositoryPort
from ..ports.query_execution import QueryExecutionPort
from ..ports.query_optimizer import QueryOptimizerPort
from ..ports.query_validator import QueryValidatorPort
from ..ports.repair_policy import RepairPolicyPort
from ..ports.schema_repository import SchemaRepositoryPort
from ..ports.semantic_resolver import SemanticResolverPort
from ..ports.semantic_validator import SemanticValidatorPort
from ..schema.manager import SchemaManager
from .example_selection_service import ExampleSelectionService
from .prompt_assembly_service import PromptAssemblyService
from .query_analysis_service import QueryAnalysisService
from .query_repair_service import QueryRepairService
from .semantic_resolution_service import SemanticResolutionService
from .semantic_validation_service import SemanticValidationService
from .sql_intent_planning_service import SqlIntentPlanningService

logger = structlog.get_logger()


class QueryGenerationService:
    """Service for converting natural language to SQL."""

    def __init__(
        self,
        ai_provider: AIProviderPort,
        schema_repository: SchemaRepositoryPort,
        cache: CachePort | None = None,
        query_optimizer: QueryOptimizerPort | None = None,
        schema_filters: dict[str, Any] | None = None,
        embedding_provider: EmbeddingProviderPort | None = None,
        example_store: ExampleRepositoryPort | None = None,
        query_validator: QueryValidatorPort | None = None,
        schema_name: str = "public",
        execution_port: QueryExecutionPort | None = None,
        error_classifier: ErrorClassifierPort | None = None,
        repair_policy: RepairPolicyPort | None = None,
        semantic_resolver: SemanticResolverPort | None = None,
        semantic_validator: SemanticValidatorPort | None = None,
    ):
        self.ai_provider = ai_provider
        self.schema_repository = schema_repository
        self.cache = cache
        self.query_optimizer = query_optimizer
        self.query_validator = query_validator
        self.schema_name = schema_name
        self.execution_port = execution_port
        self.error_classifier = error_classifier
        self.repair_policy = repair_policy

        self.schema_manager = SchemaManager(
            repository=schema_repository,
            cache=cache,
            embedding_provider=embedding_provider,
            schema_filters=schema_filters,
            schema_name=schema_name,
        )
        self.example_store = example_store
        self.max_examples = settings.max_examples
        self.cache_ttl_hours = settings.schema_refresh_interval_hours
        self.enable_query_optimization = True

        self.query_analysis_service = QueryAnalysisService()
        self.example_selection_service = ExampleSelectionService(
            example_store=example_store,
            max_examples=settings.max_examples,
            max_prompt_examples=settings.max_prompt_examples,
        )
        self.prompt_assembly_service = PromptAssemblyService()
        self.query_repair_service = QueryRepairService(ai_provider=ai_provider)
        self.semantic_resolution_service = SemanticResolutionService(semantic_resolver=semantic_resolver)
        self.sql_intent_planning_service = SqlIntentPlanningService()
        self.semantic_validation_service = SemanticValidationService(semantic_validator=semantic_validator)

    async def initialize(self, database_type: DatabaseType) -> None:
        """Initialize the service."""
        try:
            if hasattr(self.schema_repository, "initialize"):
                await self.schema_repository.initialize()

            await self.schema_manager.initialize(database_type)

            logger.info(
                "Query generation service initialized",
                provider=self.ai_provider.provider_type.value,
                database_type=database_type.value,
            )

        except Exception as e:
            logger.error("Failed to initialize query service", error=str(e))
            raise QueryGenerationException(f"Service initialization failed: {e!s}") from e

    async def generate_sql(
        self,
        question: str,
        database_type: DatabaseType,
        max_tokens: int | None = None,
        temperature: float | None = None,
        include_explanation: bool = True,
        execution_mode: str = "generate_only",
        timeout_seconds: int = 30,
        semantic_context: SemanticContext | None = None,
    ) -> dict[str, Any]:
        """Generate SQL query from natural language question."""
        try:
            start_time = datetime.now()
            resolved_max_tokens = max_tokens or settings.default_max_tokens
            resolved_temperature = temperature if temperature is not None else settings.default_temperature

            retrieval_plan = self.query_analysis_service.analyze(question)
            semantic_context, retrieval_plan = await self.semantic_resolution_service.resolve(
                question=question,
                retrieval_plan=retrieval_plan,
                database_type=database_type,
                semantic_context=semantic_context,
            )

            semantic_signature = self._semantic_signature(semantic_context)
            cache_key = (
                f"query:{question}:{database_type.value}:{self.ai_provider.provider_type.value}:"
                f"{execution_mode}:{resolved_max_tokens}:{resolved_temperature}:{semantic_signature}"
            )
            if (
                self.cache
                and execution_mode == "generate_only"
                and not self.semantic_resolution_service.is_configured
            ):
                cached_result = await self.cache.get(cache_key)
                if cached_result:
                    logger.info("Query served from cache", question=question[:50])
                    return cached_result

            relevant_tables = await self.schema_manager.find_relevant_tables(
                retrieval_plan.retrieval_query,
                database_type,
                self.max_examples * 2,
            )
            schema_context = await self.schema_manager.get_optimal_schema_context(
                retrieval_plan.retrieval_query,
                database_type,
                max_tokens or settings.max_schema_tokens,
            )
            examples = await self._find_relevant_examples(
                question,
                database_type,
                retrieval_plan,
                relevant_tables,
                semantic_context,
            )
            sql_intent_plan = self.sql_intent_planning_service.build(
                retrieval_plan=retrieval_plan,
                semantic_context=semantic_context,
                relevant_tables=list(relevant_tables),
                examples=examples,
            )

            query_context = self.prompt_assembly_service.build_query_context(
                question=question,
                database_type=database_type.value,
                schema_context=schema_context,
                retrieval_plan=retrieval_plan,
                examples=examples,
                semantic_context=semantic_context,
                sql_intent_plan=sql_intent_plan,
                max_tokens=resolved_max_tokens,
                temperature=resolved_temperature,
                metadata={
                    "service_version": "1.1",
                    "timestamp": start_time.isoformat(),
                    "relevant_tables": [table_name for table_name, _ in relevant_tables],
                },
            )

            response, validation_result, execution_validation, repair_attempts = await self._generate_response_pipeline(
                query_context=query_context,
                database_type=database_type,
                execution_mode=execution_mode,
                timeout_seconds=timeout_seconds,
                semantic_context=semantic_context,
                sql_intent_plan=sql_intent_plan,
            )

            result_metadata = {
                **(response.metadata or {}),
                "intent_context": (query_context.metadata or {}).get("intent_context", {}),
                "retrieval_plan": (query_context.metadata or {}).get("retrieval_plan", {}),
                "semantic_context": (query_context.metadata or {}).get("semantic_context", {}),
                "sql_intent_plan": (query_context.metadata or {}).get("sql_intent_plan", {}),
                "relevant_tables": (query_context.metadata or {}).get("relevant_tables", []),
                "selected_examples": [example.get("metadata", {}) for example in query_context.examples],
                "repair_attempts": repair_attempts,
                "execution_validation": execution_validation,
            }

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
                "examples_used": len(query_context.examples),
                "metadata": result_metadata,
            }

            if (
                self.cache
                and execution_mode == "generate_only"
                and validation_result.get("is_valid", False)
                and not self.semantic_resolution_service.is_configured
            ):
                await self.cache.set(cache_key, result)

            logger.info(
                "SQL generated successfully",
                question=question[:50],
                confidence=response.confidence,
                tokens_used=response.tokens_used,
                valid=validation_result.get("is_valid", False),
                execution_mode=execution_mode,
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

    async def validate_sql(self, sql: str, database_type: DatabaseType) -> dict[str, Any]:
        """Validate SQL query."""
        try:
            schema_context = await self.schema_manager.get_optimal_schema_context(
                sql, database_type, settings.max_schema_tokens
            )
            validation_result = await self.ai_provider.validate_query(sql, schema_context)
            validation_result["column_errors"] = await self._validate_column_names(sql)
            validation_result["dialect_issues"] = self._validate_dialect_rules(sql, database_type)

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
            raise ValidationException(f"SQL validation failed: {e!s}") from e

    async def get_query_suggestions(
        self, partial_question: str, database_type: DatabaseType, max_suggestions: int = 5
    ) -> list[dict[str, Any]]:
        """Get query suggestions based on partial input."""
        try:
            relevant_tables = await self.schema_manager.find_relevant_tables(
                partial_question, database_type, max_suggestions * 2
            )

            suggestions = []
            for table_name, relevance in relevant_tables:
                table_info = await self.schema_repository.get_table_info(table_name)
                suggestions.append(
                    {
                        "type": "table_exploration",
                        "text": f"Show me all data from {table_name}",
                        "relevance": relevance,
                        "table": table_name,
                        "description": f"Explore the {table_name} table",
                    }
                )

                for column in table_info.columns[:3]:
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

            suggestions.sort(key=lambda item: item["relevance"], reverse=True)
            return suggestions[:max_suggestions]

        except Exception as e:
            logger.error("Failed to get query suggestions", partial_question=partial_question, error=str(e))
            return []

    async def explain_query(self, sql: str, database_type: DatabaseType) -> dict[str, Any]:
        """Explain what an SQL query does."""
        try:
            schema_context = await self.schema_manager.get_optimal_schema_context(
                sql, database_type, settings.max_schema_tokens
            )
            explanation_context = QueryContext(
                question=f"Explain this SQL query: {sql}",
                database_type=database_type.value,
                schema_context=schema_context,
                examples=[],
                max_tokens=1000,
                temperature=0.1,
            )

            response = await self.ai_provider.generate_query(explanation_context)
            analysis: dict[str, Any] = {}
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
            raise QueryGenerationException(f"Query explanation failed: {e!s}") from e

    async def _generate_response_pipeline(
        self,
        query_context: QueryContext,
        database_type: DatabaseType,
        execution_mode: str,
        timeout_seconds: int,
        semantic_context: SemanticContext | None = None,
        sql_intent_plan: SqlIntentPlan | None = None,
    ) -> tuple[QueryResponse, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        response = await self.ai_provider.generate_query(query_context)
        repair_attempts: list[dict[str, Any]] = []

        while True:
            validation_result = await self._validate_generated_sql(
                response.sql,
                query_context.schema_context,
                database_type,
                semantic_context=semantic_context,
                sql_intent_plan=sql_intent_plan,
            )
            execution_validation = {"enabled": execution_mode != "generate_only", "success": None}

            if validation_result["column_errors"] and not (query_context.metadata or {}).get("_column_retry"):
                logger.info("Column validation failed, retrying", errors=validation_result["column_errors"])
                query_context = self._build_column_retry_context(query_context, validation_result["column_errors"])
                response = await self.ai_provider.generate_query(query_context)
                repair_attempts.append(
                    {"type": "column_retry", "errors": validation_result["column_errors"], "attempt": len(repair_attempts) + 1}
                )
                continue

            semantic_validation = validation_result.get("semantic_validation", {})
            semantic_issues = semantic_validation.get("issues", [])
            if (
                semantic_issues
                and execution_mode == "generate_validate_repair"
                and not (query_context.metadata or {}).get("_semantic_retry")
            ):
                issue_messages = [issue["message"] for issue in semantic_issues if issue.get("severity", "error") == "error"]
                if issue_messages:
                    logger.info("Semantic validation failed, retrying", issues=issue_messages)
                    query_context = self._build_semantic_retry_context(query_context, issue_messages)
                    response = await self.ai_provider.generate_query(query_context)
                    repair_attempts.append(
                        {
                            "type": "semantic_retry",
                            "issues": issue_messages,
                            "attempt": len(repair_attempts) + 1,
                        }
                    )
                    continue

            if self.enable_query_optimization and self.query_optimizer:
                optimization_result = await self.query_optimizer.optimize(response.sql)
                response.sql = optimization_result.optimized_query
                response.metadata = response.metadata or {}
                response.metadata["optimization"] = {
                    "applied": optimization_result.optimizations_applied,
                    "improvement": optimization_result.estimated_improvement,
                }

            if execution_mode == "generate_only" or self.execution_port is None:
                return response, validation_result, execution_validation, repair_attempts

            execution_validation = await self._execute_or_repair(
                response=response,
                query_context=query_context,
                database_type=database_type,
                execution_mode=execution_mode,
                timeout_seconds=timeout_seconds,
                repair_attempts=repair_attempts,
            )
            if execution_validation.get("success", False):
                return response, validation_result, execution_validation, repair_attempts

            if execution_mode != "generate_validate_repair":
                return response, validation_result, execution_validation, repair_attempts

            if not execution_validation.get("repaired_response"):
                return response, validation_result, execution_validation, repair_attempts

            response = execution_validation["repaired_response"]

    async def _execute_or_repair(
        self,
        response: QueryResponse,
        query_context: QueryContext,
        database_type: DatabaseType,
        execution_mode: str,
        timeout_seconds: int,
        repair_attempts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            result = await self.execution_port.execute_readonly(response.sql, timeout_seconds=timeout_seconds)
            return {
                "enabled": True,
                "success": True,
                "result": {
                    "row_count": result.get("row_count"),
                    "execution_time_ms": result.get("execution_time_ms"),
                },
            }
        except Exception as exc:
            if execution_mode != "generate_validate_repair" or not self.error_classifier or not self.repair_policy:
                return {"enabled": True, "success": False, "error": str(exc)}

            error_info = self.error_classifier.classify(str(exc), database_type, response.sql)
            decision = self.repair_policy.decide(error_info, database_type, len(repair_attempts))
            if not decision.should_retry:
                return {
                    "enabled": True,
                    "success": False,
                    "error": error_info.message,
                    "error_category": error_info.category,
                    "decision": decision.reason,
                }

            repair_context = RepairContext(
                original_question=query_context.question,
                database_type=database_type,
                previous_sql=response.sql,
                error=error_info,
                attempt=len(repair_attempts) + 1,
                schema_context=query_context.schema_context,
                examples=query_context.examples,
                metadata=query_context.metadata or {},
            )
            repaired_response = await self.query_repair_service.repair(
                question=query_context.question,
                database_type=database_type,
                schema_context=query_context.schema_context,
                examples=query_context.examples,
                repair_context=repair_context,
                max_tokens=query_context.max_tokens,
                temperature=0.0,
                metadata=query_context.metadata or {},
            )
            repair_attempts.append(
                {
                    "type": "execution_repair",
                    "attempt": repair_context.attempt,
                    "error_category": error_info.category,
                    "error": error_info.message,
                }
            )
            return {
                "enabled": True,
                "success": False,
                "error": error_info.message,
                "error_category": error_info.category,
                "decision": decision.reason,
                "repaired_response": repaired_response,
            }

    async def _validate_generated_sql(
        self,
        sql: str,
        schema_context: str,
        database_type: DatabaseType,
        semantic_context: SemanticContext | None = None,
        sql_intent_plan: SqlIntentPlan | None = None,
    ) -> dict[str, Any]:
        validation_result = await self.ai_provider.validate_query(sql, schema_context)
        column_errors = await self._validate_column_names(sql)
        dialect_issues = self._validate_dialect_rules(sql, database_type)
        semantic_validation = await self.semantic_validation_service.validate(sql, semantic_context, sql_intent_plan)

        issues_key = "errors" if "errors" in validation_result else "issues"
        validation_result.setdefault(issues_key, [])
        validation_result.setdefault("warnings", [])
        validation_result["column_errors"] = column_errors
        validation_result["dialect_issues"] = dialect_issues
        validation_result["semantic_validation"] = semantic_validation.to_metadata()

        if column_errors:
            validation_result[issues_key].extend(column_errors)
            validation_result["is_valid"] = False
        if dialect_issues:
            validation_result["warnings"].extend(dialect_issues)
        if semantic_validation.issues:
            validation_result[issues_key].extend(issue.message for issue in semantic_validation.issues)
            validation_result["is_valid"] = False
        if semantic_validation.warnings:
            validation_result["warnings"].extend(semantic_validation.warnings)

        return validation_result

    async def _find_relevant_examples(
        self,
        question: str,
        database_type: DatabaseType,
        retrieval_plan: Any,
        relevant_tables: Sequence[tuple[str, float]],
        semantic_context: SemanticContext | None = None,
    ) -> list[dict[str, Any]]:
        if not self.example_store:
            return []

        try:
            return await self.example_selection_service.select_examples(
                question=question,
                database_type=database_type,
                retrieval_plan=retrieval_plan,
                relevant_tables=relevant_tables,
                semantic_context=semantic_context,
            )
        except Exception as e:
            logger.warning("Failed to retrieve examples from store", error=str(e))
            return []

    async def _validate_column_names(self, sql: str) -> list[str]:
        """Validate column names in SQL against the columns of referenced tables."""
        if not self.query_validator:
            return []

        try:
            tables = await self.schema_manager.get_tables()
        except Exception:
            return []

        return await self.query_validator.validate_columns(sql, tables)

    def _validate_dialect_rules(self, sql: str, database_type: DatabaseType) -> list[str]:
        """Detect a few high-signal dialect mismatches before execution."""
        if database_type != DatabaseType.REDSHIFT:
            return []

        rules = [
            (r"\bTRUNC\s*\(", "Redshift requires DATE_TRUNC instead of TRUNC(date, format)."),
            (r"\bDISTINCT\s+ON\b", "Redshift does not support DISTINCT ON; use ROW_NUMBER with QUALIFY/CTE."),
            (r"\bSTRING_AGG\s*\(", "Redshift uses LISTAGG instead of STRING_AGG."),
            (r"\bgenerate_series\s*\(", "Redshift does not support generate_series()."),
            (r"\bARRAY_AGG\s*\(", "Redshift does not support ARRAY_AGG."),
            (r"\bNOW\s*\(", "Prefer GETDATE() or CURRENT_DATE in Redshift."),
            (r"\bINTERVAL\s+'", "Prefer DATEADD() instead of INTERVAL arithmetic in Redshift."),
        ]
        issues = []
        for pattern, message in rules:
            if re.search(pattern, sql, flags=re.IGNORECASE):
                issues.append(message)
        return issues

    def _build_column_retry_context(self, query_context: QueryContext, column_errors: list[str]) -> QueryContext:
        return QueryContext(
            question=(
                f"{query_context.question}\n\n"
                f"COLUMN ERRORS in previous attempt: {'; '.join(column_errors)}\n"
                "Fix the SQL using ONLY exact column names from the schema."
            ),
            database_type=query_context.database_type,
            schema_context=query_context.schema_context,
            examples=query_context.examples,
            max_tokens=query_context.max_tokens,
            temperature=0.0,
            metadata={**(query_context.metadata or {}), "_column_retry": True},
        )

    def _build_semantic_retry_context(self, query_context: QueryContext, semantic_issues: list[str]) -> QueryContext:
        return QueryContext(
            question=(
                f"{query_context.question}\n\n"
                f"SEMANTIC ISSUES in previous attempt: {'; '.join(semantic_issues)}\n"
                "Regenerate the SQL using the business context, required filters, preferred tables, and avoid rules."
            ),
            database_type=query_context.database_type,
            schema_context=query_context.schema_context,
            examples=query_context.examples,
            max_tokens=query_context.max_tokens,
            temperature=0.0,
            metadata={**(query_context.metadata or {}), "_semantic_retry": True},
        )

    def _semantic_signature(self, semantic_context: SemanticContext | None) -> str:
        if semantic_context is None or semantic_context.is_empty():
            return "no-semantic-context"
        payload = json.dumps(asdict(semantic_context), sort_keys=True, default=str)
        return hashlib.md5(payload.encode()).hexdigest()

    async def get_service_stats(self) -> dict[str, Any]:
        """Get service statistics."""
        stats = {
            "provider": self.ai_provider.provider_type.value,
            "provider_context_size": self.ai_provider.get_max_context_size(),
            "cache_enabled": self.cache is not None,
            "optimizer_enabled": self.query_optimizer is not None,
            "execution_port_enabled": self.execution_port is not None,
            "timestamp": datetime.now().isoformat(),
        }

        if self.cache:
            cache_stats = await self.cache.get_stats()
            stats["cache_stats"] = cache_stats

        return stats
