"""PostgreSQL repository for schema management."""

import hashlib
import os
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..core.sql_safety import DEFAULT_QUERY_ROWS, apply_row_limit, is_safe_query
from ..exceptions import SchemaException, SecurityException
from ..ports.schema_repository import SchemaMetadata, SchemaRepositoryPort, TableInfo

logger = structlog.get_logger()

# Cache configuration
SCHEMA_CACHE_TTL_HOURS = int(os.getenv("NLP2SQL_SCHEMA_CACHE_TTL_HOURS", "24"))
SCHEMA_CACHE_VERSION = "2.0"  # v2: pg_catalog queries replace information_schema (Issue #32)


class PostgreSQLRepository(SchemaRepositoryPort):
    """PostgreSQL implementation of schema repository."""

    def __init__(self, connection_string: str, schema_name: str = "public"):
        self.connection_string = connection_string
        self.database_url = connection_string  # Add this line
        self.schema_name = schema_name
        self.engine = None
        self.async_engine = None
        self._connection_pool = None
        self._initialized = False
        self._cache_dir: Optional[Path] = None

    def _get_cache_dir(self) -> Path:
        """Get the cache directory for this database connection.

        Uses the same directory structure as embeddings for consistency.
        """
        if self._cache_dir is None:
            # Create hash of connection string for unique directory
            url_hash = hashlib.md5(self.connection_string.encode()).hexdigest()[:12]
            base_dir = Path(os.getenv("NLP2SQL_EMBEDDINGS_DIR", "./embeddings"))
            self._cache_dir = base_dir / url_hash
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir

    def _get_tables_cache_path(self, schema: str) -> Path:
        """Get path for the tables cache file."""
        return self._get_cache_dir() / f"tables_cache_{schema}.pkl"

    def _is_cache_valid(self, schema: str) -> bool:
        """Check if tables cache exists and is not expired."""
        cache_path = self._get_tables_cache_path(schema)
        if not cache_path.exists():
            return False

        try:
            with open(cache_path, "rb") as f:
                cache_data = pickle.load(f)

            # Check version
            if cache_data.get("version") != SCHEMA_CACHE_VERSION:
                logger.debug("Cache version mismatch, invalidating", path=str(cache_path))
                return False

            # Check TTL
            created_at = cache_data.get("created_at")
            if created_at is None:
                return False

            ttl = timedelta(hours=SCHEMA_CACHE_TTL_HOURS)
            if datetime.now() - created_at > ttl:
                age_hours = (datetime.now() - created_at).total_seconds() / 3600
                logger.debug("Cache expired", path=str(cache_path), age_hours=age_hours)
                return False

            # Check schema matches
            if cache_data.get("schema_name") != schema:
                return False

            return True

        except Exception as e:
            logger.warning("Failed to validate cache", error=str(e))
            return False

    def _load_tables_from_cache(self, schema: str) -> Optional[List[TableInfo]]:
        """Load tables from disk cache if valid."""
        if not self._is_cache_valid(schema):
            return None

        cache_path = self._get_tables_cache_path(schema)
        try:
            with open(cache_path, "rb") as f:
                cache_data = pickle.load(f)

            tables = cache_data.get("tables", [])
            logger.info(
                "Loaded tables from disk cache",
                count=len(tables),
                cache_path=str(cache_path),
            )
            return tables

        except Exception as e:
            logger.warning("Failed to load tables from cache", error=str(e))
            return None

    def _save_tables_to_cache(self, tables: List[TableInfo], schema: str) -> None:
        """Save tables to disk cache."""
        cache_path = self._get_tables_cache_path(schema)
        try:
            cache_data = {
                "tables": tables,
                "created_at": datetime.now(),
                "schema_name": schema,
                "table_count": len(tables),
                "version": SCHEMA_CACHE_VERSION,
            }

            with open(cache_path, "wb") as f:
                pickle.dump(cache_data, f)

            logger.info(
                "Tables saved to disk cache",
                count=len(tables),
                cache_path=str(cache_path),
            )

        except Exception as e:
            logger.warning("Failed to save tables to cache", error=str(e))

    def clear_cache(self) -> None:
        """Clear all cached data for this repository."""
        cache_dir = self._get_cache_dir()
        try:
            for cache_file in cache_dir.glob("tables_cache_*.pkl"):
                cache_file.unlink()
                logger.info("Cache file deleted", path=str(cache_file))
        except Exception as e:
            logger.warning("Failed to clear cache", error=str(e))

    async def initialize(self) -> None:
        """Initialize database connections."""
        if self._initialized:
            return

        try:
            # Convert connection string to asyncpg format
            asyncpg_url = self.connection_string.replace("postgresql://", "postgresql+asyncpg://")

            # Create async engine
            self.async_engine = create_async_engine(asyncpg_url, echo=False, pool_size=10, max_overflow=20)

            # Test connection
            async with self.async_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))

            self._initialized = True
            logger.info("PostgreSQL repository initialized")

        except Exception as e:
            logger.error("Failed to initialize PostgreSQL repository", error=str(e))
            raise SchemaException(f"Database initialization failed: {e!s}")

    async def get_tables(self, schema_name: Optional[str] = None, force_refresh: bool = False) -> List[TableInfo]:
        """Get all tables in the schema using hybrid bulk query + disk cache.

        Args:
            schema_name: Schema name to query (defaults to self.schema_name)
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            List of TableInfo objects
        """
        if not self._initialized:
            await self.initialize()

        schema = schema_name or self.schema_name

        # Step 1: Try to load from cache (unless force_refresh)
        if not force_refresh:
            cached_tables = self._load_tables_from_cache(schema)
            if cached_tables is not None:
                return cached_tables

        # Step 2: Execute bulk query
        logger.info("Fetching tables with bulk query...", schema=schema)
        tables = await self._get_tables_bulk(schema)

        # Step 3: Save to cache
        self._save_tables_to_cache(tables, schema)

        return tables

    async def _get_tables_bulk(self, schema: str) -> List[TableInfo]:
        """Fetch all tables with columns and primary keys in a single bulk query.

        This replaces the N+1 query pattern (1 + N*2 queries) with a single
        JOIN query, significantly improving performance for large schemas.
        """
        # Uses pg_catalog instead of information_schema to avoid ownership-based
        # filtering that hides tables from non-owner users (Issue #32).
        bulk_query = """
        WITH table_info AS (
            SELECT
                c.relname AS table_name,
                n.nspname AS table_schema,
                obj_description(c.oid) AS table_comment,
                pg_total_relation_size(c.oid) AS size_bytes,
                COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) AS row_count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE n.nspname = :schema
            AND c.relkind = 'r'
        ),
        columns_info AS (
            SELECT
                cls.relname AS table_name,
                a.attname AS column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable,
                pg_get_expr(d.adbin, d.adrelid) AS column_default,
                CASE
                    WHEN a.atttypid IN (1043, 1042) THEN a.atttypmod - 4
                    ELSE NULL
                END AS character_maximum_length,
                CASE
                    WHEN a.atttypid = 21 THEN 16
                    WHEN a.atttypid = 23 THEN 32
                    WHEN a.atttypid = 20 THEN 64
                    WHEN a.atttypid = 1700 AND a.atttypmod >= 0 THEN ((a.atttypmod - 4) >> 16) & 65535
                    ELSE NULL
                END AS numeric_precision,
                CASE
                    WHEN a.atttypid = 1700 AND a.atttypmod >= 0 THEN (a.atttypmod - 4) & 65535
                    ELSE NULL
                END AS numeric_scale,
                a.attnum AS ordinal_position,
                col_description(cls.oid, a.attnum) AS column_comment
            FROM pg_class cls
            JOIN pg_namespace ns ON ns.oid = cls.relnamespace
            JOIN pg_attribute a ON a.attrelid = cls.oid
            LEFT JOIN pg_attrdef d ON d.adrelid = cls.oid AND d.adnum = a.attnum
            WHERE ns.nspname = :schema
            AND cls.relkind = 'r'
            AND a.attnum > 0
            AND NOT a.attisdropped
        ),
        primary_keys AS (
            SELECT
                c.relname AS table_name,
                array_agg(a.attname ORDER BY k.ordinality) AS pk_columns
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ordinality)
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
            WHERE n.nspname = :schema
            AND con.contype = 'p'
            GROUP BY c.relname
        ),
        foreign_keys AS (
            SELECT
                c.relname AS table_name,
                a.attname AS column_name,
                refc.relname AS ref_table,
                refa.attname AS ref_column,
                con.conname AS constraint_name
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_class refc ON refc.oid = con.confrelid
            CROSS JOIN LATERAL unnest(con.conkey, con.confkey)
                WITH ORDINALITY AS k(attnum, refattnum, ordinality)
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
            JOIN pg_attribute refa ON refa.attrelid = con.confrelid AND refa.attnum = k.refattnum
            WHERE n.nspname = :schema
            AND con.contype = 'f'
        )
        SELECT
            t.table_name,
            t.table_schema,
            t.table_comment,
            t.size_bytes,
            t.row_count,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.column_comment,
            c.ordinal_position,
            pk.pk_columns,
            fk.column_name as fk_column,
            fk.ref_table,
            fk.ref_column,
            fk.constraint_name as fk_constraint
        FROM table_info t
        LEFT JOIN columns_info c ON t.table_name = c.table_name
        LEFT JOIN primary_keys pk ON t.table_name = pk.table_name
        LEFT JOIN foreign_keys fk ON t.table_name = fk.table_name AND c.column_name = fk.column_name
        ORDER BY t.table_name, c.ordinal_position
        """

        try:
            start_time = time.time()
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(bulk_query), {"schema": schema})
                rows = result.fetchall()

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.info("Bulk query completed", rows=len(rows), elapsed_ms=elapsed_ms)

            # Process rows and group by table
            tables_dict: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                table_name = row[0]

                if table_name not in tables_dict:
                    tables_dict[table_name] = {
                        "name": table_name,
                        "schema": row[1],
                        "description": row[2],
                        "size_bytes": row[3],
                        "row_count": row[4],
                        "columns": [],
                        "primary_keys": list(row[14]) if row[14] else [],
                        "foreign_keys": [],
                        "indexes": [],
                        "_seen_columns": set(),
                        "_seen_fks": set(),
                    }

                # Add column (avoiding duplicates from FK join)
                col_name = row[5]
                if col_name and col_name not in tables_dict[table_name]["_seen_columns"]:
                    tables_dict[table_name]["_seen_columns"].add(col_name)
                    tables_dict[table_name]["columns"].append(
                        {
                            "name": col_name,
                            "type": row[6],
                            "nullable": row[7] == "YES",
                            "default": row[8],
                            "max_length": row[9],
                            "precision": row[10],
                            "scale": row[11],
                            "description": row[12],
                        }
                    )

                # Add foreign key (if present and not seen)
                fk_column = row[15]
                fk_constraint = row[18]
                if fk_column and fk_constraint:
                    fk_key = f"{fk_constraint}:{fk_column}"
                    if fk_key not in tables_dict[table_name]["_seen_fks"]:
                        tables_dict[table_name]["_seen_fks"].add(fk_key)
                        tables_dict[table_name]["foreign_keys"].append(
                            {
                                "column": fk_column,
                                "ref_table": row[16],
                                "ref_column": row[17],
                                "constraint_name": fk_constraint,
                            }
                        )

            # Convert to TableInfo objects
            tables = []
            for table_data in tables_dict.values():
                # Remove internal tracking fields
                del table_data["_seen_columns"]
                del table_data["_seen_fks"]

                tables.append(
                    TableInfo(
                        name=table_data["name"],
                        schema=table_data["schema"],
                        columns=table_data["columns"],
                        primary_keys=table_data["primary_keys"],
                        foreign_keys=table_data["foreign_keys"],
                        indexes=table_data["indexes"],
                        row_count=table_data["row_count"],
                        size_bytes=table_data["size_bytes"],
                        description=table_data["description"],
                        last_updated=datetime.now(),
                    )
                )

            logger.info("Tables processed from bulk query", count=len(tables))
            return tables

        except Exception as e:
            logger.error("Bulk query failed", error=str(e))
            raise SchemaException(f"Failed to get tables: {e!s}")

    async def get_table_info(self, table_name: str, schema_name: Optional[str] = None) -> TableInfo:
        """Get detailed information about a specific table."""
        schema = schema_name or self.schema_name

        try:
            # Get basic table info
            table_query = """
            SELECT
                c.relname AS table_name,
                n.nspname AS table_schema,
                obj_description(c.oid) AS table_comment,
                pg_size_pretty(pg_total_relation_size(c.oid)) AS table_size,
                pg_total_relation_size(c.oid) AS size_bytes,
                COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) AS row_count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE c.relname = :table_name AND n.nspname = :schema
            AND c.relkind = 'r'
            """

            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(table_query), {"table_name": table_name, "schema": schema})
                row = result.fetchone()

                if not row:
                    raise SchemaException(f"Table {table_name} not found in schema {schema}")

                return await self._build_table_info(row, schema)

        except Exception as e:
            logger.error("Failed to get table info", table=table_name, error=str(e))
            raise SchemaException(f"Failed to get table info: {e!s}")

    async def search_tables(self, pattern: str) -> List[TableInfo]:
        """Search tables by name pattern."""
        query = """
        SELECT
            c.relname AS table_name,
            n.nspname AS table_schema,
            obj_description(c.oid) AS table_comment,
            pg_size_pretty(pg_total_relation_size(c.oid)) AS table_size,
            pg_total_relation_size(c.oid) AS size_bytes,
            COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) AS row_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        WHERE n.nspname = :schema
        AND c.relkind = 'r'
        AND (c.relname ILIKE :pattern OR obj_description(c.oid) ILIKE :pattern)
        ORDER BY c.relname
        """

        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(query), {"schema": self.schema_name, "pattern": f"%{pattern}%"})
                rows = result.fetchall()

                tables = []
                for row in rows:
                    table_info = await self._build_table_info(row, self.schema_name)
                    tables.append(table_info)

                return tables

        except Exception as e:
            logger.error("Failed to search tables", pattern=pattern, error=str(e))
            raise SchemaException(f"Failed to search tables: {e!s}")

    async def get_related_tables(self, table_name: str) -> List[TableInfo]:
        """Get tables related through foreign keys."""
        query = """
        WITH related_tables AS (
            -- Tables that reference this table (incoming FKs)
            SELECT DISTINCT
                src.relname AS related_table,
                srcn.nspname AS related_schema
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_namespace srcn ON srcn.oid = src.relnamespace
            JOIN pg_class tgt ON tgt.oid = con.confrelid
            JOIN pg_namespace tgtn ON tgtn.oid = tgt.relnamespace
            WHERE con.contype = 'f'
            AND tgt.relname = :table_name AND tgtn.nspname = :schema

            UNION

            -- Tables that this table references (outgoing FKs)
            SELECT DISTINCT
                tgt.relname AS related_table,
                tgtn.nspname AS related_schema
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_namespace srcn ON srcn.oid = src.relnamespace
            JOIN pg_class tgt ON tgt.oid = con.confrelid
            JOIN pg_namespace tgtn ON tgtn.oid = tgt.relnamespace
            WHERE con.contype = 'f'
            AND src.relname = :table_name AND srcn.nspname = :schema
        )
        SELECT
            tc.relname AS table_name,
            tn.nspname AS table_schema,
            obj_description(tc.oid) AS table_comment,
            pg_size_pretty(pg_total_relation_size(tc.oid)) AS table_size,
            pg_total_relation_size(tc.oid) AS size_bytes,
            COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) AS row_count
        FROM related_tables rt
        JOIN pg_class tc ON tc.relname = rt.related_table
        JOIN pg_namespace tn ON tn.oid = tc.relnamespace AND tn.nspname = rt.related_schema
        LEFT JOIN pg_stat_user_tables s ON s.relid = tc.oid
        WHERE tc.relkind = 'r'
        ORDER BY tc.relname
        """

        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(query), {"table_name": table_name, "schema": self.schema_name})
                rows = result.fetchall()

                tables = []
                for row in rows:
                    table_info = await self._build_table_info(row, self.schema_name)
                    tables.append(table_info)

                return tables

        except Exception as e:
            logger.error("Failed to get related tables", table=table_name, error=str(e))
            raise SchemaException(f"Failed to get related tables: {e!s}")

    async def get_schema_metadata(self) -> SchemaMetadata:
        """Get metadata about the entire schema."""
        query = """
        SELECT
            current_database() AS database_name,
            version() AS database_version,
            COUNT(*) AS total_tables,
            SUM(pg_total_relation_size(c.oid)) AS total_size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema
        AND c.relkind = 'r'
        """

        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(query), {"schema": self.schema_name})
                row = result.fetchone()

                return SchemaMetadata(
                    database_name=row[0],
                    database_type="postgres",
                    version=row[1],
                    total_tables=row[2],
                    total_size_bytes=row[3] or 0,
                    last_analyzed=datetime.now(),
                )

        except Exception as e:
            logger.error("Failed to get schema metadata", error=str(e))
            raise SchemaException(f"Failed to get schema metadata: {e!s}")

    async def refresh_schema(self) -> None:
        """Refresh schema information from database."""
        if not self._initialized:
            await self.initialize()

        try:
            # Update table statistics
            async with self.async_engine.begin() as conn:
                await conn.execute(text("ANALYZE"))

            logger.info("Schema refreshed successfully")

        except Exception as e:
            logger.error("Failed to refresh schema", error=str(e))
            raise SchemaException(f"Failed to refresh schema: {e!s}")

    async def get_table_sample_data(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get sample data from a table."""
        query = f"SELECT * FROM {self.schema_name}.{table_name} LIMIT :limit"

        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(query), {"limit": limit})
                rows = result.fetchall()
                columns = result.keys()

                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error("Failed to get sample data", table=table_name, error=str(e))
            raise SchemaException(f"Failed to get sample data: {e!s}")

    async def _build_table_info(self, row, schema: str) -> TableInfo:
        """Build TableInfo from database row."""
        table_name = row[0]

        # Get columns
        columns = await self._get_table_columns(table_name, schema)

        # Get primary keys
        primary_keys = await self._get_primary_keys(table_name, schema)

        # Get foreign keys
        foreign_keys = await self._get_foreign_keys(table_name, schema)

        # Get indexes
        indexes = await self._get_indexes(table_name, schema)

        return TableInfo(
            name=table_name,
            schema=schema,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes,
            row_count=row[5],
            size_bytes=row[4],
            description=row[2],
            last_updated=datetime.now(),
        )

    async def _get_table_columns(self, table_name: str, schema: str) -> List[Dict[str, Any]]:
        """Get column information for a table."""
        query = """
        SELECT
            a.attname AS column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
            CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable,
            pg_get_expr(d.adbin, d.adrelid) AS column_default,
            CASE
                WHEN a.atttypid IN (1043, 1042) THEN a.atttypmod - 4
                ELSE NULL
            END AS character_maximum_length,
            CASE
                WHEN a.atttypid = 21 THEN 16
                WHEN a.atttypid = 23 THEN 32
                WHEN a.atttypid = 20 THEN 64
                WHEN a.atttypid = 1700 AND a.atttypmod >= 0 THEN ((a.atttypmod - 4) >> 16) & 65535
                ELSE NULL
            END AS numeric_precision,
            CASE
                WHEN a.atttypid = 1700 AND a.atttypmod >= 0 THEN (a.atttypmod - 4) & 65535
                ELSE NULL
            END AS numeric_scale,
            col_description(c.oid, a.attnum) AS column_comment
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
        WHERE c.relname = :table_name AND n.nspname = :schema
        AND a.attnum > 0
        AND NOT a.attisdropped
        ORDER BY a.attnum
        """

        async with self.async_engine.begin() as conn:
            result = await conn.execute(text(query), {"table_name": table_name, "schema": schema})
            rows = result.fetchall()

            columns = []
            for row in rows:
                columns.append(
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "YES",
                        "default": row[3],
                        "max_length": row[4],
                        "precision": row[5],
                        "scale": row[6],
                        "description": row[7],
                    }
                )

            return columns

    async def _get_primary_keys(self, table_name: str, schema: str) -> List[str]:
        """Get primary key columns for a table."""
        query = """
        SELECT a.attname AS column_name
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
        WHERE c.relname = :table_name AND n.nspname = :schema
        AND con.contype = 'p'
        ORDER BY k.ordinality
        """

        async with self.async_engine.begin() as conn:
            result = await conn.execute(text(query), {"table_name": table_name, "schema": schema})
            rows = result.fetchall()

            return [row[0] for row in rows]

    async def _get_foreign_keys(self, table_name: str, schema: str) -> List[Dict[str, Any]]:
        """Get foreign key constraints for a table."""
        query = """
        SELECT
            a.attname AS column_name,
            refc.relname AS referenced_table,
            refa.attname AS referenced_column,
            con.conname AS constraint_name
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_class refc ON refc.oid = con.confrelid
        CROSS JOIN LATERAL unnest(con.conkey, con.confkey)
            WITH ORDINALITY AS k(attnum, refattnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
        JOIN pg_attribute refa ON refa.attrelid = con.confrelid AND refa.attnum = k.refattnum
        WHERE c.relname = :table_name AND n.nspname = :schema
        AND con.contype = 'f'
        ORDER BY k.ordinality
        """

        async with self.async_engine.begin() as conn:
            result = await conn.execute(text(query), {"table_name": table_name, "schema": schema})
            rows = result.fetchall()

            foreign_keys = []
            for row in rows:
                foreign_keys.append(
                    {"column": row[0], "ref_table": row[1], "ref_column": row[2], "constraint_name": row[3]}
                )

            return foreign_keys

    async def _get_indexes(self, table_name: str, schema: str) -> List[Dict[str, Any]]:
        """Get indexes for a table."""
        query = """
        SELECT
            i.relname as index_name,
            array_agg(a.attname ORDER BY c.ordinality) as columns,
            ix.indisunique as is_unique,
            ix.indisprimary as is_primary
        FROM pg_class t
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN unnest(ix.indkey) WITH ORDINALITY AS c(attnum, ordinality) ON true
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.attnum
        WHERE t.relname = :table_name AND n.nspname = :schema
        GROUP BY i.relname, ix.indisunique, ix.indisprimary
        ORDER BY i.relname
        """

        async with self.async_engine.begin() as conn:
            result = await conn.execute(text(query), {"table_name": table_name, "schema": schema})
            rows = result.fetchall()

            indexes = []
            for row in rows:
                indexes.append({"name": row[0], "columns": row[1], "unique": row[2], "primary": row[3]})

            return indexes

    async def execute_query(
        self,
        sql: str,
        limit: int = DEFAULT_QUERY_ROWS,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Execute a read-only SQL query and return results.

        Args:
            sql: The SQL query to execute (must be SELECT/WITH/EXPLAIN)
            limit: Maximum number of rows to return (max: 1000)
            timeout_seconds: Query timeout in seconds (default: 30)

        Returns:
            Dictionary with results, columns, row_count, and execution_time_ms

        Raises:
            SecurityException: If query contains prohibited operations
            SchemaException: If query execution fails
        """
        if not self._initialized:
            await self.initialize()

        # Validate query is safe
        is_safe, error_message = is_safe_query(sql)
        if not is_safe:
            logger.warning("Unsafe query rejected", sql=sql[:100], reason=error_message)
            raise SecurityException(f"Query rejected: {error_message}")

        # Apply row limit
        limited_sql = apply_row_limit(sql, limit)

        try:
            start_time = time.time()

            async with self.async_engine.begin() as conn:
                # Set statement timeout for safety
                timeout_ms = timeout_seconds * 1000
                await conn.execute(text(f"SET statement_timeout = {timeout_ms}"))

                # Execute the query
                result = await conn.execute(text(limited_sql))
                rows = result.fetchall()
                columns = list(result.keys())

                # Reset statement timeout
                await conn.execute(text("SET statement_timeout = 0"))

            execution_time_ms = round((time.time() - start_time) * 1000, 2)

            # Convert rows to list of dictionaries
            results = [dict(zip(columns, row)) for row in rows]

            logger.info(
                "Query executed successfully",
                row_count=len(results),
                execution_time_ms=execution_time_ms,
            )

            return {
                "results": results,
                "columns": columns,
                "row_count": len(results),
                "execution_time_ms": execution_time_ms,
            }

        except SecurityException:
            raise
        except Exception as e:
            logger.error("Query execution failed", error=str(e), sql=sql[:100])
            raise SchemaException(f"Query execution failed: {e!s}")
