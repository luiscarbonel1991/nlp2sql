"""Public runtime configuration helpers for the high-level DSL."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.entities import SemanticContext
from ..ports.error_classifier import ErrorClassifierPort
from ..ports.query_execution import QueryExecutionPort
from ..ports.repair_policy import RepairPolicyPort
from ..ports.semantic_resolver import SemanticResolverPort
from ..ports.semantic_validator import SemanticValidatorPort


class ExecutionMode(str, Enum):
    """Execution modes exposed by the public DSL."""

    GENERATE_ONLY = "generate_only"
    GENERATE_AND_VALIDATE = "generate_and_validate"
    GENERATE_VALIDATE_REPAIR = "generate_validate_repair"


@dataclass(frozen=True)
class ExecutionHooks:
    """Grouped execution hooks for the public `connect()` API."""

    execution_port: QueryExecutionPort | None = None
    error_classifier: ErrorClassifierPort | None = None
    repair_policy: RepairPolicyPort | None = None


@dataclass(frozen=True)
class SemanticHooks:
    """Grouped semantic hooks for the public `connect()` API."""

    semantic_resolver: SemanticResolverPort | None = None
    semantic_validator: SemanticValidatorPort | None = None
    semantic_context: SemanticContext | None = None
