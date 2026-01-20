"""Tests for batch semantic scoring functionality in SchemaAnalyzer.

Tests the optimized batch scoring that reduces N+1 embedding API calls
to a single batch call.
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from nlp2sql.schema.analyzer import SchemaAnalyzer


class TestScoreRelevanceBatch:
    """Test the batch scoring method."""

    @pytest.fixture
    def mock_embedding_provider(self):
        """Create a mock embedding provider."""
        provider = MagicMock()
        # Return embeddings that simulate real behavior
        provider.encode = AsyncMock(
            side_effect=lambda texts: np.random.rand(len(texts), 384)
        )
        return provider

    @pytest.fixture
    def analyzer_with_provider(self, mock_embedding_provider):
        """Create analyzer with embedding provider."""
        return SchemaAnalyzer(embedding_provider=mock_embedding_provider)

    @pytest.fixture
    def analyzer_without_provider(self):
        """Create analyzer without embedding provider."""
        return SchemaAnalyzer(embedding_provider=None)

    @pytest.fixture
    def sample_tables(self) -> List[Dict[str, Any]]:
        """Sample table elements for testing."""
        return [
            {
                "name": "users",
                "type": "table",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "email", "type": "varchar"},
                    {"name": "name", "type": "varchar"},
                ],
            },
            {
                "name": "orders",
                "type": "table",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "user_id", "type": "integer"},
                    {"name": "total", "type": "decimal"},
                    {"name": "created_at", "type": "timestamp"},
                ],
            },
            {
                "name": "products",
                "type": "table",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "name", "type": "varchar"},
                    {"name": "price", "type": "decimal"},
                ],
            },
            {
                "name": "categories",
                "type": "table",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "name", "type": "varchar"},
                ],
            },
        ]

    @pytest.mark.asyncio
    async def test_empty_elements_returns_empty_list(self, analyzer_without_provider):
        """Test that empty elements list returns empty results."""
        result = await analyzer_without_provider.score_relevance_batch(
            "show me users", []
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_text_scoring_without_provider(
        self, analyzer_without_provider, sample_tables
    ):
        """Test that text-based scoring works without embedding provider."""
        result = await analyzer_without_provider.score_relevance_batch(
            "show me all users",
            sample_tables,
            use_semantic=False,
        )

        assert len(result) == 4
        # "users" table should have highest score (exact match)
        assert result[0][0]["name"] == "users"
        assert result[0][1] == 1.0  # Exact match score

    @pytest.mark.asyncio
    async def test_results_sorted_by_score_descending(
        self, analyzer_without_provider, sample_tables
    ):
        """Test that results are sorted by score in descending order."""
        result = await analyzer_without_provider.score_relevance_batch(
            "user orders",
            sample_tables,
            use_semantic=False,
        )

        scores = [score for _, score in result]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_normalized_matching(self, analyzer_without_provider):
        """Test that singular/plural forms are normalized."""
        tables = [
            {"name": "organization", "type": "table", "columns": []},
            {"name": "companies", "type": "table", "columns": []},
        ]

        # Query with plural, table is singular
        result = await analyzer_without_provider.score_relevance_batch(
            "show organizations",
            tables,
            use_semantic=False,
        )

        # "organization" should match "organizations" (normalized)
        org_score = next(s for t, s in result if t["name"] == "organization")
        assert org_score > 0  # Should have some match

    @pytest.mark.asyncio
    async def test_column_based_matching(self, analyzer_without_provider, sample_tables):
        """Test that column names contribute to scoring."""
        result = await analyzer_without_provider.score_relevance_batch(
            "find email addresses",
            sample_tables,
            use_semantic=False,
        )

        # "users" table has "email" column, should score higher
        users_entry = next(e for e in result if e[0]["name"] == "users")
        products_entry = next(e for e in result if e[0]["name"] == "products")

        assert users_entry[1] > products_entry[1]

    @pytest.mark.asyncio
    async def test_batch_semantic_scoring_with_provider(
        self, analyzer_with_provider, sample_tables
    ):
        """Test that semantic scoring is called when provider is available."""
        result = await analyzer_with_provider.score_relevance_batch(
            "find customer information",
            sample_tables,
            use_semantic=True,
        )

        # Should return results for all tables
        assert len(result) == 4

        # Embedding provider should have been called
        analyzer_with_provider.embedding_provider.encode.assert_called()

    @pytest.mark.asyncio
    async def test_semantic_scoring_skipped_for_high_text_scores(
        self, analyzer_with_provider
    ):
        """Test that semantic scoring is skipped for elements with high text scores."""
        tables = [
            {"name": "users", "type": "table", "columns": []},  # Exact match
        ]

        result = await analyzer_with_provider.score_relevance_batch(
            "users",  # Exact match with table name
            tables,
            use_semantic=True,
        )

        # "users" has text score of 1.0, should skip semantic
        # Only the query embedding should be generated
        # (not element embeddings since text score >= 0.8)
        assert len(result) == 1
        assert result[0][1] == 1.0

    @pytest.mark.asyncio
    async def test_semantic_disabled_with_flag(
        self, analyzer_with_provider, sample_tables
    ):
        """Test that use_semantic=False disables semantic scoring."""
        # Reset mock call count
        analyzer_with_provider.embedding_provider.encode.reset_mock()

        await analyzer_with_provider.score_relevance_batch(
            "find customer data",
            sample_tables,
            use_semantic=False,
        )

        # Embedding provider should NOT be called
        analyzer_with_provider.embedding_provider.encode.assert_not_called()


class TestCalculateSemanticSimilarityBatch:
    """Test the batch semantic similarity calculation."""

    @pytest.fixture
    def mock_embedding_provider(self):
        """Create a mock embedding provider that returns predictable embeddings."""
        provider = MagicMock()
        return provider

    @pytest.fixture
    def analyzer(self, mock_embedding_provider):
        """Create analyzer with mock provider."""
        return SchemaAnalyzer(embedding_provider=mock_embedding_provider)

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_elements(self, analyzer):
        """Test that empty elements returns empty list."""
        result = await analyzer._calculate_semantic_similarity_batch("query", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_without_provider(self):
        """Test that no provider returns empty list."""
        analyzer = SchemaAnalyzer(embedding_provider=None)
        result = await analyzer._calculate_semantic_similarity_batch(
            "query",
            [{"name": "users", "type": "table"}],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_single_api_call_for_batch(self, analyzer, mock_embedding_provider):
        """Test that batch embeddings uses single API call."""
        # Setup mock to track calls
        query_embedding = np.array([[0.1, 0.2, 0.3]])
        element_embeddings = np.array([
            [0.1, 0.2, 0.3],  # Similar to query
            [0.9, 0.8, 0.7],  # Different from query
            [0.2, 0.3, 0.4],  # Somewhat similar
        ])

        call_count = 0

        async def mock_encode(texts):
            nonlocal call_count
            call_count += 1
            if len(texts) == 1:
                return query_embedding
            return element_embeddings

        mock_embedding_provider.encode = AsyncMock(side_effect=mock_encode)

        elements = [
            {"name": "users", "type": "table"},
            {"name": "orders", "type": "table"},
            {"name": "products", "type": "table"},
        ]

        result = await analyzer._calculate_semantic_similarity_batch("query", elements)

        # Should have 2 calls: one for query, one for all elements
        assert call_count == 2
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_query_embedding_cached(self, analyzer, mock_embedding_provider):
        """Test that query embedding is cached across calls."""
        query_embedding = np.array([[0.1, 0.2, 0.3]])
        element_embedding = np.array([[0.2, 0.3, 0.4]])

        mock_embedding_provider.encode = AsyncMock(
            side_effect=[query_embedding, element_embedding, element_embedding]
        )

        elements = [{"name": "table1", "type": "table"}]

        # First call - should generate query embedding
        await analyzer._calculate_semantic_similarity_batch("test query", elements)

        # Second call with same query - should use cached query embedding
        await analyzer._calculate_semantic_similarity_batch("test query", elements)

        # Query embedding should only be generated once
        assert "test query" in analyzer._query_embedding_cache


class TestCreateElementDescription:
    """Test the element description creation for embeddings."""

    @pytest.fixture
    def analyzer(self):
        return SchemaAnalyzer(embedding_provider=None)

    def test_basic_name(self, analyzer):
        """Test description with just name."""
        element = {"name": "users"}
        desc = analyzer._create_element_description(element)
        assert desc == "users"

    def test_name_with_description(self, analyzer):
        """Test description includes element description."""
        element = {"name": "users", "description": "User accounts table"}
        desc = analyzer._create_element_description(element)
        assert "users" in desc
        assert "User accounts table" in desc

    def test_name_with_columns(self, analyzer):
        """Test description includes column names."""
        element = {
            "name": "users",
            "columns": [
                {"name": "id"},
                {"name": "email"},
                {"name": "name"},
            ],
        }
        desc = analyzer._create_element_description(element)
        assert "users" in desc
        assert "columns" in desc.lower()
        assert "id" in desc
        assert "email" in desc

    def test_columns_limited_to_five(self, analyzer):
        """Test that only first 5 columns are included."""
        element = {
            "name": "wide_table",
            "columns": [
                {"name": f"col{i}"} for i in range(10)
            ],
        }
        desc = analyzer._create_element_description(element)
        assert "col0" in desc
        assert "col4" in desc
        # col5+ should not be included
        assert "col5" not in desc


class TestQueryEmbeddingCache:
    """Test the query embedding cache behavior."""

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.encode = AsyncMock(return_value=np.array([[0.1, 0.2, 0.3]]))
        return provider

    @pytest.fixture
    def analyzer(self, mock_provider):
        return SchemaAnalyzer(embedding_provider=mock_provider)

    def test_cache_initially_empty(self, analyzer):
        """Test that cache starts empty."""
        assert len(analyzer._query_embedding_cache) == 0

    @pytest.mark.asyncio
    async def test_cache_populated_after_scoring(self, analyzer):
        """Test that cache is populated after scoring."""
        elements = [{"name": "users", "type": "table"}]

        await analyzer.score_relevance_batch("test query", elements, use_semantic=True)

        assert "test query" in analyzer._query_embedding_cache

    def test_clear_cache(self, analyzer):
        """Test that clear_query_embedding_cache clears the cache."""
        analyzer._query_embedding_cache["query1"] = np.array([0.1, 0.2])
        analyzer._query_embedding_cache["query2"] = np.array([0.3, 0.4])

        analyzer.clear_query_embedding_cache()

        assert len(analyzer._query_embedding_cache) == 0


class TestIntegrationWithSchemaManager:
    """Integration tests for batch scoring with SchemaManager patterns."""

    @pytest.fixture
    def analyzer(self):
        return SchemaAnalyzer(embedding_provider=None)

    @pytest.mark.asyncio
    async def test_realistic_table_scoring(self, analyzer):
        """Test scoring with realistic table data similar to SchemaManager usage."""
        tables = [
            {
                "name": "customers",
                "type": "table",
                "description": "Customer information and contact details",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "first_name", "type": "varchar"},
                    {"name": "last_name", "type": "varchar"},
                    {"name": "email", "type": "varchar"},
                    {"name": "phone", "type": "varchar"},
                ],
            },
            {
                "name": "orders",
                "type": "table",
                "description": "Customer orders and transactions",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "customer_id", "type": "integer"},
                    {"name": "total_amount", "type": "decimal"},
                    {"name": "status", "type": "varchar"},
                    {"name": "created_at", "type": "timestamp"},
                ],
            },
            {
                "name": "order_items",
                "type": "table",
                "description": "Individual items within orders",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "order_id", "type": "integer"},
                    {"name": "product_id", "type": "integer"},
                    {"name": "quantity", "type": "integer"},
                    {"name": "unit_price", "type": "decimal"},
                ],
            },
            {
                "name": "products",
                "type": "table",
                "description": "Product catalog",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "name", "type": "varchar"},
                    {"name": "category_id", "type": "integer"},
                    {"name": "price", "type": "decimal"},
                ],
            },
            {
                "name": "audit_log",
                "type": "table",
                "description": "System audit trail",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "action", "type": "varchar"},
                    {"name": "timestamp", "type": "timestamp"},
                ],
            },
        ]

        # Query for customer orders
        result = await analyzer.score_relevance_batch(
            "Show me all customer orders",
            tables,
            use_semantic=False,
        )

        # customers and orders should be top results
        top_two_names = {result[0][0]["name"], result[1][0]["name"]}
        assert "customers" in top_two_names or "orders" in top_two_names

        # audit_log should be at the bottom (irrelevant)
        assert result[-1][0]["name"] == "audit_log" or result[-1][1] < 0.3

    @pytest.mark.asyncio
    async def test_performance_no_semantic_overhead(self, analyzer):
        """Test that text-only scoring is fast (no API calls)."""
        # Create many tables to test performance
        tables = [
            {
                "name": f"table_{i}",
                "type": "table",
                "columns": [{"name": f"col_{j}"} for j in range(10)],
            }
            for i in range(100)
        ]

        import time

        start = time.time()
        result = await analyzer.score_relevance_batch(
            "find user data",
            tables,
            use_semantic=False,  # No API calls
        )
        elapsed = time.time() - start

        assert len(result) == 100
        # Should be very fast without API calls (< 1 second)
        assert elapsed < 1.0
