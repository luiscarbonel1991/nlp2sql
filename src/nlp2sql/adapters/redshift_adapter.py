"""Amazon Redshift repository for schema management."""

import asyncio
import hashlib
import os
import pickle
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import structlog
from psycopg2.extras import RealDictCursor

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

# SQL patterns that are not allowed for security
DANGEROUS_SQL_PATTERNS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bCALL\b",
    r"\bSET\b",
    r"\bCOPY\b",
    r"\bUNLOAD\b",  # Redshift-specific
    r"\bVACUUM\b",  # Redshift-specific
]

MAX_QUERY_ROWS = 1000
DEFAULT_QUERY_ROWS = 100


def is_safe_query(sql: str) -> Tuple[bool, str]:
    """Check if a SQL query is safe to execute (read-only)."""
    sql_upper = sql.upper().strip()

    allowed_prefixes = ("SELECT", "WITH", "EXPLAIN")
    if not any(sql_upper.startswith(prefix) for prefix in allowed_prefixes):
        return False, "Only SELECT, WITH, or EXPLAIN queries are allowed"

    for pattern in DANGEROUS_SQL_PATTERNS:
        if re.search(pattern, sql_upper, re.IGNORECASE):
            return False, "Query contains prohibited operation"

    # Handle SQL escaped quotes: 'O''Reilly' -> '' (single quotes escaped by doubling)
    sql_no_strings = re.sub(r"'(?:[^']|'')*'", "", sql)
    sql_no_strings = re.sub(r'"(?:[^"]|"")*"', "", sql_no_strings)
    if ";" in sql_no_strings.rstrip(";"):
        return False, "Multiple SQL statements are not allowed"

    return True, ""


def apply_row_limit(sql: str, limit: int) -> str:
    """Ensure query has a row limit applied."""
    limit = min(limit, MAX_QUERY_ROWS)

    # Remove string literals to avoid false positives
    # e.g., WHERE message LIKE '%LIMIT%' should not bypass the limit
    # Handle SQL escaped quotes: 'O''Reilly' -> '' (single quotes escaped by doubling)
    sql_no_strings = re.sub(r"'(?:[^']|'')*'", "''", sql)
    sql_no_strings = re.sub(r'"(?:[^"]|"")*"', '""', sql_no_strings)

    # Check for LIMIT keyword outside of strings (word boundary match)
    if re.search(r"\bLIMIT\b", sql_no_strings, re.IGNORECASE):
        return sql

    return f"{sql.rstrip(';')} LIMIT {limit}"


class RedshiftRepository(SchemaRepositoryPort):
    """Amazon Redshift implementation of schema repository.

    Uses psycopg2 directly for maximum compatibility with Redshift.
    SQLAlchemy dialects have issues with Redshift's custom configuration.
    """

    def __init__(self, connection_string: str, schema_name: str = "public"):
        self.connection_string = connection_string
        self.database_url = connection_string
        self.schema_name = schema_name
        self._connection_params = self._parse_connection_string(connection_string)
        self._initialized = False
        self._cache_dir: Optional[Path] = None

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
        """Initialize database connections."""
        if self._initialized:
            return

        try:
            # Test connection
            def test_connection():
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()

            await asyncio.to_thread(test_connection)

            self._initialized = True
            logger.info("Redshift repository initialized")

        except Exception as e:
            logger.error("Failed to initialize Redshift repository", error=str(e))
            raise SchemaException(f"Database initialization failed: {e!s}")

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
        """Get all tables in the schema using hybrid bulk query + disk cache.

        Uses SVV_TABLES and SVV_COLUMNS (Redshift system views) for better
        permission handling. See AWS docs:
        https://docs.aws.amazon.com/redshift/latest/dg/cm_chap_system-tables.html

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

        Uses Redshift SVV views for better permission handling.
        """
        # Note: Redshift's information_schema views have limited support for
        # constraints, so we skip primary key detection in the bulk query.
        # Primary keys are not essential for SQL generation.
        bulk_query = """
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
        FROM svv_tables t
        LEFT JOIN svv_columns c ON t.table_name = c.table_name
            AND t.table_schema = c.table_schema
        WHERE t.table_schema = %s
        ORDER BY t.table_name, c.ordinal_position
        """

        try:
            start_time = time.time()
            rows = await asyncio.to_thread(
                self._execute_query, bulk_query, (schema,)
            )

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.info("Bulk query completed", rows=len(rows), elapsed_ms=elapsed_ms)

            # Process rows and group by table
            tables_dict: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                table_name = row["table_name"]

                if table_name not in tables_dict:
                    # Parse pk_columns - Redshift may return string representation
                    pk_cols = row.get("pk_columns")
                    if pk_cols:
                        if isinstance(pk_cols, str):
                            # Handle string like '{col1,col2}'
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

                # Add column (avoiding duplicates)
                col_name = row.get("column_name")
                if col_name and col_name not in tables_dict[table_name]["_seen_columns"]:
                    tables_dict[table_name]["_seen_columns"].add(col_name)
                    tables_dict[table_name]["columns"].append({
                        "name": col_name,
                        "type": row.get("data_type", ""),
                        "nullable": row.get("is_nullable") == "YES",
                        "default": row.get("column_default"),
                        "max_length": row.get("character_maximum_length"),
                        "precision": row.get("numeric_precision"),
                        "scale": row.get("numeric_scale"),
                        "description": "",
                    })

            # Convert to TableInfo objects
            tables = []
            for table_data in tables_dict.values():
                del table_data["_seen_columns"]

                tables.append(TableInfo(
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
                ))

            logger.info("Tables processed from bulk query", count=len(tables))
            return tables

        except Exception as e:
            logger.error("Bulk query failed", error=str(e))
            raise SchemaException(f"Failed to get tables: {e!s}")

    async def get_table_info(self, table_name: str, schema_name: Optional[str] = None) -> TableInfo:
        """Get detailed information about a specific table."""
        if not self._initialized:
            await self.initialize()

        schema = schema_name or self.schema_name

        # Use SVV_TABLES for better Redshift compatibility
        query = """
        SELECT
            table_name,
            table_schema,
            '' as table_comment
        FROM svv_tables
        WHERE table_name = %s AND table_schema = %s
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

        # Use SVV_TABLES for better Redshift compatibility
        query = """
        SELECT
            table_name,
            table_schema,
            '' as table_comment
        FROM svv_tables
        WHERE table_schema = %s
        AND table_name ILIKE %s
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

        # Use SVV_TABLES for better Redshift compatibility
        query = """
        SELECT
            current_database() as database_name,
            version() as database_version,
            COUNT(*) as total_tables
        FROM svv_tables
        WHERE table_schema = %s
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
        """Get column information for a table.

        Uses SVV_COLUMNS (Redshift system view) for better permission handling.
        See: https://docs.aws.amazon.com/redshift/latest/dg/r_SVV_COLUMNS.html
        """
        query = """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale
        FROM svv_columns
        WHERE table_name = %s AND table_schema = %s
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
                # Set statement timeout (in milliseconds for Redshift)
                cursor = conn.cursor()
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
