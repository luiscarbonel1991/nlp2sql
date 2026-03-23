"""Example Repository Port - Interface for few-shot example storage and retrieval."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ExampleRepositoryPort(ABC):
    """Abstract interface for few-shot example repositories.

    Defines the contract for storing and retrieving query examples
    used in few-shot prompting. Implementations may use FAISS (local),
    a database, an external API, or any other storage backend.
    """

    @abstractmethod
    async def add_examples(self, examples: List[Dict[str, Any]]) -> None:
        """Add examples to the repository.

        Args:
            examples: List of examples, each with at least:
                ``{"question": str, "sql": str, "database_type": str}``
        """
        pass

    @abstractmethod
    async def search_similar(
        self,
        question: str,
        top_k: int = 5,
        database_type: Optional[str] = None,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Search for examples similar to a question.

        Args:
            question: Natural language question to match against.
            top_k: Maximum number of examples to return.
            database_type: Optional filter by database type.
            min_score: Minimum similarity score threshold.

        Returns:
            List of example dicts sorted by relevance, each containing
            at least ``question`` and ``sql`` keys.
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Remove all examples from the repository."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the repository contents."""
        pass
