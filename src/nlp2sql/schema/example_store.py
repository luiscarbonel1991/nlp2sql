"""Example store for managing and retrieving query examples using vector similarity."""

import hashlib
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
import structlog

from ..ports.embedding_provider import EmbeddingProviderPort

logger = structlog.get_logger()


class ExampleStore:
    """Manages examples for few-shot learning with FAISS indexing."""

    def __init__(
        self,
        embedding_provider: EmbeddingProviderPort,
        index_path: Optional[Path] = None,
    ):
        """
        Initialize example store.

        Args:
            embedding_provider: Embedding provider for vectorizing questions
            index_path: Optional custom path for index storage
        """
        self.embedding_provider = embedding_provider
        self.embedding_dim = self.embedding_provider.get_embedding_dimension()

        # Use environment variable or default path
        import os

        examples_dir = os.getenv("NLP2SQL_EXAMPLES_DIR", "./examples_index")
        self.index_path = index_path or Path(examples_dir)

        try:
            self.index_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error("Failed to create examples directory", path=str(self.index_path), error=str(e))
            raise

        # FAISS index for similarity search
        self.index = None
        self.id_to_example = {}
        self.example_to_id = {}
        self._next_id = 0

        # Initialize or load index
        self._initialize_index()

    def _initialize_index(self) -> None:
        """Initialize or load FAISS index."""
        index_file = self.index_path / "examples_index.faiss"
        metadata_file = self.index_path / "examples_metadata.pkl"

        if index_file.exists() and metadata_file.exists():
            # Load existing index
            self.index = faiss.read_index(str(index_file))
            with open(metadata_file, "rb") as f:
                metadata = pickle.load(f)
                self.id_to_example = metadata["id_to_example"]
                self.example_to_id = metadata["example_to_id"]
                self._next_id = metadata["next_id"]

            logger.info(
                "Loaded existing example index",
                examples=len(self.id_to_example),
                dimension=self.embedding_dim,
            )
        else:
            # Create new index
            self.index = faiss.IndexFlatIP(self.embedding_dim)
            logger.info(
                "Created new example index",
                dimension=self.embedding_dim,
            )

    async def add_examples(self, examples: List[Dict[str, Any]]) -> None:
        """
        Add examples to the store.

        Args:
            examples: List of examples with format:
                {"question": str, "sql": str, "database_type": str, "metadata": dict}
        """
        new_examples = []
        questions = []

        for example in examples:
            # Create unique key based on question and SQL
            example_key = self._create_example_key(example)

            if example_key not in self.example_to_id:
                questions.append(example["question"])
                new_examples.append(example)

                # Store mapping
                self.id_to_example[self._next_id] = {
                    "example": example,
                    "key": example_key,
                    "indexed_at": datetime.now().isoformat(),
                }
                self.example_to_id[example_key] = self._next_id
                self._next_id += 1

        if new_examples:
            # Create embeddings for questions
            embeddings = await self.embedding_provider.encode(questions)

            # Add to FAISS index
            self.index.add(np.array(embeddings, dtype=np.float32))

            # Save index
            await self._save_index()

            logger.info(
                "Added examples to index",
                new_examples=len(new_examples),
                total_examples=len(self.id_to_example),
            )

    async def search_similar(
        self,
        question: str,
        top_k: int = 5,
        database_type: Optional[str] = None,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar examples.

        Args:
            question: User's question
            top_k: Number of examples to return
            database_type: Optional filter by database type
            min_score: Minimum similarity score

        Returns:
            List of examples sorted by relevance
        """
        if self.index.ntotal == 0:
            return []

        # Create query embedding
        query_embedding = await self.embedding_provider.encode([question])

        # Search in FAISS
        k = min(top_k * 2, self.index.ntotal)
        scores, indices = self.index.search(query_embedding.astype(np.float32), k)

        # Filter and format results
        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue

            example_info = self.id_to_example[idx]
            example = example_info["example"]

            # Filter by database type if specified
            if database_type and example.get("database_type") != database_type:
                continue

            # Filter by minimum score
            if score < min_score:
                continue

            results.append(example)

            if len(results) >= top_k:
                break

        return results

    def _create_example_key(self, example: Dict[str, Any]) -> str:
        """Create unique key for example."""
        # Use hash of question + SQL to avoid duplicates
        content = f"{example['question']}|{example['sql']}"
        return hashlib.md5(content.encode()).hexdigest()

    async def _save_index(self) -> None:
        """Save FAISS index and metadata."""
        index_file = self.index_path / "examples_index.faiss"
        metadata_file = self.index_path / "examples_metadata.pkl"

        # Save FAISS index
        faiss.write_index(self.index, str(index_file))

        # Save metadata
        metadata = {
            "id_to_example": self.id_to_example,
            "example_to_id": self.example_to_id,
            "next_id": self._next_id,
            "saved_at": datetime.now().isoformat(),
        }
        with open(metadata_file, "wb") as f:
            pickle.dump(metadata, f)

    async def clear(self) -> None:
        """Clear the example store."""
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.id_to_example = {}
        self.example_to_id = {}
        self._next_id = 0

        # Remove saved files
        index_file = self.index_path / "examples_index.faiss"
        metadata_file = self.index_path / "examples_metadata.pkl"

        if index_file.exists():
            index_file.unlink()
        if metadata_file.exists():
            metadata_file.unlink()

        logger.info("Cleared example store")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the example store."""
        return {
            "total_examples": len(self.id_to_example),
            "embedding_dimension": self.embedding_dim,
            "provider_type": self.embedding_provider.provider_type,
        }
