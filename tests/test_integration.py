"""Simple integration test for nlp2sql end-to-end functionality."""

import numpy as np
import pytest

from nlp2sql.core.entities import DatabaseType
from nlp2sql.schema.embedding_manager import SchemaEmbeddingManager


class MockEmbeddingProvider:
    """Mock embedding provider for testing."""

    def __init__(self):
        self.provider_type = "mock"

    def get_embedding_dimension(self):
        return 384

    async def encode(self, texts):
        """Return normalized constant embeddings."""
        embedding = np.ones((len(texts), 384), dtype=np.float32)
        norms = np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding / norms


@pytest.mark.asyncio
async def test_schema_embedding_manager():
    """Test schema embedding manager with hybrid search."""
    provider = MockEmbeddingProvider()
    manager = SchemaEmbeddingManager(database_url="sqlite:///:memory:", embedding_provider=provider)

    # Create schema elements
    elements = [
        {"type": "column", "name": "user_id", "table_name": "users", "data_type": "INTEGER"},
        {"type": "column", "name": "customer_identifier", "table_name": "customers", "data_type": "INTEGER"},
        {"type": "table", "name": "orders", "columns": [{"name": "id"}]},
    ]

    # Add elements
    await manager.add_schema_elements(elements, DatabaseType.POSTGRES)

    # Verify TF-IDF was initialized
    assert manager.tfidf_vectorizer is not None
    assert manager.tfidf_matrix is not None

    # Search for "user_id" - should prioritize exact keyword match
    results = await manager.search_similar("user_id", top_k=3, min_score=0.0)

    # The first result should be the one with name="user_id"
    assert len(results) > 0
    top_result = results[0][0]
    assert top_result["name"] == "user_id"

    # Clean up
    await manager.clear_index()
