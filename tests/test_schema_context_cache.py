"""The schema context must come from the table list loaded at initialization.

Regression for the rc15 field test: every ask() re-read each relevant table through
repository.get_table_info() (five queries per table, each on a fresh connection), so a
question with 8 relevant tables opened about 40 database connections.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nlp2sql.core.entities import DatabaseType
from nlp2sql.ports.schema_repository import TableInfo
from nlp2sql.schema.manager import SchemaManager


def _table(name: str) -> TableInfo:
    return TableInfo(
        name=name,
        schema="public",
        columns=[{"name": "id", "type": "integer", "nullable": False}],
        primary_keys=["id"],
        foreign_keys=[],
        indexes=[],
    )


def _manager(cached: list[str], relevant: list[str]) -> SchemaManager:
    repository = MagicMock()
    repository.get_tables = AsyncMock(return_value=[_table(name) for name in cached])
    repository.get_table_info = AsyncMock(side_effect=lambda name, *args: _table(name))

    analyzer = MagicMock()
    analyzer.build_context = AsyncMock(return_value="Table: users")

    manager = SchemaManager(repository=repository, embedding_manager=MagicMock(), analyzer=analyzer)
    manager._find_relevant_tables = AsyncMock(return_value=[(name, 0.9) for name in relevant])
    return manager


@pytest.mark.asyncio
async def test_cached_tables_are_not_fetched_again():
    manager = _manager(cached=["users", "orders"], relevant=["users", "orders"])

    await manager.get_optimal_schema_context("How many users?", DatabaseType.POSTGRES)

    manager.repository.get_table_info.assert_not_awaited()
    table_details = manager.analyzer.build_context.await_args.args[1]
    assert [table["name"] for table in table_details] == ["users", "orders"]


@pytest.mark.asyncio
async def test_a_table_missing_from_the_cache_is_fetched_from_the_repository():
    manager = _manager(cached=["users"], relevant=["users", "new_table"])

    await manager.get_optimal_schema_context("How many users?", DatabaseType.POSTGRES)

    manager.repository.get_table_info.assert_awaited_once_with("new_table")
