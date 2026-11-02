"""The CLI against the docker database: real row counts, and the caches connect() wrote.

Measured on 0.2.0rc17: `inspect` reported row_count 0 for every table of the docker
database (users has 8 rows) because it summed write counters since the last statistics
reset, and `cache info` found none of the files connect() had just written.
"""

import json

import psycopg2
import pytest
from click.testing import CliRunner

import nlp2sql
from nlp2sql import ProviderConfig
from nlp2sql.cli import cli

pytestmark = pytest.mark.integration


def _row_counts(url: str, tables: list[str]) -> dict[str, int]:
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        counts = {}
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — fixed table names
            counts[table] = cur.fetchone()[0]
    return counts


def _rewrite_rows_without_changing_them(url: str, table: str, times: int) -> None:
    """Add update counts to pg_stat_user_tables; the data stays the same."""
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            for _ in range(times):
                cur.execute(f"UPDATE {table} SET id = id")  # noqa: S608 — fixed table name
            cur.execute("SELECT pg_stat_force_next_flush()")
        conn.commit()
    finally:
        conn.close()


def test_inspect_reports_rows_not_writes(postgres_available, isolated_caches):
    # Two no-op updates make the old formula (inserts + updates + deletes) differ from the
    # row count both on a freshly loaded database and on one whose statistics were reset
    _rewrite_rows_without_changing_them(postgres_available, "users", times=2)

    result = CliRunner().invoke(
        cli, ["inspect", "--database-url", postgres_available, "--format", "json", "--include-tables", "users,orders"]
    )

    assert result.exit_code == 0, result.output
    reported = {table["name"]: table["row_count"] for table in json.loads(result.stdout)}
    assert reported == _row_counts(postgres_available, ["orders", "users"])


@pytest.mark.asyncio
async def test_cache_commands_find_and_clear_what_connect_wrote(postgres_available, fake_openai, isolated_caches):
    await nlp2sql.connect(
        postgres_available,
        provider=ProviderConfig(provider="openai", api_key="sk-test"),
        examples=[{"question": "How many users?", "sql": "SELECT COUNT(*) FROM users", "database_type": "postgres"}],
    )
    written = sorted(path for path in isolated_caches.rglob("*") if path.is_file())

    info = CliRunner().invoke(cli, ["cache", "info", "--database-url", postgres_available])
    clear = CliRunner().invoke(cli, ["cache", "clear", "--all", "--database-url", postgres_available])

    assert info.exit_code == 0, info.output
    for name in ("schema_index.faiss", "schema_metadata.pkl", "tables_cache_public.pkl", "examples_index.faiss"):
        assert name in info.stdout, name
    assert clear.exit_code == 0, clear.output
    assert f"Cleared {len(written)} cache file(s)" in clear.stdout
    assert not [path for path in isolated_caches.rglob("*") if path.is_file()]
