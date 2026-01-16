"""Embedding manager for schema vectorization and search."""

import hashlib
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np
import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..core.entities import DatabaseType
from ..exceptions import SchemaException
from ..ports.cache import CachePort
from ..ports.embedding_provider import EmbeddingProviderPort

logger = structlog.get_logger()


def _get_embeddings_directory() -> Path:
    """Get writable embeddings directory with fallback chain.

    Tries directories in order:
    1. NLP2SQL_EMBEDDINGS_DIR environment variable (explicit user config)
    2. ./embeddings (development default, tests writability)
    3. /tmp/nlp2sql_embeddings (containerized/sandboxed fallback)

    This ensures the MCP server works in containerized environments like
    Claude Desktop where the current directory may be read-only.

    Returns:
        Path to a writable embeddings directory
    """
    # Try explicit config first
    explicit_dir = os.getenv("NLP2SQL_EMBEDDINGS_DIR")
    if explicit_dir:
        return Path(explicit_dir)

    # Try ./embeddings (development default)
    local_dir = Path("./embeddings")
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        # Test if writable by creating and removing a test file
        test_file = local_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        return local_dir
    except (OSError, PermissionError):
        pass

    # Fallback to /tmp for containerized environments
    tmp_dir = Path("/tmp/nlp2sql_embeddings")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Using /tmp fallback for embeddings directory (current directory not writable)",
        path=str(tmp_dir),
    )
    return tmp_dir


