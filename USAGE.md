# nlp2sql Usage Guide

## Quick Start with Automatic Schema Loading

The easiest way to use nlp2sql is with automatic schema loading from your database.

### 1. One-Line API with Smart Provider Detection

```python
import asyncio
import os
from nlp2sql import generate_sql_from_db

async def main():
    # Smart provider detection - uses first available API key
    api_keys = {
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "gemini": os.getenv("GOOGLE_API_KEY")  # Note: GOOGLE_API_KEY for Gemini
    }
    
    # Find first available provider
    for provider, api_key in api_keys.items():
        if api_key:
            print(f"🤖 Using {provider} provider")
            result = await generate_sql_from_db(
                database_url="postgresql://testuser:testpass@localhost:5432/testdb",  # Docker test DB
                question="Show me all active users",
                ai_provider=provider,
                api_key=api_key
            )
            print(f"📝 SQL: {result['sql']}")
            print(f"🎯 Confidence: {result['confidence']}")
            return result
    
    raise ValueError("No API key found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY")

asyncio.run(main())
```

### 2. Pre-Initialized Service with Provider Auto-Detection

```python
import asyncio
import os
from nlp2sql import create_and_initialize_service

async def main():
    # Auto-detect available provider
    providers = [
        {"name": "openai", "env_var": "OPENAI_API_KEY"},
        {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY"},
        {"name": "gemini", "env_var": "GOOGLE_API_KEY"}
    ]
    
    selected_provider = None
    for provider in providers:
        api_key = os.getenv(provider["env_var"])
        if api_key:
            selected_provider = {"name": provider["name"], "key": api_key}
            break
    
    if not selected_provider:
        raise ValueError("No API key found")
    
    print(f"🤖 Using {selected_provider['name']} provider")
    
    # Initialize once with Docker test database
    service = await create_and_initialize_service(
        database_url="postgresql://testuser:testpass@localhost:5432/testdb",
        ai_provider=selected_provider["name"],
        api_key=selected_provider["key"]
    )
    
    # Use multiple times - much faster after initialization
    questions = [
        "Count total users",
        "Find users who have never placed an order", 
        "Show product categories with their item counts"
    ]
    
    for i, question in enumerate(questions, 1):
        print(f"\n{i}. ❓ {question}")
        result = await service.generate_sql(question)
        print(f"   📝 SQL: {result['sql']}")
        print(f"   🎯 Confidence: {result['confidence']}")

asyncio.run(main())
```

### 3. Manual Service Creation with Enterprise Schema Filtering

```python
import asyncio
import os
from nlp2sql import create_query_service, DatabaseType

async def main():
    # Create service with enterprise-grade schema filtering
    service = create_query_service(
        database_url="postgresql://demo:demo123@localhost:5433/enterprise",  # Large Docker DB
        ai_provider="anthropic",  # Best for large schemas
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        schema_filters={
            "include_schemas": ["sales", "finance", "hr"],  # Focus on business schemas
            "exclude_schemas": ["archive", "temp"],
            "include_tables": ["customers", "orders", "products", "employees", "transactions"],
            "exclude_tables": ["audit_logs", "system_logs", "migration_history"],
            "exclude_system_tables": True
        }
    )
    
    # Initialize (loads filtered schema automatically)
    await service.initialize(DatabaseType.POSTGRES)
    
    # Generate SQL with large schema optimization
    enterprise_questions = [
        "Show revenue by month for the sales team",
        "Find top performing sales representatives",
        "Calculate customer acquisition costs by channel",
        "Show employee headcount by department"
    ]
    
    for question in enterprise_questions:
        print(f"\n❓ {question}")
        result = await service.generate_sql(
            question=question,
            database_type=DatabaseType.POSTGRES,
            max_tokens=1500,  # Higher for complex queries
            temperature=0.1   # More deterministic
        )
        
        print(f"📝 SQL: {result['sql'][:100]}{'...' if len(result['sql']) > 100 else ''}")
        print(f"🎯 Confidence: {result['confidence']}")
        print(f"✅ Valid: {result['validation']['is_valid']}")
        if result['validation'].get('issues'):
            print(f"⚠️  Issues: {result['validation']['issues']}")

asyncio.run(main())
```

