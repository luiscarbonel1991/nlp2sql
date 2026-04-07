# Enterprise Guide

This guide explains how to use `nlp2sql` in larger, governed environments without coupling the library to any private warehouse vocabulary.

The recommended enterprise mindset is:

- use the DSL as the default integration surface
- constrain schema scope aggressively
- treat semantic context as a governed artifact
- use validation and repair intentionally

## Recommended Integration Shape

In most services, initialize once and reuse the client:

```python
import os

import nlp2sql
from nlp2sql import ProviderConfig, SemanticContext


nlp = await nlp2sql.connect(
    os.environ["DATABASE_URL"],
    provider=ProviderConfig(provider="openai", api_key=os.environ["OPENAI_API_KEY"]),
    schema_filters={
        "include_tables": ["stores", "marketing_channels", "daily_channel_metrics"],
        "exclude_system_tables": True,
    },
    semantic_context=SemanticContext(
        domain="ecommerce_channel_performance",
        canonical_tables=["daily_channel_metrics"],
    ),
)
```

This gives one reusable client with stable retrieval artifacts and governed defaults.

## Governed Usage Model

Enterprise usage is not just about generating SQL. It is about shaping the meaning of requests before the model writes SQL.

### The Governing Levers


| Lever               | Purpose                                                 |
| ------------------- | ------------------------------------------------------- |
| schema filters      | limit what the system can see                           |
| semantic context    | define canonical tables, metrics, dimensions, and rules |
| examples            | show approved query patterns                            |
| execution hooks     | validate and repair against a readonly target           |
| metadata inspection | observe why a query was generated the way it was        |


### Why Semantic Context Matters

In larger systems, multiple tables may look plausible for the same question. Semantic context helps the library distinguish between:

- canonical facts vs helper tables
- approved metrics vs similarly named raw columns
- required filters vs optional user hints
- allowed tables vs legacy or deprecated relations

That is the foundation for governed generation.

## Large Schema Strategy

### 1. Reduce Scope Early

```python
schema_filters = {
    "include_tables": [
        "stores",
        "marketing_channels",
        "daily_channel_metrics",
        "orders",
        "order_items",
    ],
    "exclude_system_tables": True,
}
```

Filters are applied before indexing, which improves speed and prompt quality.

### 2. Add Semantic Context

```python
from nlp2sql import DimensionDefinition, DomainRule, MetricDefinition, SemanticContext

semantic_context = SemanticContext(
    domain="ecommerce_channel_performance",
    canonical_tables=["daily_channel_metrics"],
    metric_definitions=[
        MetricDefinition(name="revenue", description="Daily revenue at the channel grain."),
        MetricDefinition(name="orders_count", description="Daily order count at the channel grain."),
    ],
    dimension_definitions=[
        DimensionDefinition(name="source_category", description="Marketing source grouping."),
    ],
    rules=[
        DomainRule(
            name="channel_breakdown_requires_source_category",
            description="Use source_category whenever the question asks for channel or source breakdown.",
            required_dimensions=["source_category"],
            preferred_tables=["daily_channel_metrics"],
        )
    ],
)
```

### 3. Add Approved Examples

Examples should reinforce valid query shapes, not replace the semantic layer.

### 4. Enable Validation and Repair Selectively

Use `validate=True` when you have a safe readonly execution target.

Use `repair=True` when:

- the user flow benefits from automatic retry
- extra latency is acceptable
- you have enough observability to inspect failures

## Multi-Provider Strategy

`nlp2sql` does not force a single provider. Typical strategies include:

- one default provider for normal traffic
- one higher-context provider for especially large schemas
- benchmark-based provider selection before rollout

Example benchmark:

```bash
nlp2sql benchmark \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --providers openai,anthropic,gemini \
  --questions benchmark_questions.txt \
  --examples-file examples.json \
  --semantic-context-file semantic-context.json
```

## Operational Guidance

## Caching

Use persistent directories for:

- schema embeddings
- example indexes

Warm caches reduce startup work and improve steady-state latency.

## Observability

Capture at least:

- question
- generated SQL
- provider
- validation status
- `semantic_context` metadata
- `sql_intent_plan`
- repair attempts

These fields are already exposed in `QueryResult.metadata`.

## Security

Recommended guardrails:

- connect through readonly credentials
- exclude sensitive tables with schema filters
- keep SQL safety checks enabled
- use audit logging around generated SQL and metadata

Example:

```python
audit_record = {
    "question": question,
    "sql": result.sql,
    "provider": result.provider,
    "is_valid": result.is_valid,
    "metadata": result.metadata,
}
```

## Deployment Patterns

## API Service

```python
from fastapi import FastAPI

app = FastAPI()


@app.post("/query")
async def query(payload: dict[str, str]):
    result = await nlp.ask(payload["question"], validate=True, repair=True)
    return {"sql": result.sql, "metadata": result.metadata}
```

## Worker or Batch Process

Reuse a single initialized client per worker process and send multiple `ask()` calls through it.

## Serverless

Possible, but less ideal when you depend on warm retrieval caches. If you use serverless, consider externalizing or warming cache directories when possible.

## Migration Guidance

If you already have a custom NL-to-SQL service, migrate in layers:

1. replace direct provider prompting with `connect()` and `ask()`
2. add schema filters
3. move business rules into `SemanticContext`
4. add examples only after semantic scope is stable
5. enable validation and repair

That order keeps governance logic explicit and avoids overfitting to examples.

## Public Example Domain

All public documentation examples in this repository use the local e-commerce schema:

- `stores`
- `marketing_channels`
- `daily_channel_metrics`
- `orders`
- `order_items`

This keeps the enterprise guidance reproducible while still demonstrating realistic governance patterns.

## Related Docs

- [README](../README.md)
- [Architecture](ARCHITECTURE.md)
- [API Reference](API.md)
- [Configuration](CONFIGURATION.md)

