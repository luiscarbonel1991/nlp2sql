# Amazon Redshift Support

`nlp2sql` supports Redshift as a first-class warehouse target while keeping the same DSL and semantic model used for PostgreSQL.

The public examples here stay generic and use the repository's own e-commerce-style concepts rather than any private warehouse naming.

## What Changes for Redshift

At the API level, very little changes:

- use a `redshift://` URL or a compatible PostgreSQL-style Redshift URL
- keep using `connect()` and `ask()`
- use schema filters aggressively on large warehouses
- use semantic context when questions could map to multiple fact tables

## Recommended Python Usage

```python
import os

import nlp2sql
from nlp2sql import ProviderConfig, SemanticContext


nlp = await nlp2sql.connect(
    "redshift://user:password@cluster.region.redshift.amazonaws.com:5439/analytics",
    provider=ProviderConfig(provider="anthropic", api_key=os.environ["ANTHROPIC_API_KEY"]),
    schema="analytics",
    schema_filters={
        "include_tables": [
            "stores",
            "marketing_channels",
            "daily_channel_metrics",
        ],
        "exclude_system_tables": True,
    },
    semantic_context=SemanticContext(
        domain="ecommerce_channel_performance",
        canonical_tables=["daily_channel_metrics"],
    ),
)

result = await nlp.ask(
    "Show daily revenue by source category for the flagship store",
    validate=True,
    repair=True,
)
```

## Recommended CLI Usage

```bash
nlp2sql query \
  --database-url redshift://user:password@cluster.region.redshift.amazonaws.com:5439/analytics \
  --schema analytics \
  --provider anthropic \
  --question "Show daily revenue by source category for the flagship store" \
  --semantic-context-file semantic-context.json \
  --examples-file examples.json \
  --validate \
  --repair \
  --show-semantic-context \
  --show-sql-intent-plan
```

## Connection Formats

Standard Redshift cluster:

```bash
redshift://username:password@cluster-id.region.redshift.amazonaws.com:5439/database
```

Redshift Serverless:

```bash
redshift://username:password@workgroup.account.region.redshift-serverless.amazonaws.com:5439/database
```

Compatible PostgreSQL-style URL:

```bash
postgresql://username:password@cluster-id.region.redshift.amazonaws.com:5439/database
```

## Redshift Guidance

## 1. Keep Scope Small

Warehouse schemas often contain staging, helper, and legacy tables. Prefer:

- `include_schemas`
- `include_tables`
- `exclude_tables`
- `exclude_system_tables`

This improves both retrieval quality and performance.

## 2. Use Semantic Context for Canonical Facts

If multiple Redshift tables could satisfy the same question, use semantic context to define:

- the canonical fact table
- required dimensions
- required filters
- disallowed tables

This is usually more reliable than relying on examples alone.

## 3. Use Examples to Reinforce Approved Patterns

Few-shot examples are still useful, especially when you need:

- preferred join patterns
- preferred date logic
- preferred naming of derived metrics

But examples work best when the semantic layer has already narrowed the solution space.

## Redshift-Specific Implementation Notes

- metadata discovery uses Redshift-appropriate system views
- disk caching is especially helpful because warehouse catalog scans are relatively expensive
- Redshift benefits more than small PostgreSQL databases from warm retrieval caches and strong schema filters

## Troubleshooting

### Connection Errors

Check:

- network access and allowlists
- SSL requirements
- schema permissions
- readonly access for validation flows

### Empty or Wrong Results

If SQL executes but the answer is semantically wrong:

- inspect `semantic_context`
- inspect `sql_intent_plan`
- verify your schema filters are narrow enough
- add or improve semantic context before adding more examples

### Embedding Dimension Mismatch

If you see a message about index dimensions not matching the current embedding provider:

```bash
nlp2sql cache clear --embeddings
```

Then rerun with the intended embedding provider.

## Local Testing

The repository also includes local Redshift-oriented test infrastructure through Docker and LocalStack-style flows. Use that for development rather than depending on private infrastructure names in docs or examples.

## Related Docs

- [README](../README.md)
- [Architecture](ARCHITECTURE.md)
- [API Reference](API.md)
- [Configuration](CONFIGURATION.md)