## Multiple AI Providers Support

nlp2sql supports multiple AI providers - you're not locked into OpenAI!

### Supported Providers with Docker Databases

```python
# OpenAI GPT-4 - Best for complex reasoning
service = await create_and_initialize_service(
    database_url="postgresql://testuser:testpass@localhost:5432/testdb",
    ai_provider="openai",
    api_key="your-openai-key"
)

# Anthropic Claude - Best for large schemas (200K context)
service = await create_and_initialize_service(
    database_url="postgresql://demo:demo123@localhost:5433/enterprise",  # Large DB
    ai_provider="anthropic",
    api_key="your-anthropic-key",
    schema_filters={"include_schemas": ["sales"], "exclude_system_tables": True}
)

# Google Gemini - Best for high volume/cost efficiency (1M context)
service = await create_and_initialize_service(
    database_url="postgresql://testuser:testpass@localhost:5432/testdb",
    ai_provider="gemini", 
    api_key="your-google-key"  # Uses GOOGLE_API_KEY environment variable
)
```

### Installation for Different Providers

```bash
# Development installation (includes all providers)
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql
uv sync  # Installs all dependencies

# Setup Docker test databases
cd docker
docker-compose up -d
cd ..

# Production installation
pip install nlp2sql  # OpenAI only (default)
pip install nlp2sql[anthropic]  # Add Anthropic
pip install nlp2sql[gemini]     # Add Google Gemini  
pip install nlp2sql[all-providers]  # All providers
```

### Provider Comparison

| Provider | Context Size | Cost/1K tokens | Best For | Environment Variable |
|----------|-------------|----------------|----------|--------------------|
| OpenAI GPT-4 | 128K | $0.030 | Complex reasoning | `OPENAI_API_KEY` |
| Anthropic Claude | 200K | $0.015 | Large schemas | `ANTHROPIC_API_KEY` |
| Google Gemini | 1M | $0.001 | High volume/cost | `GOOGLE_API_KEY` |

### Choosing the Right Provider for Your Use Case

```python
import os
from nlp2sql import generate_sql_from_db

# For complex analytical queries - OpenAI excels at reasoning
result = await generate_sql_from_db(
    "postgresql://testuser:testpass@localhost:5432/testdb", 
    "Calculate year-over-year revenue growth by product category with seasonal adjustments",
    ai_provider="openai",
    api_key=os.getenv("OPENAI_API_KEY")
)

# For large database schemas (1000+ tables) - Anthropic has 200K context
result = await generate_sql_from_db(
    "postgresql://demo:demo123@localhost:5433/enterprise",
    "Find customers with unusual purchasing patterns across multiple business units", 
    ai_provider="anthropic",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

# For high-volume applications - Gemini is most cost-effective with 1M context
result = await generate_sql_from_db(
    "postgresql://testuser:testpass@localhost:5432/testdb",
    "Count active users today",
    ai_provider="gemini",
    api_key=os.getenv("GOOGLE_API_KEY")
)
```

### Enhanced Provider Fallback Strategy

