<p align="center">
  <img src="assets/nlp2sql-logo.png" alt="nlp2sql logo" width="400">
</p>

<p align="center">
  <a href="https://pepy.tech/projects/nlp2sql"><img src="https://static.pepy.tech/personalized-badge/nlp2sql?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads" alt="PyPI Downloads"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+"></a>
  <a href="https://github.com/psf/black"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
</p>

# nlp2sql

**DSL-first natural language to SQL for PostgreSQL and Redshift**

`nlp2sql` turns a natural language question into SQL through a reusable Python DSL:

- `await connect(...)`
- `await nlp.ask(...)`
- optional few-shot examples
- optional semantic context
- optional validation and repair

The library is designed for both simple schemas and large warehouses, but all public examples in this repository use the local e-commerce domain shipped with the project itself.

## Features

- **DSL-first API**: `connect()` returns an `NLP2SQL` client with `ask()`, `validate()`, `explain()`, and `suggest()`
- **Business-aware generation**: optional `SemanticContext` adds canonical tables, metrics, dimensions, rules, and mappings
- **Execution modes**: generate only, generate plus validate, and generate plus validate plus repair
- **Few-shot examples**: pass example lists directly or use an example repository implementation
- **Large schema support**: FAISS plus TF-IDF hybrid retrieval, schema filters, and disk-backed caches
- **Multiple providers**: OpenAI, Anthropic, and Gemini
- **Database support**: PostgreSQL and Amazon Redshift
- **Async by default**: built for services, APIs, notebooks, and workers

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | Runtime flow, services, ports, and diagrams |
| [API Reference](docs/API.md) | Python API, CLI, hooks, and metadata reference |
| [Configuration](docs/CONFIGURATION.md) | Environment variables, examples, semantic context, cache behavior |
| [Enterprise Guide](docs/ENTERPRISE.md) | Governed usage, scale, and deployment patterns |
| [Redshift Support](docs/Redshift.md) | Redshift-specific notes using public examples |
| [Examples](examples/README.md) | Safe public examples based on the local e-commerce domain |
| [Contributing](CONTRIBUTING.md) | Contribution guidelines |

## Installation

```bash
# With UV (recommended)
uv add nlp2sql

# With pip
pip install nlp2sql

# With specific providers
pip install nlp2sql[anthropic,gemini]
pip install nlp2sql[all-providers]

# With embeddings
pip install nlp2sql[embeddings-local]
pip install nlp2sql[embeddings-openai]
```

## Quick Start

### 1. Set a Provider Key

```bash
export OPENAI_API_KEY="your-openai-key"
# or ANTHROPIC_API_KEY / GOOGLE_API_KEY
```

### 2. Use the DSL

```python
import asyncio

import nlp2sql
from nlp2sql import ProviderConfig


async def main():
    nlp = await nlp2sql.connect(
        "postgresql://testuser:testpass@localhost:5432/testdb",
        provider=ProviderConfig(provider="openai", api_key="sk-..."),
    )

    result = await nlp.ask("Show active users by region")
    print(result.sql)
    print(result.confidence)
    print(result.metadata["sql_intent_plan"])


asyncio.run(main())
```

`connect()` loads the schema, initializes retrieval indexes, and returns a reusable `NLP2SQL` client. `ask()` returns a typed `QueryResult`.

### 3. Add Few-Shot Examples

Pass examples directly to `connect()`. The library handles indexing for you.

```python
nlp = await nlp2sql.connect(
    "postgresql://testuser:testpass@localhost:5432/testdb",
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
    examples=[
        {
            "question": "Show revenue by source category for the flagship store",
            "sql": (
                "SELECT d.metric_date, mc.source_category, SUM(d.revenue) AS revenue "
                "FROM daily_channel_metrics d "
                "JOIN stores s ON d.store_id = s.id "
                "JOIN marketing_channels mc ON d.channel_id = mc.id "
                "WHERE s.code = 'na_flagship' "
                "GROUP BY d.metric_date, mc.source_category"
            ),
            "database_type": "postgres",
        }
    ],
)
```

### 4. Add In-Memory Semantic Context

Use semantic context when the same question could map to multiple plausible tables or dimensions.

