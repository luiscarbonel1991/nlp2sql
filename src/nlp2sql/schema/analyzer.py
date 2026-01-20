"""Schema analyzer for relevance scoring and analysis."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..ports.embedding_provider import EmbeddingProviderPort
from ..ports.schema_strategy import SchemaChunk, SchemaContext, SchemaStrategyPort

logger = structlog.get_logger()


@dataclass
class RelevanceScore:
    """Relevance score for a schema element."""

    element_name: str
    element_type: str  # table, column
    score: float
    reasons: List[str]
    metadata: Optional[Dict[str, Any]] = None


class SchemaAnalyzer(SchemaStrategyPort):
    """Analyzes and scores schema elements for relevance."""

    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProviderPort] = None,
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        """
        Initialize schema analyzer.

        Args:
            embedding_provider: Optional embedding provider. If None, semantic similarity
                will be disabled but text-based matching will still work.
            embedding_model: Unused, kept for API compatibility.

        Note:
            The analyzer works without an embedding provider, but semantic similarity
            scoring will be disabled. For best results, provide an embedding provider.
        """
        self.embedding_provider = embedding_provider
        # Cache for query embeddings to avoid redundant API calls during relevance scoring
        # Key: query string, Value: embedding array
        self._query_embedding_cache: Dict[str, np.ndarray] = {}

        if embedding_provider is None:
            logger.info(
                "SchemaAnalyzer initialized without embedding provider. "
                "Semantic similarity scoring will be disabled. "
                "Text-based matching (exact, partial, token) will still work."
            )

        self.tfidf_vectorizer = TfidfVectorizer(ngram_range=(1, 3), stop_words="english", max_features=10000)
        self._schema_embeddings = {}
        self._schema_descriptions = {}

    async def chunk_schema(self, tables: List[Dict[str, Any]], max_chunk_size: int) -> List[SchemaChunk]:
        """Split schema into manageable chunks based on token count."""
        chunks = []
        current_chunk = []
        current_tokens = 0

        # Sort tables by estimated relevance (larger tables first)
        sorted_tables = sorted(tables, key=lambda t: len(t.get("columns", [])), reverse=True)

        for table in sorted_tables:
            table_tokens = self._estimate_tokens(table)

            if current_tokens + table_tokens > max_chunk_size and current_chunk:
                # Create chunk
                chunks.append(
                    SchemaChunk(
                        tables=[t["name"] for t in current_chunk],
                        token_count=current_tokens,
                        relevance_score=1.0,  # Will be updated based on query
                        metadata={"table_count": len(current_chunk)},
                    )
                )
                current_chunk = [table]
                current_tokens = table_tokens
            else:
                current_chunk.append(table)
                current_tokens += table_tokens

        # Add remaining tables
        if current_chunk:
            chunks.append(
                SchemaChunk(
                    tables=[t["name"] for t in current_chunk],
                    token_count=current_tokens,
                    relevance_score=1.0,
                    metadata={"table_count": len(current_chunk)},
                )
            )

        logger.info("Schema chunked", chunks=len(chunks), total_tables=len(tables))
        return chunks

    async def score_relevance(
        self,
        query: str,
        schema_element: Dict[str, Any],
        use_semantic: bool = True,
    ) -> float:
        """
        Score relevance of schema element to query.

        Args:
            query: The search query
            schema_element: Schema element to score
            use_semantic: Whether to use semantic similarity via embeddings (default: True)

        Returns:
            Relevance score between 0 and 1
        """
        element_name = schema_element.get("name", "")
        element_type = schema_element.get("type", "table")

        # Multiple scoring strategies
        scores = []
        reasons = []

        query_lower = query.lower()
        element_name_lower = element_name.lower()

        # 1. Exact match (fast) - check both exact substring and normalized forms
        # Check exact substring match first
        if element_name_lower in query_lower:
            scores.append(1.0)
            reasons.append("Exact name match in query")
        else:
            # Check normalized forms for singular/plural matching
            normalized_element = self._normalize_word(element_name_lower)
            normalized_query = self._normalize_word(query_lower)

            # Check if normalized element name is in normalized query
            if normalized_element in normalized_query and len(normalized_element) >= 3:
                scores.append(1.0)
                reasons.append(f"Exact name match (normalized): {element_name_lower} -> {normalized_element}")
            # Also check if normalized query contains the element (for cases like "organization" in "organizations")
            elif normalized_element in query_lower or element_name_lower in normalized_query:
                scores.append(1.0)
                reasons.append(f"Exact name match (cross-normalized): {element_name_lower}")

        # 2. Partial match (fast) - with normalization for singular/plural
        query_tokens = self._tokenize(query_lower)
        element_tokens = self._tokenize(element_name_lower)

        # Normalize tokens for better matching (handles singular/plural)
        normalized_query_tokens = {self._normalize_word(t) for t in query_tokens}
        normalized_element_tokens = {self._normalize_word(t) for t in element_tokens}

        # Check both exact token match and normalized token match
        common_tokens = set(query_tokens) & set(element_tokens)
        common_normalized_tokens = normalized_query_tokens & normalized_element_tokens

        if common_tokens or common_normalized_tokens:
            # Use the better match (exact tokens are preferred, but normalized also counts)
            match_count = max(len(common_tokens), len(common_normalized_tokens))
            score = match_count / max(len(query_tokens), len(element_tokens))
            scores.append(score)
            if common_normalized_tokens and not common_tokens:
                reasons.append(f"Partial token match (normalized): {common_normalized_tokens}")
            else:
                reasons.append(f"Partial token match: {common_tokens}")

        # 3. Semantic similarity using embeddings (expensive - only when explicitly requested)
        if use_semantic:
            semantic_score = await self._calculate_semantic_similarity(query, element_name, schema_element)
            if semantic_score > 0.5:
                scores.append(semantic_score)
                reasons.append(f"High semantic similarity: {semantic_score:.2f}")

        # 4. Column-based relevance for tables (optimized - no recursion)
        if element_type == "table" and "columns" in schema_element:
            column_matches = 0
            columns_to_check = schema_element["columns"][:15]  # Limit to first 15 columns

            for column in columns_to_check:
                col_name = column.get("name", "").lower()
                # Fast token matching without recursion
                if col_name in query_lower:
                    column_matches += 2  # Exact match worth more
                elif any(token in col_name for token in query_tokens):
                    column_matches += 1

            if column_matches > 0:
                column_score = min(column_matches / len(columns_to_check), 1.0) * 0.8
                if column_score > 0.2:
                    scores.append(column_score)
                    reasons.append(f"Relevant columns found ({column_matches} matches)")

        # Combine scores
        final_score = max(scores) if scores else 0.0

        # Only log significant scores to reduce overhead
        if final_score > 0.3:
            logger.debug("Relevance scored", element=element_name, score=final_score, reasons=reasons)

        return final_score

    async def compress_schema(self, schema: Dict[str, Any], target_tokens: int) -> str:
        """Compress schema information to fit token limit."""
        compressed = []
        current_tokens = 0

        # Prioritize most important information
        for table_name, table_info in schema.items():
            if current_tokens >= target_tokens:
                break

            # Basic table info
            table_desc = f"Table: {table_name}"

            # Add primary keys
            if "primary_keys" in table_info:
                table_desc += f" (PK: {', '.join(table_info['primary_keys'])})"

            # Add most important columns
            if "columns" in table_info:
                important_cols = self._get_important_columns(table_info["columns"])
                col_info = []

                for col in important_cols[:10]:  # Limit columns
                    col_str = f"{col['name']}:{col['type']}"
                    if col.get("nullable", True):
                        col_str += "?"
                    col_info.append(col_str)

                table_desc += f"\n  Columns: {', '.join(col_info)}"

            # Add foreign keys (compressed)
            if table_info.get("foreign_keys"):
                fk_info = []
                for fk in table_info["foreign_keys"][:3]:  # Limit FKs
                    fk_info.append(f"{fk['column']}->{fk['ref_table']}")
                table_desc += f"\n  FK: {', '.join(fk_info)}"

            desc_tokens = self._estimate_tokens({"description": table_desc})
            if current_tokens + desc_tokens <= target_tokens:
                compressed.append(table_desc)
                current_tokens += desc_tokens

        return "\n\n".join(compressed)

    async def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """Create embeddings for schema elements."""
        if self.embedding_provider is None:
            # Return empty array if no provider
            return np.array([])
        return await self.embedding_provider.encode(texts)

    def clear_query_embedding_cache(self) -> None:
        """Clear the query embedding cache.

        Call this between requests to prevent unbounded memory growth
        while still benefiting from per-request caching.
        """
        self._query_embedding_cache.clear()

    async def find_similar_schemas(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """Find similar schema elements using embeddings."""
        if not self._schema_embeddings:
            return []

        # Calculate similarities
        schema_names = list(self._schema_embeddings.keys())
        schema_embeddings = np.array([self._schema_embeddings[name] for name in schema_names])

        similarities = cosine_similarity([query_embedding], schema_embeddings)[0]

        # Get top-k
        top_indices = np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            if similarities[idx] > 0.3:  # Threshold
                results.append((schema_names[idx], float(similarities[idx])))

        return results

    async def build_context(self, context: SchemaContext, tables: List[Dict[str, Any]]) -> str:
        """Build optimized schema context for query."""
        # Score all tables
        table_scores = []
        for table in tables:
            score = await self.score_relevance(context.query, table)
            table_scores.append((table, score))

        # Sort by relevance
        table_scores.sort(key=lambda x: x[1], reverse=True)

        # Build context within token limit
        context_parts = []
        current_tokens = 0

        # Add database type hint
        context_parts.append(f"Database Type: {context.database_type}")
        current_tokens += 10

        # Add relevant tables
        for table, score in table_scores:
            if score < 0.2:  # Relevance threshold
                continue

            table_context = self._build_table_context(table, context)
            table_tokens = self._estimate_tokens({"text": table_context})

            if current_tokens + table_tokens <= context.max_tokens:
                context_parts.append(table_context)
                current_tokens += table_tokens
            else:
                # Try compressed version
                compressed = self._build_compressed_table_context(table)
                compressed_tokens = self._estimate_tokens({"text": compressed})
                if current_tokens + compressed_tokens <= context.max_tokens:
                    context_parts.append(compressed)
                    current_tokens += compressed_tokens
                else:
                    break

        return "\n\n".join(context_parts)

    def _estimate_tokens(self, element: Dict[str, Any]) -> int:
        """Estimate token count for an element."""
        text = str(element)
        # Rough estimation: ~4 characters per token
        return len(text) // 4

    def _normalize_word(self, word: str) -> str:
        """
        Normalize word by removing common plural endings to match singular/plural forms.

        Examples:
            "organizations" -> "organization"
            "companies" -> "compani" -> "company" (handled by common patterns)
            "categories" -> "categori" -> "category"
        """
        word_lower = word.lower().strip()

        # Common plural patterns (order matters - check longer patterns first)
        plural_patterns = [
            ("ies", "y"),  # categories -> category
            ("es", ""),  # boxes -> box, organizations -> organization
            ("s", ""),  # organizations -> organization, users -> user
        ]

        for plural_end, singular_end in plural_patterns:
            if word_lower.endswith(plural_end) and len(word_lower) > len(plural_end) + 2:
                # Only remove plural if word is long enough (avoid removing 's' from 'is', 'as', etc.)
                normalized = word_lower[: -len(plural_end)] + singular_end
                return normalized

        return word_lower

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text for matching."""
        # Split on non-alphanumeric, convert to lowercase
        tokens = re.findall(r"\w+", text.lower())
        # Handle snake_case and camelCase
        expanded_tokens = []
        for token in tokens:
            # Snake case
            expanded_tokens.extend(token.split("_"))
            # Camel case
            expanded_tokens.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", token))

        return [t.lower() for t in expanded_tokens if t]

    async def _calculate_semantic_similarity(
        self, query: str, element_name: str, schema_element: Dict[str, Any]
    ) -> float:
        """Calculate semantic similarity using embeddings."""
        # Return 0 if no embedding provider
        if self.embedding_provider is None:
            return 0.0

        # Create descriptive text for element
        element_desc = self._create_element_description(schema_element)

        # Get query embedding from cache or generate it (avoids N+1 API calls)
        if query not in self._query_embedding_cache:
            self._query_embedding_cache[query] = await self.create_embeddings([query])
        query_embedding = self._query_embedding_cache[query]

        # Get element embedding
        element_embedding = await self.create_embeddings([element_desc])

        # Check if embeddings are valid
        if query_embedding.size == 0 or element_embedding.size == 0:
            return 0.0

        # Calculate similarity
        similarity = cosine_similarity(query_embedding, element_embedding)[0][0]
        return float(similarity)

    def _create_element_description(self, element: Dict[str, Any]) -> str:
        """Create descriptive text for embedding.

        Creates a rich text description of a schema element that captures
        its name, description, and column information for semantic matching.
        """
        name = element.get("name", "")
        desc = f"{name}"

        if element.get("description"):
            desc += f" {element['description']}"

        if "columns" in element:
            col_names = [c.get("name", "") for c in element["columns"][:5]]
            if col_names:
                desc += f" with columns {', '.join(col_names)}"

        return desc

    async def score_relevance_batch(
        self,
        query: str,
        schema_elements: List[Dict[str, Any]],
        use_semantic: bool = True,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Score relevance of multiple schema elements in a single batch.

        This is more efficient than calling score_relevance() in a loop
        because it batches embedding API calls into a single request.

        Args:
            query: The search query
            schema_elements: List of schema elements to score
            use_semantic: Whether to use semantic similarity

        Returns:
            List of (element, score) tuples sorted by score descending
        """
        if not schema_elements:
            return []

        # Step 1: Fast text-based scoring for all elements (no API calls)
        text_scores: Dict[str, float] = {}
        query_lower = query.lower()
        query_tokens = self._tokenize(query_lower)
        normalized_query_tokens = {self._normalize_word(t) for t in query_tokens}

        for element in schema_elements:
            element_name = element.get("name", "")
            element_name_lower = element_name.lower()

            # Calculate text score (same logic as score_relevance)
            score = 0.0

            # Exact match
            normalized_element = self._normalize_word(element_name_lower)
            if element_name_lower in query_lower or normalized_element in query_lower:
                score = 1.0
            else:
                # Token match
                element_tokens = self._tokenize(element_name_lower)
                normalized_element_tokens = {self._normalize_word(t) for t in element_tokens}
                common_tokens = set(query_tokens) & set(element_tokens)
                common_normalized = normalized_query_tokens & normalized_element_tokens

                if common_tokens or common_normalized:
                    match_count = max(len(common_tokens), len(common_normalized))
                    score = match_count / max(len(query_tokens), len(element_tokens))

            # Column-based relevance for tables
            if element.get("type") == "table" and "columns" in element:
                column_matches = 0
                columns_to_check = element["columns"][:15]
                for column in columns_to_check:
                    col_name = column.get("name", "").lower()
                    if col_name in query_lower:
                        column_matches += 2
                    elif any(token in col_name for token in query_tokens):
                        column_matches += 1
                if column_matches > 0:
                    column_score = min(column_matches / len(columns_to_check), 1.0) * 0.8
                    score = max(score, column_score)

            text_scores[element_name] = score

        # Step 2: Batch semantic scoring (single API call) for elements that need it
        if use_semantic and self.embedding_provider is not None:
            # Filter elements that need semantic scoring (text score < 0.8)
            elements_for_semantic = [
                e for e in schema_elements
                if text_scores.get(e.get("name", ""), 0) < 0.8
            ]

            if elements_for_semantic:
                semantic_scores = await self._calculate_semantic_similarity_batch(
                    query, elements_for_semantic
                )
                # Merge scores (take max of text and semantic)
                for element, sem_score in semantic_scores:
                    name = element.get("name", "")
                    text_scores[name] = max(text_scores.get(name, 0), sem_score)

        # Step 3: Build results
        results = []
        for element in schema_elements:
            score = text_scores.get(element.get("name", ""), 0)
            results.append((element, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    async def _calculate_semantic_similarity_batch(
        self,
        query: str,
        elements: List[Dict[str, Any]],
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Calculate semantic similarity for multiple elements in one API call.

        Args:
            query: The search query
            elements: List of schema elements

        Returns:
            List of (element, similarity_score) tuples
        """
        if not elements or self.embedding_provider is None:
            return []

        # Step 1: Create descriptions for all elements
        descriptions = []
        for element in elements:
            desc = self._create_element_description(element)
            descriptions.append(desc)

        # Step 2: Get query embedding (cached)
        if query not in self._query_embedding_cache:
            self._query_embedding_cache[query] = await self.create_embeddings([query])
        query_embedding = self._query_embedding_cache[query]

        if query_embedding.size == 0:
            return []

        # Step 3: Batch embed all element descriptions (SINGLE API CALL)
        logger.debug("Batch embedding elements", count=len(descriptions))
        element_embeddings = await self.create_embeddings(descriptions)

        if element_embeddings.size == 0:
            return []

        # Step 4: Calculate all similarities in memory (vectorized)
        results = []
        # Handle both 1D and 2D embeddings
        if len(element_embeddings.shape) == 1:
            # Single embedding returned
            similarity = cosine_similarity(
                query_embedding.reshape(1, -1),
                element_embeddings.reshape(1, -1)
            )[0][0]
            if len(elements) == 1:
                results.append((elements[0], float(similarity)))
        else:
            # Multiple embeddings - use batch similarity calculation
            similarities = cosine_similarity(
                query_embedding.reshape(1, -1),
                element_embeddings
            )[0]
            for i, element in enumerate(elements):
                if i < len(similarities):
                    results.append((element, float(similarities[i])))

        return results

    def _get_important_columns(self, columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify important columns based on heuristics."""
        important = []

        # Priority patterns
        priority_patterns = ["id", "name", "date", "amount", "total", "count", "status", "type"]

        # First add primary keys and foreign keys
        for col in columns:
            if col.get("is_primary_key") or col.get("is_foreign_key"):
                important.append(col)

        # Then add columns matching priority patterns
        for col in columns:
            if col in important:
                continue
            col_name = col.get("name", "").lower()
            if any(pattern in col_name for pattern in priority_patterns):
                important.append(col)

        # Finally add remaining columns up to limit
        for col in columns:
            if col not in important:
                important.append(col)
            if len(important) >= 15:
                break

        return important

    def _build_table_context(self, table: Dict[str, Any], context: SchemaContext) -> str:
        """Build context for a single table."""
        parts = [f"Table: {table['name']}"]

        if "description" in table:
            parts.append(f"Description: {table['description']}")

        # Columns
        if "columns" in table:
            col_defs = []
            for col in table["columns"]:
                col_def = f"  - {col['name']} {col['type']}"
                if col.get("nullable", True):
                    col_def += " NULL"
                else:
                    col_def += " NOT NULL"
                if col.get("is_primary_key"):
                    col_def += " PRIMARY KEY"
                if col.get("is_foreign_key"):
                    col_def += " FOREIGN KEY"
                col_defs.append(col_def)
            parts.append("Columns:\n" + "\n".join(col_defs))

        # Relationships
        if table.get("foreign_keys"):
            fk_defs = []
            for fk in table["foreign_keys"]:
                fk_defs.append(f"  - {fk['column']} -> {fk['ref_table']}.{fk['ref_column']}")
            parts.append("Foreign Keys:\n" + "\n".join(fk_defs))

        # Sample data if requested
        if context.include_samples and "sample_data" in table:
            parts.append(f"Sample Data: {table['sample_data'][:3]}")

        return "\n".join(parts)

    def _build_compressed_table_context(self, table: Dict[str, Any]) -> str:
        """Build compressed context for a table."""
        name = table["name"]
        cols = []

        if "columns" in table:
            important_cols = self._get_important_columns(table["columns"])
            for col in important_cols[:8]:  # Limit to 8 columns
                col_str = f"{col['name']}:{col['type'][:3]}"  # Abbreviate type
                if col.get("is_primary_key"):
                    col_str += "*"
                if col.get("is_foreign_key"):
                    col_str += "→"
                cols.append(col_str)

        return f"{name}({', '.join(cols)})"
