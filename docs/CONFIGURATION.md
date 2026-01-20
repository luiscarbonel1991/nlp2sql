# Configuration Reference

This document is the single source of truth for all nlp2sql configuration options.

## Environment Variables

### AI Provider API Keys

At least one AI provider API key is required.

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | One of three | OpenAI API key for GPT-4 models |
| `ANTHROPIC_API_KEY` | One of three | Anthropic API key for Claude models |
| `GOOGLE_API_KEY` | One of three | Google API key for Gemini models |

```bash
# Set at least one provider key
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="AI..."
```

### Database Connection

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | - | Default database connection URL |

Supported formats:
```bash
# PostgreSQL
export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"

# Amazon Redshift
export DATABASE_URL="redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/dbname"
```

### Schema Management

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NLP2SQL_MAX_SCHEMA_TOKENS` | No | `8000` | Maximum tokens for schema context |
| `NLP2SQL_SCHEMA_CACHE_TTL_HOURS` | No | `24` | Schema cache time-to-live in hours |
| `NLP2SQL_EMBEDDINGS_DIR` | No | `./embeddings` | Directory for embedding cache storage |
| `NLP2SQL_EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Local embedding model name |
| `NLP2SQL_EMBEDDING_PROVIDER` | No | `local` | Embedding provider: `local` or `openai` |

```bash
# Schema management settings
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_SCHEMA_CACHE_TTL_HOURS=24
export NLP2SQL_EMBEDDINGS_DIR=/path/to/embeddings
export NLP2SQL_EMBEDDING_MODEL=all-MiniLM-L6-v2
export NLP2SQL_EMBEDDING_PROVIDER=local
```

### General Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NLP2SQL_LOG_LEVEL` | No | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `NLP2SQL_CACHE_ENABLED` | No | `true` | Enable/disable query result caching |
| `NLP2SQL_ENV` | No | - | Environment: `development`, `production` |
| `TOKENIZERS_PARALLELISM` | No | - | Set to `false` to suppress tokenizer warnings |

```bash
# General settings
export NLP2SQL_LOG_LEVEL=INFO
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_ENV=production
export TOKENIZERS_PARALLELISM=false
```

## Schema Filters

Schema filters reduce the database schema to relevant tables for better performance and accuracy.

### Filter Options

| Filter | Type | Description |
|--------|------|-------------|
| `include_schemas` | `list[str]` | Only include these schemas |
| `exclude_schemas` | `list[str]` | Exclude these schemas |
| `include_tables` | `list[str]` | Only include these tables |
| `exclude_tables` | `list[str]` | Exclude these tables |
| `exclude_system_tables` | `bool` | Exclude PostgreSQL system tables |

### Python Usage

```python
schema_filters = {
    "include_schemas": ["sales", "finance"],
    "exclude_schemas": ["archive", "temp"],
    "include_tables": ["customers", "orders", "products"],
    "exclude_tables": ["audit_logs", "migration_history"],
    "exclude_system_tables": True
}

service = await create_and_initialize_service(
    database_url="postgresql://localhost/db",
    api_key=api_key,
    schema_filters=schema_filters
)
```

### CLI Usage

```bash
nlp2sql query \
  --database-url postgresql://localhost/db \
  --question "Show sales data" \
  --schema-filters '{"include_schemas": ["sales"], "exclude_system_tables": true}'
```

### Filter Strategy by Database Size

| Database Size | Tables | Recommended Filters |
|---------------|--------|---------------------|
| Small | < 100 | No filtering needed |
| Medium | 100-500 | `exclude_system_tables: true` |
| Large | 500-1000 | Add `exclude_tables` for verbose tables |
| Enterprise | 1000+ | Use `include_tables` for core entities (15-25 tables) |

## Provider Comparison

| Provider | Context Size | Cost/1K tokens | Best For |
|----------|-------------|----------------|----------|
| OpenAI GPT-4 | 128K | $0.030 | Complex reasoning |
| Anthropic Claude | 200K | $0.015 | Large schemas |
| Google Gemini | 1M | $0.001 | High volume, cost efficiency |

## Docker Test Databases

For development and testing, use the included Docker Compose setup:

```bash
cd docker && docker-compose up -d
```

| Database | URL | Description |
|----------|-----|-------------|
| Simple | `postgresql://testuser:testpass@localhost:5432/testdb` | Small test database |
| Enterprise | `postgresql://demo:demo123@localhost:5433/enterprise` | Large enterprise schema |
| Redshift (LocalStack) | `redshift://testuser:testpass123@localhost:5439/testdb` | Redshift emulation |

## Production Configuration Example

```bash
# Production environment
export NLP2SQL_ENV=production
export NLP2SQL_LOG_LEVEL=INFO
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_SCHEMA_CACHE_TTL_HOURS=24

# AI Provider (choose one or more for fallback)
export OPENAI_API_KEY="sk-prod-..."
export ANTHROPIC_API_KEY="sk-ant-prod-..."

# Database
export DATABASE_URL="postgresql://prod-user:prod-pass@prod-host:5432/production"

# Embedding storage (persistent volume in production)
export NLP2SQL_EMBEDDINGS_DIR=/data/nlp2sql/embeddings
```
