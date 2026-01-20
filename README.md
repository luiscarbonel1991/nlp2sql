# nlp2sql

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

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

### 1. Set Environment Variables

```bash
# At least one AI provider key required
export OPENAI_API_KEY="your-openai-key"
# export ANTHROPIC_API_KEY="your-anthropic-key"
# export GOOGLE_API_KEY="your-google-key"
```

### 2. One-Line Usage

```python
import asyncio
import os
from nlp2sql import generate_sql_from_db

async def main():
    result = await generate_sql_from_db(
        database_url="postgresql://user:pass@localhost:5432/mydb",
        question="Show me all active users",
        ai_provider="openai",
        api_key=os.getenv("OPENAI_API_KEY")
    )
    print(result['sql'])
    print(f"Confidence: {result['confidence']}")

asyncio.run(main())
```

### 3. Pre-Initialized Service (Better Performance)

```python
from nlp2sql import create_and_initialize_service

async def main():
    # Initialize once
    service = await create_and_initialize_service(
        database_url="postgresql://user:pass@localhost:5432/mydb",
        ai_provider="openai",
        api_key=os.getenv("OPENAI_API_KEY")
    )

    # Use multiple times
    result1 = await service.generate_sql("Count total users")
    result2 = await service.generate_sql("Show recent orders")
```

### 4. Large Database with Schema Filtering

```python
from nlp2sql import create_and_initialize_service

service = await create_and_initialize_service(
    database_url="postgresql://localhost/enterprise",
    ai_provider="anthropic",  # Best for large schemas (200K context)
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    schema_filters={
        "include_schemas": ["sales", "finance"],
        "exclude_system_tables": True
    }
)

result = await service.generate_sql("Show revenue by month")
```

### 5. CLI Usage

```bash
# Generate SQL
nlp2sql query \
  --database-url postgresql://user:pass@localhost:5432/mydb \
  --question "Show all active users" \
  --explain

# Inspect schema
nlp2sql inspect --database-url postgresql://localhost/mydb

# Benchmark providers
nlp2sql benchmark --database-url postgresql://localhost/mydb
```

## Provider Comparison

| Provider | Context Size | Best For |
|----------|-------------|----------|
| OpenAI GPT-4 | 128K | Complex reasoning |
| Anthropic Claude | 200K | Large schemas |
| Google Gemini | 1M | High volume, cost efficiency |

See [Configuration](docs/CONFIGURATION.md) for detailed provider setup.

## Architecture

```
nlp2sql/
├── core/           # Business entities
├── ports/          # Interfaces/abstractions
├── adapters/       # External implementations (AI providers, databases)
├── services/       # Application services
├── schema/         # Schema management and embeddings
├── config/         # Configuration
└── exceptions/     # Custom exceptions
```

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
