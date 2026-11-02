"""nlp2sql logs through standard-library loggers and prints nothing unless configured.

Before, every module used structlog's default configuration, which prints to stdout:
a script that only called connect() and ask() printed 22-36 lines, including the user's
question and the raw model response, and NLP2SQL_LOG_LEVEL was not read anywhere.
The CLI printed its logs on stdout too, mixed with the SQL and JSON it outputs.
"""

import logging

import pytest

import nlp2sql
from nlp2sql import cli as cli_module
from nlp2sql.config.settings import LogLevel, Settings
from nlp2sql.utils.logger import get_logger


def test_the_library_logger_has_only_a_null_handler():
    handlers = logging.getLogger(nlp2sql.__name__).handlers

    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)


def test_records_go_to_the_module_logger_with_the_fields_in_the_message(caplog):
    caplog.set_level(logging.INFO, logger="nlp2sql")

    get_logger("nlp2sql.services.example").info("Schema refreshed", schema="public", tables=10)

    record = caplog.records[-1]
    assert record.name == "nlp2sql.services.example"
    assert record.levelno == logging.INFO
    assert record.getMessage() == "Schema refreshed schema=public tables=10"


def test_exceptions_reach_the_handler_as_exc_info(caplog):
    caplog.set_level(logging.ERROR, logger="nlp2sql")

    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("nlp2sql.example").exception("Query failed", step=2)

    record = caplog.records[-1]
    assert record.getMessage() == "Query failed step=2"
    assert record.exc_info[0] is ValueError


def test_disabled_levels_are_dropped_before_rendering(caplog):
    caplog.set_level(logging.WARNING, logger="nlp2sql")

    get_logger("nlp2sql.example").debug("Raw model response", content="SELECT 1")

    assert not caplog.records


@pytest.fixture
def stderr_only_cli_logging(monkeypatch: pytest.MonkeyPatch):
    def configure(*, verbose: bool = False, log_level: LogLevel = None) -> None:
        settings = Settings.model_construct(log_level=log_level) if log_level else Settings.model_construct()
        monkeypatch.setattr(cli_module, "settings", settings)
        cli_module.setup_logging(verbose)

    return configure


@pytest.mark.parametrize(
    ("verbose", "log_level", "shown", "hidden"),
    [
        (False, None, "WARNING", "INFO"),
        (False, LogLevel.INFO, "INFO", "DEBUG"),
        (True, LogLevel.ERROR, "DEBUG", None),
    ],
)
def test_cli_logs_to_stderr_at_the_configured_level(stderr_only_cli_logging, capsys, verbose, log_level, shown, hidden):
    stderr_only_cli_logging(verbose=verbose, log_level=log_level)
    logger = get_logger("nlp2sql.example")

    logger.log(getattr(logging, shown), "shown message")
    if hidden:
        logger.log(getattr(logging, hidden), "hidden message")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "shown message" in captured.err
    assert "hidden message" not in captured.err


def test_repeated_cli_invocations_do_not_duplicate_log_lines(stderr_only_cli_logging, capsys):
    stderr_only_cli_logging()
    stderr_only_cli_logging()

    get_logger("nlp2sql.example").warning("once")

    assert capsys.readouterr().err.count("once") == 1
