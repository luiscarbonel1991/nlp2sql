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
from sentence_transformers import SentenceTransformer

from ..core.entities import DatabaseType
from ..ports.cache import CachePort

logger = structlog.get_logger()


class SchemaEmbeddingManager:
    """Manages embeddings for schema elements with FAISS indexing."""

    def __init__(
        self,
        database_url: str,
        embedding_model: str = "all-MiniLM-L6-v2",
        cache: Optional[CachePort] = None,
        index_path: Optional[Path] = None,
    ):
        self.model = SentenceTransformer(embedding_model)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        self.cache = cache

        # Create a unique directory for each database
        db_hash = hashlib.md5(database_url.encode()).hexdigest()

        # Use environment variable for embeddings directory, fallback to ./embeddings
        embeddings_dir = os.getenv("NLP2SQL_EMBEDDINGS_DIR", "./embeddings")
        self.index_path = (index_path or Path(embeddings_dir)) / db_hash

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

        # Initialize or load index
        self._initialize_index()

    def _initialize_index(self) -> None:
        """Initialize or load FAISS index."""
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
            logger.info("Loaded existing embedding index", elements=len(self.id_to_schema))
        else:
            # Create new index
            self.index = faiss.IndexFlatIP(self.embedding_dim)  # Inner product for cosine similarity
            logger.info("Created new embedding index")

    async def add_schema_elements(self, elements: List[Dict[str, Any]], database_type: DatabaseType) -> None:
        """Add schema elements to the embedding index."""
        new_elements = []
        descriptions = []

        for element in elements:
            # Create unique key
            element_key = self._create_element_key(element, database_type)

            if element_key not in self.schema_to_id:
                # Create description for embedding
                description = self._create_element_description(element)
                descriptions.append(description)
                new_elements.append(element)

                # Store mapping
                self.id_to_schema[self._next_id] = {
                    "element": element,
                    "database_type": database_type.value,
                    "key": element_key,
                    "description": description,
                    "indexed_at": datetime.now().isoformat(),
                }
                self.schema_to_id[element_key] = self._next_id
                self._next_id += 1

        if new_elements:
            # Create embeddings
            embeddings = self.model.encode(descriptions, normalize_embeddings=True, show_progress_bar=True)

            # Add to FAISS index
            self.index.add(np.array(embeddings, dtype=np.float32))

            # Save index
            await self._save_index()

            logger.info(
                "Added schema elements to index", new_elements=len(new_elements), total_elements=len(self.id_to_schema)
            )

    async def search_similar(
        self, query: str, top_k: int = 10, database_type: Optional[DatabaseType] = None, min_score: float = 0.3
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Search for similar schema elements."""
        if self.index.ntotal == 0:
            return []

        # Check cache
        cache_key = f"schema_search:{query}:{top_k}:{database_type}"
        if self.cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                return cached_result

        # Create query embedding
        query_embedding = self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)

        # Search in FAISS
        k = min(top_k * 2, self.index.ntotal)  # Search more to filter by database type
        scores, indices = self.index.search(query_embedding.astype(np.float32), k)

        # Filter and format results
        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:  # FAISS returns -1 for not found
                continue

            schema_info = self.id_to_schema[idx]

            # Filter by database type if specified
            if database_type and schema_info["database_type"] != database_type.value:
                continue

            # Filter by minimum score
            if score < min_score:
                continue

            results.append((schema_info["element"], float(score)))

            if len(results) >= top_k:
                break

        # Cache results
        if self.cache:
            await self.cache.set(cache_key, results)

        return results

    async def get_table_embeddings(self, table_names: List[str], database_type: DatabaseType) -> Dict[str, np.ndarray]:
        """Get embeddings for specific tables."""
        embeddings = {}

        for table_name in table_names:
            element_key = f"{database_type.value}:table:{table_name}"

            if element_key in self.schema_to_id:
                idx = self.schema_to_id[element_key]
                # Reconstruct embedding from index
                embedding = self.index.reconstruct(idx)
                embeddings[table_name] = embedding
            else:
                # Create new embedding
                description = f"Table {table_name}"
                embedding = self.model.encode([description], normalize_embeddings=True, show_progress_bar=False)[0]
                embeddings[table_name] = embedding

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

        # Save metadata
        metadata = {
            "id_to_schema": self.id_to_schema,
            "schema_to_id": self.schema_to_id,
            "next_id": self._next_id,
            "saved_at": datetime.now().isoformat(),
        }
        with open(metadata_file, "wb") as f:
            pickle.dump(metadata, f)

    async def clear_index(self) -> None:
        """Clear the embedding index."""
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.id_to_schema = {}
        self.schema_to_id = {}
        self._next_id = 0

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
