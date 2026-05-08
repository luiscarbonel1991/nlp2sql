"""Adapters (implementations) for nlp2sql."""

from .local_embedding_adapter import LocalEmbeddingAdapter
from .openai_embedding_adapter import OpenAIEmbeddingAdapter

__all__ = [
    "LocalEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
]

# Optional: pgvector-backed example repository (requires the [pgvector] extra)
try:
    from .pgvector_example_repository import PgvectorExampleRepository
except ImportError:
    pass
else:
    __all__.append("PgvectorExampleRepository")
