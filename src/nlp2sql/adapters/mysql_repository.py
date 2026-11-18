"""MySQL and MariaDB repository for schema management.

Uses PyMySQL (sync, pure Python) inside asyncio.to_thread(), with a new connection per
call, like the PostgreSQL repository. PyMySQL is an optional dependency: install it with
``pip install 'nlp2sql[mysql]'``.

In MySQL a schema and a database are the same thing. The schema this repository reads is
the database of the URL; a ``schema_name`` other than the default ``"public"`` names
another database of the same server.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, unquote, urlsplit

from ..core.sql_safety import DEFAULT_QUERY_ROWS, apply_row_limit, is_safe_query
from ..exceptions import ConfigurationException, SchemaException, SecurityException
from ..ports.schema_repository import SchemaMetadata, SchemaRepositoryPort, TableInfo
from ..utils.logger import get_logger
from ._tables_cache import TablesCacheMixin

if TYPE_CHECKING:
    from pymysql.connections import Connection

logger = get_logger(__name__)

SCHEMA_CACHE_VERSION = "1.0"  # Change when the queries fill TableInfo differently

DEFAULT_PORT = 3306
# What connect(), the CLI and the MCP server pass when the caller names no schema
DEFAULT_SCHEMA_NAME = "public"
DIALECT = "mysql"

# Seconds the client waits beyond the server's own statement timeout before it drops the
# connection. MySQL's max_execution_time does not interrupt every statement.
CLIENT_TIMEOUT_MARGIN_SECONDS = 5

# Above this many names, the keys and columns of the whole schema are read and filtered
# here instead of sending the names in an IN (...) list
MAX_NAMES_IN_QUERY = 100


def _flag(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ValueError(value)


# URL query parameters handed to PyMySQL, by its own names. Anything else is refused:
# local_infile lets the server ask for files of this machine, init_command runs SQL on
# connect, read_default_file reads a local file, and client_flag can allow several
# statements per query.
URL_PARAMETERS: dict[str, Callable[[str], Any]] = {
    "charset": str,
    "connect_timeout": int,
    "read_timeout": int,
    "write_timeout": int,
    "ssl_ca": str,
    "ssl_cert": str,
    "ssl_key": str,
    "ssl_key_password": str,
    "ssl_disabled": _flag,
    "ssl_verify_cert": _flag,
    "ssl_verify_identity": _flag,
    "unix_socket": str,
}


def _load_driver() -> ModuleType:
    try:
        import pymysql  # optional dependency, imported when a repository is built
    except ImportError as error:
        raise ImportError("MySQL and MariaDB need the PyMySQL driver: pip install 'nlp2sql[mysql]'") from error
    return pymysql


def parse_mysql_url(url: str) -> dict[str, Any]:
    """PyMySQL connection arguments for a ``mysql://``, ``mysql+pymysql://`` or ``mariadb://`` URL.

    Raises ConfigurationException for a URL that cannot be read or that carries a query
    parameter outside URL_PARAMETERS. The message never repeats the URL or a value.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise ConfigurationException("The MySQL URL cannot be read: check the host and the port") from error

    params: dict[str, Any] = {
        "host": parts.hostname or "localhost",
        "port": port or DEFAULT_PORT,
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "database": unquote(parts.path.lstrip("/")),
        "charset": "utf8mb4",
    }
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        convert = URL_PARAMETERS.get(name)
        if convert is None:
            raise ConfigurationException(
                f"MySQL URL parameter '{name}' is not supported. Supported: {', '.join(sorted(URL_PARAMETERS))}"
            )
        try:
            params[name] = convert(value)
        except ValueError as error:
            raise ConfigurationException(f"MySQL URL parameter '{name}' has a value that cannot be read") from error
    return params