```python
import asyncio
import os
from nlp2sql import generate_sql_from_db
from nlp2sql.exceptions import ProviderException, TokenLimitException

async def robust_sql_generation(question: str, database_url: str = None):
    """Try multiple providers with intelligent fallback and error handling."""
    
    # Default to Docker test database if none specified
    if not database_url:
        database_url = "postgresql://testuser:testpass@localhost:5432/testdb"
    
    # Provider priority: try most reliable first, then cost-effective
    providers = [
        {"name": "openai", "env_var": "OPENAI_API_KEY", "strength": "Complex reasoning"},
        {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY", "strength": "Large schemas"},
        {"name": "gemini", "env_var": "GOOGLE_API_KEY", "strength": "Cost effective"}
    ]
    
    for provider in providers:
        api_key = os.getenv(provider["env_var"])
        if not api_key:
            print(f"⏭️  Skipping {provider['name']} - no API key found")
            continue
            
        try:
            print(f"🔄 Trying {provider['name']} ({provider['strength']})...")
            result = await generate_sql_from_db(
                database_url=database_url,
                question=question, 
                ai_provider=provider["name"],
                api_key=api_key
            )
            
            print(f"✅ Success with {provider['name']}!")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Valid: {result['validation']['is_valid']}")
            return result
            
        except TokenLimitException as e:
            print(f"❌ {provider['name']}: Token limit exceeded - {e}")
        except ProviderException as e:
            print(f"❌ {provider['name']}: Provider error - {e}")
        except Exception as e:
            print(f"❌ {provider['name']}: Unexpected error - {str(e)[:100]}")
            continue
    
    raise Exception("All providers failed - check API keys and network connectivity")

# Example usage with different scenarios
async def test_fallback_scenarios():
    """Test fallback with different query complexities."""
    
    scenarios = [
        {
            "name": "Simple Query", 
            "question": "Count total users",
            "database": "postgresql://testuser:testpass@localhost:5432/testdb"
        },
        {
            "name": "Complex Analytics",
            "question": "Show monthly user registration trends with year-over-year comparison",
            "database": "postgresql://testuser:testpass@localhost:5432/testdb"
        },
        {
            "name": "Enterprise Query",
            "question": "Analyze sales performance by representative across all regions",
            "database": "postgresql://demo:demo123@localhost:5433/enterprise"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n🧪 Testing: {scenario['name']}")
        print(f"   Question: {scenario['question']}")
        try:
            result = await robust_sql_generation(
                question=scenario['question'],
                database_url=scenario['database']
            )
            print(f"   📝 SQL: {result['sql'][:80]}{'...' if len(result['sql']) > 80 else ''}")
        except Exception as e:
            print(f"   ❌ All providers failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_fallback_scenarios())
```

## Schema Filtering for Large Databases

For databases with 1000+ tables, use schema filters to improve performance:

### Basic Filtering with Docker Enterprise Database

```python
import os
from nlp2sql import create_and_initialize_service

async def basic_filtering_demo():
    # Exclude system tables and common noise
    filters = {
        "exclude_system_tables": True,
        "exclude_tables": ["audit_log", "temp_data", "migration_history", "system_logs"]
    }

    service = await create_and_initialize_service(
        database_url="postgresql://demo:demo123@localhost:5433/enterprise",
        ai_provider="anthropic",  # Good for large schemas
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        schema_filters=filters
    )
    
    # Compare with and without filtering
    print("🔍 Testing filtered vs unfiltered schema performance...")
    
    # This query will be faster with filtering
    result = await service.generate_sql(
        "Show me sales performance metrics by team"
    )
    
    print(f"✅ Filtered query result:")
    print(f"   SQL: {result['sql'][:100]}...")
    print(f"   Confidence: {result['confidence']}")
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(basic_filtering_demo())
```

### Business Domain Filtering for Enterprise

```python
import os
from nlp2sql import create_and_initialize_service

async def business_domain_demo():
    """Demonstrate filtering by business domains for enterprise applications."""
    
    # Focus on core business entities across multiple domains
    business_filters = {
        "include_schemas": ["sales", "hr", "finance"],  # Business schemas only
        "include_tables": [
            # Customer relationship
            "customers", "customer_profiles", "customer_contacts",
            
            # Sales operations
            "orders", "order_items", "sales_reps", "territories",
            
            # Product management
            "products", "product_categories", "inventory",
            
            # Human resources
            "employees", "departments", "job_roles",
            
            # Financial
            "invoices", "payments", "transactions"
        ],
        "exclude_tables": [
            # Exclude high-volume, low-value tables
            "audit_logs", "system_logs", "email_logs",
            "temp_imports", "data_migrations", "cache_tables"
        ],
        "exclude_system_tables": True
    }
    
    print("🏢 Creating enterprise service with business domain filtering...")
    service = await create_and_initialize_service(
        database_url="postgresql://demo:demo123@localhost:5433/enterprise",
        ai_provider="anthropic",  # Best for complex schemas
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        schema_filters=business_filters
    )
    
    # Test business-focused queries
    business_queries = [
        "Show me top performing sales representatives by revenue",
        "Find customers who haven't placed orders in the last 6 months",
        "Calculate average order value by product category",
        "Show employee headcount by department",
        "Analyze payment trends over the last quarter"
    ]
    
    print(f"\n📊 Testing {len(business_queries)} business queries with filtered schema:")
    
    for i, query in enumerate(business_queries, 1):
        print(f"\n{i}. ❓ {query}")
        try:
            result = await service.generate_sql(query)
            print(f"   ✅ Success - Confidence: {result['confidence']}")
            print(f"   📝 SQL: {result['sql'][:100]}{'...' if len(result['sql']) > 100 else ''}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:100]}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(business_domain_demo())
```

