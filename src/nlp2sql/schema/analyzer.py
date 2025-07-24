"""Schema analyzer for relevance scoring and analysis."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2"):
        self.embedding_model = SentenceTransformer(embedding_model)
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

    async def score_relevance(self, query: str, schema_element: Dict[str, Any]) -> float:
        """Score relevance of schema element to query."""
        element_name = schema_element.get("name", "")
        element_type = schema_element.get("type", "table")

        # Multiple scoring strategies
        scores = []
        reasons = []

        # 1. Exact match
        if element_name.lower() in query.lower():
            scores.append(1.0)
            reasons.append("Exact name match in query")

        # 2. Partial match
        query_tokens = self._tokenize(query.lower())
        element_tokens = self._tokenize(element_name.lower())

        common_tokens = set(query_tokens) & set(element_tokens)
        if common_tokens:
            score = len(common_tokens) / max(len(query_tokens), len(element_tokens))
            scores.append(score)
            reasons.append(f"Partial token match: {common_tokens}")

        # 3. Semantic similarity using embeddings
        semantic_score = await self._calculate_semantic_similarity(query, element_name, schema_element)
        if semantic_score > 0.5:
            scores.append(semantic_score)
            reasons.append(f"High semantic similarity: {semantic_score:.2f}")

        # 4. Column-based relevance for tables
        if element_type == "table" and "columns" in schema_element:
            column_scores = []
            for column in schema_element["columns"]:
                col_score = await self.score_relevance(query, {"name": column.get("name", ""), "type": "column"})
                column_scores.append(col_score)

            if column_scores:
                avg_column_score = np.mean(column_scores)
                if avg_column_score > 0.3:
                    scores.append(avg_column_score * 0.8)  # Weight columns slightly less
                    reasons.append("Relevant columns found")

        # Combine scores
        final_score = max(scores) if scores else 0.0

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
        return self.embedding_model.encode(texts, show_progress_bar=False)

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
        # Create descriptive text for element
        element_desc = f"{element_name}"
        if "description" in schema_element:
            element_desc += f" {schema_element['description']}"
        if "columns" in schema_element:
            col_names = [c.get("name", "") for c in schema_element["columns"][:5]]
            element_desc += f" with columns {', '.join(col_names)}"

        # Get embeddings
        query_embedding = await self.create_embeddings([query])
        element_embedding = await self.create_embeddings([element_desc])

        # Calculate similarity
        similarity = cosine_similarity(query_embedding, element_embedding)[0][0]
        return float(similarity)

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
