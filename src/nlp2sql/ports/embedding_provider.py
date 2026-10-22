"""Embedding Provider Port - Interface for all embedding providers."""

from abc import ABC, abstractmethod
from typing import List

import numpy as np


class EmbeddingProviderPort(ABC):
    """Abstract interface for embedding providers."""

    @abstractmethod
    async def encode(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            numpy array of embeddings with shape (len(texts), embedding_dimension)
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this provider.

        Returns:
            Integer representing the embedding dimension
        """
        pass

    async def warmup(self) -> None:
        """
        Prepare the provider before the first question, e.g. load a local model.

        Called by connect() when the schema index already exists on disk. Not abstract:
        the default does nothing, which suits remote providers (a request here would be
        paid on every start). Added in 0.2.0rc18; existing implementations keep working.
        """
        return None

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """
        Get the provider type identifier.

        Returns:
            String identifier (e.g., "local", "openai", "cohere")
        """
        pass