### Schema-Based Filtering for Multi-Tenant Systems

```python
import os
from nlp2sql import create_and_initialize_service

async def schema_based_filtering_demo():
    """Demonstrate schema-based filtering for multi-tenant or departmental systems."""
    
    # Different filtering strategies for different use cases
    filtering_strategies = [
        {
            "name": "Sales Department Focus",
            "filters": {
                "include_schemas": ["sales", "finance"],
                "exclude_schemas": ["archive", "temp", "staging"],
                "exclude_system_tables": True
            },
            "test_query": "Show quarterly sales performance by region"
        },
        {
            "name": "HR Analytics", 
            "filters": {
                "include_schemas": ["hr", "payroll"],
                "include_tables": ["employees", "departments", "performance_reviews", "salaries"],
                "exclude_system_tables": True
            },
            "test_query": "Calculate average tenure by department"
        },
        {
            "name": "Financial Reporting",
            "filters": {
                "include_schemas": ["finance", "accounting"],
                "exclude_tables": ["audit_trails", "reconciliation_temp"],
                "exclude_system_tables": True
            },
            "test_query": "Show monthly revenue trends with cost analysis"
        }
    ]
    
    for strategy in filtering_strategies:
        print(f"\n🎯 {strategy['name']} Strategy:")
        print(f"   Filters: {strategy['filters']}")
        
        try:
            service = await create_and_initialize_service(
                database_url="postgresql://demo:demo123@localhost:5433/enterprise",
                ai_provider="anthropic",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                schema_filters=strategy['filters']
            )
            
            result = await service.generate_sql(strategy['test_query'])
            print(f"   ✅ Query successful:")
            print(f"   📝 SQL: {result['sql'][:80]}{'...' if len(result['sql']) > 80 else ''}")
            print(f"   🎯 Confidence: {result['confidence']}")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:100]}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(schema_based_filtering_demo())
```

## Command Line Interface

### Schema Inspection with Docker Databases

```bash
# Basic schema summary - simple test database
uv run nlp2sql inspect --database-url postgresql://testuser:testpass@localhost:5432/testdb

# Enterprise database inspection
uv run nlp2sql inspect --database-url postgresql://demo:demo123@localhost:5433/enterprise

# Export schema as JSON for analysis
uv run nlp2sql inspect --database-url postgresql://demo:demo123@localhost:5433/enterprise --format json --output enterprise_schema.json

# Compare databases side by side
uv run nlp2sql inspect --database-url postgresql://testuser:testpass@localhost:5432/testdb --format table > simple_db.txt
uv run nlp2sql inspect --database-url postgresql://demo:demo123@localhost:5433/enterprise --format table > enterprise_db.txt
```

### SQL Generation from CLI with Smart Provider Detection

```bash
# Generate SQL with auto-provider detection (uses first available API key)
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Show me all active users" \
  --explain

# Specify provider explicitly
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Count total orders" \
  --provider anthropic

# Enterprise database with comprehensive schema filtering
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Analyze sales performance by team" \
  --provider anthropic \
  --schema-filters '{
    "include_schemas": ["sales", "finance"], 
    "exclude_system_tables": true,
    "include_tables": ["sales_reps", "customers", "orders", "territories"],
    "exclude_tables": ["audit_logs", "temp_data"]
  }' \
  --explain

# Test all providers with the same query for comparison
for provider in openai anthropic gemini; do
  echo "\n🤖 Testing $provider:"
  uv run nlp2sql query \
    --database-url postgresql://testuser:testpass@localhost:5432/testdb \
    --question "Show product categories with item counts" \
    --provider $provider
done
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

### Performance Optimization for Large Schemas (1000+ Tables)

```python
import asyncio
import time
import os
from nlp2sql import create_and_initialize_service

