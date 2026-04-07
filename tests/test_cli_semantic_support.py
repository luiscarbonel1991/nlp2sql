"""Tests for CLI semantic context and few-shot example support."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from nlp2sql.cli import cli


def test_query_accepts_semantic_context_and_examples_and_prints_metadata(tmp_path: Path):
    runner = CliRunner()
    semantic_file = tmp_path / "semantic.json"
    semantic_file.write_text(
        """{
  "domain": "sales",
  "canonical_tables": ["channel_performance"],
  "required_filters": ["segment = 'growth'"]
}"""
    )
    examples_file = tmp_path / "examples.json"
    examples_file.write_text(
        """[
  {
    "question": "Revenue by channel",
    "sql": "SELECT channel, SUM(net_revenue) FROM channel_performance GROUP BY channel",
    "database_type": "redshift"
  }
]"""
    )

    fake_service = MagicMock()
    fake_service.generate_sql = AsyncMock(
        return_value={
            "sql": "SELECT 1",
            "confidence": 0.9,
            "tokens_used": 42,
            "validation": {"is_valid": True},
            "metadata": {
                "semantic_context": {"domain": "sales"},
                "sql_intent_plan": {"fact_table": "channel_performance"},
                "selected_examples": [{"tables": ["channel_performance"]}],
            },
        }
    )
    fake_example_store = MagicMock()

    with (
        patch("nlp2sql.cli.create_and_initialize_service", new_callable=AsyncMock) as create_service,
        patch("nlp2sql.cli.create_example_store_from_payload", new_callable=AsyncMock) as create_example_store,
    ):
        create_service.return_value = fake_service
        create_example_store.return_value = fake_example_store

        result = runner.invoke(
            cli,
            [
                "query",
                "--database-url",
                "redshift://user:pass@host:5439/db",
                "--question",
                "give me sales metrics",
                "--provider",
                "openai",
                "--embedding-provider",
                "openai",
                "--semantic-context-file",
                str(semantic_file),
                "--examples-file",
                str(examples_file),
                "--show-semantic-context",
                "--show-sql-intent-plan",
                "--show-selected-examples",
                "--validate",
            ],
            env={"OPENAI_API_KEY": "test-key"},
        )

    assert result.exit_code == 0, result.output
    assert create_service.await_args.kwargs["example_store"] is fake_example_store
    assert fake_service.generate_sql.await_args.kwargs["semantic_context"].domain == "sales"
    assert fake_service.generate_sql.await_args.kwargs["execution_mode"] == "generate_and_validate"
    assert "Semantic Context:" in result.output
    assert "SQL Intent Plan:" in result.output
    assert "Selected Examples:" in result.output


def test_benchmark_uses_detected_database_type(tmp_path: Path):
    runner = CliRunner()
    questions_file = tmp_path / "questions.txt"
    questions_file.write_text("show conversion metrics\n")
    semantic_file = tmp_path / "semantic.yaml"
    semantic_file.write_text(
        "domain: conversion\ncanonical_tables:\n  - conversion_funnel\n"
    )

    fake_service = MagicMock()
    fake_service.generate_sql = AsyncMock(
        return_value={
            "sql": "SELECT 1",
            "confidence": 0.8,
            "tokens_used": 5,
            "validation": {"is_valid": True},
            "metadata": {},
        }
    )

    with (
        patch("nlp2sql.cli.create_and_initialize_service", new_callable=AsyncMock) as create_service,
        patch("nlp2sql.cli.create_example_store_from_payload", new_callable=AsyncMock) as create_example_store,
    ):
        create_service.return_value = fake_service
        create_example_store.return_value = None

        result = runner.invoke(
            cli,
            [
                "benchmark",
                "--database-url",
                "redshift://user:pass@host:5439/db",
                "--schema",
                "analytics",
                "--questions",
                str(questions_file),
                "--providers",
                "openai",
                "--iterations",
                "1",
                "--semantic-context-file",
                str(semantic_file),
            ],
            env={"OPENAI_API_KEY": "test-key"},
        )

    assert result.exit_code == 0, result.output
    assert create_service.await_args.kwargs["database_type"].value == "redshift"
    assert fake_service.generate_sql.await_args.kwargs["database_type"].value == "redshift"
    assert fake_service.generate_sql.await_args.kwargs["semantic_context"].domain == "conversion"
