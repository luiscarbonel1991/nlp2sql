"""`nlp2sql inspect` applies its options and formats, and never prints the password.

Before, --include-tables, --exclude-tables, --exclude-system, --min-rows, --max-tables
and --sort-by were accepted and ignored, --format table and csv printed the summary,
and the summary printed the connection string with its password.
"""

import csv
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from nlp2sql.cli import cli
from nlp2sql.ports.schema_repository import TableInfo
from nlp2sql.schema.filters import filter_tables

URL = "postgresql://analyst:s3cret@db.example.com:5432/warehouse"


def _table(  # noqa: PLR0913 — one keyword per TableInfo field the tests vary
    name: str, rows: int, size: int, columns: int, *, foreign_keys: int = 0, schema: str = "public"
) -> TableInfo:
    return TableInfo(
        name=name,
        schema=schema,
        columns=[{"name": f"c{i}", "type": "integer"} for i in range(columns)],
        primary_keys=[],
        foreign_keys=[{"column": f"fk{i}"} for i in range(foreign_keys)],
        indexes=[],
        row_count=rows,
        size_bytes=size,
    )


TABLES = [
    _table("users", 8, 98_304, 13, foreign_keys=1),
    _table("orders", 12, 114_688, 12, foreign_keys=3),
    _table("audit_log", 5_000, 1_048_576, 4),
    _table("pg_stat_snapshot", 0, 8_192, 2),
]


def _inspect(*args: str, url: str = URL):
    repository = MagicMock()
    repository.get_tables = AsyncMock(return_value=TABLES)
    with patch("nlp2sql.factories.RepositoryFactory.create_and_initialize", new=AsyncMock(return_value=repository)):
        return CliRunner().invoke(cli, ["inspect", "--database-url", url, *args])


def _names(*args: str) -> list[str]:
    result = _inspect("--format", "json", *args)
    assert result.exit_code == 0, result.output
    return [table["name"] for table in json.loads(result.stdout)]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), ["audit_log", "orders", "pg_stat_snapshot", "users"]),
        (("--include-tables", "users, orders"), ["orders", "users"]),
        (("--exclude-tables", "users"), ["audit_log", "orders", "pg_stat_snapshot"]),
        (("--exclude-system",), ["audit_log", "orders", "users"]),
        (("--min-rows", "10"), ["audit_log", "orders"]),
        (("--sort-by", "rows"), ["audit_log", "orders", "users", "pg_stat_snapshot"]),
        (("--sort-by", "columns"), ["users", "orders", "audit_log", "pg_stat_snapshot"]),
        (("--sort-by", "size", "--max-tables", "2"), ["audit_log", "orders"]),
    ],
)
def test_options_select_and_order_the_tables(args, expected):
    assert _names(*args) == expected


def test_csv_has_one_row_per_table():
    result = _inspect("--format", "csv", "--include-tables", "users,orders")

    assert result.exit_code == 0, result.output
    rows = {row["name"]: row for row in csv.DictReader(io.StringIO(result.stdout))}
    assert set(rows) == {"users", "orders"}
    assert rows["users"]["row_count"] == "8"
    assert rows["users"]["columns"] == "13"
    assert rows["orders"]["foreign_keys"] == "3"


def test_table_format_lists_each_table():
    result = _inspect("--format", "table", "--sort-by", "size")

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0].split() == ["Table", "Rows", "Size", "Columns", "Foreign", "keys"]
    assert lines[2].split()[:4] == ["audit_log", "5,000", "1.0", "MB"]
    assert len(lines) == 2 + len(TABLES)


def test_summary_masks_the_password_and_counts_the_selection():
    result = _inspect("--include-tables", "users,orders")

    assert result.exit_code == 0, result.output
    assert "s3cret" not in result.output
    assert "postgresql://analyst:***@db.example.com:5432/warehouse" in result.stdout
    assert "Total tables: 2 (of 4)" in result.stdout


def test_an_invalid_url_is_not_echoed_back():
    result = CliRunner().invoke(cli, ["inspect", "--database-url", "postgress://analyst:s3cret@db/warehouse"])

    assert result.exit_code == 1
    assert "s3cret" not in result.output
    assert "unsupported scheme 'postgress'" in result.output


def test_min_rows_on_redshift_warns_that_rows_are_unknown():
    result = _inspect("--min-rows", "1", url="redshift://analyst:s3cret@c.x.redshift.amazonaws.com:5439/dev")

    assert result.exit_code == 0, result.output
    assert "Redshift tables report 0 rows" in result.stderr


def test_config_masks_the_database_password():
    result = CliRunner().invoke(cli, ["config"], env={"DATABASE_URL": URL})

    assert result.exit_code == 0, result.output
    assert "s3cret" not in result.output
    assert "analyst:***@db.example.com" in result.output


def test_filter_tables_matches_schema_filters_semantics():
    tables = [*TABLES, _table("events", 1, 1, 1, schema="analytics"), _table("sales.deals", 1, 1, 1, schema="")]

    assert [t.name for t in filter_tables(tables, include_schemas=["analytics"])] == ["events"]
    assert [t.name for t in filter_tables(tables, exclude_schemas=["public"])] == ["events", "sales.deals"]
    assert [t.name for t in filter_tables(tables, include_schemas=["sales"])] == ["sales.deals"]
    assert filter_tables(tables, include_tables=[]) == []
    assert "pg_stat_snapshot" not in [t.name for t in filter_tables(tables, exclude_system_tables=True)]
