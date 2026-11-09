"""Queries that hide code inside literals must not reach PostgreSQL, through ask() or execute_query().

Before the literal-aware check, each SQL in BYPASSES passed is_safe_query and ran on the
docker database: the hidden COMMIT kept a table created by the query, pg_read_file returned
/etc/passwd, and pg_sleep held the connection. The model output is faked, as when a prompt
injection makes a real model write such SQL.
"""

import time

import psycopg2
import pytest

import nlp2sql
from nlp2sql import ProviderConfig
from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.exceptions import SecurityException

pytestmark = pytest.mark.integration

PROBE_TABLE = "nlp2sql_safety_probe"
SLEEP_SECONDS = 3

BYPASSES = {
    "dollar_quote_hides_commit": f"SELECT $$'$$; COMMIT; CREATE TABLE {PROBE_TABLE} (id int); SELECT $$'$$",
    "dollar_quote_hides_pg_read_file": "SELECT $$'$$, pg_read_file('/etc/passwd') AS leaked, $$'$$",
    "e_string_hides_pg_sleep": f"SELECT E'\\'' , pg_sleep({SLEEP_SECONDS}), ''",
}


def _probe_table_exists(url: str) -> bool:
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{PROBE_TABLE}",))
        return cursor.fetchone()[0]


def _assert_nothing_ran(url: str, started: float, rows) -> None:
    assert not _probe_table_exists(url), "the hidden COMMIT kept a table created by the query"
    assert "root:" not in repr(rows), "pg_read_file returned a server file"
    assert time.monotonic() - started < SLEEP_SECONDS, "pg_sleep ran"


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", BYPASSES.values(), ids=BYPASSES.keys())
async def test_ask_does_not_run_sql_that_hides_code_in_literals(sql, postgres_available, fake_openai, isolated_caches):
    nlp = await nlp2sql.connect(postgres_available, provider=ProviderConfig(provider="openai", api_key="sk-test"))
    fake_openai.sql = sql

    started = time.monotonic()
    result = await nlp.ask("Show me the users", validate=True)

    _assert_nothing_ran(postgres_available, started, result.rows)
    assert result.is_valid is False
    assert result.rows is None
    assert any("Not a read-only query" in error for error in result.validation["errors"])


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", BYPASSES.values(), ids=BYPASSES.keys())
async def test_execute_query_rejects_sql_that_hides_code_in_literals(sql, postgres_available):
    # The path of the MCP server's run_sql tool
    repository = PostgreSQLRepository(postgres_available)

    started = time.monotonic()
    with pytest.raises(SecurityException):
        await repository.execute_query(sql)

    _assert_nothing_ran(postgres_available, started, None)


@pytest.mark.asyncio
async def test_literals_and_comments_are_read_as_postgresql_reads_them(postgres_available):
    # Allowed queries must run as the single statement the check read
    repository = PostgreSQLRepository(postgres_available)

    result = await repository.execute_query(
        "SELECT $$it's; DELETE$$ AS note, E'a\\nb' AS escaped, 'x''y' AS doubled, \"id\" "
        "FROM users /* ; DELETE FROM users */ ORDER BY id; -- done; DELETE",
        limit=1,
    )

    assert result["results"] == [{"note": "it's; DELETE", "escaped": "a\nb", "doubled": "x'y", "id": 1}]


@pytest.mark.asyncio
async def test_row_limit_applies_to_a_query_that_ends_with_a_comment(postgres_available):
    repository = PostgreSQLRepository(postgres_available)

    result = await repository.execute_query("SELECT id FROM users -- every user", limit=2)

    assert result["row_count"] == 2
