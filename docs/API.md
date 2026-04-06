# API Reference

This document covers the public Python API and the CLI surface. The recommended path is the DSL:

- `await connect(...)`
- `await nlp.ask(...)`

## Python API

### Entry Points

```text
nlp2sql.connect(url, provider=...)         # recommended DSL entry point
  -> NLP2SQL.ask(question, ...)
  -> NLP2SQL.validate(sql)
  -> NLP2SQL.explain(sql)
  -> NLP2SQL.suggest(partial)

create_and_initialize_service(url, ...)    # lower-level service factory
create_query_service(...)                   # manual wiring + manual initialize
generate_sql_from_db(url, question, ...)   # one-shot helper
```


| Function                          | Best for                              |
| --------------------------------- | ------------------------------------- |
| `connect()`                       | services, APIs, notebooks, workers    |
| `create_and_initialize_service()` | advanced integration and custom ports |
| `generate_sql_from_db()`          | quick scripts and experiments         |


## `connect(...)`

```python
import nlp2sql
from nlp2sql import ProviderConfig

nlp = await nlp2sql.connect(
    "postgresql://testuser:testpass@localhost:5432/testdb",
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
)
```

### Common Parameters


| Parameter                 | Type                                        | Description                                                         |
| ------------------------- | ------------------------------------------- | ------------------------------------------------------------------- |
| `database_url`            | `str`                                       | Database connection URL                                             |
| `provider`                | `ProviderConfig | None`                     | Provider config, otherwise resolved from environment                |
| `schema`                  | `str | None`                                | Schema name, usually `public` for PostgreSQL                        |
| `database_type`           | `DatabaseType | None`                       | Optional explicit override                                          |
| `schema_filters`          | `dict | None`                               | Include or exclude schemas and tables                               |
| `examples`                | `list[dict] | ExampleRepositoryPort | None` | Few-shot examples or custom repository                              |
| `embedding_provider`      | `EmbeddingProviderPort | None`              | Custom embedding provider instance                                  |
| `embedding_provider_type` | `str | None`                                | Auto-create embedding provider, typically `local` or `openai`       |
| `hooks`                   | `ExecutionHooks | None`                     | Execution, classification, and repair hooks                         |
| `semantic_hooks`          | `SemanticHooks | None`                      | Semantic resolver, validator, and optional default semantic context |
| `semantic_context`        | `SemanticContext | dict | None`             | Default semantic context applied to future `ask()` calls            |


### `hooks`

`hooks` is where execution-related behavior lives. Typical uses:

- plugging in a query execution port
- classifying runtime failures
- defining repair behavior

This is what enables `validate=True` and `repair=True` to do more than prompt-only validation.

### `semantic_hooks`

`semantic_hooks` is the semantic counterpart:

- `semantic_resolver`
- `semantic_validator`
- `semantic_context`

Use it when your service wants shared business semantics for every call from that client instance.

### `semantic_context`

You can also pass semantic context directly into `connect()`. That context becomes the default for the client and may later be overridden per request in `ask(...)`.

## `ProviderConfig`

```python
from nlp2sql import ProviderConfig

config = ProviderConfig(
    provider="openai",
    api_key="sk-...",
    model="gpt-4o",
    temperature=0.0,
    max_tokens=4000,
)
```


| Field         | Meaning                            |
| ------------- | ---------------------------------- |
| `provider`    | `openai`, `anthropic`, or `gemini` |
| `api_key`     | provider credential                |
| `model`       | optional explicit model            |
| `temperature` | generation temperature             |
| `max_tokens`  | response budget                    |


## `NLP2SQL.ask(...)`

```python
result = await nlp.ask(
    "Show revenue and order count by source category for the North America flagship store",
    validate=True,
    repair=True,
)
```

### Common Parameters


| Parameter          | Type                            | Description                                            |
| ------------------ | ------------------------------- | ------------------------------------------------------ |
| `question`         | `str`                           | Natural language request                               |
| `validate`         | `bool`                          | Run validation behavior if execution is available      |
| `repair`           | `bool`                          | Allow repair attempts on semantic or execution failure |
| `execution_mode`   | `str | None`                    | Explicit mode override                                 |
| `timeout_seconds`  | `int | float | None`            | Optional timeout for execution-aware flows             |
| `semantic_context` | `SemanticContext | dict | None` | Per-request semantic override                          |


### Execution Modes

`ask()` supports three practical modes:


| Mode                       | Meaning                                       |
| -------------------------- | --------------------------------------------- |
| `generate_only`            | Generate SQL and stop                         |
| `generate_and_validate`    | Generate and validate execution when possible |
| `generate_validate_repair` | Generate, validate, and attempt repair        |


If you do not pass `execution_mode`, the library infers it from `validate` and `repair`.

## `QueryResult`

`ask()` returns a typed `QueryResult`.


| Field                | Type                | Description                                    |
| -------------------- | ------------------- | ---------------------------------------------- |
| `sql`                | `str`               | Generated SQL                                  |
| `confidence`         | `float`             | Confidence score                               |
| `is_valid`           | `bool`              | Final validation state                         |
| `explanation`        | `str | None`        | Optional natural-language explanation          |
| `provider`           | `str`               | Provider that generated the SQL                |
| `database_type`      | `str`               | Postgres or Redshift                           |
| `tokens_used`        | `int`               | Tokens consumed                                |
| `generation_time_ms` | `float`             | End-to-end generation time                     |
| `examples_used`      | `int`               | Count of selected examples                     |
| `metadata`           | `dict[str, object]` | Runtime metadata for debugging and integration |


### `QueryResult.metadata`

The metadata payload is intentionally rich. Common fields include:


