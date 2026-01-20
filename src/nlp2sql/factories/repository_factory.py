"""Repository Factory for creating database-specific repository implementations.

This module provides a centralized factory for creating schema repository instances
based on database type. It follows the Registry pattern to allow runtime registration
of new repository types.
"""

from typing import Dict, Optional, Type

from ..core.entities import DatabaseType
from ..ports.schema_repository import SchemaRepositoryPort


class RepositoryFactory:
    """Factory for creating database repository instances.

    Uses the Registry pattern to map database types to repository implementations.
    Supports runtime registration of new repository types.

    Example:
        # Create repository using auto-detected type
        repo = RepositoryFactory.create("postgresql://user:pass@localhost/db")

        # Create and initialize in one step
        repo = await RepositoryFactory.create_and_initialize(
            "postgresql://user:pass@localhost/db",
            schema_name="public"
        )

        # Register custom repository type
        RepositoryFactory.register(DatabaseType.MYSQL, MySQLRepository)
    """

    # Class-level registry mapping DatabaseType to repository classes
    _registry: Dict[DatabaseType, Type[SchemaRepositoryPort]] = {}
    _defaults_registered: bool = False

    @classmethod
    def _register_default_repositories(cls) -> None:
        """Register default repository implementations.

        Uses lazy imports to avoid circular dependencies and only load
        adapters when actually needed.
        """
        if cls._defaults_registered:
            return

        # Lazy import to avoid circular dependencies
        from ..adapters.postgres_repository import PostgreSQLRepository
        from ..adapters.redshift_adapter import RedshiftRepository

        cls._registry[DatabaseType.POSTGRES] = PostgreSQLRepository
        cls._registry[DatabaseType.REDSHIFT] = RedshiftRepository

        cls._defaults_registered = True

    @classmethod
    def register(
        cls,
        database_type: DatabaseType,
        repository_class: Type[SchemaRepositoryPort],
    ) -> None:
        """Register a repository class for a database type.

        Args:
            database_type: The database type to register
            repository_class: The repository class implementing SchemaRepositoryPort

        Example:
            RepositoryFactory.register(DatabaseType.MYSQL, MySQLRepository)
        """
        cls._registry[database_type] = repository_class

    @classmethod
    def unregister(cls, database_type: DatabaseType) -> bool:
        """Unregister a repository class for a database type.

        Useful for testing or replacing default implementations.

        Args:
            database_type: The database type to unregister

        Returns:
            True if the type was registered and removed, False otherwise
        """
        if database_type in cls._registry:
            del cls._registry[database_type]
            return True
        return False

    @classmethod
    def get_registered_types(cls) -> list[DatabaseType]:
        """Get all registered database types.

        Returns:
            List of DatabaseType values that have registered repository implementations
        """
        cls._register_default_repositories()
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, database_type: DatabaseType) -> bool:
        """Check if a database type has a registered repository.

        Args:
            database_type: The database type to check

        Returns:
            True if a repository is registered for this type
        """
        cls._register_default_repositories()
        return database_type in cls._registry

    @classmethod
    def detect_database_type(cls, database_url: str) -> DatabaseType:
        """Detect database type from connection URL.

        Supports case-insensitive URL scheme detection and handles
        the common 'postgres://' alias for 'postgresql://'.

        Args:
            database_url: Database connection URL

        Returns:
            Detected DatabaseType

        Example:
            >>> RepositoryFactory.detect_database_type("postgresql://localhost/db")
            DatabaseType.POSTGRES
            >>> RepositoryFactory.detect_database_type("POSTGRESQL://localhost/db")
            DatabaseType.POSTGRES
            >>> RepositoryFactory.detect_database_type("postgres://localhost/db")
            DatabaseType.POSTGRES
            >>> RepositoryFactory.detect_database_type("redshift://localhost/db")
            DatabaseType.REDSHIFT
        """
        url_lower = database_url.lower()

        # PostgreSQL (handles both postgresql:// and postgres://)
        if url_lower.startswith("postgresql://") or url_lower.startswith("postgres://"):
            return DatabaseType.POSTGRES

        # Redshift
        if url_lower.startswith("redshift://"):
            return DatabaseType.REDSHIFT

        # MySQL
        if url_lower.startswith("mysql://"):
            return DatabaseType.MYSQL

        # SQLite
        if url_lower.startswith("sqlite://"):
            return DatabaseType.SQLITE

        # MSSQL
        if url_lower.startswith("mssql://"):
            return DatabaseType.MSSQL

        # Oracle
        if url_lower.startswith("oracle://"):
            return DatabaseType.ORACLE

        # Default to PostgreSQL for compatibility
        return DatabaseType.POSTGRES

    @classmethod
    def create(
        cls,
        database_url: str,
        schema_name: str = "public",
        database_type: Optional[DatabaseType] = None,
    ) -> SchemaRepositoryPort:
        """Create an uninitialized repository instance.

        The repository will need to be initialized by calling its `initialize()`
        method before use.

        Args:
            database_url: Database connection URL
            schema_name: Database schema name (default: "public")
            database_type: Database type. If None, auto-detected from URL.

        Returns:
            Uninitialized repository instance

        Raises:
            NotImplementedError: If the database type is not supported

        Example:
            repo = RepositoryFactory.create("postgresql://localhost/db")
            await repo.initialize()
        """
        cls._register_default_repositories()

        # Auto-detect database type if not provided
        if database_type is None:
            database_type = cls.detect_database_type(database_url)

        # Get repository class from registry
        repository_class = cls._registry.get(database_type)
        if repository_class is None:
            registered = [t.value for t in cls._registry.keys()]
            raise NotImplementedError(
                f"Database type '{database_type.value}' not supported. "
                f"Registered types: {registered}. "
                f"Register a custom repository with RepositoryFactory.register()"
            )

        return repository_class(database_url, schema_name)

    @classmethod
    async def create_and_initialize(
        cls,
        database_url: str,
        schema_name: str = "public",
        database_type: Optional[DatabaseType] = None,
    ) -> SchemaRepositoryPort:
        """Create and initialize a repository instance.

        This is a convenience method that creates the repository and calls
        its `initialize()` method in one step.

        Args:
            database_url: Database connection URL
            schema_name: Database schema name (default: "public")
            database_type: Database type. If None, auto-detected from URL.

        Returns:
            Initialized repository instance ready for use

        Raises:
            NotImplementedError: If the database type is not supported

        Example:
            repo = await RepositoryFactory.create_and_initialize(
                "postgresql://localhost/db",
                schema_name="public"
            )
            tables = await repo.get_tables()
        """
        repository = cls.create(database_url, schema_name, database_type)
        await repository.initialize()
        return repository
