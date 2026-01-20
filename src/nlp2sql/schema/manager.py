"""Schema manager that coordinates all schema strategies."""

import pickle
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog

from ..config.settings import settings
from ..core.entities import DatabaseType
from ..exceptions import SchemaException
from ..ports.cache import CachePort
from ..ports.embedding_provider import EmbeddingProviderPort
from ..ports.schema_repository import SchemaRepositoryPort, TableInfo
from ..ports.schema_strategy import SchemaContext
from .analyzer import SchemaAnalyzer
from .embedding_manager import SchemaEmbeddingManager

logger = structlog.get_logger()


class SchemaManager:
    """Manages database schema with multiple optimization strategies."""

    def __init__(
        self,
        repository: SchemaRepositoryPort,
        cache: Optional[CachePort] = None,
        embedding_provider: Optional[EmbeddingProviderPort] = None,
        embedding_manager: Optional[SchemaEmbeddingManager] = None,
        analyzer: Optional[SchemaAnalyzer] = None,
        schema_filters: Optional[Dict[str, Any]] = None,
        schema_name: str = "public",
    ):
        """
        Initialize schema manager.

        Args:
            repository: Schema repository port
            cache: Optional cache port
            embedding_provider: Optional embedding provider (passed to children if not explicitly provided)
            embedding_manager: Optional embedding manager (will use embedding_provider if provided)
            analyzer: Optional schema analyzer (will use embedding_provider if provided)
            schema_filters: Optional schema filters
            schema_name: Database schema name (default: "public"). Used to isolate embeddings per schema.
        """
        self.repository = repository
        self.cache = cache
        self.embedding_provider = embedding_provider
        self.schema_name = schema_name

        # Create or use provided embedding manager
        if embedding_manager is None:
            self.embedding_manager = SchemaEmbeddingManager(
                database_url=repository.database_url,
                embedding_provider=embedding_provider,
                cache=cache,
                schema_name=schema_name,
            )
        else:
            self.embedding_manager = embedding_manager

        # Create or use provided analyzer
        if analyzer is None:
            self.analyzer = SchemaAnalyzer(embedding_provider=embedding_provider)
        else:
            self.analyzer = analyzer

        # Configuration
        self.max_schema_tokens = settings.max_schema_tokens
        self.cache_enabled = settings.schema_cache_enabled
        self.refresh_interval = timedelta(hours=settings.schema_refresh_interval_hours)

        # Schema filtering
        self.schema_filters = schema_filters or {}
        self.included_schemas = self.schema_filters.get("include_schemas", None)
        self.excluded_schemas = self.schema_filters.get("exclude_schemas", [])
        self.included_tables = self.schema_filters.get("include_tables", None)
        self.excluded_tables = self.schema_filters.get("exclude_tables", [])
        self.exclude_system_tables = self.schema_filters.get("exclude_system_tables", True)

        # Internal state
        self._last_refresh = None
        self._schema_cache = {}
        self._table_relevance_cache = {}

        # Load refresh state early if index exists
        self._load_refresh_state_early()

    async def initialize(self, database_type: DatabaseType) -> None:
        """Initialize schema manager with database schema."""
        try:
            index_file = self.embedding_manager.index_path / "schema_index.faiss"
            metadata_file = self.embedding_manager.index_path / "schema_metadata.pkl"

            if index_file.exists() and metadata_file.exists():
                try:
                    with open(metadata_file, "rb") as f:
                        metadata = pickle.load(f)
                        existing_elements = len(metadata.get("id_to_schema", {}))

                    if existing_elements > 0:
                        logger.info(
                            "Schema index already exists, skipping full initialization",
                            elements=existing_elements,
                        )
                        await self._refresh_schema_if_needed()
                        if self.embedding_provider and hasattr(self.embedding_provider, "_load_model"):
                            try:
                                self.embedding_provider._load_model()
                            except Exception:
                                pass
                        return
                except Exception as e:
                    logger.warning("Failed to check existing index, proceeding with full initialization", error=str(e))

            await self._refresh_schema_if_needed()

            tables = await self.repository.get_tables()

            tables = self._apply_schema_filters(tables)

            schema_elements = []
            for table in tables:
                schema_elements.append(
                    {
                        "type": "table",
                        "name": table.name,
                        "description": table.description or f"Table {table.name}",
                        "columns": [{"name": col["name"], "type": col["type"]} for col in table.columns],
                        "foreign_keys": table.foreign_keys,
                        "primary_keys": table.primary_keys,
                    }
                )

                for column in table.columns:
                    schema_elements.append(
                        {
                            "type": "column",
                            "name": column["name"],
                            "table_name": table.name,
                            "data_type": column["type"],
                            "nullable": column.get("nullable", True),
                            "description": column.get("description", "") or f"Column {column['name']} in {table.name}",
                        }
                    )

            await self.embedding_manager.add_schema_elements(schema_elements, database_type)

            logger.info("Schema manager initialized", tables=len(tables), elements=len(schema_elements))

        except Exception as e:
            logger.error("Failed to initialize schema manager", error=str(e))
            raise SchemaException(f"Schema initialization failed: {e!s}")

    async def get_optimal_schema_context(
        self, query: str, database_type: DatabaseType, max_tokens: Optional[int] = None
    ) -> str:
        """Get optimal schema context for a query."""
        max_tokens = max_tokens or self.max_schema_tokens

        # Check cache first
        cache_key = f"schema_context:{query}:{database_type.value}:{max_tokens}"
        if self.cache_enabled and self.cache:
            cached_context = await self.cache.get(cache_key)
            if cached_context:
                return cached_context

        # Find relevant tables using multiple strategies
        relevant_tables = await self._find_relevant_tables(query, database_type)

        # Build context using analyzer
        context = SchemaContext(
            query=query,
            max_tokens=max_tokens,
            database_type=database_type.value,
            include_samples=False,
            include_indexes=True,
        )

        # Get table details
        table_details = []
        for table_name, relevance_score in relevant_tables:
            try:
                table_info = await self.repository.get_table_info(table_name)
                table_dict = self._table_info_to_dict(table_info)
                table_dict["relevance_score"] = relevance_score
                table_details.append(table_dict)
            except Exception as e:
                logger.warning("Failed to get table info", table=table_name, error=str(e))

        # Build optimized context
        schema_context = await self.analyzer.build_context(context, table_details)

        # Validate token count
        estimated_tokens = len(schema_context) // 4  # Rough estimation
        if estimated_tokens > max_tokens:
            # Compress further
            schema_dict = {table["name"]: table for table in table_details}
            schema_context = await self.analyzer.compress_schema(schema_dict, max_tokens)

        # Cache result
        if self.cache_enabled and self.cache:
            await self.cache.set(cache_key, schema_context)

        return schema_context

    async def find_relevant_tables(
        self, query: str, database_type: DatabaseType, max_tables: int = 10
    ) -> List[Tuple[str, float]]:
        """Find tables most relevant to a query."""
        return await self._find_relevant_tables(query, database_type, max_tables)

    async def get_table_relationships(self, table_name: str, database_type: DatabaseType) -> List[Dict[str, Any]]:
        """Get relationships for a table."""
        # Get direct relationships from repository
        related_tables = await self.repository.get_related_tables(table_name)

        # Find semantically related tables
        semantic_relations = await self.embedding_manager.find_related_tables(table_name, database_type)

        # Combine and deduplicate
        all_relations = {}

        # Add direct relationships
        for table in related_tables:
            all_relations[table.name] = {
                "name": table.name,
                "relationship_type": "foreign_key",
                "confidence": 1.0,
                "metadata": {"direct": True},
            }

        # Add semantic relationships
        for rel_table, confidence in semantic_relations:
            if rel_table not in all_relations:
                all_relations[rel_table] = {
                    "name": rel_table,
                    "relationship_type": "semantic",
                    "confidence": confidence,
                    "metadata": {"semantic": True},
                }

        return list(all_relations.values())

    async def analyze_query_complexity(self, query: str) -> Dict[str, Any]:
        """Analyze query complexity and suggest optimization strategies."""
        # Use embedding search to find similar queries
        similar_elements = await self.embedding_manager.search_similar(query, top_k=5)

        # Analyze query tokens
        query_tokens = self.analyzer._tokenize(query)

        # Estimate complexity
        complexity_score = self._estimate_complexity(query, query_tokens)

        # Suggest strategies
        strategies = self._suggest_strategies(complexity_score, len(similar_elements))

        return {
            "complexity_score": complexity_score,
            "token_count": len(query_tokens),
            "similar_elements": len(similar_elements),
            "suggested_strategies": strategies,
            "analyzed_at": datetime.now().isoformat(),
        }

    async def refresh_schema(self) -> None:
        """Manually refresh schema cache."""
        await self.repository.refresh_schema()
        self._last_refresh = datetime.now()
        self._save_refresh_state()

        # Clear relevant caches
        if self.cache:
            # Clear schema-related cache keys
            pass  # Implementation depends on cache implementation

        self._schema_cache.clear()
        self._table_relevance_cache.clear()

        logger.info("Schema refreshed")

    async def _get_cached_tables(self) -> List[TableInfo]:
        """Get tables from internal cache or fetch from repository.

        This avoids expensive database queries on every call to _find_relevant_tables.
        Tables are cached in memory for the lifetime of the SchemaManager instance.
        Call refresh_schema() to clear the cache and fetch fresh data.
        """
        cache_key = "_all_tables"
        if cache_key not in self._schema_cache:
            tables = await self.repository.get_tables()
            tables = self._apply_schema_filters(tables)
            self._schema_cache[cache_key] = tables
            logger.debug("Tables cached", count=len(tables))
        return self._schema_cache[cache_key]

    async def _find_relevant_tables(
        self, query: str, database_type: DatabaseType, max_tables: int = 10
    ) -> List[Tuple[str, float]]:
        """Find relevant tables using multiple strategies including batch scoring.

        Uses batch scoring when analyzing multiple tables to minimize API calls.
        """
        # Check in-memory cache first (faster than external cache)
        mem_cache_key = f"{query}:{database_type.value}:{max_tables}"
        if mem_cache_key in self._table_relevance_cache:
            logger.debug("Table relevance cache hit", query=query[:50])
            return self._table_relevance_cache[mem_cache_key]

        # Clear analyzer's query embedding cache at the start of each new query
        # This prevents unbounded memory growth while enabling per-query caching
        self.analyzer.clear_query_embedding_cache()

        # Check external cache (Redis, etc.)
        cache_key = f"relevant_tables:{query}:{database_type.value}:{max_tables}"
        if self.cache_enabled and self.cache:
            cached_tables = await self.cache.get(cache_key)
            if cached_tables:
                # Also store in memory cache for faster repeated access
                self._table_relevance_cache[mem_cache_key] = cached_tables
                return cached_tables

        # Strategy 1: Embedding similarity (uses FAISS index)
        embedding_results = await self.embedding_manager.search_similar(
            query, top_k=max_tables * 2, database_type=database_type
        )

        # Filter to tables only
        table_scores = {}
        for element, score in embedding_results:
            if element.get("type") == "table":
                table_scores[element["name"]] = max(table_scores.get(element["name"], 0), score)
            elif element.get("type") == "column":
                # Column relevance contributes to table relevance
                table_name = element.get("table_name")
                if table_name:
                    table_scores[table_name] = max(table_scores.get(table_name, 0), score * 0.8)

        # Strategy 2: Batch schema analysis
        # Use cached tables (now fast with bulk query + disk cache)
        all_tables = await self._get_cached_tables()

        # Identify tables to analyze with batch scoring
        query_tokens = set(self.analyzer._tokenize(query.lower()))
        normalized_query_tokens = {self.analyzer._normalize_word(t) for t in query_tokens}

        tables_to_analyze = []
        for table in all_tables:
            table_name_tokens = set(self.analyzer._tokenize(table.name.lower()))
            normalized_table_tokens = {self.analyzer._normalize_word(t) for t in table_name_tokens}
            has_token_match = bool(query_tokens & table_name_tokens) or bool(
                normalized_query_tokens & normalized_table_tokens
            )

            # Analyze if: has token match OR (not in results AND we need more)
            should_analyze = has_token_match or (
                table.name not in table_scores and len(table_scores) < max_tables * 2
            )

            if should_analyze:
                tables_to_analyze.append(table)

        # Use batch scoring for all tables to analyze (single API call)
        if tables_to_analyze:
            table_dicts = [self._table_info_to_dict(t) for t in tables_to_analyze]

            # Batch score all tables (uses single embedding API call)
            scored_tables = await self.analyzer.score_relevance_batch(
                query, table_dicts, use_semantic=True
            )

            for table_dict, score in scored_tables:
                if score > 0.1:  # Minimum threshold
                    table_name = table_dict["name"]
                    table_scores[table_name] = max(table_scores.get(table_name, 0), score)

        # Separate exact matches (score >= 1.0) to ensure they come first
        exact_matches = [(name, score) for name, score in table_scores.items() if score >= 1.0]
        other_matches = [(name, score) for name, score in table_scores.items() if score < 1.0]

        # Sort each group by score
        exact_matches.sort(key=lambda x: x[1], reverse=True)
        other_matches.sort(key=lambda x: x[1], reverse=True)

        # Combine: exact matches first, then others
        sorted_tables = exact_matches + other_matches

        # Apply minimum threshold and limit
        relevant_tables = []
        for table_name, score in sorted_tables:
            if score >= 0.2 and len(relevant_tables) < max_tables:
                relevant_tables.append((table_name, score))

        # Store in memory cache (always enabled, for repeated queries in same session)
        self._table_relevance_cache[mem_cache_key] = relevant_tables

        # Also cache in external cache if available
        if self.cache_enabled and self.cache:
            await self.cache.set(cache_key, relevant_tables)

        return relevant_tables

    async def _refresh_schema_if_needed(self) -> None:
        """Refresh schema if the refresh interval has passed."""
        if self._last_refresh is None:
            self._last_refresh = self._load_refresh_state()

        if self._last_refresh is None or datetime.now() - self._last_refresh > self.refresh_interval:
            await self.refresh_schema()

    def _load_refresh_state_early(self) -> None:
        """Load refresh state early in initialization if index exists."""
        metadata_file = self.embedding_manager.index_path / "schema_metadata.pkl"
        if metadata_file.exists():
            self._last_refresh = self._load_refresh_state()

    def _load_refresh_state(self) -> Optional[datetime]:
        """Load last refresh time from metadata file."""
        metadata_file = self.embedding_manager.index_path / "schema_metadata.pkl"
        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, "rb") as f:
                metadata = pickle.load(f)
                last_refresh_str = metadata.get("last_refresh")
                if last_refresh_str:
                    return datetime.fromisoformat(last_refresh_str)
        except Exception as e:
            logger.warning("Failed to load refresh state", error=str(e))
        return None

    def _save_refresh_state(self) -> None:
        """Save refresh state to metadata file."""
        if self._last_refresh is None:
            return

        metadata_file = self.embedding_manager.index_path / "schema_metadata.pkl"
        try:
            metadata = {}
            if metadata_file.exists():
                with open(metadata_file, "rb") as f:
                    metadata = pickle.load(f)

            metadata["last_refresh"] = self._last_refresh.isoformat()
            metadata["refresh_interval_hours"] = self.refresh_interval.total_seconds() / 3600

            with open(metadata_file, "wb") as f:
                pickle.dump(metadata, f)
        except Exception as e:
            logger.warning("Failed to save refresh state", error=str(e))

    def _table_info_to_dict(self, table_info: TableInfo) -> Dict[str, Any]:
        """Convert TableInfo to dictionary."""
        return {
            "name": table_info.name,
            "type": "table",
            "description": table_info.description,
            "columns": table_info.columns,
            "primary_keys": table_info.primary_keys,
            "foreign_keys": table_info.foreign_keys,
            "indexes": table_info.indexes,
            "row_count": table_info.row_count,
            "size_bytes": table_info.size_bytes,
        }

    def _estimate_complexity(self, query: str, query_tokens: List[str]) -> float:
        """Estimate query complexity on a scale of 0-1."""
        complexity_indicators = {
            "length": len(query_tokens) / 20,  # Normalize by expected length
            "joins": len([t for t in query_tokens if "join" in t.lower()]) * 0.2,
            "aggregations": len(
                [t for t in query_tokens if t.lower() in ["sum", "count", "avg", "max", "min", "group"]]
            )
            * 0.15,
            "subqueries": query.lower().count("select") * 0.1,
            "conditions": len([t for t in query_tokens if t.lower() in ["where", "having", "and", "or"]]) * 0.1,
        }

        return min(sum(complexity_indicators.values()), 1.0)

    def _suggest_strategies(self, complexity_score: float, similar_elements: int) -> List[str]:
        """Suggest optimization strategies based on complexity."""
        strategies = []

        if complexity_score > 0.7:
            strategies.append("high_complexity_optimization")
            strategies.append("schema_compression")

        if complexity_score > 0.5:
            strategies.append("relevance_filtering")

        if similar_elements > 3:
            strategies.append("example_based_generation")

        if similar_elements < 2:
            strategies.append("schema_exploration")

        return strategies

    def _apply_schema_filters(self, tables: List[TableInfo]) -> List[TableInfo]:
        """Apply schema filters to table list."""
        filtered_tables = []

        for table in tables:
            # Extract schema name if present (e.g., "public.users" -> "public")
            schema_name = None
            if hasattr(table, "schema") and table.schema:
                schema_name = table.schema
            elif "." in table.name:
                schema_name = table.name.split(".")[0]

            # Check schema-level filters
            if self.included_schemas is not None:
                if schema_name not in self.included_schemas:
                    continue

            if schema_name in self.excluded_schemas:
                continue

            # Check table-level filters
            if self.included_tables is not None:
                if table.name not in self.included_tables:
                    continue

            if table.name in self.excluded_tables:
                continue

            # Check system table filter
            if self.exclude_system_tables:
                # Common system table patterns
                system_patterns = [
                    "pg_",
                    "sql_",
                    "information_schema",
                    "sys_",
                    "sqlite_",
                    "mysql.",
                    "performance_schema",
                ]
                if any(table.name.startswith(pattern) for pattern in system_patterns):
                    continue

            filtered_tables.append(table)

        logger.info(
            "Schema filtering applied",
            original_count=len(tables),
            filtered_count=len(filtered_tables),
            filters=self.schema_filters,
        )

        return filtered_tables
