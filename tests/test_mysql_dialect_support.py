"""MySQL in the parts around the repository: prompt rules, dialect warnings, error classes.

The SQL in MYSQL_IDIOMS and POSTGRES_IDIOMS is what the prompt recommends and warns
against. tests/test_mysql_dialect_against_servers.py runs the same statements on MySQL
and MariaDB, so a rule here cannot drift from what the servers do.
"""

import pytest

from nlp2sql.adapters.default_error_classifier import DefaultErrorClassifier
from nlp2sql.adapters.default_repair_policy import DefaultRepairPolicy
from nlp2sql.adapters.regex_query_validator import RegexQueryValidator
from nlp2sql.core.database_prompts import get_database_hint
from nlp2sql.core.entities import DatabaseType
from nlp2sql.ports.schema_repository import TableInfo
from nlp2sql.services.query_service import QueryGenerationService

# What the prompt recommends: runs on both servers, and raises no dialect warning
MYSQL_IDIOMS = {
    "backtick_name": "SELECT `order_date` FROM orders",
    "concat": "SELECT CONCAT(first_name, ' ', last_name) FROM users",
    "doubled_quote": "SELECT 'it''s'",
    "cast": "SELECT CAST('12' AS SIGNED), CAST(1.5 AS DECIMAL(10,2)), CAST(1 AS CHAR)",
    "like_ignores_case": "SELECT COUNT(*) FROM stores WHERE name LIKE '%DEMO%'",
    "date_format": "SELECT DATE_FORMAT(order_date, '%Y-%m-01') AS first_day, COUNT(*) FROM orders GROUP BY first_day",
    "timestampdiff": "SELECT TIMESTAMPDIFF(DAY, MIN(order_date), MAX(order_date)) FROM orders",
    "interval": "SELECT DATE_ADD(CURDATE(), INTERVAL 1 MONTH), NOW() - INTERVAL 7 DAY",
    "group_concat": "SELECT GROUP_CONCAT(code ORDER BY code SEPARATOR ', ') FROM stores",
    "full_join_as_union": (
        "SELECT u.id, o.id FROM users u LEFT JOIN orders o ON o.user_id = u.id "
        "UNION SELECT u.id, o.id FROM users u RIGHT JOIN orders o ON o.user_id = u.id"
    ),
    "row_number": (
        "SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_date DESC) AS rn "
        "FROM orders) latest WHERE rn = 1"
    ),
    "nulls_last": "SELECT promo_code FROM orders ORDER BY promo_code IS NULL, promo_code",
    "case_instead_of_filter": "SELECT SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) FROM orders",
    "limit_offset": "SELECT id FROM orders ORDER BY id LIMIT 2 OFFSET 1",
    "boolean": "SELECT COUNT(*) FROM stores WHERE is_active = 1",
}

# What the prompt warns against, with a word of the warning it raises
POSTGRES_IDIOMS = {
    "double_pipe": ("SELECT first_name || ' ' || last_name FROM users", "CONCAT"),
    "cast_operator": ("SELECT total_amount::int FROM orders", "CAST"),
    "ilike": ("SELECT COUNT(*) FROM stores WHERE name ILIKE '%demo%'", "ILIKE"),
    "string_agg": ("SELECT STRING_AGG(code, ', ') FROM stores", "GROUP_CONCAT"),
    "date_trunc": ("SELECT DATE_TRUNC('month', order_date) FROM orders", "DATE_FORMAT"),
    "full_outer_join": ("SELECT u.id FROM users u FULL OUTER JOIN orders o ON o.user_id = u.id", "UNION"),
    "distinct_on": ("SELECT DISTINCT ON (user_id) id FROM orders", "ROW_NUMBER"),
    "nulls_last": ("SELECT promo_code FROM orders ORDER BY promo_code NULLS LAST", "IS NULL"),
    "filter_clause": ("SELECT COUNT(*) FILTER (WHERE status = 'completed') FROM orders", "CASE WHEN"),
    "generate_series": ("SELECT * FROM generate_series(1, 3)", "generate_series"),
    "quoted_interval": ("SELECT CURDATE() - INTERVAL '1 month'", "INTERVAL 1 MONTH"),
}

