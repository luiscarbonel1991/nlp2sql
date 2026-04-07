"""Helpers for loading semantic context and example artifacts from JSON/YAML."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from ..core.entities import (
    CanonicalQueryPattern,
    DatabaseType,
    DimensionDefinition,
    DomainRule,
    MetricDefinition,
    SemanticContext,
    SemanticEntityMapping,
)
from ..ports.example_repository import ExampleRepositoryPort
from ..schema.example_store import ExampleStore


def load_semantic_context(
    *,
    file_path: str | None = None,
    inline_json: str | None = None,
) -> SemanticContext | None:
    """Load a semantic context artifact from file or inline JSON."""
    payload = load_artifact_payload(
        file_path=file_path,
        inline_json=inline_json,
        artifact_name="semantic context",
    )
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Semantic context artifact must be a JSON/YAML object.")
    return semantic_context_from_dict(payload)


def load_examples_payload(
    *,
    file_path: str | None = None,
    inline_json: str | None = None,
    database_type: DatabaseType | None = None,
) -> list[dict[str, Any]] | None:
    """Load few-shot examples from file or inline JSON."""
    payload = load_artifact_payload(
        file_path=file_path,
        inline_json=inline_json,
        artifact_name="examples",
    )
    if payload is None:
        return None
    if not isinstance(payload, list):
        raise ValueError("Examples artifact must be a JSON/YAML list.")
    normalized_examples: list[dict[str, Any]] = []
    for example in payload:
        if not isinstance(example, dict):
            raise ValueError("Each example must be an object with at least question and sql.")
        if "question" not in example or "sql" not in example:
            raise ValueError("Each example must contain 'question' and 'sql'.")
        normalized_example = dict(example)
        if database_type is not None:
            normalized_example.setdefault("database_type", database_type.value)
        normalized_example.setdefault("metadata", {})
        normalized_examples.append(normalized_example)
    return normalized_examples


async def create_example_store_from_payload(
    *,
    examples: list[dict[str, Any]] | None,
    database_url: str,
    schema_name: str,
    embedding_provider_type: str | None,
    api_key: str | None = None,
) -> ExampleRepositoryPort | None:
    """Instantiate an ExampleStore from parsed examples."""
    if not examples:
        return None
    from .. import create_embedding_provider

    if embedding_provider_type is None:
        try:
            embedding_provider = create_embedding_provider(provider="local")
        except Exception:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError(
                    "Few-shot examples require embeddings. Configure a local embedding dependency or provide an OpenAI API key."
                ) from None
            embedding_provider = create_embedding_provider(provider="openai", api_key=openai_api_key)
    else:
        embedding_provider = create_embedding_provider(
            provider=embedding_provider_type,
            api_key=api_key if embedding_provider_type == "openai" else None,
        )
    example_store = ExampleStore(
        embedding_provider=embedding_provider,
        database_url=database_url,
        schema_name=schema_name,
    )
    await example_store.add_examples(examples)
    return example_store


def load_artifact_payload(
    *,
    file_path: str | None = None,
    inline_json: str | None = None,
    artifact_name: str,
) -> Any:
    """Load an artifact payload from one source only."""
    if file_path and inline_json:
        raise ValueError(f"Provide either {artifact_name} file or inline JSON, not both.")
    if file_path:
        return _load_artifact_file(file_path)
    if inline_json:
        try:
            return json.loads(inline_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid inline JSON for {artifact_name}: {exc.msg}.") from exc
    return None


def semantic_context_from_dict(payload: dict[str, Any]) -> SemanticContext:
    """Map a dictionary into a SemanticContext entity."""
    return SemanticContext(
        domain=payload.get("domain"),
        entity_mappings=[
            SemanticEntityMapping(**mapping)
            for mapping in _expect_list(payload.get("entity_mappings"), "entity_mappings")
        ],
        metric_definitions=[
            MetricDefinition(**metric)
            for metric in _expect_list(payload.get("metric_definitions"), "metric_definitions")
        ],
        dimension_definitions=[
            DimensionDefinition(**dimension)
            for dimension in _expect_list(payload.get("dimension_definitions"), "dimension_definitions")
        ],
        canonical_tables=_expect_string_list(payload.get("canonical_tables"), "canonical_tables"),
        supporting_tables=_expect_string_list(payload.get("supporting_tables"), "supporting_tables"),
        required_filters=_expect_string_list(payload.get("required_filters"), "required_filters"),
        preferred_time_logic=_expect_string_list(payload.get("preferred_time_logic"), "preferred_time_logic"),
        disallowed_tables=_expect_string_list(payload.get("disallowed_tables"), "disallowed_tables"),
        prompt_hints=_expect_string_list(payload.get("prompt_hints"), "prompt_hints"),
        rules=[DomainRule(**rule) for rule in _expect_list(payload.get("rules"), "rules")],
        patterns=[
            CanonicalQueryPattern(**pattern)
            for pattern in _expect_list(payload.get("patterns"), "patterns")
        ],
        confidence=float(payload.get("confidence", 0.0)),
        metadata=_expect_dict(payload.get("metadata"), "metadata"),
    )


def _load_artifact_file(file_path: str) -> Any:
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Artifact file not found: {file_path}")
    content = path.read_text()
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(content)
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(content)

    stripped = content.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(content)
    return yaml.safe_load(content)


def _expect_list(value: Any, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"'{field_name}' must be a list.")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"'{field_name}' entries must be objects.")
    return value


def _expect_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"'{field_name}' must be a list of strings.")
    return value


def _expect_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"'{field_name}' must be an object.")
    return value
