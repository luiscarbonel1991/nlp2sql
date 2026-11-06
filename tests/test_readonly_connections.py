"""Every connection nlp2sql opens asks the database for read-only transactions.

Redshift cannot run in CI, so this checks the connection both repositories request; the
PostgreSQL side is also tested against the docker database (test_readonly_execution_against_postgres.py).
"""

from unittest.mock import MagicMock

import psycopg2
import pytest

from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.adapters.redshift_adapter import RedshiftRepository

REPOSITORIES = [
    pytest.param(PostgreSQLRepository, "postgresql://user:pass@localhost:5432/db", id="postgresql"),
    pytest.param(RedshiftRepository, "redshift://user:pass@cluster.example.com:5439/dev", id="redshift"),
]


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [{"id": 1}]
    conn.cursor.return_value.description = [("id",)]
    monkeypatch.setattr(psycopg2, "connect", MagicMock(return_value=conn))
    return conn


@pytest.mark.parametrize("repository_class, url", REPOSITORIES)
def test_connections_are_read_only(repository_class, url, connection):
    repository_class(url)._get_connection()

    connection.set_session.assert_called_once_with(readonly=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_class, url", REPOSITORIES)
async def test_execute_query_runs_on_a_read_only_connection_and_closes_it(repository_class, url, connection):
    repository = repository_class(url)
    repository._initialized = True

    result = await repository.execute_query("SELECT id FROM users")

    assert result["results"] == [{"id": 1}]
    connection.set_session.assert_called_once_with(readonly=True)
    connection.close.assert_called_once()
    connection.commit.assert_not_called()
