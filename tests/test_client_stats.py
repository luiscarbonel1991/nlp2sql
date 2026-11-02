"""NLP2SQL.stats works from synchronous code; async code awaits get_stats().

Before, stats called asyncio.get_event_loop().run_until_complete(), which raised
"This event loop is already running" in async code and "There is no current event
loop" in a script after asyncio.run(connect(...)).
"""

import asyncio

import pytest

from nlp2sql import NLP2SQL
from nlp2sql.core.entities import DatabaseType

STATS = {"provider": "openai", "provider_context_size": 128_000}


class _Service:
    async def get_service_stats(self) -> dict:
        return STATS


def _client() -> NLP2SQL:
    return NLP2SQL(service=_Service(), database_type=DatabaseType.POSTGRES)


def test_stats_after_asyncio_run():
    nlp = asyncio.run(asyncio.sleep(0, result=_client()))

    assert nlp.stats == STATS


@pytest.mark.asyncio
async def test_async_code_awaits_get_stats():
    nlp = _client()

    assert await nlp.get_stats() == STATS
    with pytest.raises(RuntimeError, match=r"await nlp\.get_stats\(\)"):
        _ = nlp.stats
