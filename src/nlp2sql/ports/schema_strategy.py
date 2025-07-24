"""Schema Strategy Port - Interface for schema handling strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class SchemaChunk:
    """Represents a chunk of schema information."""

    tables: List[str]
    token_count: int
    relevance_score: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SchemaContext:
    """Context for schema processing."""

    query: str
    max_tokens: int
    database_type: str
    include_samples: bool = False
    include_indexes: bool = True
    metadata: Optional[Dict[str, Any]] = None


class SchemaStrategyPort(ABC):
    """Abstract interface for schema handling strategies."""

    @abstractmethod
    async def chunk_schema(self, tables: List[Dict[str, Any]], max_chunk_size: int) -> List[SchemaChunk]:
        """Split schema into manageable chunks."""
        pass

    @abstractmethod
    async def score_relevance(self, query: str, schema_element: Dict[str, Any]) -> float:
        """Score relevance of schema element to query."""
        pass

    @abstractmethod
    async def compress_schema(self, schema: Dict[str, Any], target_tokens: int) -> str:
        """Compress schema information to fit token limit."""
        pass

    @abstractmethod
    async def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """Create embeddings for schema elements."""
        pass

    @abstractmethod
    async def find_similar_schemas(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """Find similar schema elements using embeddings."""
        pass

    @abstractmethod
    async def build_context(self, context: SchemaContext, tables: List[Dict[str, Any]]) -> str:
        """Build optimized schema context for query."""
        pass
