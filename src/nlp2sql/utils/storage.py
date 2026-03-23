"""Writable directory resolution for persistent data (FAISS indexes, metadata).

Provides a three-level fallback strategy so that embedding indexes can be
persisted in both development and containerized environments (e.g., Claude
Desktop MCP where the working directory may be read-only).

Used by SchemaEmbeddingManager and ExampleStore.
"""

import os
from pathlib import Path

import structlog

logger = structlog.get_logger()


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
    tmp_dir = Path(f"/tmp/{tmp_fallback}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Using /tmp fallback for data directory (current directory not writable)",
        path=str(tmp_dir),
        env_var=env_var,
    )
    return tmp_dir
