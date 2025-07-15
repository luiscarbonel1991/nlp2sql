# Migration Guide

This guide helps you migrate from other NLP-to-SQL frameworks to nlp2sql with minimal code changes and maximum benefit.

## 🔄 From Research/Academic Frameworks

### Common Migration Pattern

Most research frameworks use a composable, task-based approach:

**Before (Research Framework):**
```python
from research_nl2sql import TaskChain, SchemaAnalyzer, QueryGenerator
from research_nl2sql.thoughts import ChainOfThought

# Complex setup
analyzer = SchemaAnalyzer(
    embeddings_model="sentence-transformers",
    enable_cot=True,
    max_tables=50
)

generator = QueryGenerator(
    model="gpt-4",
    temperature=0.1,
    thoughts_enabled=True
)

# Chain tasks together
chain = TaskChain()
chain.add_task(analyzer)
chain.add_task(generator)

# Execute
result = chain.execute(
    question="Show me sales by region",
    schema=database_schema,
    examples=few_shot_examples
)

sql = result.tasks[-1].output.sql
explanation = result.tasks[-1].thoughts.explanation
```

**After (nlp2sql):**
```python
from nlp2sql import generate_sql_from_db

# Simple, production-ready
result = await generate_sql_from_db(
    database_url="postgresql://localhost/sales_db",
    question="Show me sales by region",
    ai_provider="openai",
    api_key="your-api-key",
    explain=True  # Get explanations
)

sql = result['sql']
explanation = result['explanation']
confidence = result['confidence']  # Bonus: confidence scoring
```

### Benefits of Migration

- **90% less code** for common use cases
- **Built-in optimizations** (caching, async, schema filtering)
- **Multi-provider support** (no vendor lock-in)
- **Production-ready** (error handling, monitoring)
- **Better performance** (vector embeddings, intelligent caching)

## 🔧 From Custom OpenAI Implementations

### Typical Custom Implementation

**Before (Custom OpenAI):**
```python
import openai
import json
from typing import Dict, List

class CustomNL2SQL:
    def __init__(self, api_key: str, database_schema: Dict):
        self.client = openai.OpenAI(api_key=api_key)
        self.schema = database_schema
    
    def build_prompt(self, question: str) -> str:
        schema_text = self._schema_to_text(self.schema)
        return f"""
        Database schema:
        {schema_text}
        
        Question: {question}
        
        Generate SQL query:
        """
    
    def generate_sql(self, question: str) -> str:
        prompt = self.build_prompt(question)
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        return response.choices[0].message.content
    
    def _schema_to_text(self, schema: Dict) -> str:
        # Custom schema serialization logic
        # ... complex implementation
        pass

# Usage
nl2sql = CustomNL2SQL(api_key="...", database_schema=schema)
sql = nl2sql.generate_sql("Show active users")
```

**After (nlp2sql):**
```python
from nlp2sql import create_and_initialize_service

# Automatic schema loading and optimization
service = await create_and_initialize_service(
    database_url="postgresql://localhost/db",
    api_key="your-openai-key"
)

# Enhanced features built-in
result = await service.generate_sql("Show active users")
sql = result['sql']
confidence = result['confidence']
is_valid = result['validation']['is_valid']
```

### Migration Benefits

- **Automatic schema management** (no manual serialization)
- **Built-in validation** (SQL syntax and safety checks)
- **Performance optimization** (caching, batching)
- **Error handling** (retries, fallbacks)
- **Multi-provider ready** (easy to switch from OpenAI)

## 📊 From Single-Provider Solutions

### Locked-in Implementation

**Before (OpenAI-only):**
```python
# Tightly coupled to OpenAI
import openai

def generate_query(question: str, schema: str) -> str:
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"Schema: {schema}"},
            {"role": "user", "content": question}
        ]
    )
    return response.choices[0].message.content

# Hard to change provider
sql = generate_query("Count users", schema_text)
```

