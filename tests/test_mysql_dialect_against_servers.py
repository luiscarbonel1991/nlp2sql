"""The MySQL prompt rules, dialect warnings and error classes, checked on MySQL and MariaDB.

Every statement the prompt recommends must run on both servers, and every PostgreSQL idiom
it warns against must fail on both, or return a wrong answer. If a server starts to accept
one, its rule can go.
"""

import pytest
from click.testing import CliRunner
from test_mysql_dialect_support import MYSQL_IDIOMS, POSTGRES_IDIOMS, SILENTLY_WRONG

from nlp2sql.adapters.default_error_classifier import DefaultErrorClassifier
from nlp2sql.cli import cli
from nlp2sql.core.entities import DatabaseType
from nlp2sql.exceptions import SchemaException

pytest.importorskip("pymysql")

from nlp2sql.adapters.mysql_repository import MySQLRepository

pytestmark = pytest.mark.integration

SLOW_QUERY = (
    "SELECT COUNT(*) FROM information_schema.COLUMNS a, information_schema.COLUMNS b, information_schema.COLUMNS c"
)

# SQL that fails on both servers -> the class the repair loop must see
FAILURES = {
    "unknown_column": ("SELECT nope FROM orders", "missing_column"),
    "unknown_table": ("SELECT * FROM nope", "missing_table"),
    "syntax": ("SELECT total_amount::int FROM orders", "function_not_supported"),
    "unknown_function": ("SELECT STRING_AGG(code, ', ') FROM stores", "function_not_supported"),
    "table_denied": ("SELECT * FROM mysql.user", "permission"),
    "timeout": (SLOW_QUERY, "timeout"),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", MYSQL_IDIOMS.values(), ids=MYSQL_IDIOMS.keys())
async def test_what_the_prompt_recommends_runs(sql: str, mysql_available: str) -> None:
    result = await MySQLRepository(mysql_available).execute_query(sql)

    assert result["row_count"] >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [sql for name, (sql, _) in POSTGRES_IDIOMS.items() if name not in SILENTLY_WRONG],
    ids=[name for name in POSTGRES_IDIOMS if name not in SILENTLY_WRONG],
)
async def test_what_the_prompt_warns_against_fails(sql: str, mysql_available: str) -> None:
    with pytest.raises(SchemaException, match=r"\((1064|1305),"):
        await MySQLRepository(mysql_available).execute_query(sql)


@pytest.mark.asyncio
async def test_double_pipe_and_double_quotes_return_a_wrong_answer_without_an_error(mysql_available: str) -> None:
    repository = MySQLRepository(mysql_available)

    piped = await repository.execute_query("SELECT first_name || ' ' || last_name AS full_name FROM users LIMIT 1")
    quoted = await repository.execute_query('SELECT "order_date" AS value FROM orders LIMIT 1')

    # Logical OR of three strings, and a string literal instead of the column
    assert piped["results"] == [{"full_name": 0}]
    assert quoted["results"] == [{"value": "order_date"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(("sql", "category"), FAILURES.values(), ids=FAILURES.keys())
async def test_real_errors_get_their_class(sql: str, category: str, mysql_available: str) -> None:
    with pytest.raises(SchemaException) as error:
        await MySQLRepository(mysql_available).execute_query(sql, timeout_seconds=1)

    info = DefaultErrorClassifier().classify(str(error.value), DatabaseType.MYSQL, sql)

    assert info.category == category, str(error.value)


@pytest.mark.asyncio
async def test_a_refused_write_is_classified_read_only(mysql_available: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nlp2sql.adapters.mysql_repository.is_safe_query", lambda sql, *, dialect=None: (True, ""))

    with pytest.raises(SchemaException) as error:
        await MySQLRepository(mysql_available).execute_query("UPDATE stores SET region = 'probe' WHERE id = 1")

    info = DefaultErrorClassifier().classify(str(error.value), DatabaseType.MYSQL, "UPDATE stores")

    assert (info.category, info.retryable) == ("read_only", False)


@pytest.mark.usefixtures("isolated_caches")
def test_inspect_names_the_database_as_the_schema(mysql_available: str) -> None:
    result = CliRunner().invoke(cli, ["inspect", "--database-url", mysql_available])

    assert result.exit_code == 0, result.output
    assert "Schema: testdb" in result.output
    assert "Total tables: 9" in result.output
