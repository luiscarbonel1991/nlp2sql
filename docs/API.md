# API Reference

Complete reference for the nlp2sql Python API and CLI.

## Python API

### Quick Start Functions

#### `generate_sql_from_db`

One-line function for generating SQL from a natural language question.

```python
from nlp2sql import generate_sql_from_db

result = await generate_sql_from_db(
    database_url="postgresql://user:pass@localhost:5432/db",
    question="Show me all active users",
    ai_provider="openai",  # "openai", "anthropic", or "gemini"
    api_key="your-api-key",
    embedding_provider_type="local"  # "local" or "openai"
)

print(result['sql'])          # Generated SQL query
print(result['confidence'])   # Confidence score (0-1)
print(result['explanation'])  # Query explanation
print(result['validation'])   # Validation results
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `database_url` | `str` | Yes | Database connection URL |
| `question` | `str` | Yes | Natural language question |
| `ai_provider` | `str` | Yes | AI provider: `openai`, `anthropic`, `gemini` |
| `api_key` | `str` | Yes | Provider API key |
| `embedding_provider_type` | `str` | No | Embedding provider: `local` (default), `openai` |
| `schema_filters` | `dict` | No | Schema filtering options |

**Returns:** `dict` with keys `sql`, `confidence`, `explanation`, `validation`

#### `create_and_initialize_service`

Create a pre-initialized service for multiple queries (better performance).

```python
from nlp2sql import create_and_initialize_service

service = await create_and_initialize_service(
    database_url="postgresql://user:pass@localhost:5432/db",
    ai_provider="openai",
    api_key="your-api-key",
    schema_filters={"exclude_system_tables": True}
)

# Use multiple times - schema is cached
result1 = await service.generate_sql("Count total users")
result2 = await service.generate_sql("Show recent orders")
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `database_url` | `str` | Yes | Database connection URL |
| `ai_provider` | `str` | Yes | AI provider name |
| `api_key` | `str` | Yes | Provider API key |
| `schema_filters` | `dict` | No | Schema filtering options |
| `embedding_provider_type` | `str` | No | Embedding provider type |
| `database_type` | `DatabaseType` | No | Database type (auto-detected) |

#### `create_query_service`

Create a service with full control over initialization.

```python
from nlp2sql import create_query_service, DatabaseType

service = create_query_service(
    database_url="postgresql://user:pass@localhost:5432/db",
    ai_provider="anthropic",
    api_key="your-api-key",
    schema_filters={
        "include_schemas": ["sales", "finance"],
        "exclude_system_tables": True
    }
)

await service.initialize(DatabaseType.POSTGRES)

result = await service.generate_sql(
    question="Show revenue by month",
    database_type=DatabaseType.POSTGRES,
    max_tokens=1500,
    temperature=0.1
)
```

### Embedding Providers

```python
from nlp2sql import create_embedding_provider

# Local embeddings (free, works offline)
local_provider = create_embedding_provider("local", model="all-MiniLM-L6-v2")

# OpenAI embeddings
openai_provider = create_embedding_provider("openai", api_key="your-key")

# Use with service
service = create_query_service(
    database_url="postgresql://localhost/db",
    ai_provider="openai",
    api_key="your-key",
    embedding_provider=local_provider
)
```

### Error Handling

```python
from nlp2sql import generate_sql_from_db
from nlp2sql.exceptions import (
    SchemaException,
    QueryGenerationException,
    TokenLimitException,
    ProviderException
)

async def robust_query(question: str):
    try:
        result = await generate_sql_from_db(
            database_url="postgresql://localhost/db",
            question=question,
            ai_provider="openai",
            api_key="your-key"
        )

        if not result['validation']['is_valid']:
            print(f"Validation issues: {result['validation']['issues']}")

        return result

    except TokenLimitException as e:
        print(f"Query too complex: {e}")
    except SchemaException as e:
        print(f"Database/schema error: {e}")
    except QueryGenerationException as e:
        print(f"Generation failed: {e}")
    except ProviderException as e:
        print(f"AI provider error: {e}")
```

### Provider Fallback Pattern

```python
async def query_with_fallback(question: str, database_url: str):
    """Try multiple providers with fallback."""
    providers = [
        {"name": "openai", "env_var": "OPENAI_API_KEY"},
        {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY"},
        {"name": "gemini", "env_var": "GOOGLE_API_KEY"}
    ]

    for provider in providers:
        api_key = os.getenv(provider["env_var"])
        if not api_key:
            continue

        try:
            result = await generate_sql_from_db(
                database_url=database_url,
                question=question,
                ai_provider=provider["name"],
                api_key=api_key
            )
            return result
        except Exception as e:
            print(f"{provider['name']} failed: {e}")
            continue

    raise Exception("All providers failed")
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
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from nlp2sql import create_and_initialize_service

app = FastAPI()
service = None

class QueryRequest(BaseModel):
    question: str
    database: str = "default"

@app.on_event("startup")
async def startup():
    global service
    service = await create_and_initialize_service(
        database_url=os.getenv("DATABASE_URL"),
        ai_provider="openai",
        api_key=os.getenv("OPENAI_API_KEY")
    )

@app.post("/query")
async def generate_query(request: QueryRequest):
    try:
        result = await service.generate_sql(request.question)
        return {
            "sql": result['sql'],
            "confidence": result['confidence']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Jupyter Notebook

```python
import asyncio
from nlp2sql import generate_sql_from_db

# Generate SQL
result = await generate_sql_from_db(
    "postgresql://localhost/analytics",
    "Show user engagement by month",
    ai_provider="openai",
    api_key="your-key"
)

print(result['sql'])

# Execute with pandas
import pandas as pd
df = pd.read_sql(result['sql'], "postgresql://localhost/analytics")
df.head()
```

---

## Response Format

All query methods return a dictionary with:

```python
{
    "sql": "SELECT * FROM users WHERE active = true",
    "confidence": 0.92,
    "explanation": "This query selects all columns from the users table...",
    "validation": {
        "is_valid": True,
        "is_safe": True,
        "issues": []
    }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sql` | `str` | Generated SQL query |
| `confidence` | `float` | Confidence score (0.0 - 1.0) |
| `explanation` | `str` | Natural language explanation |
| `validation.is_valid` | `bool` | SQL syntax validity |
| `validation.is_safe` | `bool` | No dangerous operations detected |
| `validation.issues` | `list[str]` | Any validation warnings |

---

For configuration options including environment variables and schema filters, see [CONFIGURATION.md](CONFIGURATION.md).
