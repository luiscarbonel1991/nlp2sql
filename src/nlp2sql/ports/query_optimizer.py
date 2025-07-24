"""Query Optimizer Port - Interface for SQL query optimization."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class OptimizationLevel(Enum):
    """Optimization levels for queries."""

    NONE = "none"
    BASIC = "basic"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class OptimizationResult:
    """Result of query optimization."""

    original_query: str
    optimized_query: str
    optimizations_applied: List[str]
    estimated_improvement: Optional[float] = None
    warnings: List[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class QueryAnalysis:
    """Analysis of a SQL query."""

    tables_used: List[str]
    joins: List[Dict[str, Any]]
    filters: List[Dict[str, Any]]
    aggregations: List[str]
    subqueries: int
    estimated_cost: Optional[float] = None
    potential_issues: List[str] = None


class QueryOptimizerPort(ABC):
    """Abstract interface for query optimization."""

    @abstractmethod
    async def optimize(self, query: str, level: OptimizationLevel = OptimizationLevel.MODERATE) -> OptimizationResult:
        """Optimize SQL query."""
        pass

    @abstractmethod
    async def analyze(self, query: str) -> QueryAnalysis:
        """Analyze SQL query structure and performance."""
        pass

    @abstractmethod
    async def validate_syntax(self, query: str, database_type: str) -> Dict[str, Any]:
        """Validate SQL syntax for specific database."""
        pass

    @abstractmethod
    async def suggest_indexes(self, query: str, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest indexes to improve query performance."""
        pass

    @abstractmethod
    async def estimate_cost(self, query: str, schema: Dict[str, Any]) -> float:
        """Estimate query execution cost."""
        pass
