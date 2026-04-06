# nlp2sql Examples

This directory complements the main documentation. The recommended public baseline for examples is:

- the DSL: `connect()` plus `ask()`
- the repository's local e-commerce schema
- optional semantic context
- optional few-shot examples

## Public Baseline

All public-facing examples should stay aligned with the local e-commerce domain used in tests and docs:

- `stores`
- `marketing_channels`
- `users`
- `products`
- `orders`
- `order_items`
- `daily_channel_metrics`

This keeps the examples portable and avoids leaking any private warehouse vocabulary.

## Recommended Learning Path

## 1. Start the Local Database

```bash
cd docker
docker compose up -d postgres
```

Default URL:

```bash
export DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb"
```

## 2. Set a Provider Key

```bash
export OPENAI_API_KEY="your-openai-key"
```

## 3. Start with the DSL

```python
import nlp2sql
from nlp2sql import ProviderConfig


nlp = await nlp2sql.connect(
    database_url,
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
)

result = await nlp.ask("Show active users by region")
print(result.sql)
```

## 4. Add Semantic Context

Use semantic context when the same question could map to multiple tables or business meanings.

```python
from nlp2sql import SemanticContext

result = await nlp.ask(
    "Show revenue by source category for the flagship store",
    semantic_context=SemanticContext(
        domain="ecommerce_channel_performance",
        canonical_tables=["daily_channel_metrics"],
    ),
)
```

## 5. Add Examples

Examples should support the semantic layer, not replace it.

```python
examples = [
    {
        "question": "Show revenue by source category for the flagship store",
        "sql": "SELECT ...",
        "database_type": "postgres",
    }
]

nlp = await nlp2sql.connect(
    database_url,
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
    examples=examples,
)
```

## CLI Equivalents

The same concepts are available from the CLI:

```bash
nlp2sql query \
  --database-url "$DATABASE_URL" \
  --question "Show revenue by source category for the flagship store" \
  --validate \
  --repair
```

With semantic context and examples:

```bash
nlp2sql query \
  --database-url "$DATABASE_URL" \
  --question "Show revenue by source category for the flagship store" \
  --examples-file examples.json \
  --semantic-context-file semantic-context.json \
  --validate \
  --repair \
  --show-semantic-context \
  --show-sql-intent-plan \
  --show-selected-examples
```

## Example Categories

Use the subdirectories here as implementation references, but keep new public examples aligned with the DSL-first model and the local e-commerce domain.

Useful categories include:

- getting started
- advanced provider comparison
- schema management
- API service integration

## Writing New Public Examples

Prefer examples that:

- use `connect()` and `ask()`
- reference local e-commerce tables only
- show semantic context explicitly when business meaning matters
- demonstrate `validate` and `repair` when execution behavior is relevant

Avoid examples that:

- depend on private schema names
- assume unreproducible external warehouse state
- rely only on examples when semantic context is the real governing mechanism

## Related Docs

- [README](../README.md)
- [API Reference](../docs/API.md)
- [Architecture](../docs/ARCHITECTURE.md)
- [Configuration](../docs/CONFIGURATION.md)