| Key                    | Description                                   |
| ---------------------- | --------------------------------------------- |
| `semantic_context`     | Resolved semantic context used for the call   |
| `sql_intent_plan`      | Structured intent plan built before prompting |
| `selected_examples`    | Few-shot examples selected for prompting      |
| `repair_attempts`      | Repair loop details when repair is enabled    |
| `execution_validation` | Execution-time validation outcome             |
| `analysis`             | Query analysis hints                          |


Exact contents may vary by runtime path and enabled hooks.

## Few-Shot Examples

Pass examples as plain dictionaries and the library will build or reuse the retrieval index automatically:

```python
examples = [
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
]

nlp = await nlp2sql.connect(
    "postgresql://testuser:testpass@localhost:5432/testdb",
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
    examples=examples,
)
```

If you need more control, provide an `ExampleRepositoryPort` implementation instead.

## Semantic Context

Semantic context may be passed either through `connect()` or per call via `ask()`.

```python
from nlp2sql import (
    DimensionDefinition,
    DomainRule,
    MetricDefinition,
    SemanticContext,
)

semantic_context = SemanticContext(
    domain="ecommerce_channel_performance",
    canonical_tables=["daily_channel_metrics"],
    required_filters=["s.code = 'na_flagship'"],
    metric_definitions=[
        MetricDefinition(name="revenue", description="Channel revenue by day."),
        MetricDefinition(name="orders_count", description="Order count by day."),
    ],
    dimension_definitions=[
        DimensionDefinition(name="source_category", description="Channel grouping."),
    ],
    rules=[
        DomainRule(
            name="keep_source_category",
            description="Use source_category when the question asks for channel or source breakdown.",
            required_dimensions=["source_category"],
            preferred_tables=["daily_channel_metrics"],
        )
    ],
)

result = await nlp.ask(
    "Show revenue by source category for the flagship store",
    semantic_context=semantic_context,
)
```

## Lower-Level Service API

Use the service layer only when you need full control over dependency injection.

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
print(result["validation"]["is_valid"])
```

## Error Handling

```python
from nlp2sql.exceptions import (
    ProviderException,
    QueryGenerationException,
    SchemaException,
    SecurityException,
    TokenLimitException,
)

try:
    result = await nlp.ask("Show revenue by month")
except TokenLimitException:
    print("The schema context is too large. Add schema filters.")
except SchemaException:
    print("Database connection or schema discovery failed.")
except QueryGenerationException:
    print("The provider could not generate SQL.")
except ProviderException:
    print("Provider auth, network, or rate-limit error.")
except SecurityException:
    print("Generated SQL failed safety checks.")
```

## CLI Reference

### `nlp2sql query`

Generate SQL from natural language.

```bash
nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --provider openai \
  --question "Show daily revenue by source category for the North America flagship store" \
  --examples-file examples/ecommerce_examples.json \
  --semantic-context-file examples/ecommerce_semantic_context.json \
  --validate \
  --repair \
  --show-semantic-context \
  --show-sql-intent-plan \
  --show-selected-examples
```

### Important Query Options


| Option                     | Meaning                                  |
| -------------------------- | ---------------------------------------- |
| `--database-url`           | Database connection URL                  |
| `--schema`                 | Schema name                              |
| `--provider`               | `openai`, `anthropic`, or `gemini`       |
| `--api-key`                | Explicit provider key                    |
| `--embedding-provider`     | Example and schema embedding provider    |
| `--schema-filters`         | JSON schema filters                      |
| `--examples-file`          | Load few-shot examples from JSON or YAML |
| `--examples-json`          | Inline example payload                   |
| `--semantic-context-file`  | Load semantic context from JSON or YAML  |
| `--semantic-context-json`  | Inline semantic context payload          |
| `--validate`               | Enable execution validation              |
| `--repair`                 | Enable repair loop                       |
| `--show-semantic-context`  | Print resolved semantic context          |
| `--show-sql-intent-plan`   | Print generated SQL intent plan          |
| `--show-selected-examples` | Print selected few-shot examples         |


These flags are the CLI equivalents of the Python DSL features.

### `nlp2sql benchmark`

Benchmark one or more providers against the same workload.

```bash
nlp2sql benchmark \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --providers openai,anthropic \
  --questions benchmark_questions.txt \
  --examples-file examples/ecommerce_examples.json \
  --semantic-context-file examples/ecommerce_semantic_context.json \
  --iterations 2
```

The benchmark command also accepts examples and semantic context so provider comparisons stay fair.

### `nlp2sql inspect`

Inspect the schema available to the library:

```bash
nlp2sql inspect \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --include-tables stores,marketing_channels,daily_channel_metrics \
  --format table
```

### `nlp2sql cache`

Inspect or clear caches:

```bash
nlp2sql cache info
nlp2sql cache clear --embeddings
nlp2sql cache clear --queries
```

Clearing embeddings is required when switching embedding models or providers for an existing on-disk index.

## Integration Example

### FastAPI

```python
import os
from contextlib import asynccontextmanager

import nlp2sql
from fastapi import FastAPI
from nlp2sql import ProviderConfig, SemanticContext


client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = await nlp2sql.connect(
        os.getenv("DATABASE_URL"),
        provider=ProviderConfig(provider="openai", api_key=os.getenv("OPENAI_API_KEY")),
        semantic_context=SemanticContext(
            domain="ecommerce_channel_performance",
            canonical_tables=["daily_channel_metrics"],
        ),
    )
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/query")
async def query(payload: dict[str, str]):
    result = await client.ask(payload["question"], validate=True, repair=True)
    return {"sql": result.sql, "metadata": result.metadata}
```

## Related Docs

- [README](../README.md)
- [Architecture](ARCHITECTURE.md)
- [Configuration](CONFIGURATION.md)