```python
from nlp2sql import (
    DimensionDefinition,
    DomainRule,
    MetricDefinition,
    SemanticContext,
    SemanticEntityMapping,
)

semantic_context = SemanticContext(
    domain="ecommerce_channel_performance",
    canonical_tables=["daily_channel_metrics"],
    required_filters=["s.code = 'na_flagship'", "s.region = 'North America'"],
    entity_mappings=[
        SemanticEntityMapping(
            source_term="North America flagship store",
            target="store_scope",
            resolved_value="na_flagship / North America",
            filter_expression="s.code = 'na_flagship' AND s.region = 'North America'",
        )
    ],
    metric_definitions=[
        MetricDefinition(name="revenue", description="Revenue by day and source category."),
        MetricDefinition(name="orders_count", description="Orders by day and source category."),
    ],
    dimension_definitions=[
        DimensionDefinition(name="metric_date", description="Daily grain."),
        DimensionDefinition(name="source_category", description="Channel grouping."),
    ],
    rules=[
        DomainRule(
            name="preserve_source_breakdown",
            description="Keep source_category when the question asks for a source breakdown.",
            required_dimensions=["source_category"],
            preferred_tables=["daily_channel_metrics"],
        )
    ],
)

result = await nlp.ask(
    "Show daily revenue and order count by source category for the North America flagship store",
    semantic_context=semantic_context,
)
```

### 5. Validate and Repair

`ask()` supports execution-aware modes directly.

```python
result = await nlp.ask(
    "Show revenue by source category for the flagship store",
    validate=True,
    repair=True,
)
```

- `generate_only`: generate SQL only
- `generate_and_validate`: execute readonly validation when execution is wired
- `generate_validate_repair`: retry on semantic or execution failures when repair hooks are available

### 6. CLI Parity

The CLI exposes the same concepts:

```bash
nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Show daily revenue by source category for the North America flagship store" \
  --examples-file examples.json \
  --semantic-context-file semantic-context.json \
  --validate \
  --repair \
  --show-semantic-context \
  --show-sql-intent-plan \
  --show-selected-examples
```

## How It Works

```mermaid
flowchart TD
    userCode[UserCodeOrCLI] --> dsl[connectAndAskDSL]
    dsl --> analysis[QueryAnalysisService]
    analysis --> semantic[SemanticResolutionService]
    semantic --> retrieval[SchemaRetrievalAndExampleSelection]
    retrieval --> intent[SqlIntentPlanningService]
    intent --> prompt[PromptAssemblyAndAdapters]
    prompt --> llm[LLMGeneration]
    llm --> semval[SemanticValidation]
    semval --> exec[OptionalExecutionAndRepair]
    exec --> result[QueryResultMetadata]
```

At runtime the library:

1. analyzes the question
2. optionally resolves and merges semantic context
3. retrieves relevant schema and examples
4. builds a structured SQL intent plan
5. assembles the prompt
6. generates SQL
7. optionally validates, executes, and repairs
8. returns a `QueryResult` with debug metadata

See [Architecture](docs/ARCHITECTURE.md) for the full breakdown.

## Public Example Domain

This repository ships a local e-commerce integration domain used in tests and docs. It includes:

- `stores`
- `marketing_channels`
- `users`
- `products`
- `orders`
- `order_items`
- `daily_channel_metrics`

The public examples intentionally stay inside that domain to avoid leaking any private warehouse schema.

To start it locally:

```bash
cd docker
docker compose up -d postgres
```

The default URL is:

```bash
postgresql://testuser:testpass@localhost:5432/testdb
```

## Provider Comparison

| Provider | Default Model | Context Size | Best For |
|----------|---------------|--------------|----------|
| OpenAI | `gpt-4o-mini` | 128K | Fast general purpose usage |
| Anthropic | `claude-sonnet-4-20250514` | 200K | Larger schemas and long prompts |
| Gemini | `gemini-2.0-flash` | 1M | High-volume and very large contexts |

All models are configurable through `ProviderConfig`.

## Lower-Level API

`connect()` is the recommended path. Lower-level entry points still exist for advanced wiring:

```python
from nlp2sql import DatabaseType, ProviderConfig, create_and_initialize_service

service = await create_and_initialize_service(
    database_url="postgresql://testuser:testpass@localhost:5432/testdb",
    provider_config=ProviderConfig(provider="openai", api_key="sk-..."),
    database_type=DatabaseType.POSTGRES,
)

result = await service.generate_sql(
    "Count active users by region",
    database_type=DatabaseType.POSTGRES,
)
print(result["sql"])
```

## Development

```bash
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql
uv sync

# Start the local public e-commerce database
cd docker && docker compose up -d postgres

# Integration tests without llm
cd ..
uv run pytest -m "integration and not llm"

# Optional llm integration tests
uv run pytest -m "integration and llm"
```

## MCP Server

`nlp2sql` includes a Model Context Protocol server for assistant integration.

```json
{
  "mcpServers": {
    "nlp2sql": {
      "command": "python",
      "args": ["/path/to/nlp2sql/mcp_server/server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "NLP2SQL_DEFAULT_DB_URL": "postgresql://testuser:testpass@localhost:5432/testdb"
      }
    }
  }
}
```

See [mcp_server/README.md](mcp_server/README.md) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License. See [LICENSE](LICENSE).
