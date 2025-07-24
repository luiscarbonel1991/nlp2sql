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

# Release candidate with latest features (multi-provider support)
pip install nlp2sql==0.2.0rc1

# With specific providers
pip install nlp2sql[anthropic,gemini]  # Multiple providers
pip install nlp2sql[all-providers]     # All providers
```

### One-Line Usage (Simplest)

```python
import asyncio
import os
from nlp2sql import generate_sql_from_db

async def main():
    # Automatic provider detection
    providers = [
        {"name": "openai", "key": os.getenv("OPENAI_API_KEY")},
        {"name": "anthropic", "key": os.getenv("ANTHROPIC_API_KEY")},
        {"name": "gemini", "key": os.getenv("GOOGLE_API_KEY")}
    ]
    
    # Use first available provider
    selected = next((p for p in providers if p["key"]), None)
    if not selected:
        raise ValueError("No API key found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY")
    
    result = await generate_sql_from_db(
        database_url="postgresql://testuser:testpass@localhost:5432/testdb",
        question="Show me all active users",
        ai_provider=selected["name"],
        api_key=selected["key"]
    )
    print(result['sql'])

asyncio.run(main())
```

### Pre-Initialized Service (Better Performance)

```python
import asyncio
import os
from nlp2sql import create_and_initialize_service

async def main():
    # Smart provider detection
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("GOOGLE_API_KEY")
    provider = "openai" if os.getenv("OPENAI_API_KEY") else \
               "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "gemini"
    
    # Initialize once with Docker test database
    service = await create_and_initialize_service(
        database_url="postgresql://testuser:testpass@localhost:5432/testdb",
        ai_provider=provider,
        api_key=api_key
    )
    
    # Use multiple times
    result1 = await service.generate_sql("Count total users")
    result2 = await service.generate_sql("Find inactive accounts")
    result3 = await service.generate_sql("Show user registration trends")
    
    print(f"Using {provider} provider")
    for i, result in enumerate([result1, result2, result3], 1):
        print(f"Query {i}: {result['sql']}")

asyncio.run(main())
```

### Manual Service Creation (Full Control)

```python
import asyncio
import os
from nlp2sql import create_query_service, DatabaseType

async def main():
    # Create service with schema filtering for large databases
    service = create_query_service(
        database_url="postgresql://demo:demo123@localhost:5433/enterprise",
        ai_provider="anthropic",  # Good for large schemas
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        schema_filters={
            "include_schemas": ["sales", "finance"],
            "exclude_system_tables": True
        }
    )
    
    # Initialize (loads schema automatically)
    await service.initialize(DatabaseType.POSTGRES)
    
    # Generate SQL
    result = await service.generate_sql(
        question="Show revenue by month for the sales team",
        database_type=DatabaseType.POSTGRES
    )
    
    print(f"SQL: {result['sql']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Explanation: {result['explanation']}")
    print(f"Valid: {result['validation']['is_valid']}")

asyncio.run(main())
```

## 🤖 Multiple AI Providers Support

nlp2sql supports multiple AI providers - you're not locked into OpenAI!

### Supported Providers

```python
# OpenAI GPT-4 (default)
service = await create_and_initialize_service(
    database_url="postgresql://testuser:testpass@localhost:5432/testdb",
    ai_provider="openai",
    api_key="your-openai-key"
)

# Anthropic Claude
service = await create_and_initialize_service(
    database_url="postgresql://testuser:testpass@localhost:5432/testdb", 
    ai_provider="anthropic",
    api_key="your-anthropic-key"
)

# Google Gemini
service = await create_and_initialize_service(
    database_url="postgresql://testuser:testpass@localhost:5432/testdb",
    ai_provider="gemini", 
    api_key="your-google-key"
)
```

### Provider Comparison

| Provider | Context Size | Cost/1K tokens | Best For |
|----------|-------------|----------------|----------|
| OpenAI GPT-4 | 128K | $0.030 | Complex reasoning |
| Anthropic Claude | 200K | $0.015 | Large schemas |
| Google Gemini | 1M | $0.001 | High volume/cost |

## 📊 Large Schema Support

For databases with 1000+ tables, use schema filters:

```python
# Basic filtering
filters = {
    "exclude_system_tables": True,
    "exclude_tables": ["audit_log", "temp_data", "migration_history"]
}

service = await create_and_initialize_service(
    database_url="postgresql://demo:demo123@localhost:5433/enterprise",
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

# Multi-schema filtering for enterprise databases
enterprise_filters = {
    "include_schemas": ["sales", "hr", "finance"],
    "exclude_schemas": ["archive", "temp"],
    "include_tables": ["customers", "orders", "employees", "transactions"],
    "exclude_tables": ["audit_logs", "system_logs"],
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
# AI Provider API Keys (at least one required)
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
export GOOGLE_API_KEY="your-google-key"  # Note: GOOGLE_API_KEY, not GEMINI_API_KEY

# Database (Docker test databases)
export DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb"  # Simple DB
# export DATABASE_URL="postgresql://demo:demo123@localhost:5433/enterprise"  # Large DB

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

# Setup Docker test databases
cd docker
docker-compose up -d
cd ..

# Test CLI with Docker database
export OPENAI_API_KEY=your-key
uv run nlp2sql query \
  --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
  --question "How many users are there?" \
  --provider openai

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
