# nlp2sql

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Enterprise-ready Natural Language to SQL converter with multi-provider support**

A powerful Python library for converting natural language queries to optimized SQL using multiple AI providers. Built with Clean Architecture principles for enterprise-scale applications handling 1000+ table databases.

## 🚀 Why nlp2sql?

Unlike academic frameworks focused on composability, **nlp2sql is built for enterprise production environments** from day one:

- **🏢 Enterprise Scale**: Handle databases with 1000+ tables efficiently
- **🤖 Multi-Provider Native**: OpenAI, Anthropic, Gemini support - no vendor lock-in
- **⚡ Production Ready**: Advanced caching, async support, schema optimization
- **🛠️ Developer First**: Professional CLI, Docker setup, automated installation
- **🏗️ Clean Architecture**: Maintainable, testable, extensible codebase
- **📊 Performance Focused**: Benchmarking, schema filtering, vector embeddings

## ✨ Features

- **🤖 Multiple AI Providers**: OpenAI, Anthropic, Google Gemini, AWS Bedrock, Azure OpenAI
- **🗄️ Database Support**: PostgreSQL (with MySQL, SQLite, Oracle, MSSQL coming soon)
- **📊 Large Schema Handling**: Advanced strategies for databases with 1000+ tables
- **⚡ Smart Caching**: Intelligent result caching for improved performance
- **🔍 Query Optimization**: Built-in SQL query optimization
- **🧠 Schema Analysis**: AI-powered relevance scoring and schema compression
- **🔍 Vector Embeddings**: Semantic search for schema elements
- **📈 Token Management**: Efficient token usage across different providers
- **⚡ Async Support**: Full async/await support for better performance
- **🏗️ Clean Architecture**: Ports & Adapters pattern for maintainability

## 🚀 Quick Start

### Installation

```bash
# Install with UV (recommended)
uv add nlp2sql

# Or with pip
pip install nlp2sql

# With specific providers
pip install nlp2sql[anthropic,gemini]  # Multiple providers
pip install nlp2sql[all-providers]     # All providers
```

### One-Line Usage (Simplest)

```python
import asyncio
from nlp2sql import generate_sql_from_db

async def main():
    result = await generate_sql_from_db(
        database_url="postgresql://user:pass@localhost/db",
        question="Show me all active users",
        ai_provider="openai",  # or "anthropic", "gemini"
        api_key="your-api-key"
    )
    print(result['sql'])

asyncio.run(main())
```

### Pre-Initialized Service (Better Performance)

```python
import asyncio
from nlp2sql import create_and_initialize_service

async def main():
    # Initialize once
    service = await create_and_initialize_service(
        database_url="postgresql://user:pass@localhost/db",
        api_key="your-openai-api-key"
    )
    
    # Use multiple times
    result1 = await service.generate_sql("Count total users")
    result2 = await service.generate_sql("Find inactive accounts")
    result3 = await service.generate_sql("Show user registration trends")

asyncio.run(main())
```

### Manual Service Creation (Full Control)

```python
import asyncio
from nlp2sql import create_query_service, DatabaseType

async def main():
    # Create service
    service = create_query_service(
        database_url="postgresql://user:pass@localhost/db",
        ai_provider="openai",
        api_key="your-openai-api-key"
    )
    
    # Initialize (loads schema automatically)
    await service.initialize(DatabaseType.POSTGRES)
    
    # Generate SQL
    result = await service.generate_sql(
        question="Show revenue by month",
        database_type=DatabaseType.POSTGRES
    )
    
    print(f"SQL: {result['sql']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Explanation: {result['explanation']}")

asyncio.run(main())
```

## 🤖 Multiple AI Providers Support

nlp2sql supports multiple AI providers - you're not locked into OpenAI!

### Supported Providers

```python
# OpenAI GPT-4 (default)
service = await create_and_initialize_service(
    database_url="postgresql://localhost/db",
    ai_provider="openai",
    api_key="your-openai-key"
)

# Anthropic Claude
service = await create_and_initialize_service(
    database_url="postgresql://localhost/db", 
    ai_provider="anthropic",
    api_key="your-anthropic-key"
)

# Google Gemini
service = await create_and_initialize_service(
    database_url="postgresql://localhost/db",
    ai_provider="gemini", 
    api_key="your-google-key"
)
```

