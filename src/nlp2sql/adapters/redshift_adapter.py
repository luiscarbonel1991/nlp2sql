"""Amazon Redshift repository for schema management."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
import structlog

from ..exceptions import SchemaException
from ..ports.schema_repository import (
    SchemaMetadata,
    SchemaRepositoryPort,
    TableInfo,
)

logger = structlog.get_logger()


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

    async def get_tables(self, schema_name: Optional[str] = None) -> List[TableInfo]:
        """Get all tables in the schema.

        Uses SVV_TABLES (Redshift system view) instead of information_schema.tables
        for better permission handling. See AWS docs:
        https://docs.aws.amazon.com/redshift/latest/dg/cm_chap_system-tables.html
        """
        if not self._initialized:
            await self.initialize()

        schema = schema_name or self.schema_name

        # Use SVV_TABLES for better Redshift compatibility and permissions
        query = """
        SELECT
            table_name,
            table_schema,
            '' as table_comment
        FROM svv_tables
        WHERE table_schema = %s
        ORDER BY table_name
        """

        try:
            rows = await asyncio.to_thread(self._execute_query, query, (schema,))

            tables = []
            for row in rows:
                table_info = await self._build_table_info(row, schema)
                tables.append(table_info)

            return tables

        except Exception as e:
            logger.error("Failed to get tables", error=str(e))
            raise SchemaException(f"Failed to get tables: {e!s}")

    async def get_table_info(
        self, table_name: str, schema_name: Optional[str] = None
    ) -> TableInfo:
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
            row = await asyncio.to_thread(
                self._execute_query_one, query, (table_name, schema)
            )

            if not row:
                raise SchemaException(
                    f"Table {table_name} not found in schema {schema}"
                )

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
            rows = await asyncio.to_thread(
                self._execute_query, query, (self.schema_name, f"%{pattern}%")
            )

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
            row = await asyncio.to_thread(
                self._execute_query_one, query, (self.schema_name,)
            )

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

    async def get_table_sample_data(
        self, table_name: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
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

    async def _get_table_columns(
        self, table_name: str, schema: str
    ) -> List[Dict[str, Any]]:
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

        rows = await asyncio.to_thread(
            self._execute_query, query, (table_name, schema)
        )

        columns = []
        for row in rows:
            columns.append({
                "name": row["column_name"],
                "type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
                "max_length": row["character_maximum_length"],
                "precision": row["numeric_precision"],
                "scale": row["numeric_scale"],
                "description": "",
            })

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

        rows = await asyncio.to_thread(
            self._execute_query, query, (table_name, schema)
        )

        return [row["column_name"] for row in rows]
