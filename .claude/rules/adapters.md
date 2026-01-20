---
globs:
  - "src/nlp2sql/adapters/**/*.py"
---

# Creating New Adapters

## AI Provider Adapter
1. Create `adapters/new_provider_adapter.py`
2. Implement `AIProviderPort` interface
3. Follow patterns from `openai_adapter.py`
4. Update factory in `__init__.py`

## Required Methods
- `async def generate_sql(query, schema, context) -> str`
- Handle rate limits and retries
- Validate response format

## Database Repository Adapter
1. Implement `SchemaRepositoryPort`
2. Follow `postgres_repository.py` patterns
3. Handle connection pooling
4. Support schema filtering