def _quote_name(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


class MySQLRepository(TablesCacheMixin, SchemaRepositoryPort):
    """MySQL 8 and MariaDB implementation of the schema repository.

    Every connection is read-only for its whole session, and it can run one statement per
    query: PyMySQL does not ask the server for multiple statements.
    """

    tables_cache_version = SCHEMA_CACHE_VERSION

    def __init__(self, connection_string: str, schema_name: str = DEFAULT_SCHEMA_NAME) -> None:
        self._driver = _load_driver()
        self.connection_string = connection_string
        self.database_url = connection_string
        self._connection_params = parse_mysql_url(connection_string)
        url_database = self._connection_params.pop("database")
        self.schema_name = url_database if schema_name in (None, "", DEFAULT_SCHEMA_NAME) else schema_name
        if not self.schema_name:
            raise ConfigurationException("The MySQL URL names no database: mysql://user:password@host:3306/database")
        self._initialized = False
        self._cache_dir: Path | None = None
        self._server_version = ""
        self._is_mariadb = False

    # ── Connections ────────────────────────────────────────────────────

    def _get_connection(self, read_timeout: int | None = None) -> Connection:
        """A new connection to the schema's database whose transactions are all read-only."""
        params = {**self._connection_params, "database": self.schema_name}
        if read_timeout is not None:
            params["read_timeout"] = read_timeout
        return self._driver.connect(
            **params,
            cursorclass=self._driver.cursors.DictCursor,
            # nlp2sql only reads: the server refuses a write the SQL safety check misses.
            # It applies to every transaction of the session, not only to the first.
            init_command="SET SESSION TRANSACTION READ ONLY",
            autocommit=False,
            local_infile=False,
            client_flag=0,
        )

    def _execute_query(self, query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        """Run one metadata query on its own connection."""
        conn = self._get_connection()
        try:
            return self._fetch(conn, query, params)
        finally:
            conn.close()

    @staticmethod
    def _fetch(conn: Connection, query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())

    async def initialize(self) -> None:
        """Check the connection and learn whether the server is MySQL or MariaDB."""
        if self._initialized:
            return

        try:
            rows = await asyncio.to_thread(self._execute_query, "SELECT VERSION() AS version")
        except Exception as e:
            logger.error("Failed to initialize MySQL repository", error=str(e))
            hint = " (pip install 'nlp2sql[mysql]' installs it)" if "cryptography" in str(e) else ""
            raise SchemaException(f"Database initialization failed: {e!s}{hint}") from e

        self._server_version = str(rows[0]["version"])
        self._is_mariadb = "mariadb" in self._server_version.lower()
        self._initialized = True
        logger.info("MySQL repository initialized", server="mariadb" if self._is_mariadb else "mysql")

    # ── Schema discovery ───────────────────────────────────────────────

    async def get_tables(self, schema_name: str | None = None, force_refresh: bool = False) -> list[TableInfo]:
        """All base tables of the schema, from the disk cache when it is current."""
        if not self._initialized:
            await self.initialize()

        schema = schema_name or self.schema_name
        if not force_refresh:
            cached_tables = self._load_tables_from_cache(schema)
            if cached_tables is not None:
                return cached_tables

        tables = await self._read_tables(schema, "get tables")
        self._save_tables_to_cache(tables, schema)
        return tables

    async def get_table_info(self, table_name: str, schema_name: str | None = None) -> TableInfo:
        """Columns, keys and indexes of one table."""
        if not self._initialized:
            await self.initialize()

        schema = schema_name or self.schema_name
        tables = await self._read_tables(schema, "get table info", names=[table_name])
        if not tables:
            raise SchemaException(f"Table {table_name} not found in schema {schema}")
        return tables[0]

    async def search_tables(self, pattern: str) -> list[TableInfo]:
        """Tables whose name or comment contains ``pattern``, in any case."""
        if not self._initialized:
            await self.initialize()
        return await self._read_tables(self.schema_name, "search tables", pattern=pattern)

    async def get_related_tables(self, table_name: str) -> list[TableInfo]:
        """Tables that reference ``table_name`` or that it references, in the same schema."""
        if not self._initialized:
            await self.initialize()

        query = """
        SELECT TABLE_NAME AS table_name, REFERENCED_TABLE_NAME AS ref_table
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_SCHEMA = %s
        AND (TABLE_NAME = %s OR REFERENCED_TABLE_NAME = %s)
        """
        schema = self.schema_name
        try:
            rows = await asyncio.to_thread(self._execute_query, query, (schema, schema, table_name, table_name))
        except Exception as e:
            logger.error("Failed to get related tables", table=table_name, error=str(e))
            raise SchemaException(f"Failed to get related tables: {e!s}") from e

        related = sorted({name for row in rows for name in (row["table_name"], row["ref_table"])} - {table_name})
        if not related:
            return []
        return await self._read_tables(schema, "get related tables", names=related)

    async def get_schema_metadata(self) -> SchemaMetadata:
        """Name, server version, table count and size of the schema."""
        if not self._initialized:
            await self.initialize()

        query = """
        SELECT COUNT(*) AS total_tables, SUM(DATA_LENGTH + INDEX_LENGTH) AS total_size
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        """
        try:
            rows = await asyncio.to_thread(self._execute_query, query, (self.schema_name,))
        except Exception as e:
            logger.error("Failed to get schema metadata", error=str(e))
            raise SchemaException(f"Failed to get schema metadata: {e!s}") from e

        return SchemaMetadata(
            database_name=self.schema_name,
            database_type=DIALECT,
            version=self._server_version,
            total_tables=rows[0]["total_tables"],
            total_size_bytes=int(rows[0]["total_size"] or 0),
            last_analyzed=datetime.now(),
            custom_metadata={"server": "mariadb" if self._is_mariadb else "mysql"},
        )

    async def get_table_sample_data(self, table_name: str, limit: int = 5) -> list[dict[str, Any]]:
        """The first ``limit`` rows of a table."""
        if not self._initialized:
            await self.initialize()

        # Names are quoted here; the row count is sent as a parameter
        query = f"SELECT * FROM {_quote_name(self.schema_name)}.{_quote_name(table_name)} LIMIT %s"  # noqa: S608
        try:
            return await asyncio.to_thread(self._execute_query, query, (int(limit),))
        except Exception as e:
            logger.error("Failed to get sample data", table=table_name, error=str(e))
            raise SchemaException(f"Failed to get sample data: {e!s}") from e

    # ── Reading information_schema ─────────────────────────────────────

    async def _read_tables(
        self, schema: str, action: str, names: list[str] | None = None, pattern: str | None = None
    ) -> list[TableInfo]:
        try:
            start_time = time.time()
            tables = await asyncio.to_thread(self._read_tables_sync, schema, names, pattern)
        except Exception as e:
            logger.error(f"Failed to {action}", schema=schema, error=str(e))
            raise SchemaException(f"Failed to {action}: {e!s}") from e

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logger.info("Tables read from information_schema", count=len(tables), elapsed_ms=elapsed_ms)
        return tables

    def _read_tables_sync(self, schema: str, names: list[str] | None, pattern: str | None) -> list[TableInfo]:
        """Tables with their columns, keys and indexes: four queries on one connection.

        The number of queries does not grow with the number of tables.
        """
        conn = self._get_connection()
        try:
            if not self._is_mariadb:
                # MySQL 8 answers TABLE_ROWS and the sizes from statistics it caches for a
                # day by default; 0 reads them from the storage engine
                self._fetch(conn, "SET SESSION information_schema_stats_expiry = 0")

            table_rows = self._fetch(conn, *self._tables_query(schema, names, pattern))
            if not table_rows:
                return []

            found = [row["table_name"] for row in table_rows]
            narrow = found if (names is not None or pattern is not None) else None
            if narrow is not None and len(narrow) > MAX_NAMES_IN_QUERY:
                narrow = None
            column_rows = self._fetch(conn, *self._columns_query(schema, narrow))
            index_rows = self._fetch(conn, *self._indexes_query(schema, narrow))
            foreign_key_rows = self._fetch(conn, *self._foreign_keys_query(schema, narrow))
        finally:
            conn.close()

        return self._assemble(schema, table_rows, column_rows, index_rows, foreign_key_rows)

    @staticmethod
    def _names_filter(names: list[str] | None) -> tuple[str, list[str]]:
        if names is None:
            return "", []
        return f" AND TABLE_NAME IN ({', '.join(['%s'] * len(names))})", list(names)

    def _tables_query(self, schema: str, names: list[str] | None, pattern: str | None) -> tuple[str, list[Any]]:
        # TABLE_ROWS is the storage engine's estimate for InnoDB, like PostgreSQL's reltuples.
        # Every column has an alias: MySQL returns these names in upper case, MariaDB in lower.
        query = """
        SELECT TABLE_NAME AS table_name, TABLE_ROWS AS row_count,
               DATA_LENGTH + INDEX_LENGTH AS size_bytes, TABLE_COMMENT AS table_comment
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        """
        params: list[Any] = [schema]
        name_filter, name_params = self._names_filter(names)
        query += name_filter
        params += name_params
        if pattern is not None:
            # LOWER on both sides: MySQL compares these names with a case-sensitive collation
            query += " AND (LOWER(TABLE_NAME) LIKE LOWER(%s) OR LOWER(TABLE_COMMENT) LIKE LOWER(%s))"
            params += [f"%{pattern}%", f"%{pattern}%"]
        return query + " ORDER BY TABLE_NAME", params

    def _columns_query(self, schema: str, names: list[str] | None) -> tuple[str, list[Any]]:
        name_filter, name_params = self._names_filter(names)
        query = f"""
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name, COLUMN_TYPE AS data_type,
               IS_NULLABLE AS is_nullable, COLUMN_DEFAULT AS column_default,
               CHARACTER_MAXIMUM_LENGTH AS max_length, NUMERIC_PRECISION AS numeric_precision,
               NUMERIC_SCALE AS numeric_scale, COLUMN_COMMENT AS column_comment
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s{name_filter}
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """  # noqa: S608 - only %s placeholders are interpolated
        return query, [schema, *name_params]

    def _indexes_query(self, schema: str, names: list[str] | None) -> tuple[str, list[Any]]:
        name_filter, name_params = self._names_filter(names)
        query = f"""
        SELECT TABLE_NAME AS table_name, INDEX_NAME AS index_name, COLUMN_NAME AS column_name,
               NON_UNIQUE AS non_unique
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = %s{name_filter}
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
        """  # noqa: S608 - only %s placeholders are interpolated
        return query, [schema, *name_params]

    def _foreign_keys_query(self, schema: str, names: list[str] | None) -> tuple[str, list[Any]]:
        name_filter, name_params = self._names_filter(names)
        query = f"""
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
               REFERENCED_TABLE_NAME AS ref_table, REFERENCED_COLUMN_NAME AS ref_column,
               CONSTRAINT_NAME AS constraint_name
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL{name_filter}
        ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION
        """  # noqa: S608 - only %s placeholders are interpolated
        return query, [schema, *name_params]

    def _column_default(self, value: str | None) -> str | None:
        # MariaDB writes the default as an expression: NULL for none, 'text' for a string
        if self._is_mariadb and value == "NULL":
            return None
        return value

    def _assemble(
        self,
        schema: str,
        table_rows: list[dict[str, Any]],
        column_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        foreign_key_rows: list[dict[str, Any]],
    ) -> list[TableInfo]:
        now = datetime.now()
        tables = {
            row["table_name"]: TableInfo(
                name=row["table_name"],
                schema=schema,
                columns=[],
                primary_keys=[],
                foreign_keys=[],
                indexes=[],
                row_count=int(row["row_count"] or 0),
                size_bytes=int(row["size_bytes"] or 0),
                description=row["table_comment"] or None,
                last_updated=now,
            )
            for row in table_rows
        }

        for row in column_rows:
            table = tables.get(row["table_name"])
            if table is None:
                continue
            table.columns.append(
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": self._column_default(row["column_default"]),
                    "max_length": row["max_length"],
                    "precision": row["numeric_precision"],
                    "scale": row["numeric_scale"],
                    "description": row["column_comment"] or None,
                }
            )

        indexes: dict[tuple[str, str], dict[str, Any]] = {}
        for row in index_rows:
            table = tables.get(row["table_name"])
            if table is None:
                continue
            key = (row["table_name"], row["index_name"])
            if key not in indexes:
                indexes[key] = {
                    "name": row["index_name"],
                    "columns": [],
                    "unique": not row["non_unique"],
                    "primary": row["index_name"] == "PRIMARY",
                }
                table.indexes.append(indexes[key])
            indexes[key]["columns"].append(row["column_name"])
            if row["index_name"] == "PRIMARY":
                table.primary_keys.append(row["column_name"])

        for row in foreign_key_rows:
            table = tables.get(row["table_name"])
            if table is None:
                continue
            table.foreign_keys.append(
                {
                    "column": row["column_name"],
                    "ref_table": row["ref_table"],
                    "ref_column": row["ref_column"],
                    "constraint_name": row["constraint_name"],
                }
            )

        return list(tables.values())

    # ── Query execution ────────────────────────────────────────────────

    async def execute_query(
        self,
        sql: str,
        limit: int = DEFAULT_QUERY_ROWS,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
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

        is_safe, error_message = is_safe_query(sql, dialect=DIALECT)
        if not is_safe:
            logger.warning("Unsafe query rejected", sql=sql[:100], reason=error_message)
            raise SecurityException(f"Query rejected: {error_message}")

        limited_sql = apply_row_limit(sql, limit, dialect=DIALECT)
        timeout_seconds = int(timeout_seconds)

        def _run_query() -> dict[str, Any]:
            start_time = time.time()
            conn = self._get_connection(read_timeout=timeout_seconds + CLIENT_TIMEOUT_MARGIN_SECONDS)
            try:
                with conn.cursor() as cursor:
                    if self._is_mariadb:
                        cursor.execute(f"SET SESSION max_statement_time = {timeout_seconds}")
                    else:
                        cursor.execute(f"SET SESSION max_execution_time = {timeout_seconds * 1000}")
                    # No arguments: a % in the query is SQL, not a placeholder
                    cursor.execute(limited_sql)
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []

                return {
                    "results": [dict(row) for row in rows],
                    "columns": columns,
                    "row_count": len(rows),
                    "execution_time_ms": round((time.time() - start_time) * 1000, 2),
                }
            finally:
                # Closing rolls the transaction back and ends the session with its settings
                conn.close()

        try:
            result = await asyncio.to_thread(_run_query)
        except Exception as e:
            logger.error("Query execution failed", error=str(e), sql=sql[:100])
            raise SchemaException(f"Query execution failed: {e!s}") from e

        logger.info(
            "Query executed successfully",
            row_count=result["row_count"],
            execution_time_ms=result["execution_time_ms"],
        )
        return result
