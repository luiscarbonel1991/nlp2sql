"""The table list of a schema, cached on disk: shared by the database adapters.

Reading the tables, columns and keys of a large schema takes seconds, so each adapter
keeps the result in a pickle file next to the schema index and reuses it until it is
older than NLP2SQL_SCHEMA_CACHE_TTL_HOURS.
"""

from __future__ import annotations

import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from ..ports.schema_repository import TableInfo
from ..utils.logger import get_logger
from ..utils.storage import EMBEDDINGS_LOCATION, get_data_directory, tables_cache_directory_name

logger = get_logger(__name__)

SCHEMA_CACHE_TTL_HOURS = int(os.getenv("NLP2SQL_SCHEMA_CACHE_TTL_HOURS", "24"))


class TablesCacheMixin:
    """Disk cache of get_tables() for a repository with a connection string and a schema.

    The adapter sets ``tables_cache_version`` and changes it whenever its queries fill
    TableInfo differently, so files written by an older release are read again from
    the database.
    """

    tables_cache_version: ClassVar[str]
    # A schema that looks empty is often one the user cannot see yet: an adapter can
    # choose not to remember that answer for the whole TTL
    cache_empty_table_list: ClassVar[bool] = True

    connection_string: str
    schema_name: str
    _cache_dir: Path | None

    def _get_cache_dir(self) -> Path:
        """Directory of this connection's cache: same base as the schema index, with its /tmp fallback."""
        if self._cache_dir is None:
            base_dir = get_data_directory(*EMBEDDINGS_LOCATION)
            self._cache_dir = base_dir / tables_cache_directory_name(self.connection_string)
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir

    def _get_tables_cache_path(self, schema: str) -> Path:
        return self._get_cache_dir() / f"tables_cache_{schema}.pkl"

    def _read_tables_cache(self, schema: str) -> dict[str, Any] | None:
        """The cache file of ``schema`` if it exists, is current and is not expired."""
        cache_path = self._get_tables_cache_path(schema)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open("rb") as f:
                cache_data = pickle.load(f)  # noqa: S301 - a file this class wrote, in the user's data directory
        except Exception as e:
            logger.warning("Failed to read tables cache", error=str(e))
            return None

        reason = self._why_unusable(cache_data, schema)
        if reason:
            logger.debug("Tables cache not used", path=str(cache_path), reason=reason)
            return None
        return cache_data

    def _why_unusable(self, cache_data: object, schema: str) -> str | None:
        if not isinstance(cache_data, dict) or cache_data.get("version") != self.tables_cache_version:
            return "written for another cache version"
        created_at = cache_data.get("created_at")
        if not isinstance(created_at, datetime):
            return "no creation time"
        if datetime.now() - created_at > timedelta(hours=SCHEMA_CACHE_TTL_HOURS):
            return "expired"
        if cache_data.get("schema_name") != schema:
            return "written for another schema"
        return None

    def _is_cache_valid(self, schema: str) -> bool:
        return self._read_tables_cache(schema) is not None

    def _load_tables_from_cache(self, schema: str) -> list[TableInfo] | None:
        cache_data = self._read_tables_cache(schema)
        if cache_data is None:
            return None

        tables = cache_data.get("tables", [])
        logger.info("Loaded tables from disk cache", count=len(tables), schema=schema)
        return tables

    def _save_tables_to_cache(self, tables: list[TableInfo], schema: str) -> None:
        if not tables and not self.cache_empty_table_list:
            logger.debug("Skipping cache save for empty tables list", schema=schema)
            return

        cache_path = self._get_tables_cache_path(schema)
        cache_data = {
            "tables": tables,
            "created_at": datetime.now(),
            "schema_name": schema,
            "table_count": len(tables),
            "version": self.tables_cache_version,
        }
        try:
            with cache_path.open("wb") as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            logger.warning("Failed to save tables to cache", error=str(e))
            return
        logger.info("Tables saved to disk cache", count=len(tables), cache_path=str(cache_path))

    def clear_cache(self) -> None:
        """Delete the cached table list of every schema of this connection."""
        try:
            for cache_file in self._get_cache_dir().glob("tables_cache_*.pkl"):
                cache_file.unlink()
                logger.info("Cache file deleted", path=str(cache_file))
        except Exception as e:
            logger.warning("Failed to clear cache", error=str(e))

    async def refresh_schema(self) -> None:
        """Drop the cached table list so the next get_tables() reads the database again.

        Runs nothing against the database.
        """
        cache_path = self._get_tables_cache_path(self.schema_name)
        try:
            cache_path.unlink()
        except FileNotFoundError:
            return
        except OSError as e:
            logger.warning("Failed to remove tables cache", path=str(cache_path), error=str(e))
            return
        logger.info("Schema cache invalidated", schema=self.schema_name)
