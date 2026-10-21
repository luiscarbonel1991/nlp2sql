"""refresh_schema() must invalidate the table cache and run nothing against the database.

PostgreSQLRepository.refresh_schema() used to run ANALYZE on the whole database (on the
first connect() and every 24 hours), which changed nothing nlp2sql reads, and
RedshiftRepository.refresh_schema() was a no-op, so neither actually refreshed the
cached table list.
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.adapters.redshift_adapter import RedshiftRepository

REPOSITORIES = [
    (PostgreSQLRepository, "postgresql://user:pass@localhost:5432/db"),
    (RedshiftRepository, "redshift://user:pass@localhost:5439/dev"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("repository_class", "url"), REPOSITORIES)
async def test_refresh_schema_drops_the_table_cache_without_touching_the_database(
    tmp_path: Path, repository_class, url, caplog
):
    caplog.set_level(logging.INFO, logger="nlp2sql")
    with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
        repository = repository_class(url)
        cache_path = repository._get_tables_cache_path(repository.schema_name)
        cache_path.write_bytes(b"cached tables")

        with patch.object(repository, "_get_connection", side_effect=AssertionError("no database access expected")):
            await repository.refresh_schema()

    assert not cache_path.exists()
    assert "Schema cache invalidated" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("repository_class", "url"), REPOSITORIES)
async def test_refresh_schema_without_a_cache_file_is_a_no_op(tmp_path: Path, repository_class, url, caplog):
    caplog.set_level(logging.INFO, logger="nlp2sql")
    with patch.dict("os.environ", {"NLP2SQL_EMBEDDINGS_DIR": str(tmp_path)}):
        repository = repository_class(url)
        await repository.refresh_schema()

    assert not repository._get_tables_cache_path(repository.schema_name).exists()
    # The first connect() refreshes before any cache exists; it used to log an invalidation
    assert "Schema cache invalidated" not in caplog.text
