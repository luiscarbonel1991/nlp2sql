"""Correct SQL must not come back invalid when no semantic layer is configured.

Gold set from the rc15 field test: 14 realistic questions over the docker e-commerce
schema, each with a correct query checked with EXPLAIN. The fake OpenAI API returns that
exact query, so any is_valid=False comes from nlp2sql's own validation. rc15 marked 4 of
these 14 invalid (the heuristic plan's fact table was enforced as a business rule).
"""

import json
from pathlib import Path

import pytest

import nlp2sql
from nlp2sql import ProviderConfig

pytestmark = pytest.mark.integration

GOLD_QUESTIONS = json.loads((Path(__file__).parent / "data" / "gold_questions.json").read_text())


@pytest.mark.asyncio
async def test_correct_queries_are_valid_without_a_semantic_layer(postgres_available, fake_openai, isolated_caches):
    nlp = await nlp2sql.connect(
        postgres_available,
        provider=ProviderConfig(provider="openai", api_key="sk-test-not-a-real-key"),
    )

    invalid = {}
    for item in GOLD_QUESTIONS:
        fake_openai.sql = item["sql"]
        result = await nlp.ask(item["question"], execution_mode="generate_and_validate")
        if not result.is_valid:
            invalid[item["question"]] = result.metadata.get("execution_validation")

    assert invalid == {}