async def optimized_for_large_db():
    """Demonstrate performance optimization strategies for enterprise-scale databases."""
    
    # Strategy for 1000+ table databases - progressive filtering
    optimization_levels = [
        {
            "name": "Level 1 - Basic Optimization",
            "filters": {
                "exclude_system_tables": True
            }
        },
        {
            "name": "Level 2 - Schema Focused", 
            "filters": {
                "exclude_system_tables": True,
                "include_schemas": ["sales", "finance", "hr"],
                "exclude_schemas": ["archive", "temp", "staging"]
            }
        },
        {
            "name": "Level 3 - Table Specific (Recommended for 1000+ tables)",
            "filters": {
                "exclude_system_tables": True,
                "include_schemas": ["sales", "finance"],
                "include_tables": [
                    # Core business entities (15-25 tables max)
                    "customers", "sales_reps", "territories", "opportunities",
                    "orders", "order_items", "products", "product_categories",
                    "invoices", "payments", "transactions", "accounts",
                    "contracts", "quotes", "leads"
                ],
                "exclude_tables": [
                    # Exclude high-volume, low-business-value tables
                    "audit_logs", "system_logs", "email_logs", "api_logs",
                    "session_data", "cache_tables", "temp_imports",
                    "data_migrations", "backup_tables", "etl_staging"
                ]
            }
        }
    ]
    
    # Test query for performance comparison
    test_query = "Analyze sales performance by representative with customer acquisition metrics"
    
    print("🚀 Performance Optimization Demo for Large Databases")
    print("=" * 60)
    
    for level in optimization_levels:
        print(f"\n📊 {level['name']}")
        print(f"   Filters: {len(level['filters'])} filter types")
        
        try:
            start_time = time.time()
            
            service = await create_and_initialize_service(
                database_url="postgresql://demo:demo123@localhost:5433/enterprise",
                ai_provider="anthropic",  # Best for large schemas
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                schema_filters=level['filters']
            )
            
            initialization_time = time.time() - start_time
            
            query_start = time.time()
            result = await service.generate_sql(test_query)
            query_time = time.time() - query_start
            
            print(f"   ✅ Initialization: {initialization_time:.2f}s")
            print(f"   ✅ Query generation: {query_time:.2f}s")
            print(f"   🎯 Confidence: {result['confidence']}")
            print(f"   📝 SQL: {result['sql'][:80]}{'...' if len(result['sql']) > 80 else ''}")
            
            # Get schema statistics if available
            if hasattr(service, 'schema_repository'):
                tables = await service.schema_repository.get_tables()
                print(f"   📊 Tables loaded: {len(tables)}")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:100]}")
    
    print("\n💡 Performance Tips for Large Databases:")
    print("   1. Always start with exclude_system_tables=True")
    print("   2. Use include_tables for laser-focused queries (15-25 tables max)")
    print("   3. Leverage include_schemas for departmental boundaries")
    print("   4. Exclude high-volume audit/log tables")
    print("   5. Consider Anthropic provider for 200K context window")
    print("   6. Monitor initialization vs query time ratios")
    
    print("\n🎯 Expected Performance Gains with Level 3:")
    print("   • 10-50x faster initialization")
    print("   • 5-20x faster query generation")
    print("   • 80-95% reduction in memory usage")
    print("   • Higher AI confidence scores")
    print("   • More focused, accurate SQL queries")

if __name__ == "__main__":
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

### FastAPI Integration with Multi-Provider Support

