# nlp2sql - Quick Start Guide

## 🚀 Get Started in 5 Minutes

### 1. Install Dependencies
```bash
# Make sure you have UV installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

### 2. Set Environment Variables
```bash
# Required
export OPENAI_API_KEY="your-openai-api-key"
export DATABASE_URL="postgresql://user:password@localhost:5432/your_db"

# Optional (with defaults)
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_LOG_LEVEL=INFO
```

### 3. Basic Usage
```python
import asyncio
from nlp2sql import create_query_service, DatabaseType

async def main():
    # Create and initialize service
    service = create_query_service(
        database_url="postgresql://user:password@localhost:5432/your_db",
        ai_provider="openai",
        api_key="your-openai-api-key",
        database_type=DatabaseType.POSTGRES
    )
    
    await service.initialize(DatabaseType.POSTGRES)
    
    # Generate SQL from natural language
    result = await service.generate_sql(
        question="Show me all customers from Madrid",
        database_type=DatabaseType.POSTGRES
    )
    
    print(f"Generated SQL: {result['sql']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Explanation: {result['explanation']}")
    print(f"Valid: {result['validation']['is_valid']}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 4. Test the Library
```bash
# Run basic tests
uv run pytest tests/test_basic.py -v

# Run demo examples
uv run python examples/simple_demo.py
uv run python examples/real_world_example.py
```

### 5. Example Queries You Can Try

**Simple queries:**
- "Show me all customers"
- "Count total orders"
- "Find products with low stock"

**Complex queries:**
- "Show me customers from Madrid who bought more than 1000 euros"
- "Find the top 5 best-selling products last month"
- "Which customers haven't placed any orders in the last 6 months?"

**Analytical queries:**
- "Show me sales trends by month"
- "What's the average order value by city?"
- "Find customers with the highest lifetime value"

### 6. Advanced Features

```python
# Query validation
validation = await service.validate_sql(
    sql="SELECT * FROM customers WHERE city = 'Madrid'",
    database_type=DatabaseType.POSTGRES
)

# Query suggestions
suggestions = await service.get_query_suggestions(
    partial_question="show customers",
    database_type=DatabaseType.POSTGRES
)

# Explain existing query
explanation = await service.explain_query(
    sql="SELECT COUNT(*) FROM orders WHERE status = 'completed'",
    database_type=DatabaseType.POSTGRES
)
```

### 7. Configuration Options

```python
from nlp2sql.config.settings import settings

# Customize settings
settings.max_schema_tokens = 12000
settings.default_temperature = 0.1
settings.cache_enabled = True
```

### 8. Error Handling

```python
from nlp2sql.exceptions import (
    TokenLimitException, 
    QueryGenerationException, 
    ValidationException
)

try:
    result = await service.generate_sql(
        question="your complex query",
        database_type=DatabaseType.POSTGRES
    )
except TokenLimitException as e:
    print(f"Token limit exceeded: {e.tokens_used}/{e.max_tokens}")
except QueryGenerationException as e:
    print(f"SQL generation failed: {e}")
except ValidationException as e:
    print(f"Invalid SQL generated: {e}")
```

## 🎯 Perfect for Your Use Case

This library is specifically designed to solve the challenge of converting natural language to SQL in enterprise environments with:

- ✅ **Large database schemas** (1000+ tables)
- ✅ **Multiple AI providers** (OpenAI, Claude, Gemini, etc.)
- ✅ **Intelligent caching** for fast responses
- ✅ **Automatic query optimization**
- ✅ **SQL validation** and error handling
- ✅ **Production-ready** architecture

## 🔧 Development Commands

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking
uv run mypy src/

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=nlp2sql --cov-report=html
```

## 🚀 You're Ready!

Your nlp2sql library is now ready to solve your natural language to SQL challenge. The architecture is designed to be:

- **Scalable** - handles large schemas efficiently
- **Extensible** - easy to add new AI providers and databases
- **Maintainable** - clean code with good separation of concerns
- **Production-ready** - robust error handling and logging

Start with simple queries and gradually move to more complex ones as you get familiar with the library!