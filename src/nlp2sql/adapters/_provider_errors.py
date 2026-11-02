"""Translate provider SDK errors into nlp2sql exceptions, and decide what is retried.

The AI adapters retry only transient failures. Before, every exception was retried
three times with backoff, so an invalid API key took about 8 seconds to surface.
Works without importing any SDK: OpenAI and Anthropic errors carry ``status_code``,
google.api_core errors carry an integer ``code``.

Output that is not the expected JSON is a different failure: the request worked, the
model answered badly. ``call_with_format_retry`` asks again once, without waiting,
and counts the tokens of both answers.
"""

from typing import Any, Awaitable, Callable, Dict, NamedTuple, Optional, TypeVar

from ..exceptions import (
    ProviderAuthenticationError,
    ProviderException,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseFormatError,
    ProviderUnavailableError,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

TRANSIENT_PROVIDER_ERRORS = (ProviderRateLimitError, ProviderUnavailableError)
FORMAT_RETRY_ATTEMPTS = 2

ResponseT = TypeVar("ResponseT")


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


class ParsedGeneration(NamedTuple):
    response: Any
    result: Dict[str, Any]
    tokens_used: int
    format_retries: int


async def call_with_format_retry(
    send: Callable[[], Awaitable[ResponseT]],
    parse: Callable[[ResponseT], Dict[str, Any]],
    tokens_of: Callable[[ResponseT], int],
    *,
    provider: str,
    attempts: int = FORMAT_RETRY_ATTEMPTS,
) -> ParsedGeneration:
    """Send a generation request and parse it, asking again when the output is malformed.

    Tokens are read before parsing, so a discarded answer still counts. Every other
    error propagates on the first attempt; transient ones are retried by the caller.
    """
    tokens_used = 0
    for attempt in range(1, attempts + 1):
        response = await send()
        tokens_used += tokens_of(response)
        try:
            return ParsedGeneration(response, parse(response), tokens_used, attempt - 1)
        except ProviderResponseFormatError as error:
            error.details["tokens_used"] = tokens_used
            if attempt == attempts:
                raise
            logger.warning("Malformed model output, asking again", provider=provider, error=str(error))
    raise ValueError("attempts must be at least 1")
