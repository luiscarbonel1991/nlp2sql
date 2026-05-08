"""pgvector-backed implementation of ExampleRepositoryPort.

Stores few-shot examples in Postgres using the pgvector extension instead of a
local FAISS index on disk. Behavior mirrors ``ExampleStore`` (metadata
enrichment, rich embedding text, per-database namespace isolation) so both
adapters return comparable results for the same inputs.

Uses psycopg2 with ``asyncio.to_thread()`` wrappers to match the event-loop-safe
pattern adopted by ``PostgreSQLRepository``.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any

import numpy as np
import psycopg2
import structlog
from psycopg2 import sql as psycopg2_sql
from psycopg2.extras import Json, RealDictCursor, execute_values

from ..exceptions import SchemaException
from ..ports.embedding_provider import EmbeddingProviderPort
from ..ports.example_repository import ExampleRepositoryPort

try:
    from pgvector.psycopg2 import register_vector
except ImportError as exc:
    raise ImportError(
        "PgvectorExampleRepository requires the 'pgvector' package. "
        "Install with: pip install 'nlp2sql[pgvector]' (or 'pip install pgvector')."
    ) from exc

logger = structlog.get_logger()

DEFAULT_TABLE_NAME = "nlp2sql_examples"
_TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PgvectorExampleRepository(ExampleRepositoryPort):
    """Postgres + pgvector implementation of ``ExampleRepositoryPort``.

    Stores few-shot examples as rows in a Postgres table with a ``vector``
    column and uses an HNSW index for approximate nearest-neighbor search.
    Per-database isolation is enforced via a ``namespace`` column whose value
    is ``md5(database_url:schema_name)`` by default (same hashing as
    :class:`~nlp2sql.schema.example_store.ExampleStore`).

    Preconditions:
        * Postgres 12+ with the ``vector`` extension installed (or installable).
        * The connecting user has ``CREATE`` privileges when
          ``auto_migrate=True``, or the schema has been provisioned externally.
    """

    def __init__(  # noqa: PLR0913 — constructor keeps adapter-specific knobs explicit
        self,
        connection_string: str,
        embedding_provider: EmbeddingProviderPort,
        *,
        namespace: str | None = None,
        database_url: str | None = None,
        schema_name: str = "public",
        table_name: str = DEFAULT_TABLE_NAME,
        auto_migrate: bool = True,
    ) -> None:
        """Initialize the repository.

        Args:
            connection_string: Postgres DSN (``postgresql://user:pass@host/db``).
            embedding_provider: Provider used to vectorize examples and queries.
            namespace: Explicit namespace label. Takes precedence over
                ``database_url``-derived hashing. Defaults to ``"default"`` when
                neither is supplied.
            database_url: When provided (and ``namespace`` is not), the
                namespace is computed as ``md5(database_url:schema_name)``.
                Matches the directory-isolation strategy used by the FAISS
                adapter so two backends can share a logical tenant id.
            schema_name: Database schema combined with ``database_url`` for the
                namespace hash. Ignored when ``namespace`` is explicit.
            table_name: Postgres table that stores the examples. Must match
                ``^[a-zA-Z_][a-zA-Z0-9_]*$``.
            auto_migrate: When ``True`` (default) the constructor idempotently
                creates the ``vector`` extension, table, and indexes. When
                ``False`` it only validates that the existing schema matches
                the provider dimension.
        """
        if not _TABLE_NAME_PATTERN.match(table_name):
            raise ValueError(f"Invalid table_name {table_name!r}: must match {_TABLE_NAME_PATTERN.pattern}")

        self.connection_string = connection_string
        self.embedding_provider = embedding_provider
        self.embedding_dim = embedding_provider.get_embedding_dimension()
        self.table_name = table_name
        self._table_ident = psycopg2_sql.Identifier(table_name)

        if namespace:
            self.namespace = namespace
        elif database_url:
            index_key = f"{database_url}:{schema_name}"
            self.namespace = hashlib.md5(index_key.encode(), usedforsecurity=False).hexdigest()
        else:
            self.namespace = "default"

        if auto_migrate:
            self._run_migrations()
        else:
            self._validate_schema()

        logger.info(
            "pgvector example repository ready",
            table=self.table_name,
            namespace=self.namespace,
            dimension=self.embedding_dim,
            provider=self.embedding_provider.provider_type,
            auto_migrate=auto_migrate,
        )

    # ── Connection helpers ────────────────────────────────────────────────

    def _get_connection(self) -> Any:
        """Return a fresh connection with the pgvector type adapter registered."""
        conn = psycopg2.connect(self.connection_string)
        register_vector(conn)
        return conn

    def _get_ddl_connection(self) -> Any:
        """Plain connection for DDL — avoids ``register_vector`` starting a
        transaction before we can flip on autocommit."""
        conn = psycopg2.connect(self.connection_string)
        conn.autocommit = True
        return conn

    # ── Schema lifecycle ──────────────────────────────────────────────────

    def _run_migrations(self) -> None:
        """Create extension, table, and indexes idempotently."""
        conn = self._get_ddl_connection()
        try:
            cur = conn.cursor()
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

                existing_dim = self._existing_embedding_dimension(cur)
                if existing_dim is not None and existing_dim != self.embedding_dim:
                    raise SchemaException(self._dim_mismatch_message(existing_dim))

                create_table = psycopg2_sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {table} ("
                    "id BIGSERIAL PRIMARY KEY, "
                    "namespace TEXT NOT NULL, "
                    "question TEXT NOT NULL, "
                    "sql TEXT NOT NULL, "
                    # NULLABLE to mirror ExampleStore (FAISS), which stores
                    # examples as-is and does not require ``database_type``.
                    # Postgres NULL semantics align with FAISS filtering:
                    # ``WHERE database_type = 'x'`` excludes NULL rows
                    # (matching FAISS), and unfiltered queries include them.
                    "database_type TEXT, "
                    "metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb, "
                    "embedding VECTOR({dim}) NOT NULL, "
                    "provider_type TEXT NOT NULL, "
                    "content_hash TEXT NOT NULL, "
                    "indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                    ")"
                ).format(
                    table=self._table_ident,
                    dim=psycopg2_sql.SQL(str(self.embedding_dim)),
                )
                cur.execute(create_table)

                # Close the DDL race: another client with a different declared
                # dimension might have created the table between our check and
                # CREATE TABLE IF NOT EXISTS — re-read and validate.
                post_create_dim = self._existing_embedding_dimension(cur)
                if post_create_dim is not None and post_create_dim != self.embedding_dim:
                    raise SchemaException(self._dim_mismatch_message(post_create_dim))

                cur.execute(
                    psycopg2_sql.SQL(
                        "CREATE UNIQUE INDEX IF NOT EXISTS {idx} ON {table} (namespace, content_hash)"
                    ).format(
                        idx=psycopg2_sql.Identifier(f"{self.table_name}_namespace_hash_uq"),
                        table=self._table_ident,
                    )
                )
                cur.execute(
                    psycopg2_sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {table} (namespace)").format(
                        idx=psycopg2_sql.Identifier(f"{self.table_name}_namespace_idx"),
                        table=self._table_ident,
                    )
                )
                cur.execute(
                    psycopg2_sql.SQL(
                        "CREATE INDEX IF NOT EXISTS {idx} ON {table} USING hnsw (embedding vector_cosine_ops)"
                    ).format(
                        idx=psycopg2_sql.Identifier(f"{self.table_name}_embedding_hnsw_idx"),
                        table=self._table_ident,
                    )
                )
            finally:
                cur.close()
        finally:
            conn.close()

    def _validate_schema(self) -> None:
        """Verify the table exists with matching embedding dimension."""
        conn = self._get_ddl_connection()
        try:
            cur = conn.cursor()
            try:
                existing_dim = self._existing_embedding_dimension(cur)
                if existing_dim is None:
                    raise SchemaException(
                        f"Table {self.table_name!r} not found and auto_migrate=False. "
                        "Provision the schema manually or enable auto_migrate."
                    )
                if existing_dim != self.embedding_dim:
                    raise SchemaException(self._dim_mismatch_message(existing_dim))
            finally:
                cur.close()
        finally:
            conn.close()

    def _existing_embedding_dimension(self, cur: Any) -> int | None:
        """Return the ``embedding`` column dimension if the table exists.

        Restricted to ordinary tables (``relkind = 'r'``) in the connection's
        current schema so that a homonymous table or view in another schema
        cannot mislead the dimension check.
        """
        cur.execute(
            "SELECT pg_catalog.format_type(a.atttypid, a.atttypmod) AS formatted "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = %s AND a.attname = 'embedding' "
            "AND a.attnum > 0 AND NOT a.attisdropped "
            "AND c.relkind = 'r' "
            "AND n.nspname = current_schema() "
            "LIMIT 1",
            (self.table_name,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        formatted = row[0] if isinstance(row, tuple) else row["formatted"]
        match = re.match(r"vector\((\d+)\)", formatted or "")
        return int(match.group(1)) if match else None

    def _dim_mismatch_message(self, existing_dim: int) -> str:
        return (
            "Example store embedding dimension mismatch. "
            f"Table {self.table_name!r} has {existing_dim} dims but provider "
            f"{self.embedding_provider.provider_type!r} produces {self.embedding_dim}. "
            "Drop the table or switch to a matching provider."
        )

    # ── Example shape helpers (mirrors ExampleStore for parity) ───────────

    def _create_content_hash(self, example: dict[str, Any]) -> str:
        content = f"{example['question']}|{example['sql']}"
        return hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

    def _enrich_example(self, example: dict[str, Any]) -> dict[str, Any]:
        # ``or {}`` so callers that pass ``metadata=None`` (a common pattern
        # in ETL pipelines that leave optional fields explicit) don't crash.
        metadata = dict(example.get("metadata") or {})
        metadata.setdefault("tables", self._extract_sql_tables(example.get("sql", "")))
        return {**example, "metadata": metadata}

    def _create_example_embedding_text(self, example: dict[str, Any]) -> str:
        metadata = example.get("metadata") or {}
        tables = metadata.get("tables", [])
        metrics = metadata.get("metrics", [])
        dimensions = metadata.get("dimensions", [])
        intent = metadata.get("intent")

        parts = [f"Question: {example['question']}", f"SQL: {example['sql']}"]
        if tables:
            parts.append(f"Tables: {', '.join(tables)}")
        if metrics:
            parts.append(f"Metrics: {', '.join(metrics)}")
        if dimensions:
            parts.append(f"Dimensions: {', '.join(dimensions)}")
        if intent:
            parts.append(f"Intent: {intent}")
        return " | ".join(parts)

    def _extract_sql_tables(self, sql: str) -> list[str]:
        matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z0-9_.\"]+)", sql, flags=re.IGNORECASE)
        tables: list[str] = []
        for match in matches:
            table_name = match.strip('"').split(".")[-1]
            if table_name and table_name not in tables:
                tables.append(table_name)
        return tables

    # ── Port implementation ───────────────────────────────────────────────

    async def add_examples(self, examples: list[dict[str, Any]]) -> None:
        """Insert examples, deduplicating on ``(namespace, content_hash)``."""
        if not examples:
            return

        enriched: list[dict[str, Any]] = []
        embedding_texts: list[str] = []
        for example in examples:
            enriched_example = self._enrich_example(example)
            enriched.append(enriched_example)
            embedding_texts.append(self._create_example_embedding_text(enriched_example))

        embeddings = await self.embedding_provider.encode(embedding_texts)
        embeddings_array = np.asarray(embeddings, dtype=np.float32)
        if embeddings_array.shape[0] != len(enriched):
            raise SchemaException(
                f"Embedding provider returned {embeddings_array.shape[0]} vectors for {len(enriched)} examples."
            )

        provider_type = self.embedding_provider.provider_type
        rows: list[tuple[Any, ...]] = []
        for example, vector in zip(enriched, embeddings_array):
            rows.append(
                (
                    self.namespace,
                    example["question"],
                    example["sql"],
                    # Pass through as-is (may be ``None``) to match ExampleStore
                    # behavior: missing ``database_type`` is preserved as NULL,
                    # not silently coerced to a sentinel string.
                    example.get("database_type"),
                    Json(example.get("metadata") or {}),
                    vector,
                    provider_type,
                    self._create_content_hash(example),
                )
            )

        def _insert() -> int:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                try:
                    template = psycopg2_sql.SQL(
                        "INSERT INTO {table} "
                        "(namespace, question, sql, database_type, metadata, "
                        "embedding, provider_type, content_hash) "
                        "VALUES %s "
                        "ON CONFLICT (namespace, content_hash) DO NOTHING"
                    ).format(table=self._table_ident)
                    execute_values(cur, template.as_string(conn), rows)
                    inserted = cur.rowcount
                    conn.commit()
                    return inserted
                finally:
                    cur.close()
            finally:
                conn.close()

        inserted = await asyncio.to_thread(_insert)
        logger.info(
            "Added examples to pgvector store",
            inserted=inserted,
            requested=len(examples),
            namespace=self.namespace,
        )

    async def search_similar(
        self,
        question: str,
        top_k: int = 5,
        database_type: str | None = None,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Return the top-k examples ordered by cosine similarity to ``question``."""
        if top_k <= 0:
            return []

        query_embeddings = await self.embedding_provider.encode([question])
        embeddings_array = np.asarray(query_embeddings, dtype=np.float32)
        if embeddings_array.ndim < 2 or embeddings_array.shape[0] == 0:
            raise SchemaException(
                f"Embedding provider returned an empty/invalid result for the query "
                f"(shape={embeddings_array.shape}). Expected (>=1, {self.embedding_dim})."
            )
        query_vector = embeddings_array[0]

        # cosine distance ∈ [0, 2]; similarity = 1 - distance.
        # Keep negative values so ``min_score > 1`` correctly excludes every
        # row (no distance can satisfy ``<= negative``).
        max_distance = 1.0 - min_score

        def _search() -> list[dict[str, Any]]:
            conn = self._get_connection()
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                try:
                    filter_sql = psycopg2_sql.SQL("")
                    params: list[Any] = [query_vector, self.namespace, query_vector, max_distance]
                    if database_type is not None:
                        filter_sql = psycopg2_sql.SQL(" AND database_type = %s")
                        params.append(database_type)
                    params.extend([query_vector, top_k])

                    query = psycopg2_sql.SQL(
                        "SELECT question, sql, database_type, metadata, "
                        "(1 - (embedding <=> %s)) AS similarity_score "
                        "FROM {table} "
                        "WHERE namespace = %s AND (embedding <=> %s) <= %s{filter} "
                        "ORDER BY embedding <=> %s "
                        "LIMIT %s"
                    ).format(table=self._table_ident, filter=filter_sql)

                    cur.execute(query, params)
                    return [dict(row) for row in cur.fetchall()]
                finally:
                    cur.close()
            finally:
                conn.close()

        rows = await asyncio.to_thread(_search)
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "question": row["question"],
                    "sql": row["sql"],
                    "database_type": row["database_type"],
                    "metadata": row["metadata"] or {},
                    "similarity_score": float(row["similarity_score"]),
                }
            )
        return results

    async def clear(self) -> None:
        """Remove every example in the current namespace."""

        def _clear() -> int:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                try:
                    cur.execute(
                        psycopg2_sql.SQL("DELETE FROM {table} WHERE namespace = %s").format(table=self._table_ident),
                        (self.namespace,),
                    )
                    deleted = cur.rowcount
                    conn.commit()
                    return deleted
                finally:
                    cur.close()
            finally:
                conn.close()

        deleted = await asyncio.to_thread(_clear)
        logger.info("Cleared pgvector example store", deleted=deleted, namespace=self.namespace)

    def get_stats(self) -> dict[str, Any]:
        """Return counts and metadata for the current namespace."""
        conn = self._get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            try:
                cur.execute(
                    psycopg2_sql.SQL(
                        "SELECT COUNT(*) AS total, "
                        "COALESCE("
                        "  array_agg(DISTINCT database_type) "
                        "    FILTER (WHERE database_type IS NOT NULL), "
                        "  ARRAY[]::TEXT[]"
                        ") AS database_types "
                        "FROM {table} WHERE namespace = %s"
                    ).format(table=self._table_ident),
                    (self.namespace,),
                )
                row = cur.fetchone() or {}
                return {
                    "total_examples": int(row.get("total", 0) or 0),
                    "embedding_dimension": self.embedding_dim,
                    "provider_type": self.embedding_provider.provider_type,
                    "namespace": self.namespace,
                    "database_types": list(row.get("database_types") or []),
                }
            finally:
                cur.close()
        finally:
            conn.close()
