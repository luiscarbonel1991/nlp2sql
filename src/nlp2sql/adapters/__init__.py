"""Adapters (implementations) for nlp2sql."""

from .local_embedding_adapter import LocalEmbeddingAdapter
from .openai_embedding_adapter import OpenAIEmbeddingAdapter

__all__ = [
    "LocalEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
]
