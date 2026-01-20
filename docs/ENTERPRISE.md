# Enterprise Guide

This document covers enterprise-specific features for large-scale production deployments and migration from other frameworks.

## Large Schema Management

### The Challenge: 1000+ Table Databases

Enterprise databases often contain hundreds or thousands of tables. Traditional NLP-to-SQL approaches fail at this scale due to:

- **Token limitations**: Cannot fit entire schema in AI context
- **Performance issues**: Slow schema processing and query generation
- **Relevance problems**: AI gets confused by irrelevant tables
- **Memory consumption**: Large schemas consume excessive memory

### Solution: Intelligent Schema Filtering

nlp2sql uses multi-level filtering to handle large schemas efficiently.

```python
schema_filters = {
    # Schema-level filtering
    "include_schemas": ["sales", "finance", "hr"],
    "exclude_schemas": ["archive", "temp"],

    # Table-level filtering
    "include_tables": ["customers", "orders", "products"],
    "exclude_tables": ["audit_logs", "migration_history"],
    "exclude_system_tables": True
}

service = await create_and_initialize_service(
    database_url="postgresql://enterprise-db/production",
    ai_provider="anthropic",  # Best for large schemas (200K context)
    api_key=api_key,
    schema_filters=schema_filters
)
```

### Vector Embeddings for Schema Relevance

nlp2sql uses vector embeddings to automatically find the most relevant tables for each query:

```python
# AI automatically identifies relevant tables
question = "Show me sales performance by region"
# Includes: sales_orders, territories, sales_reps
# Excludes: hr_employees, finance_accounts, inventory_items
```

### Performance by Database Size

| Database Size | Tables | nlp2sql | Traditional Approach |
|---------------|--------|---------|---------------------|
| Small | 10-50 | < 1s | < 1s |
| Medium | 100-500 | 1-3s | 5-15s |
| Large | 1000+ | 3-8s | Timeout/Fail |
| Enterprise | 5000+ | 5-15s | Not feasible |

---

## Multi-Provider Architecture

### Avoiding Vendor Lock-in

Most frameworks lock you into a single AI provider, creating risks:
- **Cost risk**: Price changes affect entire system
- **Performance risk**: No alternatives if service degrades
- **Availability risk**: Outages affect entire system

### Multi-Provider Strategy

```python
async def robust_query_generation(question: str):
    providers = ["openai", "anthropic", "gemini"]

    for provider in providers:
        try:
            result = await generate_sql_from_db(
                database_url=db_url,
                question=question,
                ai_provider=provider,
                api_key=get_api_key(provider)
            )
            return result
        except Exception as e:
            logger.warning(f"Provider {provider} failed: {e}")
            continue

    raise Exception("All providers failed")
```

### Provider Selection by Use Case

```python
def select_optimal_provider(question: str, schema_size: int):
    if schema_size > 1000:
        return "anthropic"  # 200K context window
    elif "complex" in question.lower():
        return "openai"     # Best reasoning
    else:
        return "gemini"     # Most cost-effective
```

### Cost Comparison

Use the built-in benchmarking to compare providers:

```bash
nlp2sql benchmark \
  --database-url postgresql://localhost/db \
  --providers openai,anthropic,gemini \
  --questions test_queries.txt
```

---

## Performance Optimization

### Caching Layers

nlp2sql implements multiple caching layers:

1. **Schema embedding cache**: Vector representations of table schemas, persistent across restarts
2. **Query result cache**: Stores generated SQL for similar questions (reduces AI calls by 60-80%)
3. **Provider response cache**: Handles rate limiting automatically

### Async Architecture

```python
# Concurrent query processing
async def process_batch(questions: list[str]):
    tasks = [service.generate_sql(q) for q in questions]
    return await asyncio.gather(*tasks)
```

### Memory Optimization

- **Lazy loading**: Load schema elements only when needed
- **Streaming processing**: Handle large schemas without memory spikes
- **Connection pooling**: Efficient database connection management

---

## Security and Compliance

### Data Privacy

```python
# Exclude sensitive tables from schema
sensitive_filters = {
    "exclude_tables": [
        "user_passwords", "payment_tokens", "personal_data"
    ]
}
```

### SQL Injection Prevention

```python
result = await generate_sql(question)
if not result['validation']['is_safe']:
    raise SecurityError("Generated SQL contains unsafe patterns")
```

### Audit Logging

