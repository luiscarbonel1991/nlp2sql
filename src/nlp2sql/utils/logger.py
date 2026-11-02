"""Loggers for nlp2sql modules.

nlp2sql never configures logging. Each module logs through the standard-library
logger named after it (``nlp2sql.adapters.openai_adapter``, ...), so records go
wherever the application sends them, and nowhere when it configures nothing: the
``nlp2sql`` logger has a ``NullHandler``, as the logging HOWTO recommends for
libraries. Before, the library logged through structlog's default configuration,
which prints to stdout, including user questions and raw model responses.

The structlog call style stays (``logger.info("event", key=value)``); the
processors here render it to one message string and never touch the application's
global structlog configuration.
"""

import logging
from typing import Any

import structlog


def _render(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> tuple[tuple[str], dict[str, Any]]:
    """``event key=value ...`` as the message; ``exc_info`` goes to the stdlib logger as is."""
    exc_info = event_dict.pop("exc_info", None)
    event = event_dict.pop("event", "")
    fields = " ".join(f"{key}={value}" for key, value in event_dict.items())
    message = f"{event} {fields}" if fields else str(event)
    return (message,), ({"exc_info": exc_info} if exc_info else {})


_PROCESSORS = [structlog.stdlib.filter_by_level, _render]


def get_logger(name: str) -> Any:
    """Return a structlog-style logger that emits through ``logging.getLogger(name)``."""
    return structlog.wrap_logger(
        logging.getLogger(name),
        processors=_PROCESSORS,
        wrapper_class=structlog.stdlib.BoundLogger,
    )
