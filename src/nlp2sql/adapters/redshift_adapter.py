"""Amazon Redshift repository for schema management."""

import asyncio
import hashlib
import os
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
import structlog
from psycopg2 import sql as psycopg2_sql
from psycopg2.extras import RealDictCursor

from ..core.sql_safety import DEFAULT_QUERY_ROWS, apply_row_limit, is_safe_query
from ..exceptions import SchemaException, SecurityException
from ..ports.schema_repository import (
    SchemaMetadata,
    SchemaRepositoryPort,
    TableInfo,
)

logger = structlog.get_logger()

# Cache configuration
SCHEMA_CACHE_TTL_HOURS = int(os.getenv("NLP2SQL_SCHEMA_CACHE_TTL_HOURS", "24"))
SCHEMA_CACHE_VERSION = "1.0"  # Increment when cache format changes


class RedshiftRepository(SchemaRepositoryPort):
    """Amazon Redshift implementation of schema repository.

    Uses psycopg2 directly for maximum compatibility with Redshift.
    SQLAlchemy dialects have issues with Redshift's custom configuration.
    """

    def __init__(self, connection_string: str, schema_name: str = "public"):
        self.connection_string = connection_string
        self.database_url = connection_string
        self.schema_name = schema_name.lower() if schema_name else schema_name
        self._connection_params = self._parse_connection_string(connection_string)
        self._initialized = False
        self._cache_dir: Optional[Path] = None
        # System view configuration (auto-detected at init)
        self._table_view: str = "svv_tables"
        self._column_view: str = "svv_columns"
        self._schema_col: str = "table_schema"
        self._db_filter: str = ""
        self._db_filter_aliased: str = ""

    def _get_cache_dir(self) -> Path:
        """Get the cache directory for this database connection."""
        if self._cache_dir is None:
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

            if cache_data.get("version") != SCHEMA_CACHE_VERSION:
                return False

            created_at = cache_data.get("created_at")
            if created_at is None:
                return False

            ttl = timedelta(hours=SCHEMA_CACHE_TTL_HOURS)
            if datetime.now() - created_at > ttl:
                return False

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
            logger.info("Loaded tables from disk cache", count=len(tables))
            return tables

        except Exception as e:
            logger.warning("Failed to load tables from cache", error=str(e))
            return None

    def _save_tables_to_cache(self, tables: List[TableInfo], schema: str) -> None:
        """Save tables to disk cache. Skips caching if tables list is empty."""
        if not tables:
            logger.debug("Skipping cache save for empty tables list", schema=schema)
            return

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

            logger.info("Tables saved to disk cache", count=len(tables))

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

    def _parse_connection_string(self, conn_str: str) -> Dict[str, Any]:
        """Parse connection string into psycopg2 parameters."""
        # Handle redshift:// or postgresql:// prefix
        if conn_str.startswith("redshift://"):
            conn_str = conn_str[11:]  # Remove "redshift://"
        elif conn_str.startswith("postgresql://"):
            conn_str = conn_str[13:]  # Remove "postgresql://"

        # Parse user:password@host:port/database
        auth_host, database = conn_str.rsplit("/", 1)
        auth, host_port = auth_host.rsplit("@", 1)
        user, password = auth.split(":", 1)

        if ":" in host_port:
            host, port = host_port.split(":", 1)
            port = int(port)
        else:
            host = host_port
            port = 5439  # Default Redshift port

        return {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
            "sslmode": "prefer",
        }

    def _get_connection(self):
        """Create a new database connection."""
        return psycopg2.connect(**self._connection_params)

    async def initialize(self) -> None:
        """Initialize database connections and detect available system views."""
        if self._initialized:
            return

        try:

            def test_connection():
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()

            await asyncio.to_thread(test_connection)
            await self._detect_system_views()

            self._initialized = True
            logger.info("Redshift repository initialized", table_view=self._table_view)

        except SchemaException:
            raise
        except Exception as e:
            logger.error("Failed to initialize Redshift repository", error=str(e))
            raise SchemaException(f"Database initialization failed: {e!s}")

    async def _detect_system_views(self) -> None:
        """Auto-detect which system views are available for this connection.

        Fallback chain: svv_tables → svv_all_tables → information_schema
        """
        probes = [
            {
                "table_view": "svv_tables",
                "column_view": "svv_columns",
                "schema_col": "table_schema",
                "db_filter": "",
                "db_filter_aliased": "",
                "query": "SELECT COUNT(*) as cnt FROM svv_tables WHERE table_schema = %s",
            },
            {
                "table_view": "svv_all_tables",
                "column_view": "svv_all_columns",
                "schema_col": "schema_name",
                "db_filter": "AND database_name = current_database()",
                "db_filter_aliased": "AND t.database_name = current_database()",
                "query": (
                    "SELECT COUNT(*) as cnt FROM svv_all_tables "
                    "WHERE schema_name = %s AND database_name = current_database()"
                ),
            },
            {
                "table_view": "information_schema.tables",
                "column_view": "information_schema.columns",
                "schema_col": "table_schema",
                "db_filter": "AND table_type IN ('BASE TABLE', 'VIEW')",
                "db_filter_aliased": "AND t.table_type IN ('BASE TABLE', 'VIEW')",
                "query": (
                    "SELECT COUNT(*) as cnt FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')"
                ),
            },
        ]

        for probe in probes:
            try:
                row = await asyncio.to_thread(self._execute_query_one, probe["query"], (self.schema_name,))
                if row and row["cnt"] > 0:
                    self._table_view = probe["table_view"]
                    self._column_view = probe["column_view"]
                    self._schema_col = probe["schema_col"]
                    self._db_filter = probe["db_filter"]
                    self._db_filter_aliased = probe["db_filter_aliased"]
                    logger.info(
                        "Schema discovery source selected",
                        view=probe["table_view"],
                        schema=self.schema_name,
                        tables=row["cnt"],
                    )
                    return
            except Exception as e:
                logger.debug("Probe failed", view=probe["table_view"], error=str(e))

        logger.warning(
            "All schema discovery probes returned 0 tables",
            schema=self.schema_name,
        )

    def _execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute a query and return results as list of dicts."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            return [dict(row) for row in results]
        finally:
            conn.close()

    def _execute_query_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Execute a query and return one result as dict."""
        results = self._execute_query(query, params)
        return results[0] if results else None

    async def get_tables(self, schema_name: Optional[str] = None, force_refresh: bool = False) -> List[TableInfo]:
        """Get all tables in the schema using bulk query + disk cache.

        The system view source (svv_tables, svv_all_tables, or information_schema)
        is auto-detected at initialization time.
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

    def _process_bulk_rows(self, rows: List[Dict]) -> List[TableInfo]:
        """Convert raw bulk query rows into TableInfo objects."""
        tables_dict: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            table_name = row["table_name"]

            if table_name not in tables_dict:
                pk_cols = row.get("pk_columns")
                if pk_cols:
                    if isinstance(pk_cols, str):
                        pk_cols = pk_cols.strip("{}").split(",") if pk_cols != "{}" else []
                    elif isinstance(pk_cols, list):
                        pk_cols = list(pk_cols)
                    else:
                        pk_cols = []
                else:
                    pk_cols = []

                tables_dict[table_name] = {
                    "name": table_name,
                    "schema": row["table_schema"],
                    "description": row.get("table_comment", ""),
                    "columns": [],
                    "primary_keys": pk_cols,
                    "foreign_keys": [],
                    "indexes": [],
                    "_seen_columns": set(),
                }

            col_name = row.get("column_name")
            if col_name and col_name not in tables_dict[table_name]["_seen_columns"]:
                tables_dict[table_name]["_seen_columns"].add(col_name)
                tables_dict[table_name]["columns"].append(
                    {
                        "name": col_name,
                        "type": row.get("data_type", ""),
                        "nullable": row.get("is_nullable") == "YES",
                        "default": row.get("column_default"),
                        "max_length": row.get("character_maximum_length"),
                        "precision": row.get("numeric_precision"),
                        "scale": row.get("numeric_scale"),
                        "description": "",
                    }
                )

        tables = []
        for table_data in tables_dict.values():
            del table_data["_seen_columns"]
            tables.append(
                TableInfo(
                    name=table_data["name"],
                    schema=table_data["schema"],
                    columns=table_data["columns"],
                    primary_keys=table_data["primary_keys"],
                    foreign_keys=table_data["foreign_keys"],
                    indexes=table_data["indexes"],
                    row_count=0,
                    size_bytes=0,
                    description=table_data["description"],
                    last_updated=datetime.now(),
                )
            )

        logger.info("Tables processed from bulk query", count=len(tables))
        return tables

    async def _get_tables_bulk(self, schema: str) -> List[TableInfo]:
        """Fetch all tables with columns in a single bulk query."""
        bulk_query = f"""
        SELECT
            t.table_name,
            t.{self._schema_col} as table_schema,
            '' as table_comment,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.ordinal_position,
            NULL as pk_columns
        FROM {self._table_view} t
        LEFT JOIN {self._column_view} c ON t.table_name = c.table_name
            AND t.{self._schema_col} = c.{self._schema_col}
        WHERE t.{self._schema_col} = %s {self._db_filter_aliased}
        ORDER BY t.table_name, c.ordinal_position
        """

        try:
            start_time = time.time()
            rows = await asyncio.to_thread(self._execute_query, bulk_query, (schema,))

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.info("Bulk query completed", rows=len(rows), elapsed_ms=elapsed_ms)
            return self._process_bulk_rows(rows)

        except Exception as e:
            if self._table_view != "information_schema.tables":
                logger.warning(
                    "Bulk query failed, retrying with information_schema",
                    error=str(e),
                    original_view=self._table_view,
                )
                return await self._get_tables_bulk_information_schema(schema)

            logger.error("Bulk query failed", error=str(e))
            raise SchemaException(f"Failed to get tables: {e!s}")

    async def _get_tables_bulk_information_schema(self, schema: str) -> List[TableInfo]:
        """Fallback bulk query using information_schema (no state mutation)."""
        fallback_query = """
        SELECT
            t.table_name,
            t.table_schema,
            '' as table_comment,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.ordinal_position,
            NULL as pk_columns
        FROM information_schema.tables t
        LEFT JOIN information_schema.columns c ON t.table_name = c.table_name
            AND t.table_schema = c.table_schema
        WHERE t.table_schema = %s AND t.table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY t.table_name, c.ordinal_position
        """
        try:
            start_time = time.time()
            rows = await asyncio.to_thread(self._execute_query, fallback_query, (schema,))
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.info(
                "information_schema fallback completed",
                rows=len(rows),
                elapsed_ms=elapsed_ms,
            )
            return self._process_bulk_rows(rows)
        except Exception as e:
            logger.error("information_schema fallback also failed", error=str(e))
            raise SchemaException(f"Failed to get tables: {e!s}")

    async def get_table_info(self, table_name: str, schema_name: Optional[str] = None) -> TableInfo:
        """Get detailed information about a specific table."""
        if not self._initialized:
            await self.initialize()

        schema = schema_name or self.schema_name

        query = f"""
        SELECT
            table_name,
            {self._schema_col} as table_schema,
            '' as table_comment
        FROM {self._table_view}
        WHERE table_name = %s AND {self._schema_col} = %s {self._db_filter}
        """

        try:
            row = await asyncio.to_thread(self._execute_query_one, query, (table_name, schema))

            if not row:
                raise SchemaException(f"Table {table_name} not found in schema {schema}")

            return await self._build_table_info(row, schema)

        except SchemaException:
            raise
        except Exception as e:
            logger.error("Failed to get table info", table=table_name, error=str(e))
            raise SchemaException(f"Failed to get table info: {e!s}")

    async def search_tables(self, pattern: str) -> List[TableInfo]:
        """Search tables by name pattern."""
        if not self._initialized:
            await self.initialize()

        query = f"""
        SELECT
            table_name,
            {self._schema_col} as table_schema,
            '' as table_comment
        FROM {self._table_view}
        WHERE {self._schema_col} = %s
        AND table_name ILIKE %s {self._db_filter}
        ORDER BY table_name
        """

        try:
            rows = await asyncio.to_thread(self._execute_query, query, (self.schema_name, f"%{pattern}%"))

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
        if not self._initialized:
            await self.initialize()

        # Redshift has limited FK support, return empty list
        return []

    async def get_schema_metadata(self) -> SchemaMetadata:
        """Get metadata about the entire schema."""
        if not self._initialized:
            await self.initialize()

        query = f"""
        SELECT
            current_database() as database_name,
            version() as database_version,
            COUNT(*) as total_tables
        FROM {self._table_view}
        WHERE {self._schema_col} = %s {self._db_filter}
        """

        try:
            row = await asyncio.to_thread(self._execute_query_one, query, (self.schema_name,))

            return SchemaMetadata(
                database_name=row["database_name"],
                database_type="redshift",
                version=row["database_version"],
                total_tables=row["total_tables"],
                total_size_bytes=0,
                last_analyzed=datetime.now(),
            )

        except Exception as e:
            logger.error("Failed to get schema metadata", error=str(e))
            raise SchemaException(f"Failed to get schema metadata: {e!s}")

    async def refresh_schema(self) -> None:
        """Refresh schema information from database."""
        if not self._initialized:
            await self.initialize()

        logger.info("Schema refresh requested (no-op for Redshift)")

    async def get_table_sample_data(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get sample data from a table."""
        if not self._initialized:
            await self.initialize()

        query = f'SELECT * FROM "{self.schema_name}"."{table_name}" LIMIT %s'

        try:
            return await asyncio.to_thread(self._execute_query, query, (limit,))

        except Exception as e:
            logger.error("Failed to get sample data", table=table_name, error=str(e))
            raise SchemaException(f"Failed to get sample data: {e!s}")

    async def _build_table_info(self, row: Dict, schema: str) -> TableInfo:
        """Build TableInfo from database row."""
        table_name = row["table_name"]

        # Get columns
        columns = await self._get_table_columns(table_name, schema)

        # Get primary keys
        primary_keys = await self._get_primary_keys(table_name, schema)

        return TableInfo(
            name=table_name,
            schema=schema,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=[],
            indexes=[],
            row_count=0,
            size_bytes=0,
            description=row.get("table_comment", ""),
            last_updated=datetime.now(),
        )

    async def _get_table_columns(self, table_name: str, schema: str) -> List[Dict[str, Any]]:
        """Get column information for a table."""
        query = f"""
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale
        FROM {self._column_view}
        WHERE table_name = %s AND {self._schema_col} = %s {self._db_filter}
        ORDER BY ordinal_position
        """

        rows = await asyncio.to_thread(self._execute_query, query, (table_name, schema))

        columns = []
        for row in rows:
            columns.append(
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["column_default"],
                    "max_length": row["character_maximum_length"],
                    "precision": row["numeric_precision"],
                    "scale": row["numeric_scale"],
                    "description": "",
                }
            )

        return columns

    async def _get_primary_keys(self, table_name: str, schema: str) -> List[str]:
        """Get primary key columns for a table."""
        query = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = %s AND tc.table_schema = %s
        AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """

        rows = await asyncio.to_thread(self._execute_query, query, (table_name, schema))

        return [row["column_name"] for row in rows]

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

        def _run_query() -> Dict[str, Any]:
            start_time = time.time()
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                # Set search_path so unqualified table names resolve to our schema
                cursor.execute(
                    psycopg2_sql.SQL("SET search_path TO {}, public").format(psycopg2_sql.Identifier(self.schema_name))
                )
                cursor.execute(f"SET statement_timeout TO {timeout_seconds * 1000}")
                cursor.close()

                # Execute the actual query
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(limited_sql)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                cursor.close()

                execution_time_ms = round((time.time() - start_time) * 1000, 2)

                return {
                    "results": [dict(row) for row in rows],
                    "columns": columns,
                    "row_count": len(rows),
                    "execution_time_ms": execution_time_ms,
                }
            finally:
                # Reset statement timeout before closing (match PostgreSQL behavior)
                try:
                    cursor = conn.cursor()
                    cursor.execute("SET statement_timeout TO 0")
                    cursor.close()
                except Exception:
                    pass  # Best effort reset
                conn.close()

        try:
            result = await asyncio.to_thread(_run_query)

            logger.info(
                "Query executed successfully",
                row_count=result["row_count"],
                execution_time_ms=result["execution_time_ms"],
            )

            return result

        except SecurityException:
            raise
        except Exception as e:
            logger.error("Query execution failed", error=str(e), sql=sql[:100])
            raise SchemaException(f"Query execution failed: {e!s}")
