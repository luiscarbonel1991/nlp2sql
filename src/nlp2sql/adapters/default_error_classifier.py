"""Default execution error classifier."""

from __future__ import annotations

import re

from ..core.entities import DatabaseType, ExecutionErrorInfo
from ..ports.error_classifier import ErrorClassifierPort

# PyMySQL writes an error as "(1054, \"Unknown column ...\")". The number says what failed;
# the words do not: a syntax error quotes the query, which can hold "column" or "table",
# and "FUNCTION db.f does not exist" reads like a missing column.
_MYSQL_ERROR_CODE = re.compile(r"\((\d{4}),")

_MYSQL_SYNTAX_HINTS = [
    "Regenerate using syntax supported by MySQL and MariaDB.",
    "Avoid PostgreSQL idioms: :: casts, ILIKE, || concatenation, DATE_TRUNC, STRING_AGG, FULL OUTER JOIN, "
    "DISTINCT ON, NULLS LAST and INTERVAL '1 month'.",
]

# code -> (category, retryable, hints)
_MYSQL_ERRORS: dict[int, tuple[str, bool, list[str]]] = {
    1054: (
        "missing_column",
        True,
        ["Verify exact column names from the schema.", "Avoid inferring columns not present in the schema."],
    ),
    1146: (
        "missing_table",
        True,
        ["Use only tables present in the retrieved schema context.", "Check schema prefixes if needed."],
    ),
    1064: ("function_not_supported", True, _MYSQL_SYNTAX_HINTS),
    1305: ("function_not_supported", True, _MYSQL_SYNTAX_HINTS),
    1055: (
        "execution_error",
        True,
        ["Add every selected column that is not inside an aggregate function to GROUP BY."],
    ),
    3024: ("timeout", True, ["Prefer simpler aggregations, fewer joins, and explicit limits."]),
    1969: ("timeout", True, ["Prefer simpler aggregations, fewer joins, and explicit limits."]),
    1044: ("permission", False, ["The database user cannot read this database."]),
    1045: ("permission", False, ["The database user or its password was refused."]),
    1142: ("permission", False, ["The database user cannot read this table."]),
    1143: ("permission", False, ["The database user cannot read this column."]),
    1792: ("read_only", False, ["nlp2sql runs read-only queries: only SELECT statements can run."]),
}


class DefaultErrorClassifier(ErrorClassifierPort):
    """Classify common SQL execution errors into repair-friendly buckets."""

    def classify(
        self,
        error_message: str,
        database_type: DatabaseType,
        sql: str,
    ) -> ExecutionErrorInfo:
        lowered = error_message.lower()

        if database_type == DatabaseType.MYSQL:
            known = self._classify_mysql(error_message)
            if known is not None:
                return known

        # Before the words below: "cannot execute CREATE TABLE in a read-only transaction"
        # names a table, and asking the model again cannot make a write allowed
        if "read-only transaction" in lowered or "read only transaction" in lowered:
            return ExecutionErrorInfo(
                category="read_only",
                message=error_message,
                retryable=False,
                hints=["nlp2sql runs read-only queries: only SELECT statements can run."],
            )

        if any(token in lowered for token in ("column", "does not exist", "unknown column")):
            return ExecutionErrorInfo(
                category="missing_column",
                message=error_message,
                retryable=True,
                hints=[
                    "Verify exact column names from the schema.",
                    "Avoid inferring columns not present in the schema.",
                ],
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
                hints.append(
                    "For Redshift avoid INTERVAL arithmetic, TRUNC(date, format), DISTINCT ON, and STRING_AGG."
                )
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
                hints=[
                    "Choose accessible tables and columns only when the schema/context indicates they are available."
                ],
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

    @staticmethod
    def _classify_mysql(error_message: str) -> ExecutionErrorInfo | None:
        """Classify by the error number of MySQL and MariaDB, when the message carries one."""
        match = _MYSQL_ERROR_CODE.search(error_message)
        if match is None:
            return None
        code = int(match.group(1))
        known = _MYSQL_ERRORS.get(code)
        if known is None:
            return None
        category, retryable, hints = known
        return ExecutionErrorInfo(
            category=category,
            message=error_message,
            retryable=retryable,
            hints=list(hints),
            metadata={"mysql_error_code": code},
        )
