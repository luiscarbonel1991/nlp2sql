"""SQL safety constants and utilities — pure business logic, no external dependencies."""

import re

# SQL patterns that are not allowed for security (read-only enforcement)
DANGEROUS_SQL_PATTERNS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bCALL\b",
    r"\bSET\b",
    r"\bCOPY\b",
    r"\bUNLOAD\b",
    r"\bVACUUM\b",
]

ALLOWED_QUERY_PREFIXES = ("SELECT", "WITH", "EXPLAIN")

MAX_QUERY_ROWS = 1000
DEFAULT_QUERY_ROWS = 100


def is_safe_query(sql: str) -> tuple[bool, str]:
    """Check if a SQL query is safe to execute (read-only).

    Args:
        sql: The SQL query to validate.

    Returns:
        Tuple of (is_safe, error_message).
    """
    sql_upper = sql.upper().strip()

    # Must start with SELECT, WITH, or EXPLAIN
    if not any(sql_upper.startswith(prefix) for prefix in ALLOWED_QUERY_PREFIXES):
        return False, "Only SELECT, WITH, or EXPLAIN queries are allowed"

    # Check for dangerous patterns
    for pattern in DANGEROUS_SQL_PATTERNS:
        if re.search(pattern, sql_upper, re.IGNORECASE):
            return False, "Query contains prohibited operation"

    # Check for multiple statements (SQL injection protection)
    # Remove string literals before checking for semicolons
    sql_no_strings = re.sub(r"'(?:[^']|'')*'", "", sql)
    sql_no_strings = re.sub(r'"(?:[^"]|"")*"', "", sql_no_strings)
    if ";" in sql_no_strings.rstrip(";"):
        return False, "Multiple SQL statements are not allowed"

    return True, ""


def apply_row_limit(sql: str, limit: int) -> str:
    """Ensure query has a row limit applied.

    Args:
        sql: The SQL query.
        limit: Maximum rows to return.

    Returns:
        SQL with LIMIT clause applied.
    """
    limit = min(limit, MAX_QUERY_ROWS)

    # Remove string literals to avoid false positives
    # e.g., WHERE message LIKE '%LIMIT%' should not bypass the limit
    # Handle SQL escaped quotes: 'O''Reilly' -> '' (single quotes escaped by doubling)
    sql_no_strings = re.sub(r"'(?:[^']|'')*'", "''", sql)
    sql_no_strings = re.sub(r'"(?:[^"]|"")*"', '""', sql_no_strings)

    # Check for LIMIT keyword outside of strings (word boundary match)
    if re.search(r"\bLIMIT\b", sql_no_strings, re.IGNORECASE):
        return sql

    return f"{sql.rstrip(';')} LIMIT {limit}"
