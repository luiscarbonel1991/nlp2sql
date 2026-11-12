"""Ports (interfaces) for nlp2sql."""

from .ai_provider import (
    AIProviderPort,
    AIProviderType,
    QueryContext,
    QueryResponse,
    checked_validation,
    validation_unavailable,
)
from .cache import CachePort
from .embedding_provider import EmbeddingProviderPort
from .query_optimizer import OptimizationLevel, OptimizationResult, QueryAnalysis, QueryOptimizerPort
from .schema_repository import SchemaMetadata, SchemaRepositoryPort, TableInfo
from .schema_strategy import SchemaChunk, SchemaContext, SchemaStrategyPort

__all__ = [
    # AI Provider
    "AIProviderPort",
    "AIProviderType",
    "QueryContext",
    "QueryResponse",
    "checked_validation",
    "validation_unavailable",
    # Cache
    "CachePort",
    # Embedding Provider
    "EmbeddingProviderPort",
    # Query Optimizer
    "QueryOptimizerPort",
    "OptimizationLevel",
    "OptimizationResult",
    "QueryAnalysis",
    # Schema Repository
    "SchemaRepositoryPort",
    "TableInfo",
    "SchemaMetadata",
    # Schema Strategy
    "SchemaStrategyPort",
    "SchemaChunk",
    "SchemaContext",
]
