"""Writable directory resolution for persistent data (FAISS indexes, metadata).

Provides a three-level fallback strategy so that embedding indexes can be
persisted in both development and containerized environments (e.g., Claude
Desktop MCP where the working directory may be read-only).

Used by SchemaEmbeddingManager, ExampleStore, the schema repositories' table caches
and the ``nlp2sql cache`` commands, which must look where the library writes.
"""

import hashlib
import os
from pathlib import Path

from .logger import get_logger

logger = get_logger(__name__)

# (environment variable, ./default subdirectory, /tmp fallback) for get_data_directory
EMBEDDINGS_LOCATION = ("NLP2SQL_EMBEDDINGS_DIR", "embeddings", "nlp2sql_embeddings")
EXAMPLES_LOCATION = ("NLP2SQL_EXAMPLES_DIR", "examples_index", "nlp2sql_examples")


def index_directory_name(database_url: str, schema_name: str) -> str:
    """Directory of one database and schema's schema index and example index."""
    return hashlib.md5(f"{database_url}:{schema_name}".encode(), usedforsecurity=False).hexdigest()


def tables_cache_directory_name(database_url: str) -> str:
    """Directory of one database's table caches (``tables_cache_<schema>.pkl``)."""
    return hashlib.md5(database_url.encode(), usedforsecurity=False).hexdigest()[:12]


def _tmp_fallback_directory(tmp_fallback: str) -> Path:
    return Path(f"/tmp/{tmp_fallback}")  # noqa: S108 — fallback when the working directory is read-only


def get_data_directory(
    env_var: str,
    default_subdir: str,
    tmp_fallback: str,
) -> Path:
    """Resolve a writable directory with a three-level fallback chain.

    Resolution order:
        1. Value of *env_var* environment variable (explicit user config).
        2. ``./{default_subdir}`` under the current working directory
           (development default), verified writable via a probe file.
        3. ``/tmp/{tmp_fallback}`` (containerized / sandboxed fallback).

    Args:
        env_var: Environment variable name to check first.
        default_subdir: Subdirectory name under CWD for the development default.
        tmp_fallback: Directory name under ``/tmp`` for the container fallback.

    Returns:
        Path to a writable directory (created if necessary).
    """
    # 1. Explicit config via environment variable
    explicit_dir = os.getenv(env_var)
    if explicit_dir:
        return Path(explicit_dir)

    # 2. Development default with writable probe
    local_dir = Path(f"./{default_subdir}")
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        test_file = local_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        return local_dir
    except (OSError, PermissionError):
        pass

    # 3. Containerized fallback
    tmp_dir = _tmp_fallback_directory(tmp_fallback)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Using /tmp fallback for data directory (current directory not writable)",
        path=str(tmp_dir),
        env_var=env_var,
    )
    return tmp_dir


def existing_data_directories(env_var: str, default_subdir: str, tmp_fallback: str) -> list[Path]:
    """Where get_data_directory() may have written, without creating anything.

    With *env_var* set, only that directory; otherwise ``./{default_subdir}`` and the
    ``/tmp/{tmp_fallback}`` fallback. Only directories that exist are returned.
    """
    explicit_dir = os.getenv(env_var)
    candidates = (
        [Path(explicit_dir)] if explicit_dir else [Path(f"./{default_subdir}"), _tmp_fallback_directory(tmp_fallback)]
    )
    return [path for path in candidates if path.is_dir()]
