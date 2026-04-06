"""Tests for JSON/YAML semantic and examples artifact loading."""

from pathlib import Path

import yaml

from nlp2sql.core.entities import DatabaseType
from nlp2sql.utils.artifact_loader import load_examples_payload, load_semantic_context


def test_load_semantic_context_from_json(tmp_path: Path):
    semantic_file = tmp_path / "semantic.json"
    semantic_file.write_text(
        """{
  "domain": "sales",
  "canonical_tables": ["channel_performance"],
  "required_filters": ["segment = 'growth'"]
}"""
    )

    semantic_context = load_semantic_context(file_path=str(semantic_file))

    assert semantic_context is not None
    assert semantic_context.domain == "sales"
    assert semantic_context.canonical_tables == ["channel_performance"]


def test_load_semantic_context_from_yaml(tmp_path: Path):
    semantic_file = tmp_path / "semantic.yaml"
    semantic_file.write_text(
        yaml.safe_dump(
            {
                "domain": "conversion",
                "canonical_tables": ["conversion_funnel"],
                "required_filters": ["region = 'north_america'"],
            }
        )
    )

    semantic_context = load_semantic_context(file_path=str(semantic_file))

    assert semantic_context is not None
    assert semantic_context.domain == "conversion"
    assert semantic_context.required_filters == ["region = 'north_america'"]


def test_load_examples_payload_from_json(tmp_path: Path):
    examples_file = tmp_path / "examples.json"
    examples_file.write_text(
        """[
  {
    "question": "Revenue by channel",
    "sql": "SELECT channel, SUM(net_revenue) FROM channel_performance GROUP BY channel"
  }
]"""
    )

    examples = load_examples_payload(
        file_path=str(examples_file),
        database_type=DatabaseType.REDSHIFT,
    )

    assert examples is not None
    assert examples[0]["database_type"] == "redshift"
    assert examples[0]["metadata"] == {}
