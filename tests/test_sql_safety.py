"""Read-only checks must look at SQL structure, not at the data inside string literals."""

import pytest

from nlp2sql.core.sql_safety import apply_row_limit, is_safe_query


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM orders WHERE notes = 'customer asked to DELETE the account'",
        "SELECT name FROM products WHERE name = 'Gift Set'",
        "SELECT 'it''s an UPDATE' AS label",
        'SELECT "create" FROM audit_log',
    ],
)
def test_keywords_inside_literals_are_allowed(sql):
    assert is_safe_query(sql) == (True, "")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT dblink_exec('dbname=prod', 'DELETE FROM users')",
        "SELECT * FROM dblink('dbname=prod', 'SELECT 1') AS t(x int)",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity",
        "SELECT set_config('statement_timeout', '0', false)",
        "SELECT nextval('orders_id_seq')",
        "SELECT pg_sleep(600)",
    ],
)
def test_side_effecting_functions_are_rejected(sql):
    is_safe, error = is_safe_query(sql)
    assert is_safe is False
    assert "prohibited function" in error


def test_statement_hidden_after_a_literal_is_still_rejected():
    is_safe, _ = is_safe_query("SELECT 1 FROM t WHERE x = ''; DELETE FROM t; --'")
    assert is_safe is False


# Literals are found the way PostgreSQL finds them, so none of these can hide code
@pytest.mark.parametrize(
    "sql, reason",
    [
        ("SELECT $$'$$; COMMIT; CREATE TABLE probe (id int); SELECT $$'$$", "prohibited operation"),
        ("SELECT $$'$$; COMMIT; SELECT $$'$$", "Multiple SQL statements"),
        ("SELECT $tag$'$tag$; COMMIT; SELECT $tag$'$tag$", "Multiple SQL statements"),
        ("SELECT $$'$$, pg_read_file('/etc/passwd'), $$'$$", "prohibited function pg_read_file()"),
        (r"SELECT E'\'' , pg_sleep(600), ''", "ambiguous"),
        (r"SELECT 'a\'' , pg_sleep(600), ''", "ambiguous"),
        ("SELECT * INTO probe FROM users", "prohibited operation"),
        ("SELECT 1INTO probe FROM users", "prohibited operation"),
        ("SELECT 1; -- note\nDELETE FROM users", "prohibited operation"),
        ("SELECT 1 /* /* */ ; DELETE FROM users; /* */ */", "Nested comments"),
    ],
)
def test_literals_and_comments_cannot_hide_code(sql, reason):
    is_safe, error = is_safe_query(sql)
    assert is_safe is False
    assert reason in error


@pytest.mark.parametrize(
    "sql",
    [
        'SELECT "pg_sleep"(5)',
        "SELECT pg_catalog.pg_sleep(5)",
        "SELECT pg_sleep/**/(5)",
        "SELECT query_to_xml('select pg_read_file(''/etc/passwd'')', true, true, '')",
        "SELECT * FROM ts_stat('select to_tsvector(body) from posts')",
    ],
)
def test_prohibited_functions_are_found_however_they_are_written(sql):
    is_safe, error = is_safe_query(sql)
    assert is_safe is False
    assert "prohibited function" in error


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("SELECT 'abc", "unterminated string"),
        ("SELECT 1 /* note", "unterminated comment"),
        ('SELECT "abc', "unterminated quoted identifier"),
        ("SELECT $$abc", "unterminated dollar-quoted"),
        ("SELECT 'C:\\' AS path", "ambiguous"),
        ('SELECT U&"pg\\005fsleep"(5)', "Unicode-escaped identifiers"),
    ],
)
def test_queries_the_check_cannot_read_reliably_are_rejected(sql, reason):
    is_safe, error = is_safe_query(sql)
    assert is_safe is False
    assert reason in error


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT $$it's a DELETE; really$$ AS note",
        "SELECT $q$-- not a comment$q$ AS note",
        "SELECT E'it''s' AS s, E'line\\nbreak' AS t, E'back\\\\slash' AS u",
        "SELECT name FROM users WHERE name LIKE '%\\_%'",
        "-- most active customers\nSELECT id FROM users",
        "/* DELETE later; */ SELECT id FROM users",
        "SELECT id FROM users; -- done",
        "SELECT id FROM users /* ; DELETE FROM users */",
        'SELECT "into", "set" FROM audit_log',
        "SELECT price$usd FROM products WHERE id = $1",
    ],
)
def test_literals_comments_and_quoted_names_are_still_allowed(sql):
    assert is_safe_query(sql) == (True, "")


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("SELECT * FROM users -- top users", "SELECT * FROM users LIMIT 100"),
        ("SELECT * FROM users; -- done", "SELECT * FROM users LIMIT 100"),
        ("SELECT * FROM users /* LIMIT 5 */", "SELECT * FROM users LIMIT 100"),
        ("SELECT $$LIMIT$$ AS word FROM users", "SELECT $$LIMIT$$ AS word FROM users LIMIT 100"),
        ("SELECT * FROM users LIMIT 5 -- five", "SELECT * FROM users LIMIT 5 -- five"),
    ],
)
def test_row_limit_is_not_hidden_by_comments_or_literals(sql, expected):
    assert apply_row_limit(sql, 100) == expected