```python
audit_log = {
    "timestamp": datetime.utcnow(),
    "user": current_user.id,
    "question": question,
    "generated_sql": result['sql'],
    "provider": result['provider'],
    "confidence": result['confidence']
}
```

---

## Deployment Patterns

### Microservice Architecture

```python
from fastapi import FastAPI
from nlp2sql import create_and_initialize_service

app = FastAPI()
service = None

@app.on_event("startup")
async def startup():
    global service
    service = await create_and_initialize_service(
        database_url=os.getenv("DATABASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY")
    )

@app.post("/query")
async def generate_query(question: str):
    return await service.generate_sql(question)
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nlp2sql-service
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: nlp2sql
        image: nlp2sql:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: ai-credentials
              key: openai
```

### AWS Lambda

```python
import json
from nlp2sql import generate_sql_from_db

def lambda_handler(event, context):
    question = event['question']
    result = await generate_sql_from_db(
        database_url=os.environ['DATABASE_URL'],
        question=question,
        api_key=os.environ['OPENAI_API_KEY']
    )
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }
```

---

## Migration Guide

### From Custom OpenAI Implementations

**Before:**
```python
import openai

class CustomNL2SQL:
    def __init__(self, api_key: str, database_schema: dict):
        self.client = openai.OpenAI(api_key=api_key)
        self.schema = database_schema

    def generate_sql(self, question: str) -> str:
        prompt = self._build_prompt(question)
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
```

**After:**
```python
from nlp2sql import create_and_initialize_service

# Automatic schema loading and optimization
service = await create_and_initialize_service(
    database_url="postgresql://localhost/db",
    api_key="your-openai-key"
)

result = await service.generate_sql("Show active users")
sql = result['sql']
confidence = result['confidence']
is_valid = result['validation']['is_valid']
```

### From Research Frameworks

**Before:**
```python
from research_nl2sql import TaskChain, SchemaAnalyzer, QueryGenerator

chain = TaskChain()
chain.add_task(SchemaAnalyzer(embeddings_model="sentence-transformers"))
chain.add_task(QueryGenerator(model="gpt-4"))
result = chain.execute(question, schema)
sql = result.tasks[-1].output.sql
```

**After:**
```python
from nlp2sql import generate_sql_from_db

result = await generate_sql_from_db(
    database_url="postgresql://localhost/db",
    question=question,
    ai_provider="openai",
    api_key="your-api-key"
)
sql = result['sql']
```

### Migration Benefits

- **90% less code** for common use cases
- **Built-in optimizations**: caching, async, schema filtering
- **Multi-provider support**: no vendor lock-in
- **Production-ready**: error handling, monitoring

### Step-by-Step Migration

**Phase 1: Drop-in Replacement (1-2 days)**

```bash
pip install nlp2sql
```

```python
# Replace basic calls
# Old: sql = old_framework.generate(question, schema)
# New:
result = await generate_sql_from_db(db_url, question, api_key=key)
sql = result['sql']
```

**Phase 2: Add Enterprise Features (1 week)**

```python
# Add schema filtering
filters = {"exclude_system_tables": True}
service = await create_and_initialize_service(db_url, schema_filters=filters)

# Add multi-provider support
benchmark_results = await benchmark_providers(db_url, test_questions)
```

**Phase 3: Optimization (2-4 weeks)**

```python
# Fine-tune filters for your database
custom_filters = {
    "include_schemas": ["sales", "finance"],
    "include_tables": ["customers", "orders", "products"],
    "exclude_system_tables": True
}

# Configure caching
await service.configure_cache(ttl=3600, max_size=10000)
```

### Common Migration Issues

**Issue: Schema format differences**
Solution: nlp2sql auto-detects schema format - no manual formatting needed.

**Issue: Different response format**
Solution: Extract SQL from response dict:
```python
sql = result['sql']  # Extract just the SQL
```

**Issue: Synchronous to async**
Solution: Use sync wrapper:
```python
import asyncio
def generate_sql_sync(question: str) -> str:
    return asyncio.run(generate_sql_from_db(db_url, question))['sql']
```

---

## Migration Checklist

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

**Expected Results:**
- 50-90% code reduction for common use cases
- 2-5x performance improvement with caching
- Better reliability with multi-provider fallbacks

---

For configuration details, see [CONFIGURATION.md](CONFIGURATION.md).
For API reference, see [API.md](API.md).
