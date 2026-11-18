"""The disk cache of get_tables() that the database adapters share."""

import pickle
from pathlib import Path

import pytest

from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.adapters.redshift_adapter import RedshiftRepository
from nlp2sql.ports.schema_repository import TableInfo

POSTGRES_URL = "postgresql://user:pass@localhost/db"
REDSHIFT_URL = "redshift://user:pass@cluster.example.com:5439/db"


def _table(name: str) -> TableInfo:
    return TableInfo(
        name=name,
        schema="public",
        columns=[{"name": "id", "type": "integer", "nullable": False}],
        primary_keys=["id"],
        foreign_keys=[],
        indexes=[],
    )


@pytest.fixture(autouse=True)
def cache_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("NLP2SQL_EMBEDDINGS_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize(
    ("repository", "url"), [(PostgreSQLRepository, POSTGRES_URL), (RedshiftRepository, REDSHIFT_URL)]
)
def test_tables_saved_by_one_repository_are_loaded_by_the_next(repository: type, url: str) -> None:
    repository(url)._save_tables_to_cache([_table("users")], "public")

    loaded = repository(url)._load_tables_from_cache("public")

    assert [table.name for table in loaded] == ["users"]


def test_postgres_remembers_an_empty_schema() -> None:
    PostgreSQLRepository(POSTGRES_URL)._save_tables_to_cache([], "public")

    assert PostgreSQLRepository(POSTGRES_URL)._load_tables_from_cache("public") == []


def test_redshift_does_not_remember_an_empty_schema() -> None:
    repository = RedshiftRepository(REDSHIFT_URL)

    repository._save_tables_to_cache([], "public")

    assert not repository._get_tables_cache_path("public").exists()
    assert repository._load_tables_from_cache("public") is None


def test_a_file_written_for_another_cache_version_is_ignored() -> None:
    repository = PostgreSQLRepository(POSTGRES_URL)
    repository._save_tables_to_cache([_table("users")], "public")
    path = repository._get_tables_cache_path("public")
    data = pickle.loads(path.read_bytes())  # noqa: S301 - written two lines above
    path.write_bytes(pickle.dumps({**data, "version": "0"}))

    assert repository._load_tables_from_cache("public") is None


def test_a_file_that_is_not_a_cache_is_ignored() -> None:
    repository = PostgreSQLRepository(POSTGRES_URL)
    repository._get_tables_cache_path("public").write_bytes(b"not a pickle")

    assert repository._load_tables_from_cache("public") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repository", "url"), [(PostgreSQLRepository, POSTGRES_URL), (RedshiftRepository, REDSHIFT_URL)]
)
async def test_refresh_schema_drops_only_the_file_of_its_schema(repository: type, url: str) -> None:
    repo = repository(url)
    repo._save_tables_to_cache([_table("users")], "public")
    repo._save_tables_to_cache([_table("events")], "analytics")

    await repo.refresh_schema()
    await repo.refresh_schema()  # nothing left to drop: no error

    assert repo._load_tables_from_cache("public") is None
    assert [table.name for table in repo._load_tables_from_cache("analytics")] == ["events"]
