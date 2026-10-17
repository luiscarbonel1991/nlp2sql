"""Read-only checks must look at SQL structure, not at the data inside string literals."""

import pytest

from nlp2sql.core.sql_safety import is_safe_query


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