# These two do not fail: the server returns a wrong answer
SILENTLY_WRONG = {"double_pipe"}


def _dialect_issues(sql: str, database_type: DatabaseType = DatabaseType.MYSQL) -> list[str]:
    return QueryGenerationService._validate_dialect_rules(object.__new__(QueryGenerationService), sql, database_type)


# ── Prompt ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rule",
    ["backticks", "CONCAT(", "GROUP_CONCAT(", "CAST(value AS type)", "DATE_FORMAT(", "INTERVAL 1 MONTH", "GROUP BY"],
)
def test_prompt_gives_the_model_the_mysql_rules(rule: str) -> None:
    assert rule in get_database_hint("mysql")


def test_prompt_says_the_two_mistakes_that_return_a_wrong_answer() -> None:
    hint = get_database_hint("mysql")

    assert "NEVER with double quotes" in hint
    assert "NEVER with ||" in hint


# ── Dialect warnings ─────────────────────────────────────────────────


@pytest.mark.parametrize(("sql", "word"), POSTGRES_IDIOMS.values(), ids=POSTGRES_IDIOMS.keys())
def test_a_postgres_idiom_raises_a_warning_that_names_the_mysql_form(sql: str, word: str) -> None:
    issues = _dialect_issues(sql)

    assert len(issues) == 1, issues
    assert word in issues[0]


@pytest.mark.parametrize("sql", MYSQL_IDIOMS.values(), ids=MYSQL_IDIOMS.keys())
def test_mysql_sql_raises_no_warning(sql: str) -> None:
    assert _dialect_issues(sql) == []


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM orders WHERE notes LIKE '%a || b%'",
        "SELECT id FROM orders WHERE notes = 'ratio 2::1, ILIKE, NULLS LAST and DATE_TRUNC('",
        "SELECT id FROM orders WHERE notes = 'it''s a FULL OUTER JOIN'",
    ],
    ids=["double-pipe", "several", "after-a-doubled-quote"],
)
def test_text_inside_a_string_literal_is_not_syntax(sql: str) -> None:
    assert _dialect_issues(sql) == []


def test_mysql_rules_do_not_apply_to_postgres() -> None:
    assert _dialect_issues("SELECT first_name || last_name FROM users", DatabaseType.POSTGRES) == []


# ── Error classifier ─────────────────────────────────────────────────

# Messages as execute_query raises them, copied from MySQL 8.4 and MariaDB 11.4
SYNTAX_ERROR_QUOTING_A_COLUMN = (
    'Query execution failed: (1064, "You have an error in your SQL syntax; check the manual that corresponds to '
    "your MySQL server version for the right syntax to use near '::int AS column_total FROM table_a' at line 1\")"
)
MYSQL_ERRORS = {
    "unknown_column": ("(1054, \"Unknown column 'nope' in 'field list'\")", "missing_column", True),
    "unknown_table": ("(1146, \"Table 'testdb.nope' doesn't exist\")", "missing_table", True),
    "syntax_near_column_and_table": (SYNTAX_ERROR_QUOTING_A_COLUMN, "function_not_supported", True),
    "unknown_function": ("(1305, 'FUNCTION testdb.STRING_AGG does not exist')", "function_not_supported", True),
    "group_by": (
        '(1055, "Expression #2 of SELECT list is not in GROUP BY clause and contains nonaggregated column '
        "'testdb.orders.total_amount' which is not functionally dependent on columns in GROUP BY clause\")",
        "execution_error",
        True,
    ),
    "mysql_timeout": (
        "(3024, 'Query execution was interrupted, maximum statement execution time exceeded')",
        "timeout",
        True,
    ),
    "mariadb_timeout": ("(1969, 'Query execution was interrupted (max_statement_time exceeded)')", "timeout", True),
    "table_denied": (
        "(1142, \"SELECT command denied to user 'reader'@'10.0.0.1' for table 'user'\")",
        "permission",
        False,
    ),
    "read_only": ("(1792, 'Cannot execute statement in a READ ONLY transaction.')", "read_only", False),
}


