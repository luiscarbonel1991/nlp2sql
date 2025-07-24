"""Schema Repository Port - Interface for database schema management."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TableInfo:
    """Information about a database table."""

    name: str
    schema: str
    columns: List[Dict[str, Any]]
    primary_keys: List[str]
    foreign_keys: List[Dict[str, Any]]
    indexes: List[Dict[str, Any]]
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    description: Optional[str] = None
    last_updated: Optional[datetime] = None


@dataclass
class SchemaMetadata:
    """Metadata about the database schema."""

    database_name: str
    database_type: str  # postgres, mysql, etc.
    version: str
    total_tables: int
    total_size_bytes: Optional[int] = None
    last_analyzed: Optional[datetime] = None
    custom_metadata: Optional[Dict[str, Any]] = None


class SchemaRepositoryPort(ABC):
    """Abstract interface for schema repository."""

    @abstractmethod
    async def get_tables(self, schema_name: Optional[str] = None) -> List[TableInfo]:
        """Get all tables in the database or specific schema."""
        pass

    @abstractmethod
    async def get_table_info(self, table_name: str, schema_name: Optional[str] = None) -> TableInfo:
        """Get detailed information about a specific table."""
        pass

    @abstractmethod
    async def search_tables(self, pattern: str) -> List[TableInfo]:
        """Search tables by name pattern."""
        pass

    @abstractmethod
    async def get_related_tables(self, table_name: str) -> List[TableInfo]:
        """Get tables related through foreign keys."""
        pass

    @abstractmethod
    async def get_schema_metadata(self) -> SchemaMetadata:
        """Get metadata about the entire schema."""
        pass

    @abstractmethod
    async def refresh_schema(self) -> None:
        """Refresh schema information from database."""
        pass

    @abstractmethod
    async def get_table_sample_data(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get sample data from a table."""
        pass