class SchemaEmbeddingManager:
    """Manages embeddings for schema elements with FAISS indexing."""

    def __init__(
        self,
        database_url: str,
        embedding_provider: Optional[EmbeddingProviderPort] = None,
        embedding_model: str = "all-MiniLM-L6-v2",
        cache: Optional[CachePort] = None,
        index_path: Optional[Path] = None,
        schema_name: str = "public",
    ):
        """
        Initialize schema embedding manager.

        Args:
            database_url: Database connection URL
            embedding_provider: Optional embedding provider. If None, embedding-based search is disabled.
            embedding_model: Model name for local adapter (unused, kept for API compatibility).
            cache: Optional cache port for caching results
            index_path: Optional custom path for index storage
            schema_name: Database schema name (default: "public"). Used to isolate embeddings per schema.

        Note:
            If embedding_provider is None, the manager will work but search_similar() will
            always return empty results. This allows the system to function without embeddings
            (using text-based matching only in SchemaAnalyzer).
        """
        self.embedding_provider = embedding_provider
        self.schema_name = schema_name

        if embedding_provider is None:
            logger.info(
                "SchemaEmbeddingManager initialized without embedding provider. "
                "Embedding-based search will be disabled."
            )

        self.cache = cache

        # Create a unique directory for each database+schema combination
        # This prevents embeddings from different schemas being mixed together
        index_key = f"{database_url}:{schema_name}"
        db_hash = hashlib.md5(index_key.encode()).hexdigest()

        # Get embeddings directory with fallback chain for containerized environments
        embeddings_dir = _get_embeddings_directory()
        self.index_path = (index_path or embeddings_dir) / db_hash

        try:
            self.index_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error("Failed to create embeddings directory", path=str(self.index_path), error=str(e))
            raise

        # FAISS index for similarity search
        self.index = None
        self.id_to_schema = {}
        self.schema_to_id = {}
        self._next_id = 0

        # Hybrid Search (TF-IDF)
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
        self.tfidf_texts = []

        # Skip index initialization if no embedding provider
        if embedding_provider is None:
            self.embedding_dim = None
            return

        # Try to load dimension from metadata if index exists
        index_file = self.index_path / "schema_index.faiss"
        metadata_file = self.index_path / "schema_metadata.pkl"

        if index_file.exists() and metadata_file.exists():
            try:
                with open(metadata_file, "rb") as f:
                    metadata = pickle.load(f)
                    provider_dim = self.embedding_provider.get_embedding_dimension()

                    # Use provider dimension, not stored dimension
                    # This ensures we detect mismatches correctly
                    self.embedding_dim = provider_dim
            except Exception as e:
                logger.warning("Failed to load dimension from metadata, loading model", error=str(e))
                self.embedding_dim = self.embedding_provider.get_embedding_dimension()
        else:
            self.embedding_dim = self.embedding_provider.get_embedding_dimension()

        # Initialize or load index
        self._initialize_index()

    def _initialize_index(self) -> None:
        """Initialize or load FAISS index with dimension validation."""
        index_file = self.index_path / "schema_index.faiss"
        metadata_file = self.index_path / "schema_metadata.pkl"

        if index_file.exists() and metadata_file.exists():
            # Load existing index
            self.index = faiss.read_index(str(index_file))
            with open(metadata_file, "rb") as f:
                metadata = pickle.load(f)
                self.id_to_schema = metadata["id_to_schema"]
                self.schema_to_id = metadata["schema_to_id"]
                self._next_id = metadata["next_id"]

                # Load TF-IDF data if available
                if "tfidf_vectorizer" in metadata:
                    self.tfidf_vectorizer = metadata["tfidf_vectorizer"]
                    self.tfidf_matrix = metadata["tfidf_matrix"]
                    self.tfidf_texts = metadata.get("tfidf_texts", [])

            # Check dimension mismatch
            existing_dim = self.index.d
            stored_provider = metadata.get("provider_type", "unknown")
            stored_dim = metadata.get("embedding_dimension", existing_dim)
            provider_dimension = self.embedding_provider.get_embedding_dimension()

            # Compare with current provider dimension, not stored dimension
            if existing_dim != provider_dimension:
                logger.error(
                    "Embedding dimension mismatch detected",
                    existing_dim=existing_dim,
                    provider_dimension=provider_dimension,
                    stored_provider=stored_provider,
                    current_provider=self.embedding_provider.provider_type,
                )
                error_msg = (
                    f"Embedding provider changed. Existing index dimensions ({existing_dim}) "
                    f"don't match new provider ({provider_dimension}). "
                    f"Please clear the index or migrate to the new provider. "
                    f"Previous provider: {stored_provider}, "
                    f"Current provider: {self.embedding_provider.provider_type}. "
                    f"Run: nlp2sql cache clear --embeddings"
                )
                raise SchemaException(error_msg)

            # Warn if provider type changed but dimensions match (unlikely but possible)
            if stored_provider != "unknown" and stored_provider != self.embedding_provider.provider_type:
                logger.warning(
                    "Embedding provider type changed but dimensions match",
                    previous_provider=stored_provider,
                    current_provider=self.embedding_provider.provider_type,
                    dimension=self.embedding_dim,
                )

            logger.info(
                "Loaded existing embedding index",
                elements=len(self.id_to_schema),
                dimension=self.embedding_dim,
                provider=self.embedding_provider.provider_type,
            )
        else:
            # Create new index
            self.index = faiss.IndexFlatIP(self.embedding_dim)  # Inner product for cosine similarity
            logger.info(
                "Created new embedding index",
                dimension=self.embedding_dim,
                provider=self.embedding_provider.provider_type,
            )

    async def add_schema_elements(self, elements: List[Dict[str, Any]], database_type: DatabaseType) -> None:
        """Add schema elements to the embedding index."""
        # Skip if no embedding provider
        if self.embedding_provider is None or self.index is None:
            logger.debug("Skipping schema element indexing - no embedding provider")
            return

        # Phase 1: Collect elements without storing mappings yet
        # This prevents orphan mappings if embedding validation fails
        new_elements = []
        descriptions = []
        element_keys = []  # Track keys for later mapping storage

        for element in elements:
            # Create unique key
            element_key = self._create_element_key(element, database_type)

            if element_key not in self.schema_to_id:
                # Create description for embedding
                description = self._create_element_description(element)

                # Skip elements with empty or invalid descriptions
                is_invalid = not description or not isinstance(description, str) or not description.strip()
                if is_invalid:
                    logger.warning(
                        "Skipping element with invalid description",
                        element_key=element_key,
                        description=description,
                    )
                    continue

                descriptions.append(description)
                new_elements.append(element)
                element_keys.append(element_key)  # Store key for later

        if not new_elements or not descriptions:
            return

        # Phase 2: Generate embeddings and validate BEFORE storing any mappings
        embeddings = await self.embedding_provider.encode(descriptions)

        # Validate embeddings - if validation fails, no mappings were stored (no orphans)
        if embeddings.size == 0:
            logger.warning(
                "No embeddings generated, skipping index update",
                elements_count=len(new_elements),
                descriptions_count=len(descriptions),
            )
            return

        if len(embeddings) != len(new_elements):
            logger.error(
                "Mismatch between embeddings and elements",
                embeddings_count=len(embeddings),
                elements_count=len(new_elements),
            )
            return

        # Phase 3: Store mappings ONLY after embeddings are validated
        # This ensures mappings and FAISS index stay in sync
        for element, element_key, description in zip(new_elements, element_keys, descriptions):
            self.id_to_schema[self._next_id] = {
                "element": element,
                "database_type": database_type.value,
                "key": element_key,
                "description": description,
                "indexed_at": datetime.now().isoformat(),
            }
            self.schema_to_id[element_key] = self._next_id
            self._next_id += 1

        # Phase 4: Add to FAISS index (mappings already stored)
        self.index.add(np.array(embeddings, dtype=np.float32))

        # Update TF-IDF index
        self._update_tfidf_index(descriptions)

        # Save index
        await self._save_index()

        logger.info(
            "Added schema elements to index", new_elements=len(new_elements), total_elements=len(self.id_to_schema)
        )

    async def search_similar(
        self, query: str, top_k: int = 10, database_type: Optional[DatabaseType] = None, min_score: float = 0.3
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Search for similar schema elements."""
        # Return empty if no embedding provider or no index
        if self.embedding_provider is None or self.index is None:
            return []

        if self.index.ntotal == 0:
            return []

        # Check cache
        cache_key = f"schema_search:{query}:{top_k}:{database_type}"
        if self.cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                return cached_result

        # Create query embedding using provider
        query_embedding = await self.embedding_provider.encode([query])

        # Search in FAISS (Dense Search)
        # Get more candidates for re-ranking
        k = min(top_k * 3, self.index.ntotal)
        dense_scores, dense_indices = self.index.search(query_embedding.astype(np.float32), k)

        # Prepare results map for merging
        # Map: index -> {element, dense_score, sparse_score}
        candidates = {}

        # Process Dense Results
        for idx, score in zip(dense_indices[0], dense_scores[0]):
            if idx < 0:
                continue
            candidates[idx] = {"score": float(score), "dense_score": float(score), "sparse_score": 0.0}

        # Sparse Search (TF-IDF)
        if self.tfidf_vectorizer and self.tfidf_matrix is not None:
            try:
                query_vec = self.tfidf_vectorizer.transform([query])
                # Calculate cosine similarity between query and all docs
                sparse_scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

                # Get top sparse results
                # We look at all docs because sparse search is fast
                sparse_indices = sparse_scores.argsort()[::-1][:k]

                for idx in sparse_indices:
                    score = float(sparse_scores[idx])
                    if score > 0:
                        if idx in candidates:
                            candidates[idx]["sparse_score"] = score
                        else:
                            # If not in dense results, add it
                            # Note: Dense score is 0 here, which is a penalty
                            candidates[idx] = {"score": 0.0, "dense_score": 0.0, "sparse_score": score}
            except Exception as e:
                logger.warning("TF-IDF search failed, falling back to dense only", error=str(e))

        # Combine Scores (Hybrid Reranking)
        # Weight: 0.5 Dense + 0.5 Sparse
        # Balanced weighting gives equal priority to semantic meaning and exact keyword matches
        # This helps ensure tables with exact name matches (like "organization" for "count organizations")
        # are properly ranked even when dense embeddings favor other tables
        alpha = 0.5
        final_results = []

        for idx, data in candidates.items():
            schema_info = self.id_to_schema[idx]

            # Filter by database type if specified
            if database_type and schema_info["database_type"] != database_type.value:
                continue

            # Calculate hybrid score
            hybrid_score = (data["dense_score"] * alpha) + (data["sparse_score"] * (1 - alpha))

            if hybrid_score < min_score:
                continue

            final_results.append((schema_info["element"], hybrid_score))

        # Sort by hybrid score
        final_results.sort(key=lambda x: x[1], reverse=True)
        results = final_results[:top_k]

        # Cache results
        if self.cache:
            await self.cache.set(cache_key, results)

        return results

    async def get_table_embeddings(self, table_names: List[str], database_type: DatabaseType) -> Dict[str, np.ndarray]:
        """Get embeddings for specific tables."""
        # Return empty if no embedding provider
        if self.embedding_provider is None or self.index is None:
            return {}

        embeddings = {}

        for table_name in table_names:
            element_key = f"{database_type.value}:table:{table_name}"

            if element_key in self.schema_to_id:
                idx = self.schema_to_id[element_key]
                # Reconstruct embedding from index
                embedding = self.index.reconstruct(idx)
                embeddings[table_name] = embedding
            else:
                # Create new embedding using provider
                description = f"Table {table_name}"
                embedding_array = await self.embedding_provider.encode([description])
                embeddings[table_name] = embedding_array[0]

        return embeddings

    async def find_related_tables(
        self, table_name: str, database_type: DatabaseType, top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """Find tables related to a given table."""
        # Search using table name as query
        results = await self.search_similar(
            f"Table {table_name}",
            top_k=top_k * 2,  # Get more results to filter
            database_type=database_type,
        )

        # Filter to only tables (not columns) and exclude self
        related_tables = []
        for element, score in results:
            if element.get("type") == "table" and element.get("name") != table_name:
                related_tables.append((element["name"], score))

            if len(related_tables) >= top_k:
                break

        return related_tables

    async def update_embeddings(self, elements: List[Dict[str, Any]], database_type: DatabaseType) -> None:
        """Update embeddings for existing elements."""
        # Remove old embeddings
        for element in elements:
            element_key = self._create_element_key(element, database_type)
            if element_key in self.schema_to_id:
                # Note: FAISS doesn't support removal, so we mark as outdated
                old_id = self.schema_to_id[element_key]
                self.id_to_schema[old_id]["outdated"] = True

        # Add new embeddings
        await self.add_schema_elements(elements, database_type)

    def _create_element_key(self, element: Dict[str, Any], database_type: DatabaseType) -> str:
        """Create unique key for schema element."""
        element_type = element.get("type", "unknown")
        element_name = element.get("name", "unnamed")

        if element_type == "column":
            table_name = element.get("table_name", "unknown_table")
            return f"{database_type.value}:{element_type}:{table_name}.{element_name}"
        return f"{database_type.value}:{element_type}:{element_name}"

    def _create_element_description(self, element: Dict[str, Any]) -> str:
        """Create description for embedding."""
        parts = []

        element_type = element.get("type", "unknown")
        element_name = element.get("name", "unnamed")

        # Base description
        parts.append(f"{element_type.capitalize()} {element_name}")

        # Add custom description if available
        if "description" in element:
            parts.append(element["description"])

        # Add column information for tables
        if element_type == "table" and "columns" in element:
            col_names = [col.get("name", "") for col in element["columns"][:10]]
            if col_names:
                parts.append(f"Columns: {', '.join(col_names)}")

        # Add data type for columns
        if element_type == "column" and "data_type" in element:
            parts.append(f"Type: {element['data_type']}")
            if "table_name" in element:
                parts.append(f"In table: {element['table_name']}")

        # Add relationships
        if element.get("foreign_keys"):
            fk_tables = [fk.get("ref_table", "") for fk in element["foreign_keys"]]
            if fk_tables:
                parts.append(f"Related to: {', '.join(set(fk_tables))}")

        return " | ".join(parts)

    async def _save_index(self) -> None:
        """Save FAISS index and metadata."""
        index_file = self.index_path / "schema_index.faiss"
        metadata_file = self.index_path / "schema_metadata.pkl"

        # Save FAISS index
        faiss.write_index(self.index, str(index_file))

        # Load existing metadata to preserve fields managed by other components
        existing_metadata = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, "rb") as f:
                    existing_metadata = pickle.load(f)
            except Exception:
                pass

        # Save metadata including provider information
        metadata = {
            "id_to_schema": self.id_to_schema,
            "schema_to_id": self.schema_to_id,
            "next_id": self._next_id,
            "saved_at": datetime.now().isoformat(),
            "provider_type": self.embedding_provider.provider_type,
            "embedding_dimension": self.embedding_dim,
            "tfidf_vectorizer": self.tfidf_vectorizer,
            "tfidf_matrix": self.tfidf_matrix,
            "tfidf_texts": self.tfidf_texts,
        }

        # Preserve refresh state fields managed by SchemaManager
        if "last_refresh" in existing_metadata:
            metadata["last_refresh"] = existing_metadata["last_refresh"]
        if "refresh_interval_hours" in existing_metadata:
            metadata["refresh_interval_hours"] = existing_metadata["refresh_interval_hours"]

        with open(metadata_file, "wb") as f:
            pickle.dump(metadata, f)

    def _update_tfidf_index(self, new_texts: List[str]) -> None:
        """Update TF-IDF index with new texts."""
        # Append new texts
        self.tfidf_texts.extend(new_texts)

        # Re-fit vectorizer on all texts
        # Note: For very large schemas, this might be slow and need optimization
        # (e.g., incremental fitting or batching), but for <100k elements it's fine.
        if self.tfidf_texts:
            self.tfidf_vectorizer = TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),  # Use unigrams and bigrams
                min_df=1,  # Include terms that appear even once
                stop_words="english",
            )
            self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.tfidf_texts)

    async def clear_index(self) -> None:
        """Clear the embedding index."""
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.id_to_schema = {}
        self.schema_to_id = {}
        self._next_id = 0

        # Clear TF-IDF
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
        self.tfidf_texts = []

        # Clear cache if available
        if self.cache:
            await self.cache.clear()

        # Remove saved files
        index_file = self.index_path / "schema_index.faiss"
        metadata_file = self.index_path / "schema_metadata.pkl"

        if index_file.exists():
            index_file.unlink()
        if metadata_file.exists():
            metadata_file.unlink()

        logger.info("Cleared embedding index")
