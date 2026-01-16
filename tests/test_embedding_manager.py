"""Tests for SchemaEmbeddingManager, particularly edge cases and bug fixes."""

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nlp2sql.core.entities import DatabaseType
from nlp2sql.schema.embedding_manager import SchemaEmbeddingManager


class MockEmbeddingProvider:
    """Mock embedding provider for testing."""

    def __init__(self, dimension: int = 384, fail_on_encode: bool = False, return_empty: bool = False):
        self.dimension = dimension
        self.fail_on_encode = fail_on_encode
        self.return_empty = return_empty
        self.encode_calls = []

    async def encode(self, texts: list[str]) -> np.ndarray:
        """Mock encode that can simulate failures."""
        self.encode_calls.append(texts)

        if self.fail_on_encode:
            raise Exception("Simulated encoding failure")

        if self.return_empty:
            return np.array([]).reshape(0, self.dimension)

        # Return valid embeddings
        embeddings = np.random.randn(len(texts), self.dimension).astype(np.float32)
        # Normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / norms

    def get_embedding_dimension(self) -> int:
        return self.dimension

    @property
    def provider_type(self) -> str:
        return "mock"


class TestOrphanMappingsPrevention:
    """Tests for Issue 12: Orphan mappings on early return in add_schema_elements.

    This test class verifies that mappings (id_to_schema, schema_to_id) are NOT
    stored when embedding generation fails, preventing desynchronization between
    mappings and the FAISS index.
    """

    @pytest.fixture
    def temp_index_path(self, tmp_path):
        """Create a temporary path for test indices."""
        return tmp_path / "test_embeddings"

    @pytest.mark.asyncio
    async def test_no_orphan_mappings_when_embeddings_empty(self, temp_index_path):
        """Test that no mappings are created when embedding provider returns empty array.

        This is the core test for Issue 12: if embeddings.size == 0, we should
        return early WITHOUT having stored any mappings.
        """
        # Create provider that returns empty embeddings
        provider = MockEmbeddingProvider(return_empty=True)

        manager = SchemaEmbeddingManager(
            database_url="postgresql://test:test@localhost/test",
            embedding_provider=provider,
            index_path=temp_index_path,
        )

        # Verify initial state
        assert len(manager.id_to_schema) == 0
        assert len(manager.schema_to_id) == 0
        initial_next_id = manager._next_id

        # Try to add elements
        elements = [
            {"type": "table", "name": "users", "columns": [{"name": "id"}]},
            {"type": "table", "name": "orders", "columns": [{"name": "id"}]},
        ]

        await manager.add_schema_elements(elements, DatabaseType.POSTGRES)

        # CRITICAL: No mappings should be stored since embeddings were empty
        assert len(manager.id_to_schema) == 0, "Orphan mappings detected in id_to_schema"
        assert len(manager.schema_to_id) == 0, "Orphan mappings detected in schema_to_id"
        assert manager._next_id == initial_next_id, "_next_id should not have incremented"

        # Verify encode was called
        assert len(provider.encode_calls) == 1

    @pytest.mark.asyncio
    async def test_no_orphan_mappings_when_embedding_count_mismatch(self, temp_index_path):
        """Test that no mappings are created when embedding count doesn't match elements.

        This tests the second validation check in add_schema_elements.
        """

        class MismatchProvider(MockEmbeddingProvider):
            """Provider that returns wrong number of embeddings."""

            async def encode(self, texts: list[str]) -> np.ndarray:
                self.encode_calls.append(texts)
                # Return fewer embeddings than requested
                return np.random.randn(1, self.dimension).astype(np.float32)

        provider = MismatchProvider()

        manager = SchemaEmbeddingManager(
            database_url="postgresql://test:test@localhost/test",
            embedding_provider=provider,
            index_path=temp_index_path,
        )

        # Verify initial state
        assert len(manager.id_to_schema) == 0
        assert len(manager.schema_to_id) == 0

        # Try to add multiple elements
        elements = [
            {"type": "table", "name": "users", "columns": [{"name": "id"}]},
            {"type": "table", "name": "orders", "columns": [{"name": "id"}]},
            {"type": "table", "name": "products", "columns": [{"name": "id"}]},
        ]

        await manager.add_schema_elements(elements, DatabaseType.POSTGRES)

        # CRITICAL: No mappings should be stored since embedding count mismatched
        assert len(manager.id_to_schema) == 0, "Orphan mappings detected in id_to_schema"
        assert len(manager.schema_to_id) == 0, "Orphan mappings detected in schema_to_id"

    @pytest.mark.asyncio
    async def test_mappings_created_on_success(self, temp_index_path):
        """Test that mappings ARE created when everything succeeds."""
        provider = MockEmbeddingProvider()

        manager = SchemaEmbeddingManager(
            database_url="postgresql://test:test@localhost/test",
            embedding_provider=provider,
            index_path=temp_index_path,
        )

        elements = [
            {"type": "table", "name": "users", "columns": [{"name": "id"}]},
            {"type": "table", "name": "orders", "columns": [{"name": "id"}]},
        ]

        await manager.add_schema_elements(elements, DatabaseType.POSTGRES)

        # Mappings should be created
        assert len(manager.id_to_schema) == 2
        assert len(manager.schema_to_id) == 2

        # FAISS index should have the same count
        assert manager.index.ntotal == 2

        # Verify consistency: mapping IDs should be valid FAISS indices
        for faiss_id in manager.id_to_schema.keys():
            assert faiss_id < manager.index.ntotal, f"Mapping ID {faiss_id} exceeds FAISS index size"

    @pytest.mark.asyncio
    async def test_faiss_index_mapping_consistency(self, temp_index_path):
        """Test that FAISS index and mappings stay synchronized."""
        provider = MockEmbeddingProvider()

        manager = SchemaEmbeddingManager(
            database_url="postgresql://test:test@localhost/test",
            embedding_provider=provider,
            index_path=temp_index_path,
        )

        # Add first batch
        elements1 = [{"type": "table", "name": "users", "columns": [{"name": "id"}]}]
        await manager.add_schema_elements(elements1, DatabaseType.POSTGRES)

        assert manager.index.ntotal == 1
        assert len(manager.id_to_schema) == 1

        # Add second batch
        elements2 = [{"type": "table", "name": "orders", "columns": [{"name": "id"}]}]
        await manager.add_schema_elements(elements2, DatabaseType.POSTGRES)

        assert manager.index.ntotal == 2
        assert len(manager.id_to_schema) == 2

        # All mapping IDs should be valid FAISS indices
        for faiss_id in manager.id_to_schema.keys():
            # Should be able to reconstruct without error
            embedding = manager.index.reconstruct(faiss_id)
            assert embedding.shape == (provider.dimension,)


class TestEmbeddingManagerWithoutProvider:
    """Tests for SchemaEmbeddingManager when no provider is configured."""

    @pytest.fixture
    def temp_index_path(self, tmp_path):
        return tmp_path / "test_embeddings"

    @pytest.mark.asyncio
    async def test_graceful_handling_without_provider(self, temp_index_path):
        """Test that manager works without embedding provider."""
        manager = SchemaEmbeddingManager(
            database_url="postgresql://test:test@localhost/test",
            embedding_provider=None,
            index_path=temp_index_path,
        )

        # Should not raise
        elements = [{"type": "table", "name": "users", "columns": [{"name": "id"}]}]
        await manager.add_schema_elements(elements, DatabaseType.POSTGRES)

        # search_similar should return empty
        results = await manager.search_similar("users")
        assert results == []
