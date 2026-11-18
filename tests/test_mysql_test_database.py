"""The MySQL and MariaDB test databases hold what the PostgreSQL one does.

docker/mysql/init-schema.sql is a translation of docker/init-schema.sql. These checks
read information_schema, where the MySQL adapter finds tables, keys and comments, so
a translation that loads but lost its foreign keys or comments fails here.
"""

from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from conftest import EXPECTED_TABLES

pymysql = pytest.importorskip("pymysql")

pytestmark = pytest.mark.integration

VIEWS = {"order_summaries", "store_channel_sales"}


@pytest.fixture
def cursor(mysql_available: str) -> Iterator["pymysql.cursors.Cursor"]:
    parts = urlsplit(mysql_available)
    connection = pymysql.connect(
        host=parts.hostname,
        port=parts.port,
        user=parts.username,
        password=parts.password,
        database=parts.path.lstrip("/"),
    )
    try:
        with connection.cursor() as cur:
            yield cur
    finally:
        connection.close()


def test_tables_and_views_match_the_postgres_schema(cursor: "pymysql.cursors.Cursor") -> None:
    cursor.execute("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = DATABASE()")
    found = dict(cursor.fetchall())

    assert {name for name, kind in found.items() if kind == "BASE TABLE"} == EXPECTED_TABLES
    assert {name for name, kind in found.items() if kind == "VIEW"} == VIEWS


def test_seed_rows_match_the_postgres_schema(cursor: "pymysql.cursors.Cursor") -> None:
    counts = {}
    for table in ("stores", "users", "products", "orders", "order_items", "daily_channel_metrics"):
        cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - fixed table names
        counts[table] = cursor.fetchone()[0]

    assert counts == {
        "stores": 3,
        "users": 8,
        "products": 10,
        "orders": 12,
        "order_items": 20,
        "daily_channel_metrics": 14,
    }


def test_foreign_keys_are_enforced_declarations_not_ignored_text(cursor: "pymysql.cursors.Cursor") -> None:
    cursor.execute(
        "SELECT table_name, column_name, referenced_table_name FROM information_schema.key_column_usage "
        "WHERE table_schema = DATABASE() AND referenced_table_name IS NOT NULL"
    )
    foreign_keys = set(cursor.fetchall())

    assert len(foreign_keys) == 12  # noqa: PLR2004 - one per REFERENCES of the PostgreSQL schema
    assert ("orders", "user_id", "users") in foreign_keys
    assert ("categories", "parent_id", "categories") in foreign_keys


def test_tables_carry_their_comments(cursor: "pymysql.cursors.Cursor") -> None:
    cursor.execute(
        "SELECT table_comment FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'orders'"
    )

    assert cursor.fetchone()[0] == "Transactional orders tied to stores and marketing channels"


def test_views_return_rows(cursor: "pymysql.cursors.Cursor") -> None:
    cursor.execute("SELECT COUNT(*) FROM order_summaries")
    assert cursor.fetchone()[0] == 12  # noqa: PLR2004 - one row per order

    cursor.execute("SELECT SUM(orders_count) FROM store_channel_sales")
    assert cursor.fetchone()[0] == 12  # noqa: PLR2004
