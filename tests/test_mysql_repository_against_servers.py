"""The MySQL repository against MySQL 8.4 and MariaDB 11.4 (docker/mysql/init-schema.sql).

Every test runs once per server. The two differ where the repository has to adapt: the
statement timeout variable, how a column default is written, and the case of the column
names of information_schema.
"""

import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from conftest import EXPECTED_TABLES
from fakes.fake_openai import FakeOpenAI

import nlp2sql
from nlp2sql import ProviderConfig
from nlp2sql.exceptions import SchemaException

pymysql = pytest.importorskip("pymysql")

from nlp2sql.adapters.mysql_repository import MySQLRepository  # noqa: E402 - after the driver check

pytestmark = pytest.mark.integration

PROBE_TABLE = "nlp2sql_readonly_probe"

# Each one stays valid SQL with the LIMIT that execute_query appends
WRITES = {
    "update": "UPDATE stores SET region = 'probe' WHERE id = 1",
    "create_table": f"CREATE TABLE {PROBE_TABLE} AS SELECT 1 AS id",
    "commit_then_create": f"SELECT 1; COMMIT; CREATE TABLE {PROBE_TABLE} AS SELECT 1 AS id",
}

# Far more rows than either server can count in a second
SLOW_QUERY = (
    "SELECT COUNT(*) FROM information_schema.COLUMNS a, information_schema.COLUMNS b, information_schema.COLUMNS c"
)


def _is_mariadb(url: str) -> bool:
    return url.startswith("mariadb://")


