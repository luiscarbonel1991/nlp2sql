"""Cache Port - Interface for caching mechanisms."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, Dict, Optional


class CachePort(ABC):
    """Abstract interface for cache implementations."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[timedelta] = None) -> None:
        """Set value in cache with optional TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cache entries."""
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        pass