**After (nlp2sql):**
```python
from nlp2sql import generate_sql_from_db

# Provider flexibility
result = await generate_sql_from_db(
    database_url="postgresql://localhost/db",
    question="Count users",
    ai_provider="openai"  # Easy to change to "anthropic" or "gemini"
)

# Compare providers
benchmark_results = await benchmark_providers(
    database_url="postgresql://localhost/db",
    questions=["Count users", "Show sales trends"],
    providers=["openai", "anthropic", "gemini"]
)
```

### Provider Migration Strategy

```python
# Gradual migration approach
async def hybrid_generation(question: str):
    # Start with your current provider
    try:
        result = await generate_sql_from_db(
            database_url=db_url,
            question=question,
            ai_provider="openai"  # Your current provider
        )
        
        # Log for comparison
        log_result("openai", result)
        return result
        
    except Exception:
        # Fallback to alternative provider
        return await generate_sql_from_db(
            database_url=db_url,
            question=question,
            ai_provider="anthropic"  # Backup provider
        )
```

## 🗄️ From Manual Schema Management

### Manual Schema Handling

**Before (Manual):**
```python
# Manual schema extraction and formatting
def get_schema_text(connection):
    tables = []
    cursor = connection.cursor()
    
    cursor.execute("SELECT table_name FROM information_schema.tables")
    table_names = cursor.fetchall()
    
    for (table_name,) in table_names:
        cursor.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
        """)
        columns = cursor.fetchall()
        
        table_info = f"Table {table_name}:\n"
        for col_name, col_type in columns:
            table_info += f"  - {col_name}: {col_type}\n"
        
        tables.append(table_info)
    
    return "\n".join(tables)

# Manual prompt construction
schema_text = get_schema_text(db_connection)
prompt = f"Schema:\n{schema_text}\n\nQuestion: {question}"
```

**After (nlp2sql):**
```python
# Automatic schema management with optimization
service = await create_and_initialize_service(
    database_url="postgresql://localhost/db",
    schema_filters={
        "exclude_system_tables": True,
        "min_row_count": 100  # Focus on tables with data
    }
)

# Intelligent schema selection per query
result = await service.generate_sql(question)
# Only relevant tables are included in the prompt automatically
```

### Schema Optimization Benefits

- **Automatic relevance filtering** (only relevant tables included)
- **Vector embeddings** (semantic table selection)
- **Token optimization** (fits more tables in context)
- **Performance improvement** (faster query generation)
- **Zero maintenance** (no manual schema updates)

## 🏢 From Basic to Enterprise Features

### Basic Implementation

**Before (Basic):**
```python
def simple_nl2sql(question: str) -> str:
    # Basic implementation
    response = call_ai_api(question)
    return response.text

# No error handling, caching, or optimization
sql = simple_nl2sql("Show sales data")
```

**After (Enterprise nlp2sql):**
```python
# Enterprise-ready implementation
async def enterprise_nl2sql(question: str):
    try:
        result = await generate_sql_from_db(
            database_url=database_url,
            question=question,
            ai_provider="openai",
            schema_filters=enterprise_filters
        )
        
        # Built-in features
        if result['confidence'] < 0.7:
            # Automatic fallback to more powerful model
            result = await generate_sql_from_db(
                database_url=database_url,
                question=question,
                ai_provider="anthropic",  # Better for complex queries
                schema_filters=enterprise_filters
            )
        
        # Automatic validation
        if not result['validation']['is_valid']:
            raise ValueError(f"Invalid SQL: {result['validation']['issues']}")
        
        # Audit logging
        log_query(question, result)
        
        return result
        
    except Exception as e:
        # Enterprise error handling
        alert_on_call_team(e)
        return fallback_response(question)
```

## 📈 Performance Migration

### Before: Synchronous, No Caching

```python
# Slow, synchronous implementation
def process_questions(questions: List[str]) -> List[str]:
    results = []
    for question in questions:
        # No caching, each call goes to AI provider
        sql = generate_sql_sync(question)
        results.append(sql)
    return results

# Sequential processing
start_time = time.time()
results = process_questions(questions)  # Takes 30+ seconds
print(f"Processed {len(questions)} in {time.time() - start_time}s")
```

