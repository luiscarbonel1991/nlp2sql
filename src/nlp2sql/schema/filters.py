"""Which tables a schema filter keeps.

Pure function shared by SchemaManager (``schema_filters``) and ``nlp2sql inspect``, so
both apply the same rules.
"""

from collections.abc import Collection, Iterable
from typing import Optional

from ..ports.schema_repository import TableInfo

SYSTEM_TABLE_PREFIXES = (
    "pg_",
    "sql_",
    "information_schema",
    "sys_",
    "sqlite_",
    "mysql.",
    "performance_schema",
)


def _schema_of(table: TableInfo) -> Optional[str]:
    if getattr(table, "schema", None):
        return table.schema
    if "." in table.name:
        return table.name.split(".")[0]
    return None


def filter_tables(  # noqa: PLR0913 — one keyword per schema_filters key
    tables: Iterable[TableInfo],
    *,
    include_schemas: Optional[Collection[str]] = None,
    exclude_schemas: Optional[Collection[str]] = None,
    include_tables: Optional[Collection[str]] = None,
    exclude_tables: Optional[Collection[str]] = None,
    exclude_system_tables: bool = False,
) -> list[TableInfo]:
    """Return the tables the filters keep, in their original order.

    ``include_*`` set to None keeps everything; an empty collection keeps nothing.
    System tables are recognized by name prefix (``SYSTEM_TABLE_PREFIXES``).
    """
    exclude_schemas = exclude_schemas or ()
    exclude_tables = exclude_tables or ()
    kept = []
    for table in tables:
        schema_name = _schema_of(table)
        if include_schemas is not None and schema_name not in include_schemas:
            continue
        if schema_name in exclude_schemas:
            continue
        if include_tables is not None and table.name not in include_tables:
            continue
        if table.name in exclude_tables:
            continue
        if exclude_system_tables and table.name.startswith(SYSTEM_TABLE_PREFIXES):
            continue
        kept.append(table)
    return kept
