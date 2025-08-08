"""Core domain entities for nlp2sql."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DatabaseType(Enum):
    """Supported database types."""

    POSTGRES = "postgres"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    MSSQL = "mssql"
    ORACLE = "oracle"
    REDSHIFT = "redshift"


class QueryIntent(Enum):
    """Types of query intents."""

    SELECT = "select"
    AGGREGATE = "aggregate"
    JOIN = "join"
    FILTER = "filter"
    GROUP = "group"
    ORDER = "order"
    COMPLEX = "complex"


@dataclass
class Query:
    """Represents a natural language query."""

    text: str
    intent: Optional[QueryIntent] = None
    entities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SQLQuery:
    """Represents a generated SQL query."""

    sql: str
    database_type: DatabaseType
    tables_used: List[str]
    confidence: float
    explanation: str
    optimized: bool = False
    execution_time_ms: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SchemaElement:
    """Represents a schema element (table, column, etc.)."""

    name: str
    type: str  # table, column, index, etc.
    data_type: Optional[str] = None
    nullable: Optional[bool] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DatabaseSchema:
    """Represents a complete database schema."""

    name: str
    database_type: DatabaseType
    tables: List[SchemaElement]
    relationships: List[Dict[str, Any]]
    version: str
    analyzed_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryExample:
    """Example of natural language to SQL mapping."""

    natural_language: str
    sql: str
    database_type: DatabaseType
    intent: QueryIntent
    complexity: int  # 1-5 scale
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
