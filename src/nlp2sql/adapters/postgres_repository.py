"""PostgreSQL repository for schema management."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..exceptions import SchemaException
from ..ports.schema_repository import SchemaMetadata, SchemaRepositoryPort, TableInfo

logger = structlog.get_logger()


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

    async def get_tables(self, schema_name: Optional[str] = None) -> List[TableInfo]:
        """Get all tables in the schema."""
        if not self._initialized:
            await self.initialize()

        schema = schema_name or self.schema_name

        query = """
        SELECT 
            t.table_name,
            t.table_schema,
            obj_description(c.oid) as table_comment,
            pg_size_pretty(pg_total_relation_size(c.oid)) as table_size,
            pg_total_relation_size(c.oid) as size_bytes,
            n_tup_ins + n_tup_upd + n_tup_del as row_count
        FROM information_schema.tables t
        LEFT JOIN pg_class c ON c.relname = t.table_name
        LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
        WHERE t.table_schema = :schema
        AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
        """

        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(query), {"schema": schema})
                rows = result.fetchall()

                tables = []
                for row in rows:
                    table_info = await self._build_table_info(row, schema)
                    tables.append(table_info)

                return tables

        except Exception as e:
            logger.error("Failed to get tables", error=str(e))
            raise SchemaException(f"Failed to get tables: {e!s}")

    async def get_table_info(self, table_name: str, schema_name: Optional[str] = None) -> TableInfo:
        """Get detailed information about a specific table."""
        schema = schema_name or self.schema_name

        try:
            # Get basic table info
            table_query = """
            SELECT 
                t.table_name,
                t.table_schema,
                obj_description(c.oid) as table_comment,
                pg_size_pretty(pg_total_relation_size(c.oid)) as table_size,
                pg_total_relation_size(c.oid) as size_bytes,
                COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) as row_count
            FROM information_schema.tables t
            LEFT JOIN pg_class c ON c.relname = t.table_name
            LEFT JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.table_schema
            LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name AND s.schemaname = t.table_schema
            WHERE t.table_name = :table_name AND t.table_schema = :schema
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
            t.table_name,
            t.table_schema,
            obj_description(c.oid) as table_comment,
            pg_size_pretty(pg_total_relation_size(c.oid)) as table_size,
            pg_total_relation_size(c.oid) as size_bytes,
            COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) as row_count
        FROM information_schema.tables t
        LEFT JOIN pg_class c ON c.relname = t.table_name
        LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
        WHERE t.table_schema = :schema
        AND t.table_type = 'BASE TABLE'
        AND (t.table_name ILIKE :pattern OR obj_description(c.oid) ILIKE :pattern)
        ORDER BY t.table_name
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
            -- Tables that reference this table
            SELECT DISTINCT
                kcu.table_name as related_table,
                kcu.table_schema as related_schema
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.referential_constraints rc ON kcu.constraint_name = rc.constraint_name
            JOIN information_schema.key_column_usage kcu2 ON rc.unique_constraint_name = kcu2.constraint_name
            WHERE kcu2.table_name = :table_name AND kcu2.table_schema = :schema
            
            UNION
            
            -- Tables that this table references
            SELECT DISTINCT
                kcu2.table_name as related_table,
                kcu2.table_schema as related_schema
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.referential_constraints rc ON kcu.constraint_name = rc.constraint_name
            JOIN information_schema.key_column_usage kcu2 ON rc.unique_constraint_name = kcu2.constraint_name
            WHERE kcu.table_name = :table_name AND kcu.table_schema = :schema
        )
        SELECT 
            t.table_name,
            t.table_schema,
            obj_description(c.oid) as table_comment,
            pg_size_pretty(pg_total_relation_size(c.oid)) as table_size,
            pg_total_relation_size(c.oid) as size_bytes,
            COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) as row_count
        FROM related_tables rt
        JOIN information_schema.tables t ON rt.related_table = t.table_name AND rt.related_schema = t.table_schema
        LEFT JOIN pg_class c ON c.relname = t.table_name
        LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
        WHERE t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
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
            current_database() as database_name,
            version() as database_version,
            COUNT(*) as total_tables,
            SUM(pg_total_relation_size(c.oid)) as total_size
        FROM information_schema.tables t
        LEFT JOIN pg_class c ON c.relname = t.table_name
        LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE t.table_schema = :schema
        AND t.table_type = 'BASE TABLE'
        """

        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(query), (self.schema_name,))
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
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            col_description(pgc.oid, ordinal_position) as column_comment
        FROM information_schema.columns c
        LEFT JOIN pg_class pgc ON pgc.relname = c.table_name
        LEFT JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace
        WHERE c.table_name = :table_name AND c.table_schema = :schema
        ORDER BY ordinal_position
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
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = :table_name AND tc.table_schema = :schema
        AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """

        async with self.async_engine.begin() as conn:
            result = await conn.execute(text(query), {"table_name": table_name, "schema": schema})
            rows = result.fetchall()

            return [row[0] for row in rows]

    async def _get_foreign_keys(self, table_name: str, schema: str) -> List[Dict[str, Any]]:
        """Get foreign key constraints for a table."""
        query = """
        SELECT 
            kcu.column_name,
            kcu2.table_name as referenced_table,
            kcu2.column_name as referenced_column,
            rc.constraint_name
        FROM information_schema.key_column_usage kcu
        JOIN information_schema.referential_constraints rc ON kcu.constraint_name = rc.constraint_name
        JOIN information_schema.key_column_usage kcu2 ON rc.unique_constraint_name = kcu2.constraint_name
        WHERE kcu.table_name = :table_name AND kcu.table_schema = :schema
        ORDER BY kcu.ordinal_position
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
