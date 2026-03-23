"""Provider configuration for AI provider instances."""

from dataclasses import dataclass
from typing import ClassVar, Optional


@dataclass(frozen=True)
class ProviderConfig:
    """Unified configuration for an AI provider.

    Encapsulates provider identity, credentials, and generation parameters
    in a single immutable object. All optional fields default to None,
    meaning the adapter's built-in default will be used.

    Args:
        provider: Provider name ("openai", "anthropic", "gemini").
        api_key: API key. None = adapter falls back to env vars / settings.
        model: Model identifier. None = use DEFAULT_MODELS[provider].
        temperature: Sampling temperature. None = adapter default (0.1).
        max_tokens: Maximum tokens in response. None = adapter default (2000).
    """

    provider: str
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    SUPPORTED_PROVIDERS: ClassVar[frozenset[str]] = frozenset({"openai", "anthropic", "gemini"})

    DEFAULT_MODELS: ClassVar[dict[str, str]] = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-sonnet-4-20250514",
        "gemini": "gemini-2.0-flash",
    }

    def __post_init__(self) -> None:
        if self.provider not in self.SUPPORTED_PROVIDERS:
            msg = f"Unsupported provider: '{self.provider}'. Supported: {sorted(self.SUPPORTED_PROVIDERS)}"
            raise ValueError(msg)

    @property
    def resolved_model(self) -> str:
        """Return the explicit model or the provider's default."""
        return self.model or self.DEFAULT_MODELS[self.provider]
