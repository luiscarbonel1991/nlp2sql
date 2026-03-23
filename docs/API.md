# API Reference

Complete reference for the nlp2sql Python API and CLI.

## Python API

### Entry Points

```
nlp2sql.connect(url, provider=...)         # DSL: returns NLP2SQL client (recommended)
  └─ nlp.ask(question)                     # returns QueryResult (.sql, .confidence, .is_valid)
  └─ nlp.validate(sql)                     # validate a SQL string
  └─ nlp.explain(sql)                      # explain a SQL query
  └─ nlp.suggest(partial)                  # autocomplete suggestions

create_and_initialize_service(url, ...)    # lower-level: returns QueryGenerationService
  └─ service.generate_sql(question, ...)   # returns dict

generate_sql_from_db(url, question, ...)   # one-shot: creates everything per call
```

**When to use which:**

| Function | Best for | Schema loading |
|----------|----------|----------------|
| `nlp2sql.connect()` | Most users, APIs, notebooks | Once at startup |
| `create_and_initialize_service` | Custom wiring, legacy code | Once at startup |
| `generate_sql_from_db` | One-off scripts | Every call |

### `nlp2sql.connect()` (Recommended)

```python
import nlp2sql
from nlp2sql import ProviderConfig

nlp = await nlp2sql.connect(
    "postgresql://user:pass@localhost:5432/mydb",
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
)

result = await nlp.ask("Show me all active users")
print(result.sql)           # Generated SQL
print(result.confidence)    # 0.0 - 1.0
print(result.is_valid)      # bool
print(result.explanation)   # Natural language explanation
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `database_url` | `str` | Yes | Database connection URL |
| `provider` | `ProviderConfig` | No | AI provider configuration (falls back to env vars) |
| `schema` | `str` | No | Database schema name (default: `"public"`) |
| `database_type` | `DatabaseType` | No | Auto-detected from URL if not provided |
| `schema_filters` | `dict` | No | Schema filtering options |
| `examples` | `list[dict]` or `ExampleRepositoryPort` | No | Few-shot examples (see below) |
| `embedding_provider` | `EmbeddingProviderPort` | No | Pre-built embedding provider |
| `embedding_provider_type` | `str` | No | Auto-create embeddings: `"local"` or `"openai"` |

**Returns:** `NLP2SQL` client with `.ask()`, `.validate()`, `.explain()`, `.suggest()` methods.

### `ProviderConfig`

Unified configuration for AI providers:

```python
from nlp2sql import ProviderConfig

config = ProviderConfig(
    provider="openai",          # "openai", "anthropic", "gemini"
    api_key="sk-...",           # or use env vars
    model="gpt-4o",            # None = provider default
    temperature=0.1,            # None = 0.1
    max_tokens=2000,            # None = 2000
)

# Check resolved model
print(config.resolved_model)  # "gpt-4o" (or default if model=None)
```

**Default models per provider:**

| Provider | Default Model |
|----------|--------------|
| openai | gpt-4o-mini |
| anthropic | claude-sonnet-4-20250514 |
| gemini | gemini-2.0-flash |

### `QueryResult`

Typed result from `nlp.ask()`:

| Field | Type | Description |
|-------|------|-------------|
| `sql` | `str` | Generated SQL query |
| `confidence` | `float` | Confidence score (0.0 - 1.0) |
| `is_valid` | `bool` | SQL validation result |
| `explanation` | `str \| None` | Natural language explanation |
| `provider` | `str` | Provider that generated the SQL |
| `database_type` | `str` | Database type used |
| `tokens_used` | `int` | Tokens consumed |
| `generation_time_ms` | `float` | Generation time in milliseconds |
| `examples_used` | `int` | Number of few-shot examples included |
| `metadata` | `dict` | Additional metadata |

### Few-Shot Examples

Pass a plain list of dicts to `connect()` -- it handles embedding and FAISS indexing:

```python
nlp = await nlp2sql.connect(
    "redshift://user:pass@host:5439/db",
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
    schema="dwh_data_share_llm",
    examples=[
        {
            "question": "Total revenue last month?",
            "sql": "SELECT SUM(revenue) FROM sales WHERE date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')",
            "database_type": "redshift",
        },
        {
            "question": "Orders by country",
            "sql": "SELECT country, COUNT(*) FROM orders GROUP BY country ORDER BY 2 DESC",
            "database_type": "redshift",
        },
    ],
)
```

For advanced control, pass an `ExampleRepositoryPort` instance instead.

### Error Handling

```python
from nlp2sql.exceptions import (
    SchemaException,
    QueryGenerationException,
    TokenLimitException,
    ProviderException,
    SecurityException,
)

try:
    result = await nlp.ask("Show revenue by month")
except TokenLimitException:
    print("Schema too large -- add schema_filters")
except SchemaException:
    print("Database connection or schema error")
except QueryGenerationException:
    print("AI provider failed to generate SQL")
except ProviderException:
    print("AI provider API error (rate limit, auth, etc.)")
```

### Advanced: Direct Service Access

For full control over the lifecycle:

```python
from nlp2sql import create_and_initialize_service, ProviderConfig, DatabaseType

