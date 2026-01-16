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

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """
        Get the provider type identifier.

        Returns:
            String identifier (e.g., "local", "openai", "cohere")
        """
        pass
