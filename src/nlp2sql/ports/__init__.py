"""Ports (interfaces) for nlp2sql."""
from .ai_provider import AIProviderPort, AIProviderType, QueryContext, QueryResponse
from .cache import CachePort
from .query_optimizer import QueryOptimizerPort, OptimizationLevel, OptimizationResult, QueryAnalysis
from .schema_repository import SchemaRepositoryPort, TableInfo, SchemaMetadata
from .schema_strategy import SchemaStrategyPort, SchemaChunk, SchemaContext

__all__ = [
    # AI Provider
    "AIProviderPort",
    "AIProviderType", 
    "QueryContext",
    "QueryResponse",
    
    # Cache
    "CachePort",
    
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