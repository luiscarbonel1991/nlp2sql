"""Local embedding adapter using sentence-transformers."""

import asyncio
import threading
from typing import List

import numpy as np
import structlog

from ..ports.embedding_provider import EmbeddingProviderPort

logger = structlog.get_logger()

_model_cache = {}
_model_cache_lock = threading.Lock()


def _get_cached_model(model_name: str):
    if model_name not in _model_cache:
        with _model_cache_lock:
            if model_name not in _model_cache:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading local embedding model", model=model_name)
                _model_cache[model_name] = SentenceTransformer(model_name)
                logger.info(
                    "Local embedding model loaded",
                    model=model_name,
                    dimension=_model_cache[model_name].get_sentence_embedding_dimension(),
                )
    return _model_cache[model_name]


class LocalEmbeddingAdapter(EmbeddingProviderPort):
    """Adapter for local embeddings using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize local embedding adapter.

        Args:
            model_name: Name of the sentence-transformers model to use

        Raises:
            ImportError: If sentence-transformers is not installed
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed. "
                "To use local embeddings, install with: "
                "pip install nlp2sql[embeddings-local]"
            ) from e

        self._model_name = model_name
        self._model: SentenceTransformer = None
        self._embedding_dim: int = None

    def _load_model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            self._model = _get_cached_model(self._model_name)
            self._embedding_dim = self._model.get_sentence_embedding_dimension()

    async def encode(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for texts using sentence-transformers.

        Args:
            texts: List of text strings to embed

        Returns:
            numpy array of embeddings with shape (len(texts), embedding_dimension)
        """
        self._load_model()

        # Wrap synchronous encode() in async to avoid blocking
        # Use to_thread for Python 3.9+ (project requires >=3.9)
        embeddings = await asyncio.to_thread(
            self._model.encode,
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return np.array(embeddings)

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this provider.

        Returns:
            Integer representing the embedding dimension
            (384 for all-MiniLM-L6-v2)

        Raises:
            ImportError: If sentence-transformers is not installed
                (lazy loading case)
        """
        try:
            self._load_model()
            return self._embedding_dim
        except ImportError as e:
            # Re-raise with helpful message if model loading fails
            # during lazy loading
            raise ImportError(
                "sentence-transformers is not installed. "
                "To use local embeddings, install with: "
                "pip install nlp2sql[embeddings-local]"
            ) from e

    @property
    def provider_type(self) -> str:
        """Get the provider type identifier."""
        return "local"