### After: Async, Cached, Optimized

```python
# Fast, async implementation with caching
async def process_questions_optimized(questions: List[str]) -> List[Dict]:
    # Concurrent processing
    tasks = [
        generate_sql_from_db(
            database_url=db_url,
            question=question,
            ai_provider="openai"
        )
        for question in questions
    ]
    
    # All queries processed concurrently with automatic caching
    results = await asyncio.gather(*tasks)
    return results

# Concurrent processing with caching
start_time = time.time()
results = await process_questions_optimized(questions)  # Takes 3-5 seconds
print(f"Processed {len(questions)} in {time.time() - start_time}s")
```

## 🔧 Step-by-Step Migration Process

### Phase 1: Drop-in Replacement (1-2 days)

1. **Install nlp2sql**
   ```bash
   pip install nlp2sql
   ```

2. **Replace basic calls**
   ```python
   # Replace this
   sql = old_framework.generate(question, schema)
   
   # With this
   result = await generate_sql_from_db(db_url, question)
   sql = result['sql']
   ```

3. **Test compatibility**
   ```python
   # Run existing test suite
   assert old_sql == new_result['sql']  # Should match or improve
   ```

### Phase 2: Add Enterprise Features (1 week)

1. **Add schema filtering**
   ```python
   filters = {"exclude_system_tables": True}
   service = await create_and_initialize_service(db_url, schema_filters=filters)
   ```

2. **Add multi-provider support**
   ```python
   # Test different providers
   providers = ["openai", "anthropic", "gemini"]
   results = await benchmark_providers(db_url, test_questions, providers)
   ```

3. **Add monitoring**
   ```python
   # Built-in performance tracking
   metrics = await service.get_performance_metrics()
   ```

### Phase 3: Optimization (2-4 weeks)

1. **Optimize for your schema**
   ```python
   # Fine-tune filters for your database
   custom_filters = analyze_schema_usage(db_url)
   ```

2. **Provider optimization**
   ```python
   # Choose optimal provider per query type
   optimal_providers = await optimize_provider_selection(historical_queries)
   ```

3. **Caching optimization**
   ```python
   # Configure caching for your patterns
   await service.configure_cache(ttl=3600, max_size=10000)
   ```

## ⚠️ Common Migration Issues

### Issue 1: Schema Format Differences

**Problem**: Old framework expects specific schema format
**Solution**: nlp2sql auto-detects schema format

```python
# No manual schema formatting needed
service = await create_and_initialize_service(database_url)  # Auto-detects
```

### Issue 2: Different Response Format

**Problem**: Old framework returns just SQL string
**Solution**: Extract SQL from nlp2sql response

```python
# Compatibility wrapper
def get_sql_only(question: str) -> str:
    result = await generate_sql_from_db(db_url, question)
    return result['sql']  # Extract just the SQL
```

### Issue 3: Synchronous to Async

**Problem**: Existing code is synchronous
**Solution**: Use sync wrapper

```python
import asyncio

def generate_sql_sync(question: str) -> str:
    return asyncio.run(generate_sql_from_db(db_url, question))['sql']
```

## 📞 Migration Support

Need help with your migration? We provide:

- **Migration assessment** (free evaluation of your current setup)
- **Custom migration scripts** (automated conversion tools)
- **Performance optimization** (enterprise tuning)
- **Training and documentation** (team onboarding)

Contact: devhighlevel@gmail.com

## ✅ Migration Checklist

- [ ] Install nlp2sql
- [ ] Test basic functionality with existing queries
- [ ] Compare performance with current solution
- [ ] Implement schema filtering for your database
- [ ] Test multi-provider support
- [ ] Add monitoring and logging
- [ ] Optimize caching configuration
- [ ] Train team on new features
- [ ] Plan gradual rollout
- [ ] Monitor production performance

Migration to nlp2sql typically results in:
- **50-90% code reduction** for common use cases
- **2-5x performance improvement** with caching
- **Better reliability** with multi-provider fallbacks
- **Enterprise features** without additional development