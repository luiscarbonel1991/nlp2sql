"""PostgreSQL itself refuses writes from nlp2sql, even SQL the safety check would miss.

The safety check is replaced by one that accepts everything, so only the database stands
between the query and a write. Before the read-only session, SELECT ... INTO made a table
(rolled back only because the connection closed without a commit), a COMMIT inside the
query kept the next statement's table, and nextval() moved a sequence for good.
"""

import psycopg2
import pytest

import nlp2sql
from nlp2sql import ProviderConfig
from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.exceptions import SchemaException

pytestmark = pytest.mark.integration

PROBE_TABLE = "nlp2sql_readonly_probe"

WRITES = {
    "select_into": f"SELECT * INTO {PROBE_TABLE} FROM users",
    # Ends in a SELECT, so the LIMIT that execute_query appends keeps it valid SQL
    "commit_then_create": f"SELECT 1; COMMIT; CREATE TABLE {PROBE_TABLE} AS SELECT 1 AS id",
    "nextval": "SELECT nextval('users_id_seq')",
}


@pytest.fixture
def check_misses_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    def accept(sql: str) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr("nlp2sql.adapters.postgres_repository.is_safe_query", accept)
    monkeypatch.setattr("nlp2sql.services.query_service.is_safe_query", accept)


def _database_state(url: str) -> tuple[bool, int]:
    """Whether the probe table exists, and the users id sequence position."""
    with psycopg2.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{PROBE_TABLE}",))
        table_exists = cursor.fetchone()[0]
        cursor.execute("SELECT last_value FROM users_id_seq")
        return table_exists, cursor.fetchone()[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", WRITES.values(), ids=WRITES.keys())
async def test_execute_query_cannot_write(sql, postgres_available, check_misses_everything):
    repository = PostgreSQLRepository(postgres_available)
    before = _database_state(postgres_available)

    with pytest.raises(SchemaException, match="read-only transaction"):
        await repository.execute_query(sql)

    assert _database_state(postgres_available) == before == (False, before[1])


@pytest.mark.asyncio
async def test_ask_cannot_write(postgres_available, check_misses_everything, fake_openai, isolated_caches):
    nlp = await nlp2sql.connect(postgres_available, provider=ProviderConfig(provider="openai", api_key="sk-test"))
    fake_openai.sql = WRITES["commit_then_create"]
    before = _database_state(postgres_available)

    result = await nlp.ask("Show me the users", validate=True)

    assert result.is_valid is False
    assert "read-only transaction" in result.metadata["execution_validation"]["error"]
    assert _database_state(postgres_available) == before


@pytest.mark.asyncio
async def test_statement_timeout_still_applies(postgres_available, check_misses_everything):
    repository = PostgreSQLRepository(postgres_available)

    with pytest.raises(SchemaException, match="statement timeout"):
        await repository.execute_query("SELECT pg_sleep(5)", timeout_seconds=1)
