"""What an application gets from connect() and ask(): no output, results, reasons.

Measured on 0.2.0rc17 with tests/fakes/fake_openai.py and the docker database:
connect() + ask() printed 23 lines on stdout (15 on a warm start) including the user's
question; a warm connect() made one embedding request ("warmup"); QueryResult had no
rows, columns or validation reasons, although the query had been executed.
"""

import json
import logging

import pytest
from click.testing import CliRunner

import nlp2sql
from nlp2sql import ProviderConfig
from nlp2sql.cli import cli

pytestmark = pytest.mark.integration

QUESTION = "How many users have placed orders?"


async def _connect(url: str):
    return await nlp2sql.connect(url, provider=ProviderConfig(provider="openai", api_key="sk-test"))


@pytest.mark.asyncio
async def test_connect_and_ask_print_nothing(postgres_available, fake_openai, isolated_caches, capfd):
    nlp = await _connect(postgres_available)
    await nlp.ask(QUESTION, validate=True)

    out, err = capfd.readouterr()
    assert out == ""
    assert err == ""


@pytest.mark.asyncio
async def test_the_question_and_model_output_are_logged_only_at_debug(
    postgres_available, fake_openai, isolated_caches, caplog
):
    caplog.set_level(logging.DEBUG, logger="nlp2sql")
    nlp = await _connect(postgres_available)

    await nlp.ask(QUESTION, validate=True)

    records = [record for record in caplog.records if record.name.startswith("nlp2sql")]
    above_debug = [record.getMessage() for record in records if record.levelno > logging.DEBUG]
    assert above_debug, "INFO logs are still emitted when the application asks for them"
    assert not any(QUESTION in message for message in above_debug)
    assert not any('"explanation": "fake"' in message for message in above_debug)
    assert any(QUESTION in record.getMessage() for record in records if record.levelno == logging.DEBUG)


@pytest.mark.asyncio
async def test_a_warm_start_sends_no_embedding_requests(postgres_available, fake_openai, isolated_caches):
    await _connect(postgres_available)
    fake_openai.requests.clear()

    await _connect(postgres_available)

    assert fake_openai.calls("embedding") == 0


@pytest.mark.asyncio
async def test_an_executed_query_returns_its_rows_columns_and_validation(
    postgres_available, fake_openai, isolated_caches
):
    nlp = await _connect(postgres_available)

    result = await nlp.ask(QUESTION, validate=True)

    assert result.is_valid
    assert result.columns == ["user_count"]
    assert len(result.rows) == 1
    assert result.rows[0]["user_count"] > 0
    assert result.validation["is_valid"] is True
    assert result.validation["errors"] == []
    assert "_rows" not in result.metadata["execution_validation"]


@pytest.mark.asyncio
async def test_without_execution_there_are_no_rows(postgres_available, fake_openai, isolated_caches):
    nlp = await _connect(postgres_available)

    result = await nlp.ask(QUESTION)

    assert result.rows is None
    assert result.columns is None
    assert result.validation["is_valid"] is True


@pytest.mark.asyncio
async def test_an_invalid_query_says_why(postgres_available, fake_openai, isolated_caches):
    nlp = await _connect(postgres_available)
    fake_openai.sql = "SELECT COUNT(*) FROM no_such_table"

    result = await nlp.ask(QUESTION, validate=True)

    assert not result.is_valid
    assert result.rows is None
    assert any("Execution failed" in error for error in result.validation["errors"])


def test_cli_json_output_is_not_mixed_with_logs(postgres_available, isolated_caches):
    result = CliRunner().invoke(cli, ["inspect", "--database-url", postgres_available, "--format", "json"])

    assert result.exit_code == 0, result.output
    tables = json.loads(result.stdout)
    assert {"users", "orders"} <= {table["name"] for table in tables}
