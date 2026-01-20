# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**nlp2sql** is an enterprise-ready Python library that converts natural language queries to SQL using multiple AI providers (OpenAI, Anthropic Claude, Google Gemini). Built with Clean Architecture principles for production scale (1000+ tables).

## Documentation

| Document | Description |
|----------|-------------|
| `README.md` | Overview and Quick Start |
| `docs/ARCHITECTURE.md` | Component Diagram and Data Flow |
| `docs/API.md` | Python API and CLI Reference |
| `docs/CONFIGURATION.md` | Environment Variables (single source of truth) |
| `docs/ENTERPRISE.md` | Large Scale Features and Migration |
| `docs/Redshift.md` | Amazon Redshift Integration |

## Development Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest                              # All tests
uv run pytest tests/test_basic.py -v       # Single test file
uv run pytest -m "not integration"         # Skip integration tests

# Code quality
uv run ruff format .                       # Format code
uv run ruff check .                        # Lint code
uv run mypy src/                           # Type checking

# CLI usage
uv run nlp2sql --help
uv run nlp2sql query --database-url "postgresql://testuser:testpass@localhost:5432/testdb" --question "How many users?"

# Docker test databases
cd docker && docker compose up -d          # Start databases
# Simple DB: postgresql://testuser:testpass@localhost:5432/testdb
# Enterprise DB: postgresql://demo:demo123@localhost:5433/enterprise
# Redshift (LocalStack): redshift://testuser:testpass123@localhost:5439/testdb
```

## Architecture

The codebase follows Clean Architecture (Hexagonal/Ports & Adapters):

```
src/nlp2sql/
├── core/           # Business entities (pure Python, no external dependencies)
├── ports/          # Interfaces/abstractions (contracts)
│   ├── ai_provider.py          # AIProviderPort - interface for AI providers
│   ├── embedding_provider.py   # EmbeddingProviderPort - interface for embeddings
│   ├── schema_repository.py    # SchemaRepositoryPort - database schema access
│   └── cache.py, query_optimizer.py, schema_strategy.py
├── adapters/       # External implementations
│   ├── openai_adapter.py       # OpenAI GPT implementation
│   ├── anthropic_adapter.py    # Anthropic Claude implementation
│   ├── gemini_adapter.py       # Google Gemini implementation
│   ├── postgres_repository.py  # PostgreSQL schema repository
│   ├── redshift_adapter.py     # Amazon Redshift repository
│   ├── local_embedding_adapter.py   # sentence-transformers embeddings
│   └── openai_embedding_adapter.py  # OpenAI embeddings
├── services/       # Application services (orchestration)
│   └── query_service.py        # QueryGenerationService - main orchestrator
├── schema/         # Schema management
│   ├── schema_manager.py       # Coordinates filtering and strategies
│   ├── schema_analyzer.py      # Scores schema relevance
│   └── schema_embedding_manager.py  # FAISS vector embeddings
├── config/         # Configuration (Pydantic Settings)
├── exceptions/     # Custom exceptions hierarchy
└── cli.py          # Click-based CLI
```

### Key Data Flow

1. User query → `QueryGenerationService`
2. `SchemaManager` applies filters (schemas, tables, system tables)
3. `SchemaEmbeddingManager` finds semantically similar schema elements (FAISS)
4. `SchemaAnalyzer` scores relevance within token limits
5. Selected AI provider generates SQL
6. Query validated and cached

## Key Patterns

### Adding a New AI Provider

1. Create adapter in `adapters/` implementing `AIProviderPort`
2. Follow existing patterns in `openai_adapter.py`
3. Update factory function in `__init__.py`

### Schema Filters (for large databases)

```python
schema_filters = {
    "include_schemas": ["sales", "finance"],
    "exclude_schemas": ["archive", "temp"],
    "include_tables": ["users", "orders"],
    "exclude_tables": ["audit_logs"],
    "exclude_system_tables": True
}
```

## Environment Variables

See `docs/CONFIGURATION.md` for complete reference. Key variables:

```bash
# AI Providers (at least one required)
OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY

# Schema Management
NLP2SQL_MAX_SCHEMA_TOKENS=8000
NLP2SQL_SCHEMA_CACHE_ENABLED=true
NLP2SQL_SCHEMA_REFRESH_HOURS=24

# Embeddings
NLP2SQL_EMBEDDING_PROVIDER=local
NLP2SQL_EMBEDDING_MODEL=all-MiniLM-L6-v2

# General
NLP2SQL_LOG_LEVEL=INFO
NLP2SQL_CACHE_ENABLED=true
```

## MCP Server

Located in `mcp_server/` - provides tools for AI assistants:
- `ask_database` - Natural language to SQL with optional execution
- `explore_schema` - Schema discovery
- `run_sql` - Direct SQL execution (read-only)
- `list_databases` - List configured connections
- `explain_sql` - Query explanation

Configuration example: `.mcp.json.example`

## Code Style

- **Line length**: 120 characters
- **Formatting**: Ruff (Black-compatible)
- **Type hints**: Required everywhere (mypy strict)
- **Async/await**: For all I/O operations
- **Naming**: PascalCase classes, snake_case functions, UPPER_SNAKE_CASE constants
- **Documentation**: No emojis in code or technical docs