```python
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import asyncio
from nlp2sql import create_and_initialize_service
from nlp2sql.exceptions import ProviderException, TokenLimitException

app = FastAPI(title="nlp2sql API", description="Natural Language to SQL API with multi-provider support")

# Request/Response models
class SQLRequest(BaseModel):
    question: str
    provider: Optional[str] = None  # auto-detect if not specified
    database: Optional[str] = "simple"  # "simple" or "enterprise"
    explain: bool = False

class SQLResponse(BaseModel):
    sql: str
    confidence: float
    provider: str
    explanation: Optional[str] = None
    validation: Dict[str, Any]
    execution_time: float

# Global services cache
services_cache = {}

async def get_or_create_service(provider: str, database: str):
    """Get cached service or create new one."""
    cache_key = f"{provider}_{database}"
    
    if cache_key not in services_cache:
        # Database URLs
        db_urls = {
            "simple": "postgresql://testuser:testpass@localhost:5432/testdb",
            "enterprise": "postgresql://demo:demo123@localhost:5433/enterprise"
        }
        
        # Provider API keys
        api_keys = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "gemini": os.getenv("GOOGLE_API_KEY")
        }
        
        api_key = api_keys.get(provider)
        if not api_key:
            raise HTTPException(status_code=400, detail=f"No API key found for {provider}")
        
        # Schema filters for enterprise database
        schema_filters = None
        if database == "enterprise":
            schema_filters = {
                "include_schemas": ["sales", "finance", "hr"],
                "exclude_system_tables": True,
                "exclude_tables": ["audit_logs", "system_logs"]
            }
        
        try:
            service = await create_and_initialize_service(
                database_url=db_urls[database],
                ai_provider=provider,
                api_key=api_key,
                schema_filters=schema_filters
            )
            services_cache[cache_key] = service
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to initialize {provider} service: {str(e)}")
    
    return services_cache[cache_key]

async def detect_best_provider() -> str:
    """Auto-detect available provider."""
    providers = [
        ("openai", os.getenv("OPENAI_API_KEY")),
        ("anthropic", os.getenv("ANTHROPIC_API_KEY")), 
        ("gemini", os.getenv("GOOGLE_API_KEY"))
    ]
    
    for provider, api_key in providers:
        if api_key:
            return provider
    
    raise HTTPException(status_code=400, detail="No API keys found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY")

@app.post("/generate-sql", response_model=SQLResponse)
async def generate_sql_endpoint(request: SQLRequest):
    """Generate SQL from natural language with provider fallback."""
    import time
    start_time = time.time()
    
    try:
        # Auto-detect provider if not specified
        provider = request.provider or await detect_best_provider()
        
        # Get service (cached or create new)
        service = await get_or_create_service(provider, request.database)
        
        # Generate SQL
        result = await service.generate_sql(request.question)
        
        execution_time = time.time() - start_time
        
        return SQLResponse(
            sql=result['sql'],
            confidence=result['confidence'],
            provider=provider,
            explanation=result.get('explanation') if request.explain else None,
            validation=result['validation'],
            execution_time=execution_time
        )
        
    except TokenLimitException as e:
        raise HTTPException(status_code=413, detail=f"Query too complex: {str(e)}")
    except ProviderException as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@app.get("/providers")
async def list_providers():
    """List available providers and their status."""
    providers = [
        {"name": "openai", "available": bool(os.getenv("OPENAI_API_KEY"))},
        {"name": "anthropic", "available": bool(os.getenv("ANTHROPIC_API_KEY"))},
        {"name": "gemini", "available": bool(os.getenv("GOOGLE_API_KEY"))}
    ]
    return {"providers": providers}

@app.get("/health")
async def health_check():
    """Health check endpoint with service status."""
    return {
        "status": "healthy",
        "services_cached": len(services_cache),
        "providers_available": len([p for p in [
            os.getenv("OPENAI_API_KEY"),
            os.getenv("ANTHROPIC_API_KEY"), 
            os.getenv("GOOGLE_API_KEY")
        ] if p])
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Usage Examples:**
```bash
# Start the API server
cd nlp2sql && uvicorn main:app --reload

# Test with curl
curl -X POST "http://localhost:8000/generate-sql" \
     -H "Content-Type: application/json" \
     -d '{
       "question": "Show me top 5 customers by revenue",
       "database": "enterprise",
       "provider": "anthropic",
       "explain": true
     }'

# Check available providers
curl "http://localhost:8000/providers"
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