def _database_state(url: str) -> tuple[bool, list[str]]:
    """Whether the probe table exists, and the regions of the stores."""
    parts = urlsplit(url)
    connection = pymysql.connect(
        host=parts.hostname,
        port=parts.port,
        user=parts.username,
        password=parts.password,
        database=parts.path.lstrip("/"),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
                (PROBE_TABLE,),
            )
            table_exists = cursor.fetchone()[0] > 0
            cursor.execute("SELECT region FROM stores ORDER BY id")
            return table_exists, [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()


@pytest.fixture
def check_misses_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    def accept(sql: str, *, dialect: object = None) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr("nlp2sql.adapters.mysql_repository.is_safe_query", accept)
    monkeypatch.setattr("nlp2sql.services.query_service.is_safe_query", accept)


@pytest.mark.asyncio
@pytest.mark.usefixtures("isolated_caches")
async def test_reads_the_base_tables_of_the_url_database(mysql_available: str) -> None:
    repository = MySQLRepository(mysql_available)

    tables = await repository.get_tables()

    # The two views of the schema are not tables
    assert {table.name for table in tables} == EXPECTED_TABLES
    assert {table.schema for table in tables} == {"testdb"}
    assert all(isinstance(table.row_count, int) and table.size_bytes > 0 for table in tables)


@pytest.mark.asyncio
@pytest.mark.usefixtures("isolated_caches")
async def test_a_table_carries_its_columns_keys_indexes_and_comment(mysql_available: str) -> None:
    orders = await MySQLRepository(mysql_available).get_table_info("orders")
    columns = {column["name"]: column for column in orders.columns}

    assert orders.description == "Transactional orders tied to stores and marketing channels"
    assert orders.primary_keys == ["id"]
    assert {(key["column"], key["ref_table"], key["ref_column"]) for key in orders.foreign_keys} == {
        ("user_id", "users", "id"),
        ("store_id", "stores", "id"),
        ("channel_id", "marketing_channels", "id"),
    }
    assert {"name": "idx_orders_status", "columns": ["status"], "unique": False, "primary": False} in orders.indexes
    assert {"name": "PRIMARY", "columns": ["id"], "unique": True, "primary": True} in orders.indexes
    assert list(columns)[:5] == ["id", "user_id", "store_id", "channel_id", "total_amount"]
    assert columns["total_amount"]["type"] == "decimal(10,2)"
    assert columns["total_amount"]["nullable"] is False
    assert (columns["total_amount"]["precision"], columns["total_amount"]["scale"]) == (10, 2)
    assert columns["status"]["max_length"] == 20  # noqa: PLR2004


@pytest.mark.asyncio
@pytest.mark.usefixtures("isolated_caches")
async def test_a_column_without_a_default_has_none_on_both_servers(mysql_available: str) -> None:
    orders = await MySQLRepository(mysql_available).get_table_info("orders")
    defaults = {column["name"]: column["default"] for column in orders.columns}

    # MariaDB reports the text NULL for it, and writes a string default with its quotes
    assert defaults["user_id"] is None
    assert defaults["status"] == ("'pending'" if _is_mariadb(mysql_available) else "pending")


@pytest.mark.asyncio
@pytest.mark.usefixtures("isolated_caches")
async def test_get_tables_and_get_table_info_describe_a_table_the_same_way(mysql_available: str) -> None:
    repository = MySQLRepository(mysql_available)

    listed = next(table for table in await repository.get_tables() if table.name == "order_items")
    single = await repository.get_table_info("order_items")

    assert (listed.columns, listed.primary_keys, listed.foreign_keys, listed.indexes) == (
        single.columns,
        single.primary_keys,
        single.foreign_keys,
        single.indexes,
    )


@pytest.mark.asyncio
async def test_a_table_that_does_not_exist_is_an_error(mysql_available: str) -> None:
    with pytest.raises(SchemaException, match="Table invoices not found in schema testdb"):
        await MySQLRepository(mysql_available).get_table_info("invoices")


@pytest.mark.asyncio
async def test_search_ignores_case_and_reads_comments(mysql_available: str) -> None:
    repository = MySQLRepository(mysql_available)

    by_name = await repository.search_tables("ORDER")
    by_comment = await repository.search_tables("storefront dimension")

    # The views order_summaries and store_channel_sales are not tables
    assert {table.name for table in by_name} == {"orders", "order_items"}
    assert {table.name for table in by_comment} == {"stores"}
    assert await repository.search_tables("no-such-table") == []


@pytest.mark.asyncio
async def test_related_tables_follow_foreign_keys_in_both_directions(mysql_available: str) -> None:
    related = await MySQLRepository(mysql_available).get_related_tables("orders")

    # orders references three tables, and order_items references orders
    assert {table.name for table in related} == {"users", "stores", "marketing_channels", "order_items"}


@pytest.mark.asyncio
async def test_metadata_names_the_database_and_the_server(mysql_available: str) -> None:
    metadata = await MySQLRepository(mysql_available).get_schema_metadata()

    assert metadata.database_name == "testdb"
    assert metadata.database_type == "mysql"
    assert metadata.total_tables == len(EXPECTED_TABLES)
    assert metadata.total_size_bytes > 0
    assert metadata.custom_metadata == {"server": "mariadb" if _is_mariadb(mysql_available) else "mysql"}
    assert ("MariaDB" in metadata.version) is _is_mariadb(mysql_available)


@pytest.mark.asyncio
async def test_sample_data_returns_the_first_rows(mysql_available: str) -> None:
    rows = await MySQLRepository(mysql_available).get_table_sample_data("stores", limit=2)

    assert [row["code"] for row in rows] == ["na_flagship", "eu_boutique"]


@pytest.mark.asyncio
async def test_execute_query_returns_rows_and_applies_the_limit(mysql_available: str) -> None:
    repository = MySQLRepository(mysql_available)

    # The % of LIKE is SQL here, not a placeholder of the driver
    result = await repository.execute_query("SELECT `email` FROM users WHERE email LIKE '%@%' ORDER BY id", limit=3)

    assert result["columns"] == ["email"]
    assert result["row_count"] == 3  # noqa: PLR2004 - of the 8 users
    assert all("@" in row["email"] for row in result["results"])


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", WRITES.values(), ids=WRITES.keys())
@pytest.mark.usefixtures("check_misses_everything")
async def test_execute_query_cannot_write(sql: str, mysql_available: str) -> None:
    repository = MySQLRepository(mysql_available)
    before = _database_state(mysql_available)

    # A write is refused by the read-only session; a second statement is a syntax error,
    # because the connection does not ask for multiple statements
    with pytest.raises(SchemaException, match=r"READ ONLY transaction|error in your SQL syntax"):
        await repository.execute_query(sql)

    assert _database_state(mysql_available) == before
    assert before[0] is False


@pytest.mark.asyncio
async def test_statement_timeout_stops_a_slow_query(mysql_available: str) -> None:
    repository = MySQLRepository(mysql_available)
    started = time.monotonic()

    with pytest.raises(SchemaException, match=r"max_statement_time exceeded|maximum statement execution time exceeded"):
        await repository.execute_query(SLOW_QUERY, timeout_seconds=1)

    # Stopped by the server, before the client's own read timeout
    assert time.monotonic() - started < 4  # noqa: PLR2004


@pytest.mark.asyncio
async def test_connect_and_ask_with_execution(
    mysql_available: str, fake_openai: FakeOpenAI, isolated_caches: Path
) -> None:
    nlp = await nlp2sql.connect(mysql_available, provider=ProviderConfig(provider="openai", api_key="sk-test"))

    result = await nlp.ask("How many users are there?", validate=True)

    assert isinstance(nlp._service.schema_repository, MySQLRepository)
    assert result.sql == fake_openai.sql
    assert result.is_valid is True, result.metadata
    assert (isolated_caches / "embeddings").exists()


@pytest.mark.asyncio
@pytest.mark.usefixtures("check_misses_everything", "isolated_caches")
async def test_ask_cannot_write(mysql_available: str, fake_openai: FakeOpenAI) -> None:
    nlp = await nlp2sql.connect(mysql_available, provider=ProviderConfig(provider="openai", api_key="sk-test"))
    fake_openai.sql = WRITES["create_table"]
    before = _database_state(mysql_available)

    result = await nlp.ask("Show me the users", validate=True)

    assert result.is_valid is False
    assert "READ ONLY transaction" in result.metadata["execution_validation"]["error"]
    assert _database_state(mysql_available) == before
