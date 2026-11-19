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
    # Every rule was run against MySQL 8.4 and MariaDB 11.4. Rules 1 and 2 matter most: the
    # server accepts the wrong form and returns a wrong result instead of an error.
    "mysql": (
        "You specialize in MySQL and MariaDB SQL. Write SQL that runs on both. "
        "CRITICAL RULES: "
        '1) Quote identifiers with backticks (`order`), NEVER with double quotes: "name" is a string literal, '
        "so the query runs and returns the text instead of the column. "
        "2) Concatenate with CONCAT(a, b, ...), NEVER with ||, which is logical OR and returns 0 or 1. "
        "3) Write string literals in single quotes, and a quote inside one as '' (not \\'). "
        "4) There is no :: cast - use CAST(value AS type) with SIGNED, UNSIGNED, DECIMAL(p,s), CHAR, DATE or "
        "DATETIME (not INT, VARCHAR or TEXT). "
        "5) There is no ILIKE - LIKE already ignores case with the default collations. "
        "6) There is no DATE_TRUNC, TO_CHAR or EXTRACT(EPOCH ...) - use DATE_FORMAT(date, '%Y-%m-01'), YEAR(), "
        "MONTH(), DATE(), TIMESTAMPDIFF(unit, start, end) and UNIX_TIMESTAMP(). "
        "7) Date arithmetic is DATE_ADD(date, INTERVAL 1 MONTH) or date - INTERVAL 7 DAY: the unit is a keyword "
        "outside the quotes, never INTERVAL '1 month'. Use NOW() and CURDATE(). "
        "8) Use GROUP_CONCAT(col ORDER BY col SEPARATOR ', ') instead of STRING_AGG. "
        "9) There is no FULL OUTER JOIN - combine a LEFT JOIN and a RIGHT JOIN with UNION. "
        "10) There is no DISTINCT ON - use ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) in a subquery and "
        "keep the rows where it is 1. "
        "11) There is no NULLS FIRST or NULLS LAST - use ORDER BY col IS NULL, col. "
        "12) There is no FILTER (WHERE ...) - use SUM(CASE WHEN ... THEN 1 ELSE 0 END) or COUNT(CASE WHEN ... END). "
        "13) There is no generate_series(). "
        "14) Every selected column that is not inside an aggregate must be in GROUP BY. "
        "15) Limit rows with LIMIT n OFFSET m, not FETCH FIRST. "
        "16) Booleans are stored as 1 and 0."
    ),
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
