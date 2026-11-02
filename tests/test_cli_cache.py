"""`nlp2sql cache` finds the caches where the library writes them, and deletes only those.

Before, `cache info` looked for ./schema_index.faiss and ./query_cache.db, so it missed
the per-database indexes, and `cache clear --embeddings` deleted the whole embeddings
directory (table caches included) while leaving the example index.
tests/test_cli_against_postgres.py checks the same commands on caches written by connect().
"""

import pickle
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from nlp2sql.cli import cli
from nlp2sql.utils.storage import index_directory_name, tables_cache_directory_name

URL = "postgresql://analyst:s3cret@db.example.com:5432/warehouse"
OTHER_URL = "postgresql://analyst:s3cret@db.example.com:5432/staging"


def _write(path: Path, content: bytes = b"x" * 2048) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _tables_cache(path: Path, table_count: int) -> Path:
    data = {"tables": [], "created_at": datetime.now(), "schema_name": "public", "table_count": table_count}
    return _write(path, pickle.dumps(data))


@pytest.fixture
def caches(isolated_caches: Path) -> dict[str, Path]:
    embeddings, examples = isolated_caches / "embeddings", isolated_caches / "examples"
    index = embeddings / index_directory_name(URL, "public")
    other_index = embeddings / index_directory_name(OTHER_URL, "public")
    example_index = examples / index_directory_name(URL, "public")
    return {
        "schema_index": _write(index / "schema_index.faiss"),
        "schema_metadata": _write(index / "schema_metadata.pkl"),
        "other_schema_index": _write(other_index / "schema_index.faiss"),
        "tables": _tables_cache(embeddings / tables_cache_directory_name(URL) / "tables_cache_public.pkl", 9),
        "other_tables": _tables_cache(
            embeddings / tables_cache_directory_name(OTHER_URL) / "tables_cache_public.pkl", 4
        ),
        "example_index": _write(example_index / "examples_index.faiss"),
        "example_metadata": _write(example_index / "examples_metadata.pkl"),
        "unrelated": _write(embeddings / "notes" / "README.txt"),
    }


def _run(*args: str):
    return CliRunner().invoke(cli, ["cache", *args])


def test_info_lists_every_cache_with_its_location(caches):
    result = _run("info")

    assert result.exit_code == 0, result.output
    assert "Schema indexes: 2" in result.stdout
    assert str(caches["schema_index"].parent.resolve()) in result.stdout
    assert "Table caches: 2" in result.stdout
    assert "9 tables (schema: public" in result.stdout
    assert "Example indexes: 1" in result.stdout
    assert str(caches["example_index"].parent.resolve()) in result.stdout
    assert "query_cache.db" not in result.stdout


def test_info_for_one_database(caches):
    result = _run("info", "--database-url", OTHER_URL)

    assert result.exit_code == 0, result.output
    assert "analyst:***@" in result.stdout
    assert "s3cret" not in result.output
    assert str(caches["other_schema_index"].parent.resolve()) in result.stdout
    assert str(caches["schema_index"].parent.resolve()) not in result.stdout
    assert "4 tables" in result.stdout
    assert "Example indexes: none found" in result.stdout


def test_clear_embeddings_removes_indexes_and_keeps_table_caches(caches):
    result = _run("clear", "--embeddings")

    assert result.exit_code == 0, result.output
    for name in ("schema_index", "schema_metadata", "other_schema_index", "example_index", "example_metadata"):
        assert not caches[name].exists(), name
    assert not caches["schema_index"].parent.exists()
    assert caches["tables"].exists() and caches["other_tables"].exists()
    assert caches["unrelated"].exists()
    assert "Cleared 5 cache file(s)" in result.stdout


def test_clear_tables_for_one_database(caches):
    result = _run("clear", "--tables", "--database-url", URL)

    assert result.exit_code == 0, result.output
    assert not caches["tables"].exists()
    assert caches["other_tables"].exists()
    assert caches["schema_index"].exists()


def test_clear_all_never_touches_other_files(caches, isolated_caches):
    result = _run("clear", "--all")

    assert result.exit_code == 0, result.output
    remaining = sorted(p.relative_to(isolated_caches) for p in isolated_caches.rglob("*") if p.is_file())
    assert remaining == [Path("embeddings/notes/README.txt")]
    assert (isolated_caches / "embeddings").is_dir() and (isolated_caches / "examples").is_dir()


def test_clear_needs_to_be_told_what(caches):
    assert _run("clear").exit_code == 1


def test_there_is_no_query_cache_to_clear(caches):
    result = _run("clear", "--queries")

    assert result.exit_code == 0, result.output
    assert "no query cache on disk" in result.stdout
    assert caches["schema_index"].exists()
