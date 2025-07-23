# nlp2sql - Quick Start Guide

## 🚀 Get Started in 5 Minutes

### 1. Install Dependencies
```bash
# Make sure you have UV installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install dependencies
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql
uv sync

# Start Docker test databases
cd docker
docker-compose up -d
cd ..
```

### 2. Set Environment Variables
```bash
# AI Provider API Keys (at least one required)
export OPENAI_API_KEY="your-openai-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"  # optional
export GOOGLE_API_KEY="your-google-api-key"        # optional (Note: GOOGLE_API_KEY, not GEMINI_API_KEY)

# Docker Test Databases (automatically available after step 1)
export DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb"  # Simple DB
# export DATABASE_URL="postgresql://demo:demo123@localhost:5433/enterprise"  # Enterprise DB

# Optional Performance Settings
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_LOG_LEVEL=INFO
export TOKENIZERS_PARALLELISM=false  # Suppress warnings
```

### 3. Basic Usage with Smart Provider Detection
```python
import asyncio
import os
from nlp2sql import create_query_service, DatabaseType

async def main():
    # Smart provider detection - uses first available API key
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
        raise ValueError("No API key found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY")
    
    print(f"🤖 Using {selected_provider['name'].title()} provider")
    
    # Create and initialize service with Docker test database
    service = create_query_service(
        database_url="postgresql://testuser:testpass@localhost:5432/testdb",
        ai_provider=selected_provider["name"],
        api_key=selected_provider["key"]
    )
    
    await service.initialize(DatabaseType.POSTGRES)
    
    # Generate SQL from natural language
    result = await service.generate_sql(
        question="Show me all users with their email addresses",
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
# Test CLI with different providers (auto-detection)
uv run nlp2sql query \
  --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
  --question "How many users are there?"

# Test specific provider
uv run nlp2sql query \
  --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
  --question "Show me all products with their categories" \
  --provider anthropic --explain

# Run demo examples (now use Docker databases and smart provider detection)
uv run python examples/getting_started/simple_demo.py
uv run python examples/documentation/real_world_example.py
uv run python examples/advanced/test_multiple_providers.py

# Run basic tests
uv run pytest tests/test_basic.py -v
```

### 5. Example Queries You Can Try

**Simple queries (testdb Docker database):**
- "How many users are there?"
- "Show me all products with their categories"
- "Find the top 5 products by average rating"
- "Count total orders placed"

**Complex queries (testdb):**
- "Show me users who have never placed an order"
- "Find products that have no reviews yet"
- "Which categories have the most expensive products?"
- "Show me all orders with their customer information"

**Enterprise queries (enterprise Docker database):**
- "Show sales performance by representative"
- "Calculate monthly revenue trends"
- "Find customers with highest lifetime value"
- "Identify departments with most employees"

**Multi-provider testing:**
```bash
# Test the same query with different providers
for provider in openai anthropic gemini; do
  echo "Testing $provider..."
  uv run nlp2sql query \
    --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
    --question "Show me the most popular product categories" \
    --provider $provider
done
```

### 6. Advanced Features

```python
import asyncio
import os
from nlp2sql import create_and_initialize_service

async def advanced_features_demo():
    # Provider auto-detection
    providers = [
        {"name": "openai", "key": os.getenv("OPENAI_API_KEY")},
        {"name": "anthropic", "key": os.getenv("ANTHROPIC_API_KEY")}, 
        {"name": "gemini", "key": os.getenv("GOOGLE_API_KEY")}
    ]
    
    selected = next((p for p in providers if p["key"]), None)
    if not selected:
        print("No API key found")
        return
        
    # Initialize with Docker database and schema filtering
    service = await create_and_initialize_service(
        database_url="postgresql://demo:demo123@localhost:5433/enterprise",
        ai_provider=selected["name"],
        api_key=selected["key"],
        schema_filters={
            "include_schemas": ["sales", "hr"],
            "exclude_system_tables": True
        }
    )
    
    # Generate with validation
    result = await service.generate_sql(
        "Show me sales representatives with their territories"
    )
    
    print(f"🤖 Provider: {selected['name']}")
    print(f"📝 SQL: {result['sql']}")
    print(f"🎯 Confidence: {result['confidence']}")
    print(f"✅ Valid: {result['validation']['is_valid']}")
    print(f"📊 Issues: {result['validation'].get('issues', [])}")
    
    # Test with different providers if available
    for provider in providers:
        if provider["key"] and provider["name"] != selected["name"]:
            print(f"\n🔄 Testing {provider['name']}...")
            # Quick test with different provider
            break

if __name__ == "__main__":
    asyncio.run(advanced_features_demo())
```

### 7. Multi-Provider Configuration

