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

**Enterprise-ready Natural Language to SQL converter with multi-provider support**

Convert natural language queries to optimized SQL using multiple AI providers. Built with Clean Architecture principles for enterprise-scale applications handling 1000+ table databases.

## Features

- **Multiple AI Providers**: OpenAI, Anthropic Claude, Google Gemini - no vendor lock-in
- **Database Support**: PostgreSQL, Amazon Redshift
- **Large Schema Handling**: Vector embeddings and intelligent filtering for 1000+ tables
- **Smart Caching**: Query and schema embedding caching for improved performance
- **Async Support**: Full async/await support
- **Clean Architecture**: Ports & Adapters pattern for maintainability

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | Component diagram and data flow |
| [API Reference](docs/API.md) | Python API and CLI command reference |
| [Configuration](docs/CONFIGURATION.md) | Environment variables and schema filters |
| [Enterprise Guide](docs/ENTERPRISE.md) | Large-scale deployment and migration |
| [Redshift Support](docs/Redshift.md) | Amazon Redshift setup and examples |
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
pip install nlp2sql[embeddings-local]   # Local embeddings (free)
pip install nlp2sql[embeddings-openai]  # OpenAI embeddings
```

## Quick Start

### 1. Set an API Key

```bash
export OPENAI_API_KEY="your-openai-key"
# or ANTHROPIC_API_KEY, GOOGLE_API_KEY
```

### 2. Connect and Ask

```python
import asyncio
import nlp2sql
from nlp2sql import ProviderConfig

async def main():
    nlp = await nlp2sql.connect(
        "postgresql://user:pass@localhost:5432/mydb",
        provider=ProviderConfig(provider="openai", api_key="sk-..."),
    )

    result = await nlp.ask("Show me all active users")
    print(result.sql)
    print(result.confidence)
    print(result.is_valid)

asyncio.run(main())
```

`connect()` auto-detects the database type from the URL, loads the schema, and builds the FAISS embedding index. Subsequent `ask()` calls reuse everything from disk cache.

### 3. Few-Shot Examples

Pass a list of dicts -- `connect()` handles embedding and indexing automatically:

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
    ],
)

result = await nlp.ask("Show me total sales this quarter")
```

### 4. Schema Filtering (Large Databases)

```python
nlp = await nlp2sql.connect(
    "postgresql://localhost/enterprise",
    provider=ProviderConfig(provider="anthropic", api_key="sk-ant-..."),
    schema_filters={
        "include_schemas": ["sales", "finance"],
        "exclude_system_tables": True,
    },
)
```

### 5. Custom Model and Temperature

```python
nlp = await nlp2sql.connect(
    "postgresql://localhost/mydb",
    provider=ProviderConfig(
        provider="openai",
        api_key="sk-...",
        model="gpt-4o",
        temperature=0.0,
        max_tokens=4000,
    ),
)
```

### 6. CLI

```bash
nlp2sql query \
  --database-url postgresql://user:pass@localhost:5432/mydb \
  --question "Show all active users" \
  --explain

nlp2sql inspect --database-url postgresql://localhost/mydb
```

### Advanced: Direct Service Access

For full control over the lifecycle, the lower-level API is still available:

```python
from nlp2sql import create_and_initialize_service, ProviderConfig, DatabaseType

service = await create_and_initialize_service(
    database_url="postgresql://localhost/mydb",
    provider_config=ProviderConfig(provider="openai", api_key="sk-..."),
    database_type=DatabaseType.POSTGRES,
)
result = await service.generate_sql("Count total users", database_type=DatabaseType.POSTGRES)
```

## How It Works

```
Question ──► Cache check ──► Schema retrieval ──► Relevance filtering ──► Context building ──► AI generation ──► Validation
                                    │                     │                      │
                              SchemaRepository    FAISS + TF-IDF hybrid   Reuses precomputed
                              (+ disk cache)      + batch scoring          relevance scores
```

1. **Schema retrieval** -- Fetches tables from database via `SchemaRepository` (with disk cache for Redshift)
2. **Relevance filtering** -- FAISS dense search + TF-IDF sparse search (50/50 hybrid) finds candidate tables; batch scoring refines with precomputed embeddings
3. **Context building** -- Builds optimized schema context within token limits, reusing scores from step 2 (zero additional embedding calls)
4. **SQL generation** -- AI provider (OpenAI, Anthropic, or Gemini) generates SQL from question + schema context
5. **Validation** -- SQL syntax and safety checks before returning results

See [Architecture](docs/ARCHITECTURE.md) for the detailed flow with method references and design decisions.

## Provider Comparison

| Provider | Default Model | Context Size | Best For |
|----------|--------------|-------------|----------|
| OpenAI | gpt-4o-mini | 128K | Cost-effective, fast |
| Anthropic | claude-sonnet-4-20250514 | 200K | Large schemas |
| Google Gemini | gemini-2.0-flash | 1M | High volume |

All models are configurable via `ProviderConfig(model="...")`. See [Configuration](docs/CONFIGURATION.md) for details.

## Architecture

Clean Architecture (Ports & Adapters) with three layers: core entities, port interfaces, and adapter implementations. The schema management layer uses FAISS + TF-IDF hybrid search for relevance filtering at scale.

```
nlp2sql/
├── client.py       # DSL: connect() + NLP2SQL class (recommended entry point)
├── core/           # Pure Python: entities, ProviderConfig, QueryResult, sql_safety, sql_keywords
├── ports/          # Interfaces: AIProviderPort, SchemaRepositoryPort, EmbeddingProviderPort,
│                   #   ExampleRepositoryPort, QuerySafetyPort, QueryValidatorPort, CachePort
├── adapters/       # Implementations: OpenAI, Anthropic, Gemini, PostgreSQL, Redshift,
│                   #   RegexQueryValidator
├── services/       # Orchestration: QueryGenerationService
├── schema/         # Schema management: SchemaManager, SchemaAnalyzer, SchemaEmbeddingManager,
│                   #   ExampleStore
├── config/         # Pydantic Settings (centralized defaults)
└── exceptions/     # Exception hierarchy (NLP2SQLException -> 8 subclasses)
```

See [Architecture](docs/ARCHITECTURE.md) for the full component diagram, data flow, and design decisions.

## Development

```bash
# Clone and install
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql
uv sync

# Start test databases
cd docker && docker-compose up -d

# Run tests
uv run pytest

# Code quality
uv run ruff format .
uv run ruff check .
uv run mypy src/
```

## MCP Server

nlp2sql includes a Model Context Protocol server for AI assistant integration.

```json
{
  "mcpServers": {
    "nlp2sql": {
      "command": "python",
      "args": ["/path/to/nlp2sql/mcp_server/server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "NLP2SQL_DEFAULT_DB_URL": "postgresql://user:pass@localhost:5432/mydb"
      }
    }
  }
}
```

Tools: `ask_database`, `explore_schema`, `run_sql`, `list_databases`, `explain_sql`

See [mcp_server/README.md](mcp_server/README.md) for complete setup.

## Contributing

We welcome contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE).

## Author

**Luis Carbonel** - [@luiscarbonel1991](https://github.com/luiscarbonel1991)
