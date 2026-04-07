"""SQL dialect hints for AI providers.

Each entry provides database-specific guidance that helps AI providers
generate syntactically correct SQL for the target database. Centralized
here to avoid duplication across adapters.
"""

DATABASE_SQL_HINTS: dict[str, str] = {
    "postgres": (
        "You specialize in PostgreSQL syntax and features. "
        "Use PostgreSQL-specific functions and syntax when appropriate."
    ),
    "mysql": ("You specialize in MySQL syntax and features. Use MySQL-specific functions and syntax when appropriate."),
    "sqlite": (
        "You specialize in SQLite syntax and features. Use SQLite-specific functions and syntax when appropriate."
    ),
    "mssql": ("You specialize in SQL Server syntax and features. Use T-SQL syntax when appropriate."),
    "oracle": (
        "You specialize in Oracle SQL syntax and features. Use Oracle-specific functions and syntax when appropriate."
    ),
    "redshift": (
        "You specialize in Amazon Redshift SQL syntax for data warehouse analytics. "
        "CRITICAL RULES: "
        "1) Use DATEADD(datepart, n, date) instead of INTERVAL arithmetic "
        "(e.g., DATEADD(month, -1, CURRENT_DATE) not CURRENT_DATE - INTERVAL '1 month'). "
        "2) Use DATE_TRUNC('unit', date) for truncation - NEVER use TRUNC(date, 'format'). "
        "3) Use LISTAGG(col, delimiter) WITHIN GROUP (ORDER BY ...) instead of STRING_AGG. "
        "4) CONCAT() only takes 2 arguments - use || operator to chain more. "
        "5) Use GETDATE() or CURRENT_DATE instead of NOW(). "
        "6) DISTINCT ON is not supported - use ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) = 1 pattern. "
        "7) generate_series() is not supported - use CTEs or date tables for sequences. "
        "8) No ARRAY types or ARRAY_AGG - use SUPER type for semi-structured data. "
        "9) Use APPROXIMATE COUNT(DISTINCT col) for large cardinality counts. "
        "10) Prefer QUALIFY with ROW_NUMBER() when filtering window-function results. "
        "11) Avoid SELECT * - only select needed columns for columnar storage efficiency. "
        "12) Do not use unsupported PostgreSQL idioms such as NOW(), STRING_AGG, or INTERVAL literals."
    ),
}


def get_database_hint(database_type: str) -> str:
    """Get SQL dialect hint for a database type.

    Args:
        database_type: Database type string (e.g., 'postgres', 'redshift').

    Returns:
        Dialect-specific prompt hint, or empty string if unknown.
    """
    return DATABASE_SQL_HINTS.get(database_type.lower(), "")
