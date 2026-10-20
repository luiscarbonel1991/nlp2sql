"""Translate provider SDK errors into nlp2sql exceptions.

The AI adapters retry only transient failures. Before, every exception was retried
three times with backoff, so an invalid API key took about 8 seconds to surface.
Works without importing any SDK: OpenAI and Anthropic errors carry ``status_code``,
google.api_core errors carry an integer ``code``.
"""

from typing import Optional

from ..exceptions import (
    ProviderAuthenticationError,
    ProviderException,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)

TRANSIENT_PROVIDER_ERRORS = (ProviderRateLimitError, ProviderUnavailableError)


def _http_status(exc: BaseException) -> Optional[int]:
    for attribute in ("status_code", "code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int) and 100 <= value < 600:
            return int(value)
    return None


def _is_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__
    return "Timeout" in name or "Connection" in name


def classify_provider_error(exc: BaseException, message: str) -> ProviderException:
    """Return the nlp2sql exception for ``exc``; nlp2sql exceptions pass through unchanged."""
    if isinstance(exc, ProviderException):
        return exc

    status = _http_status(exc)
    if status in (401, 403):
        return ProviderAuthenticationError(message, {"status_code": status})
    if status == 429:
        return ProviderRateLimitError(message, {"status_code": status})
    if status is not None and (status >= 500 or status in (408, 409)):
        return ProviderUnavailableError(message, {"status_code": status})
    if status is not None and 400 <= status < 500:
        return ProviderRequestError(message, {"status_code": status})
    if _is_transport_error(exc):
        return ProviderUnavailableError(message)
    return ProviderException(message)
