"""What one question costs: LLM calls, reported tokens, database connections.

Numbers measured on 0.2.0rc16 with tests/fakes/fake_openai.py and the docker database:
2 LLM calls per ask() (the second one, an LLM review of the SQL, unreported in
tokens_used), 10 new database connections for a simple question and 41 for a
multi-table one, and an ANALYZE of the whole database on the first connect().
"""

import asyncio

import psycopg2
import pytest

import nlp2sql
from nlp2sql import ProviderConfig

pytestmark = pytest.mark.integration

MULTI_TABLE_QUESTION = (
    "Show monthly revenue by marketing channel source category and store region, "
    "with order counts, average review rating and product category"
)


class _DatabaseStats:
    """Reads pg_stat counters through one long-lived monitoring connection."""

    def __init__(self, url: str):
        self.connection = psycopg2.connect(url)
        self.connection.autocommit = True

    async def read(self) -> dict:
        await asyncio.sleep(1.5)  # backends report their statistics with a short delay
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT pg_stat_clear_snapshot()")
            cursor.execute("SELECT sessions FROM pg_stat_database WHERE datname = current_database()")
            sessions = cursor.fetchone()[0]
            cursor.execute("SELECT max(last_analyze) FROM pg_stat_user_tables")
            last_analyze = cursor.fetchone()[0]
        return {"sessions": sessions, "last_analyze": last_analyze}

    def close(self) -> None:
        self.connection.close()


@pytest.fixture
def database_stats(postgres_available):
    stats = _DatabaseStats(postgres_available)
    yield stats
    stats.close()


async def _connect(url: str, **kwargs):
    return await nlp2sql.connect(url, provider=ProviderConfig(provider="openai", api_key="sk-test"), **kwargs)


@pytest.mark.asyncio
async def test_one_llm_call_per_question_and_tokens_match_the_api(postgres_available, fake_openai, isolated_caches):
    nlp = await _connect(postgres_available)
    fake_openai.requests.clear()

    result = await nlp.ask("How many users have placed orders?")

    assert fake_openai.calls("generate") == 1
    assert fake_openai.calls("validate") == 0
    assert result.tokens_used == fake_openai.chat_tokens()
    assert result.metadata["token_usage"]["llm_calls"] == 1


@pytest.mark.asyncio
async def test_llm_validation_on_request_is_counted(postgres_available, fake_openai, isolated_caches):
    nlp = await _connect(postgres_available, llm_validation=True)
    fake_openai.requests.clear()

    result = await nlp.ask("How many users have placed orders?")

    assert fake_openai.calls("generate") == 1
    assert fake_openai.calls("validate") == 1
    assert result.tokens_used == fake_openai.chat_tokens()
    assert result.metadata["token_usage"]["llm_calls"] == 2


@pytest.mark.asyncio
async def test_a_question_opens_no_database_connections(
    postgres_available, fake_openai, isolated_caches, database_stats
):
    nlp = await _connect(postgres_available)
    before = await database_stats.read()

    await nlp.ask(MULTI_TABLE_QUESTION)

    after = await database_stats.read()
    assert after["sessions"] - before["sessions"] <= 1


@pytest.mark.asyncio
async def test_connect_does_not_analyze_the_database(postgres_available, fake_openai, isolated_caches, database_stats):
    before = await database_stats.read()

    await _connect(postgres_available)

    after = await database_stats.read()
    assert after["last_analyze"] == before["last_analyze"]
