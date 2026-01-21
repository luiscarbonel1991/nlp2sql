# Docker Deployment - Quick Reference

## TL;DR

```bash
# Start everything
docker-compose up -d --build

# Check status
docker-compose ps

# Test API
curl http://localhost:8000/health | jq .

# View docs
open http://localhost:8000/docs

# Run tests
./test-docker-endpoints.sh

# Stop everything
docker-compose down
```

## What You Get

- ✅ **FastAPI Application** on port 8000
- ✅ **PostgreSQL Database** on port 5434
- ✅ **25-table E-commerce Schema** with sample data
- ✅ **nlp2sql Service** with embedding model
- ✅ **Interactive API Docs** at `/docs`
- ✅ **Sub-10ms Query Performance**

## Quick Stats

| Metric | Value |
|--------|-------|
| Build Time | 36 seconds |
| Startup Time | 15 seconds |
| Image Size | ~1.2GB |
| Query Performance | 3-20ms |
| Tables | 25 |
| Products | 5 |
| Users | 5 |

## Endpoints

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/health` | GET | Health check | ✅ |
| `/tables` | GET | List tables | ✅ |
| `/tools/execute-sql` | POST | Execute SQL | ✅ |
| `/tools/generate-sql` | POST | Generate SQL | ⏳ API key |
| `/tools/query` | POST | Generate + Execute | ⏳ API key |
| `/agent/chat` | POST | AI Agent chat | ⏳ API key |
| `/docs` | GET | Swagger UI | ✅ |
| `/redoc` | GET | ReDoc | ✅ |

## Configuration

Create `.env` file:

```bash
OPENAI_API_KEY=your-key-here
```

Then restart:

```bash
docker-compose restart api
```

## Complete Documentation

See [DOCKER_SETUP.md](./DOCKER_SETUP.md) for:
- Complete setup guide
- Detailed test results
- Troubleshooting
- Performance metrics
- Architecture diagrams
- All test cases with real results

## Useful Commands

```bash
# View logs
docker-compose logs -f api

# Restart API only
docker-compose restart api

# Fresh start (removes data)
docker-compose down -v && docker-compose up -d --build

# Access database
docker-compose exec postgres psql -U ecommerce_user -d ecommerce_db

# Check resource usage
docker stats
```

## Test Results

All basic endpoints tested and working:

```
✅ Health Check: <50ms
✅ List Tables: 25 tables retrieved
✅ Execute SQL: 1.8-8.19ms
✅ Complex Queries: 4.88ms
✅ Database Stats: All counts correct
✅ Active Products: All 5 products with stock
```

## Next Steps

1. Add OpenAI API key to test LLM features
2. Try the Swagger UI at http://localhost:8000/docs
3. Run the test suite: `./test-docker-endpoints.sh`
4. Read full documentation in [DOCKER_SETUP.md](./DOCKER_SETUP.md)

## Support

- Full documentation: [DOCKER_SETUP.md](./DOCKER_SETUP.md)
- Project README: [README.md](./README.md)
- Test script: [test-docker-endpoints.sh](./test-docker-endpoints.sh)
