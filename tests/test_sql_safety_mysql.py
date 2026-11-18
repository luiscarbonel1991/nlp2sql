"""The read-only check reads a query the way MySQL and MariaDB do when told the dialect.

The queries of the first test were run on mysql:8.4 and mariadb:11.4: at least one of
the two executes the part that the PostgreSQL reading of the query treats as a
literal or a comment.
"""

import pytest

from nlp2sql.core.entities import DatabaseType
from nlp2sql.core.sql_safety import apply_row_limit, is_safe_query


def check(sql: str) -> tuple[bool, str]:
    return is_safe_query(sql, dialect=DatabaseType.MYSQL)


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        # MariaDB reads $a$ as a name, so what follows is code, not a dollar-quoted string
        ("SELECT 1 AS $a$, sleep(600) AS $a$", "prohibited function sleep()"),
        ("SELECT 1 AS $$, load_file('/etc/passwd') AS $$", "prohibited function load_file()"),
        # 5--1 is 5 - (-1): no comment starts there
        ("SELECT 5--1, sleep(600)", "prohibited function sleep()"),
        ("SELECT 1 --x\n FROM t; DELETE FROM t", "prohibited operation"),
        # The server runs what is inside these comments
        ("SELECT 1 /*! , sleep(600) */", "Comments that the server runs"),
        ("SELECT 1 /*!50000 , sleep(600) */", "Comments that the server runs"),
        ("SELECT 1 /*M! , sleep(600) */", "Comments that the server runs"),
        ("SELECT /*+ SET_VAR(max_execution_time=0) */ * FROM orders", "Comments that the server runs"),
        # A backtick name can hold a quote; the code after it is still code
        ("SELECT `it's`, sleep(600), `it's` FROM t", "prohibited function sleep()"),
        ("SELECT * FROM users INTO OUTFILE '/var/lib/mysql-files/users.csv'", "prohibited operation"),
        ("SELECT body FROM posts INTO DUMPFILE '/tmp/x'", "prohibited operation"),
        ("SELECT NEXT VALUE FOR order_seq", "prohibited operation"),
    ],
)
def test_code_that_mysql_runs_is_not_read_as_a_literal_or_a_comment(sql: str, reason: str) -> None:
    is_safe, error = check(sql)

    assert is_safe is False
    assert reason in error


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT sleep(600)",
        "SELECT sleep (600)",
        "SELECT sleep/**/(600)",
        "SELECT `sleep`(600)",
        'SELECT "sleep"(600)',
        "SELECT benchmark(100000000, md5('x'))",
        "SELECT load_file('/etc/passwd')",
        "SELECT get_lock('orders', 3600)",
        "SELECT release_all_locks()",
        "SELECT nextval(order_seq)",
    ],
)
def test_prohibited_mysql_functions_are_found_however_they_are_written(sql: str) -> None:
    is_safe, error = check(sql)

    assert is_safe is False
    assert "prohibited function" in error


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        (r"SELECT 'a\'' , sleep(600), ''", "ambiguous"),
        (r'SELECT "a\"" , sleep(600), ""', "ambiguous"),
        ("SELECT `abc", "unterminated quoted identifier"),
        ('SELECT "abc', "unterminated string"),
        ("SELECT 1 # note\n; DELETE FROM users", "prohibited operation"),
    ],
)
def test_queries_the_check_cannot_read_reliably_are_rejected(sql: str, reason: str) -> None:
    is_safe, error = check(sql)

    assert is_safe is False
    assert reason in error


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT `order`, `select`, `into` FROM `audit log`",
        "SELECT `a``b` FROM t",
        'SELECT name FROM users WHERE status = "please DELETE me"',
        'SELECT "say ""hi""" AS greeting',
        "SELECT id FROM users # active only; DELETE later",
        "SELECT id FROM users -- active only; DELETE later",
        "SELECT price - -1, 5--1 FROM products",
        "SELECT CAST(name AS CHAR CHARACTER SET utf8mb4) FROM users",
        "SELECT CONVERT(name USING utf8mb4), _utf8mb4'x', 0x41 FROM users",
        "SELECT price$usd FROM products",
        r"SELECT name FROM users WHERE name LIKE '%\_%'",
        "SELECT id FROM users LIMIT 5, 10",
    ],
)
def test_ordinary_mysql_queries_are_allowed(sql: str) -> None:
    assert check(sql) == (True, "")


def test_character_set_does_not_excuse_a_set_statement() -> None:
    is_safe, error = check("SELECT 1 FROM t WHERE character = 1; SET GLOBAL read_only = 0")

    assert is_safe is False
    assert "prohibited operation" in error


@pytest.mark.parametrize("dialect", [DatabaseType.MYSQL, "mysql", "MySQL", "mariadb"])
def test_the_dialect_is_a_database_type_or_its_name(dialect: object) -> None:
    assert is_safe_query("SELECT `id` FROM t # note", dialect=dialect) == (True, "")
    assert is_safe_query("SELECT sleep(1)", dialect=dialect)[0] is False


@pytest.mark.parametrize("dialect", [None, DatabaseType.POSTGRES, DatabaseType.REDSHIFT, "postgres"])
def test_other_dialects_keep_the_postgresql_reading(dialect: object) -> None:
    # A dollar-quoted string is data for PostgreSQL, and sleep() is not one of its functions
    assert is_safe_query("SELECT $a$, sleep(600) AS $a$", dialect=dialect) == (True, "")
    assert is_safe_query("SELECT pg_sleep(1)", dialect=dialect)[0] is False


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT * FROM users # top users", "SELECT * FROM users LIMIT 100"),
        ("SELECT * FROM users -- top users", "SELECT * FROM users LIMIT 100"),
        ("SELECT `limit` FROM users", "SELECT `limit` FROM users LIMIT 100"),
        ('SELECT "LIMIT" FROM users;', 'SELECT "LIMIT" FROM users LIMIT 100'),
        ("SELECT * FROM users LIMIT 5 # five", "SELECT * FROM users LIMIT 5 # five"),
    ],
)
def test_row_limit_is_not_hidden_by_mysql_comments_or_names(sql: str, expected: str) -> None:
    assert apply_row_limit(sql, 100, dialect=DatabaseType.MYSQL) == expected
