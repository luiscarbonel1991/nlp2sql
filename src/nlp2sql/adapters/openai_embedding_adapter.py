"""OpenAI embedding adapter."""

from typing import List

import numpy as np
import structlog
from openai import AsyncOpenAI

from ..exceptions import ProviderException
from ..ports.embedding_provider import EmbeddingProviderPort

logger = structlog.get_logger()


class OpenAIEmbeddingAdapter(EmbeddingProviderPort):
    """Adapter for OpenAI embeddings API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """
        Initialize OpenAI embedding adapter.

        Args:
            api_key: OpenAI API key
            model: OpenAI embedding model name (default: text-embedding-3-small)

        Raises:
            ProviderException: If API key is not provided
        """
        if not api_key:
            raise ProviderException("OpenAI API key is required for OpenAI embeddings")

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

        # Embedding dimensions for different models
        self._dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

    async def encode(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for texts using OpenAI API.

        Args:
            texts: List of text strings to embed

        Returns:
            numpy array of normalized embeddings with shape (len(texts), embedding_dimension)
            Embeddings are normalized to unit vectors for cosine similarity with FAISS IndexFlatIP

        Raises:
            ProviderException: If API call fails
        """
        # Validate input
        if not texts:
            logger.warning("Empty texts list provided to encode, returning empty array")
            dim = self.get_embedding_dimension()
            return np.array([]).reshape(0, dim)

        # Process texts but preserve array length for 1:1 mapping with caller's data
        # NOTE: We do NOT filter here - filtering is done by the caller (embedding_manager)
        # to ensure the returned embeddings array has the same length as the input.
        # This maintains consistency with local_embedding_adapter behavior.
        processed_texts = []
        for text in texts:
            if text is None:
                # Replace None with a placeholder that produces a valid embedding
                logger.warning("None value found in texts list, using placeholder")
                processed_texts.append(" ")  # Single space - minimal valid input
            elif not isinstance(text, str):
                processed_texts.append(str(text))
            elif not text.strip():
                # Empty/whitespace string - use placeholder
                logger.warning("Empty string found in texts list, using placeholder")
                processed_texts.append(" ")  # Single space - minimal valid input
            else:
                processed_texts.append(text)

        try:
            response = await self.client.embeddings.create(model=self.model, input=processed_texts)

            # Extract embeddings from response
            embeddings = [item.embedding for item in response.data]
            embeddings_array = np.array(embeddings)

            # Normalize embeddings for cosine similarity with FAISS IndexFlatIP
            # This is critical: FAISS IndexFlatIP uses inner product which only works
            # as cosine similarity when vectors are normalized to unit length
            norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
            # Avoid division by zero (though rare for real embeddings)
            norms = np.where(norms == 0, 1, norms)
            normalized_embeddings = embeddings_array / norms

            logger.debug(
                "OpenAI embeddings generated and normalized",
                model=self.model,
                texts_count=len(processed_texts),
                dimension=normalized_embeddings.shape[1],
            )

            return normalized_embeddings

        except Exception as e:
            logger.error("Failed to generate OpenAI embeddings", error=str(e), model=self.model)
            raise ProviderException(f"OpenAI embedding generation failed: {e!s}") from e

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this provider.

        Returns:
            Integer representing the embedding dimension
        """
        # Default to 1536 if model not in our dimension map
        return self._dimensions.get(self.model, 1536)

    @property
    def provider_type(self) -> str:
        """Get the provider type identifier."""
        return "openai"