```python
import os
from nlp2sql import create_and_initialize_service

async def multi_provider_setup():
    """Demonstrate configuration for different providers and use cases."""
    
    # Configuration for different scenarios
    configs = [
        {
            "name": "Simple Database - OpenAI",
            "provider": "openai",
            "database_url": "postgresql://testuser:testpass@localhost:5432/testdb",
            "use_case": "Complex reasoning queries"
        },
        {
            "name": "Enterprise Database - Anthropic", 
            "provider": "anthropic",
            "database_url": "postgresql://demo:demo123@localhost:5433/enterprise",
            "schema_filters": {
                "include_schemas": ["sales", "finance"],
                "exclude_system_tables": True
            },
            "use_case": "Large schema handling"
        },
        {
            "name": "High Volume - Gemini",
            "provider": "gemini", 
            "database_url": "postgresql://testuser:testpass@localhost:5432/testdb",
            "use_case": "Cost-effective queries"
        }
    ]
    
    for config in configs:
        api_key = os.getenv(f"{config['provider'].upper()}_API_KEY") or \
                 os.getenv("GOOGLE_API_KEY" if config['provider'] == 'gemini' else f"{config['provider'].upper()}_API_KEY")
        
        if api_key:
            print(f"\n🔧 {config['name']}")
            print(f"   Use case: {config['use_case']}")
            print(f"   Provider: {config['provider']}")
            
            service = await create_and_initialize_service(
                database_url=config['database_url'],
                ai_provider=config['provider'],
                api_key=api_key,
                schema_filters=config.get('schema_filters')
            )
            
            # Test with a simple query
            result = await service.generate_sql("Count total records")
            print(f"   ✅ Test query successful: {result['sql'][:50]}...")

if __name__ == "__main__":
    import asyncio
    asyncio.run(multi_provider_setup())
```

### 8. Error Handling & Provider Fallback

```python
import asyncio
import os
from nlp2sql import generate_sql_from_db
from nlp2sql.exceptions import (
    TokenLimitException, 
    QueryGenerationException, 
    ProviderException
)

async def robust_query_with_fallback(question: str):
    """Try multiple providers with proper error handling."""
    
    providers = [
        {"name": "openai", "env_var": "OPENAI_API_KEY"},
        {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY"},
        {"name": "gemini", "env_var": "GOOGLE_API_KEY"}
    ]
    
    database_url = "postgresql://testuser:testpass@localhost:5432/testdb"
    
    for provider in providers:
        api_key = os.getenv(provider["env_var"])
        if not api_key:
            print(f"⏭️  Skipping {provider['name']} - no API key")
            continue
            
        try:
            print(f"🔄 Trying {provider['name']}...")
            result = await generate_sql_from_db(
                database_url=database_url,
                question=question,
                ai_provider=provider["name"],
                api_key=api_key
            )
            
            print(f"✅ Success with {provider['name']}!")
            print(f"   SQL: {result['sql']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Valid: {result['validation']['is_valid']}")
            return result
            
        except TokenLimitException as e:
            print(f"❌ {provider['name']}: Token limit exceeded")
        except QueryGenerationException as e:
            print(f"❌ {provider['name']}: Query generation failed - {str(e)[:100]}")
        except ProviderException as e:
            print(f"❌ {provider['name']}: Provider error - {str(e)[:100]}") 
        except Exception as e:
            print(f"❌ {provider['name']}: Unexpected error - {str(e)[:100]}")
    
    raise Exception("All providers failed")

# Test the fallback system
if __name__ == "__main__":
    asyncio.run(robust_query_with_fallback("Show me user analytics with monthly trends"))
```

## 🎯 Perfect for Your Use Case

This library is specifically designed to solve the challenge of converting natural language to SQL in enterprise environments with:

- ✅ **Multiple AI providers** (OpenAI, Anthropic, Gemini) with smart auto-detection
- ✅ **Large database schemas** (1000+ tables) with advanced filtering
- ✅ **Docker development environment** for quick testing
- ✅ **Intelligent caching** for fast responses
- ✅ **Automatic query optimization** and validation
- ✅ **Production-ready** architecture with robust error handling
- ✅ **Provider fallback system** for maximum reliability

## 🐳 Docker Quick Test

```bash
# Start test databases
cd docker && docker-compose up -d

# Test all providers quickly
for provider in openai anthropic gemini; do
  if [ ! -z "${!provider^^}_API_KEY" ] || [ ! -z "$GOOGLE_API_KEY" ]; then
    echo "Testing $provider..."
    uv run nlp2sql query \
      --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
      --question "How many users are registered?" \
      --provider $provider
  fi
done
```

## 🔧 Development Commands

```bash
# Setup development environment
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql
uv sync
cd docker && docker-compose up -d && cd ..

# Test CLI functionality
export OPENAI_API_KEY=your-key  # or ANTHROPIC_API_KEY or GOOGLE_API_KEY
uv run nlp2sql validate  # Check configuration
uv run nlp2sql providers test  # Test all providers

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

# Test examples
uv run python examples/getting_started/simple_demo.py
uv run python examples/advanced/test_multiple_providers.py
```

## 🚀 You're Ready!

Your nlp2sql library is now ready to solve your natural language to SQL challenge. The architecture is designed to be:

- **Multi-Provider** - seamlessly switch between OpenAI, Anthropic, and Gemini
- **Scalable** - handles large schemas efficiently with smart filtering
- **Developer-Friendly** - Docker setup, comprehensive CLI, auto-detection
- **Production-Ready** - robust error handling, validation, and fallback systems
- **Enterprise-Scale** - supports 1000+ table databases with advanced optimization

### Next Steps:

1. **Start Simple**: Test with Docker databases using auto-provider detection
2. **Scale Up**: Try enterprise database with schema filtering
3. **Compare Providers**: Use benchmark command to find optimal provider
4. **Production Deploy**: Implement fallback system for maximum reliability

**Quick Win**: Run this command to see everything working:
```bash
uv run nlp2sql query \
  --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
  --question "Show me a summary of our data" \
  --explain
```

Start with simple queries and gradually move to more complex ones as you get familiar with the library!