@pytest.mark.parametrize(("message", "category", "retryable"), MYSQL_ERRORS.values(), ids=MYSQL_ERRORS.keys())
def test_mysql_errors_are_classified_by_their_number(message: str, category: str, retryable: bool) -> None:
    info = DefaultErrorClassifier().classify(message, DatabaseType.MYSQL, "SELECT 1")

    assert (info.category, info.retryable) == (category, retryable)
    assert info.message == message


def test_group_by_error_tells_the_model_what_to_change() -> None:
    info = DefaultErrorClassifier().classify(MYSQL_ERRORS["group_by"][0], DatabaseType.MYSQL, "SELECT 1")

    assert "GROUP BY" in info.hints[0]


def test_a_mysql_error_number_it_does_not_know_falls_back_to_the_words() -> None:
    info = DefaultErrorClassifier().classify(
        "(1052, \"Column 'id' in field list is ambiguous\")", DatabaseType.MYSQL, "SELECT 1"
    )

    assert info.category == "missing_column"


def test_error_numbers_are_only_read_for_mysql() -> None:
    # In a PostgreSQL message, "(1792," would be part of the query text
    info = DefaultErrorClassifier().classify(
        'syntax error at or near "(1792, 2)"', DatabaseType.POSTGRES, "SELECT (1792, 2)"
    )

    assert info.category == "function_not_supported"


@pytest.mark.parametrize(
    ("message", "database_type"),
    [
        ("Query execution failed: cannot execute CREATE TABLE AS in a read-only transaction", DatabaseType.POSTGRES),
        ("Query execution failed: cannot execute INSERT in a read-only transaction", DatabaseType.REDSHIFT),
        (MYSQL_ERRORS["read_only"][0], DatabaseType.MYSQL),
    ],
    ids=["postgres", "redshift", "mysql"],
)
def test_a_refused_write_is_not_sent_back_to_the_model(message: str, database_type: DatabaseType) -> None:
    # It was "missing_table", retryable: the message names a table
    info = DefaultErrorClassifier().classify(message, database_type, "CREATE TABLE t AS SELECT 1")
    decision = DefaultRepairPolicy().decide(info, database_type, attempt=0)

    assert info.category == "read_only"
    assert decision.should_retry is False
    assert decision.reason == "non_retryable:read_only"


# ── Column validation ────────────────────────────────────────────────


def _table(name: str, columns: list[str]) -> TableInfo:
    return TableInfo(
        name=name,
        schema="shop",
        columns=[{"name": column} for column in columns],
        primary_keys=[],
        foreign_keys=[],
        indexes=[],
    )


TABLES = [_table("orders", ["id", "user_id", "total_amount", "date"]), _table("users", ["id", "email"])]


@pytest.mark.asyncio
async def test_backticked_names_are_checked_like_plain_ones() -> None:
    validator = RegexQueryValidator()

    # The validator reports a name that is part of a real column's name
    wrong = await validator.validate_columns("SELECT `amount` FROM `shop`.`orders`", TABLES)
    right = await validator.validate_columns(
        "SELECT `o`.`total_amount`, `u`.`email` FROM `orders` `o` JOIN `users` `u` ON `u`.`id` = `o`.`user_id`",
        TABLES,
    )

    assert len(wrong) == 1
    assert "Column 'amount' not found" in wrong[0]
    assert "total_amount" in wrong[0]
    assert right == []


@pytest.mark.asyncio
async def test_mysql_functions_are_not_taken_for_columns() -> None:
    # "date" is a column of orders, and it is inside the names of these functions
    sql = (
        "SELECT DATE_FORMAT(`date`, '%Y-%m') AS month_label, DATEDIFF(CURDATE(), MAX(`date`)) AS age_days "
        "FROM orders GROUP BY month_label"
    )

    assert await RegexQueryValidator().validate_columns(sql, TABLES) == []