service = await create_and_initialize_service(
    database_url="postgresql://localhost/mydb",
    provider_config=ProviderConfig(provider="openai", api_key="sk-..."),
    database_type=DatabaseType.POSTGRES,
)

# Returns raw dict (not QueryResult)
result = await service.generate_sql("Count total users", database_type=DatabaseType.POSTGRES)
print(result["sql"])
print(result["validation"]["is_valid"])
```

---

## CLI Reference

### Installation Verification

```bash
uv run nlp2sql --help
uv run nlp2sql validate
```

### Core Commands

#### `nlp2sql query`

Generate SQL from natural language.

```bash
# Basic query (auto-detects provider)
nlp2sql query \
  --database-url postgresql://user:pass@localhost:5432/db \
  --question "Show me all active users"

# Specify provider
nlp2sql query \
  --database-url postgresql://user:pass@localhost:5432/db \
  --question "Count total orders" \
  --provider anthropic

# With explanation and schema filters
nlp2sql query \
  --database-url postgresql://user:pass@localhost:5432/db \
  --question "Show sales by region" \
  --provider openai \
  --explain \
  --schema-filters '{"include_schemas": ["sales"], "exclude_system_tables": true}'
```

**Options:**
| Option | Description |
|--------|-------------|
| `--database-url` | Database connection URL |
| `--question` | Natural language question |
| `--provider` | AI provider: `openai`, `anthropic`, `gemini` |
| `--api-key` | API key (or use environment variable) |
| `--explain` | Include detailed explanation |
| `--temperature` | Model creativity (0.0-1.0) |
| `--max-tokens` | Maximum response tokens |
| `--schema-filters` | JSON string with schema filters |

#### `nlp2sql inspect`

Inspect database schema.

```bash
# Basic inspection
nlp2sql inspect --database-url postgresql://user:pass@localhost:5432/db

# Filtered inspection
nlp2sql inspect \
  --database-url postgresql://user:pass@localhost:5432/db \
  --exclude-system \
  --min-rows 1000 \
  --sort-by size \
  --format json \
  --output schema.json

# Specific tables
nlp2sql inspect \
  --database-url postgresql://user:pass@localhost:5432/db \
  --include-tables users,products,orders \
  --format table
```

**Options:**
| Option | Description |
|--------|-------------|
| `--include-tables` | Comma-separated tables to include |
| `--exclude-tables` | Comma-separated tables to exclude |
| `--exclude-system` | Exclude system tables |
| `--min-rows` | Minimum row count filter |
| `--max-tables` | Limit number of tables shown |
| `--sort-by` | Sort by: `name`, `rows`, `size`, `columns` |
| `--format` | Output: `summary`, `json`, `table`, `csv` |
| `--output` | Output file path |

#### `nlp2sql benchmark`

Benchmark AI providers.

```bash
# Benchmark all available providers
nlp2sql benchmark \
  --database-url postgresql://user:pass@localhost:5432/db

# Custom benchmark
nlp2sql benchmark \
  --database-url postgresql://user:pass@localhost:5432/db \
  --questions benchmark_questions.txt \
  --providers openai,anthropic,gemini \
  --iterations 3
```

**Options:**
| Option | Description |
|--------|-------------|
| `--questions` | File with test questions (one per line) |
| `--providers` | Comma-separated providers to test |
| `--iterations` | Number of iterations per test |
| `--schema-filters` | JSON string with schema filters |

#### `nlp2sql providers`

Manage AI providers.

```bash
# List providers and status
nlp2sql providers list

# Test provider connections
nlp2sql providers test
nlp2sql providers test --provider openai
```

#### `nlp2sql cache`

Manage cache.

```bash
# Show cache info
nlp2sql cache info

# Clear cache
nlp2sql cache clear --all
nlp2sql cache clear --embeddings
nlp2sql cache clear --queries
```

#### `nlp2sql setup` and `nlp2sql validate`

Setup and validation.

```bash
# Interactive setup
nlp2sql setup

# Validate configuration
nlp2sql validate
nlp2sql validate -v  # Verbose
```

---

## Integration Examples

### FastAPI

```python
import os
from contextlib import asynccontextmanager

import nlp2sql
from fastapi import FastAPI, HTTPException
from nlp2sql import ProviderConfig
from pydantic import BaseModel

nlp_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global nlp_client
    nlp_client = await nlp2sql.connect(
        os.getenv("DATABASE_URL"),
        provider=ProviderConfig(provider="openai", api_key=os.getenv("OPENAI_API_KEY")),
    )
    yield

app = FastAPI(lifespan=lifespan)

class QueryRequest(BaseModel):
    question: str

@app.post("/query")
async def generate_query(request: QueryRequest):
    result = await nlp_client.ask(request.question)
    return {"sql": result.sql, "confidence": result.confidence, "valid": result.is_valid}
```

### Jupyter Notebook

```python
import nlp2sql
from nlp2sql import ProviderConfig

nlp = await nlp2sql.connect(
    "postgresql://localhost/analytics",
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
)

result = await nlp.ask("Show user engagement by month")
print(result.sql)

# Execute with pandas
import pandas as pd
df = pd.read_sql(result.sql, "postgresql://localhost/analytics")
df.head()
```

---

For configuration options including environment variables and schema filters, see [CONFIGURATION.md](CONFIGURATION.md).
