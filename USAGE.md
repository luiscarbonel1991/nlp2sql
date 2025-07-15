# nlp2sql Usage Guide

## Quick Start with Automatic Schema Loading

The easiest way to use nlp2sql is with automatic schema loading from your database.

### 1. One-Line API (Simplest)

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

### 2. Pre-Initialized Service (Better Performance)

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

### 3. Manual Service Creation (Full Control)

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

asyncio.run(main())
```

## Multiple AI Providers Support

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

### Installation for Different Providers

```bash
# OpenAI only (included by default)
pip install nlp2sql

# Add Anthropic support
pip install nlp2sql[anthropic]

# Add Google Gemini support  
pip install nlp2sql[gemini]

# Install all providers
pip install nlp2sql[all-providers]
```

### Provider Comparison

| Provider | Context Size | Cost/1K tokens | Best For |
|----------|-------------|----------------|----------|
| OpenAI GPT-4 | 128K | $0.030 | Complex reasoning |
| Anthropic Claude | 200K | $0.015 | Large schemas |
| Google Gemini | 30K | $0.001 | High volume/cost |

### Choosing the Right Provider

```python
# For complex analytical queries
result = await generate_sql_from_db(
    database_url, 
    "Calculate year-over-year revenue growth by product category",
    ai_provider="openai"
)

# For large database schemas (1000+ tables)
result = await generate_sql_from_db(
    database_url,
    "Find customers with unusual purchasing patterns", 
    ai_provider="anthropic"  # 200K context window
)

# For high-volume applications
result = await generate_sql_from_db(
    database_url,
    "Count active users today",
    ai_provider="gemini"  # Most cost-effective
)
```

### Provider Fallback Strategy

```python
import asyncio
from nlp2sql import generate_sql_from_db

async def robust_sql_generation(question):
    """Try multiple providers for reliability."""
    providers = [
        ("openai", os.getenv("OPENAI_API_KEY")),
        ("anthropic", os.getenv("ANTHROPIC_API_KEY")),
        ("gemini", os.getenv("GOOGLE_API_KEY"))
    ]
    
    for provider, api_key in providers:
        if not api_key:
            continue
            
        try:
            result = await generate_sql_from_db(
                database_url, question, 
                ai_provider=provider, api_key=api_key
            )
            return result
        except Exception as e:
            print(f"Provider {provider} failed: {e}")
            continue
    
    raise Exception("All providers failed")
```

## Schema Filtering for Large Databases

For databases with 1000+ tables, use schema filters to improve performance:

### Basic Filtering

```python
from nlp2sql import create_and_initialize_service

# Exclude system tables
filters = {
    "exclude_system_tables": True,
    "excluded_tables": ["audit_log", "temp_data", "migration_history"]
}

service = await create_and_initialize_service(
    database_url="postgresql://localhost/large_db",
    api_key="your-api-key",
    schema_filters=filters
)
```

### Business Domain Filtering

```python
# Focus on specific business domains
business_filters = {
    "include_tables": [
        # User management
        "users", "user_profiles", "user_sessions",
        
        # Sales
        "orders", "order_items", "customers",
        
        # Inventory
        "products", "inventory", "suppliers"
    ],
    "exclude_system_tables": True
}

service = await create_and_initialize_service(
    database_url="postgresql://localhost/large_db",
    schema_filters=business_filters,
    api_key="your-api-key"
)
```

### Schema-Based Filtering

```python
# Multi-tenant or multi-schema databases
schema_filters = {
    "include_schemas": ["public", "sales"],
    "exclude_schemas": ["archive", "temp"],
    "exclude_system_tables": True
}

service = await create_and_initialize_service(
    database_url="postgresql://localhost/multitenant_db",
    schema_filters=schema_filters,
    api_key="your-api-key"
)
```

## Command Line Interface

### Schema Inspection

```bash
# Basic schema summary
nlp2sql inspect --database-url postgresql://localhost/db

# Export schema as JSON
nlp2sql inspect --database-url postgresql://localhost/db --format json --output schema.json

# Table list format
nlp2sql inspect --database-url postgresql://localhost/db --format table
```

### SQL Generation from CLI

```bash
# Generate SQL from command line
nlp2sql query \
  --database-url postgresql://localhost/db \
  --question "Show me all active users" \
  --api-key your-openai-key

# With schema filtering
nlp2sql query \
  --database-url postgresql://localhost/db \
  --question "Count total orders" \
  --schema-filters '{"exclude_system_tables": true}'
```

## Advanced Examples

### Error Handling

```python
import asyncio
from nlp2sql import generate_sql_from_db, SchemaException, QueryGenerationException

