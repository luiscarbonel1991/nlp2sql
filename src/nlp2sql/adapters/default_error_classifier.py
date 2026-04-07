"""Default execution error classifier."""

from __future__ import annotations

from ..core.entities import DatabaseType, ExecutionErrorInfo
from ..ports.error_classifier import ErrorClassifierPort


class DefaultErrorClassifier(ErrorClassifierPort):
    """Classify common SQL execution errors into repair-friendly buckets."""

    def classify(
        self,
        error_message: str,
        database_type: DatabaseType,
        sql: str,
    ) -> ExecutionErrorInfo:
        lowered = error_message.lower()

        if any(token in lowered for token in ("column", "does not exist", "unknown column")):
            return ExecutionErrorInfo(
                category="missing_column",
                message=error_message,
                retryable=True,
                hints=["Verify exact column names from the schema.", "Avoid inferring columns not present in the schema."],
            )
        if any(token in lowered for token in ("relation", "table", "view", "not found")):
            return ExecutionErrorInfo(
                category="missing_table",
                message=error_message,
                retryable=True,
                hints=["Use only tables present in the retrieved schema context.", "Check schema prefixes if needed."],
            )
        if any(token in lowered for token in ("function", "not supported", "syntax error", "parse error")):
            hints = ["Regenerate using syntax supported by the target database."]
            if database_type == DatabaseType.REDSHIFT:
                hints.append("For Redshift avoid INTERVAL arithmetic, TRUNC(date, format), DISTINCT ON, and STRING_AGG.")
            return ExecutionErrorInfo(
                category="function_not_supported",
                message=error_message,
                retryable=True,
                hints=hints,
            )
        if any(token in lowered for token in ("permission", "access denied", "not authorized")):
            return ExecutionErrorInfo(
                category="permission",
                message=error_message,
                retryable=False,
                hints=["Choose accessible tables and columns only when the schema/context indicates they are available."],
            )
        if "timeout" in lowered:
            return ExecutionErrorInfo(
                category="timeout",
                message=error_message,
                retryable=True,
                hints=["Prefer simpler aggregations, fewer joins, and explicit limits."],
            )

        return ExecutionErrorInfo(
            category="execution_error",
            message=error_message,
            retryable=True,
            hints=["Regenerate the SQL with a simpler query shape and stricter adherence to the schema context."],
            metadata={"sql_preview": sql[:120]},
        )