### Provider Comparison

| Provider | Context Size | Cost/1K tokens | Best For |
|----------|-------------|----------------|----------|
| OpenAI GPT-4 | 128K | $0.030 | Complex reasoning |
| Anthropic Claude | 200K | $0.015 | Large schemas |
| Google Gemini | 30K | $0.001 | High volume/cost |

## 📊 Large Schema Support

For databases with 1000+ tables, use schema filters:

```python
# Basic filtering
filters = {
    "exclude_system_tables": True,
    "excluded_tables": ["audit_log", "temp_data", "migration_history"]
}

service = await create_and_initialize_service(
    database_url="postgresql://localhost/large_db",
    api_key="your-api-key",
    schema_filters=filters
)

# Business domain filtering
business_filters = {
    "include_tables": [
        "users", "customers", "orders", "products",
        "invoices", "payments", "addresses"
    ],
    "exclude_system_tables": True
}
```

## 🏗️ Architecture

nlp2sql follows Clean Architecture principles with clear separation of concerns:

```
nlp2sql/
├── core/           # Business entities and domain logic
├── ports/          # Interfaces/abstractions
├── adapters/       # External service implementations
├── services/       # Application services
├── schema/         # Schema management strategies
├── config/         # Configuration management
└── exceptions/     # Custom exceptions
```

## Configuration

### Environment Variables

```bash
# AI Provider API Keys
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
export GOOGLE_API_KEY="your-google-key"

# Database
export DATABASE_URL="postgresql://user:pass@localhost:5432/db"

# Optional Settings
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_LOG_LEVEL=INFO
```

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql

# Install dependencies
uv sync

# Run tests
uv run pytest

# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking
uv run mypy src/
```

## 🏢 Enterprise Use Cases

### Data Analytics Teams
- **Large Schema Navigation**: Query enterprise databases with 1000+ tables
- **Multi-Tenant Support**: Schema filtering for different business units
- **Performance Optimization**: Intelligent caching and query optimization

### DevOps & Platform Teams
- **Multi-Provider Strategy**: Avoid vendor lock-in, optimize costs
- **Infrastructure as Code**: Docker setup, automated deployment
- **Monitoring & Benchmarking**: Performance tracking across providers

### Business Intelligence
- **Self-Service Analytics**: Non-technical users query databases naturally
- **Audit & Compliance**: Explainable queries with confidence scoring
- **Cost Management**: Provider comparison and optimization

## 📊 Performance & Scale

| Metric | nlp2sql | Typical Framework |
|--------|---------|-------------------|
| **Max Tables Supported** | 1000+ | ~100 |
| **AI Providers** | 3+ (OpenAI, Anthropic, Gemini) | Usually 1 |
| **Query Cache** | ✅ Advanced | ❌ Basic/None |
| **Schema Optimization** | ✅ Vector embeddings | ❌ Manual |
| **Enterprise CLI** | ✅ Professional | ❌ Basic/None |
| **Docker Setup** | ✅ Production-ready | ❌ Manual |

## 🔄 Migration from Other Frameworks

Coming from other NLP-to-SQL frameworks? nlp2sql provides:
- **Drop-in replacement** for most common patterns
- **Enhanced performance** with minimal code changes
- **Additional features** without breaking existing workflows

See our [Migration Guide](docs/migration.md) for framework-specific instructions.

## 🤝 Contributing

We welcome contributions! This project follows enterprise development practices:
- Clean Architecture patterns
- Comprehensive testing
- Type safety with mypy
- Code formatting with black/ruff

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author & Maintainer

**Luis Carbonel** - *Initial work and ongoing development*
- GitHub: [@luiscarbonel1991](https://github.com/luiscarbonel1991)
- Email: devhighlevel@gmail.com

Built with enterprise needs in mind, refined through real-world production use cases.