async def robust_query():
    try:
        result = await generate_sql_from_db(
            database_url="postgresql://localhost/db",
            question="Show me user analytics",
            api_key="your-api-key"
        )
        
        if result['validation']['is_valid']:
            print(f"SQL: {result['sql']}")
            print(f"Confidence: {result['confidence']}")
        else:
            print(f"Invalid SQL generated: {result['validation']['issues']}")
            
    except SchemaException as e:
        print(f"Schema error: {e}")
    except QueryGenerationException as e:
        print(f"Query generation error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

asyncio.run(robust_query())
```

### Custom Configuration

```python
import asyncio
from nlp2sql import create_query_service, DatabaseType

async def custom_config():
    service = create_query_service(
        database_url="postgresql://localhost/db",
        ai_provider="openai",
        api_key="your-api-key",
        schema_filters={
            "exclude_system_tables": True,
            "included_tables": ["users", "orders", "products"]
        }
    )
    
    await service.initialize(DatabaseType.POSTGRES)
    
    # Generate with custom parameters
    result = await service.generate_sql(
        question="Find high-value customers",
        database_type=DatabaseType.POSTGRES,
        max_tokens=1000,
        temperature=0.0,  # More deterministic
        include_explanation=True
    )
    
    print(f"SQL: {result['sql']}")
    print(f"Explanation: {result['explanation']}")

asyncio.run(custom_config())
```

### Performance Optimization for Large Schemas

```python
import asyncio
from nlp2sql import create_and_initialize_service

async def optimized_for_large_db():
    # Strategy for 1000+ table databases
    large_db_config = {
        "exclude_system_tables": True,
        
        # Only include core business tables
        "include_tables": [
            # Core entities (10-20 tables)
            "users", "customers", "orders", "products",
            "invoices", "payments", "addresses",
            
            # Frequently queried tables
            "user_sessions", "order_history", "product_categories"
        ],
        
        # Exclude verbose/audit tables
        "excluded_tables": [
            "audit_logs", "system_logs", "migration_history",
            "temporary_imports", "data_exports"
        ]
    }
    
    service = await create_and_initialize_service(
        database_url="postgresql://localhost/enterprise_db",
        api_key="your-api-key",
        schema_filters=large_db_config
    )
    
    # This will be much faster with filtered schema
    result = await service.generate_sql(
        "Show me monthly revenue trends for the last year"
    )
    
    print(f"Optimized SQL: {result['sql']}")

asyncio.run(optimized_for_large_db())
```

## Best Practices

### 1. Start Simple, Then Optimize

```python
# Start with the one-line API
result = await generate_sql_from_db(url, question, api_key)

# If performance is an issue, use pre-initialization
service = await create_and_initialize_service(url, api_key=api_key)

# For large schemas, add filtering
service = await create_and_initialize_service(
    url, api_key=api_key, schema_filters=filters
)
```

### 2. Schema Filtering Strategy

For different database sizes:

- **< 100 tables**: No filtering needed
- **100-500 tables**: Use `exclude_system_tables=True`
- **500-1000 tables**: Add `excluded_tables` for verbose tables
- **1000+ tables**: Use `include_tables` for core business entities

### 3. Caching and Reuse

```python
# Good: Initialize once, use many times
service = await create_and_initialize_service(url, api_key=api_key)
for question in questions:
    result = await service.generate_sql(question)

# Avoid: Re-creating service for each query
for question in questions:
    result = await generate_sql_from_db(url, question, api_key)  # Slow!
```

### 4. Error Handling

Always handle potential errors:
- `SchemaException`: Database connection or schema issues
- `QueryGenerationException`: AI provider or query generation issues
- `TokenLimitException`: Query too complex for context window

## Integration Examples

### FastAPI Integration

```python
from fastapi import FastAPI, HTTPException
from nlp2sql import create_and_initialize_service

app = FastAPI()

# Initialize service at startup
@app.on_event("startup")
async def startup():
    app.nlp2sql_service = await create_and_initialize_service(
        database_url="postgresql://localhost/db",
        api_key="your-api-key"
    )

@app.post("/generate-sql")
async def generate_sql(question: str):
    try:
        result = await app.nlp2sql_service.generate_sql(question)
        return {"sql": result['sql'], "confidence": result['confidence']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Jupyter Notebook

```python
# Install in notebook
!pip install nlp2sql

# Use in cell
import asyncio
from nlp2sql import generate_sql_from_db

# Generate SQL
result = await generate_sql_from_db(
    "postgresql://localhost/analytics_db",
    "Show me user engagement metrics by month",
    api_key="your-api-key"
)

print("Generated SQL:")
print(result['sql'])

# Execute the SQL (using pandas)
import pandas as pd
df = pd.read_sql(result['sql'], "postgresql://localhost/analytics_db")
df.head()
```

This guide shows how nlp2sql automatically handles schema loading, making it much easier to use while providing powerful filtering options for large databases.