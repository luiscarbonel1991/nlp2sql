"""Core domain entities for nlp2sql."""

from dataclasses import asdict, dataclass, field
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


@dataclass
class QueryIntentContext:
    """Structured understanding of a natural language analytics question."""

    intent: QueryIntent
    business_terms: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    time_grains: List[str] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    expected_operations: List[str] = field(default_factory=list)
    requires_aggregation: bool = False
    requires_join: bool = False
    requires_ordering: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalPlan:
    """Signals shared across schema retrieval and example selection."""

    original_question: str
    normalized_question: str
    intent_context: QueryIntentContext
    retrieval_query: str
    example_query: str
    keyword_hints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticEntityMapping:
    """Resolved business term mapped to a concrete SQL concept."""

    source_term: str
    target: str
    resolved_value: str
    filter_expression: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        if self.filter_expression:
            return f"{self.source_term} -> {self.filter_expression}"
        return f"{self.source_term} -> {self.target} = {self.resolved_value}"


@dataclass
class MetricDefinition:
    """Canonical business metric description."""

    name: str
    expression: Optional[str] = None
    description: Optional[str] = None
    source_columns: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DimensionDefinition:
    """Canonical business dimension description."""

    name: str
    expression: Optional[str] = None
    description: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    allowed_values: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainRule:
    """Business guardrails that constrain SQL generation."""

    name: str
    description: str
    required_filters: List[str] = field(default_factory=list)
    preferred_tables: List[str] = field(default_factory=list)
    disallowed_tables: List[str] = field(default_factory=list)
    required_dimensions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalQueryPattern:
    """Reference query shape for a business domain."""

    name: str
    description: str
    canonical_sql: Optional[str] = None
    preferred_tables: List[str] = field(default_factory=list)
    metric_names: List[str] = field(default_factory=list)
    dimension_names: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticContext:
    """Resolved business semantic context for a question."""

    domain: Optional[str] = None
    entity_mappings: List[SemanticEntityMapping] = field(default_factory=list)
    metric_definitions: List[MetricDefinition] = field(default_factory=list)
    dimension_definitions: List[DimensionDefinition] = field(default_factory=list)
    canonical_tables: List[str] = field(default_factory=list)
    supporting_tables: List[str] = field(default_factory=list)
    required_filters: List[str] = field(default_factory=list)
    preferred_time_logic: List[str] = field(default_factory=list)
    disallowed_tables: List[str] = field(default_factory=list)
    prompt_hints: List[str] = field(default_factory=list)
    rules: List[DomainRule] = field(default_factory=list)
    patterns: List[CanonicalQueryPattern] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(
            [
                self.domain,
                self.entity_mappings,
                self.metric_definitions,
                self.dimension_definitions,
                self.canonical_tables,
                self.supporting_tables,
                self.required_filters,
                self.preferred_time_logic,
                self.disallowed_tables,
                self.prompt_hints,
                self.rules,
                self.patterns,
            ]
        )

    def to_metadata(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["entity_mappings"] = [
            {
                **asdict(mapping),
                "prompt_text": mapping.to_prompt_text(),
            }
            for mapping in self.entity_mappings
        ]
        return payload


@dataclass
class SqlIntentPlan:
    """Structured plan that narrows the space before SQL generation."""

    domain: Optional[str] = None
    fact_table: Optional[str] = None
    supporting_tables: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    time_range: Optional[str] = None
    group_by: List[str] = field(default_factory=list)
    order_by: List[str] = field(default_factory=list)
    semantic_context_ref: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticIssue:
    """Semantic issue detected before or after SQL generation."""

    category: str
    message: str
    severity: str = "error"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticValidationResult:
    """Result of semantic validation rules."""

    is_valid: bool = True
    issues: List[SemanticIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [asdict(issue) for issue in self.issues],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class ExampleCandidate:
    """Normalized example candidate produced by selection/reranking."""

    question: str
    sql: str
    score: float
    tables: List[str] = field(default_factory=list)
    intent: Optional[QueryIntent] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionErrorInfo:
    """Classified execution error used by repair policies."""

    category: str
    message: str
    retryable: bool
    hints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairDecision:
    """Decision returned by a repair policy."""

    should_retry: bool
    max_attempts: int
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairContext:
    """Context passed into the repair loop."""

    original_question: str
    database_type: DatabaseType
    previous_sql: str
    error: ExecutionErrorInfo
    attempt: int
    schema_context: str
    examples: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
