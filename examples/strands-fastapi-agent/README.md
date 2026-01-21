# Strands FastAPI Agent - Natural Language Database Queries

A production-ready FastAPI application that combines Strands Agents with nlp2sql to provide natural language database queries. This example demonstrates how to build an intelligent API for e-commerce analytics using AI agents and tool calling.

## Features

- **Strands Agents Integration**: Conversational AI agent with tool calling capabilities for natural language interactions
- **NLP2SQL Conversion**: Automatic conversion of natural language questions to SQL queries with confidence scoring
- **E-commerce Domain**: Pre-configured with a comprehensive e-commerce database schema (25 tables)
- **Docker Support**: Easy local development with Docker Compose for PostgreSQL
- **REST API**: FastAPI with automatic Swagger UI documentation
- **Analytics Ready**: Query products, orders, customers, inventory, and more through natural language

## Quick Start

### Option 1: Docker (Recommended)

Run the complete application with Docker:

```bash
# Start all services (API + Database)
docker-compose up -d --build

# Check status
docker-compose ps

# Test the API
curl http://localhost:8000/health | jq .

# Access Swagger UI
open http://localhost:8000/docs
```

See [DOCKER_SETUP.md](./DOCKER_SETUP.md) for complete Docker documentation with test results.

### Option 2: Local Development

#### 1. Start the Database

```bash
docker-compose up -d postgres
```

This will start a PostgreSQL database on port `5434` with a comprehensive e-commerce schema.

### 2. Configure Environment

Copy `.env.example` to `.env` and update with your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```env
OPENAI_API_KEY=your-openai-key-here
DATABASE_URL=postgresql://ecommerce_user:ecommerce_pass@localhost:5434/ecommerce_db
DATABASE_TYPE=POSTGRES
SCHEMA_NAME=public
```

### 3. Install Dependencies

```bash
uv sync
```

### 4. Run the Server

```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Strands Agent Endpoint (Intelligent Tool Calling)

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What tables are available and how many users are there?"}'
```

The Strands Agent will:
1. Intelligently decide which tools to use
2. Call `list_tables_tool` to see available tables
3. Call `generate_sql_tool` to create SQL
4. Call `execute_sql_tool` to run the query
5. Format results naturally in the response

### Direct nlp2sql Endpoints (No Agent)

#### Generate SQL Only
```bash
curl -X POST http://localhost:8000/tools/generate-sql \
  -H "Content-Type: application/json" \
  -d '{"question": "how many orders were placed last month"}'
```

#### Execute Raw SQL
```bash
curl -X POST http://localhost:8000/tools/execute-sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT COUNT(*) FROM orders"}'
```

#### Generate and Execute in One Step
```bash
curl -X POST http://localhost:8000/tools/query \
  -H "Content-Type: application/json" \
  -d '{"question": "show me the top 5 best selling products"}'
```

#### List Available Tables
```bash
curl http://localhost:8000/tables
```

## Example E-commerce Queries

The API is optimized for e-commerce domain questions like:

- **Products**: "Show me all products in the Electronics category"
- **Orders**: "How many orders were placed this month?"
- **Customers**: "List customers who haven't ordered in the last 6 months"
- **Inventory**: "Which products are running low on stock?"
- **Sales**: "What are the top 10 best selling products?"
- **Revenue**: "Calculate total revenue by month for this year"
- **Reviews**: "Show products with average rating above 4 stars"
- **Cart Analytics**: "What's the average cart abandonment rate?"

## Database Schema

The e-commerce schema includes:

- **Users & Authentication**: Users, addresses, payment methods
- **Product Catalog**: Products, categories, brands, variants, images, reviews, tags
- **Orders**: Orders, order items, status history
- **Shopping Cart**: Carts and cart items
- **Marketing**: Coupons, campaigns, promotions
- **Inventory**: Warehouses, inventory tracking, transactions
- **Analytics**: Page views, search queries

## Development

### Database Management

```bash
# Start database
docker-compose up -d

# Stop database
docker-compose down

# View logs
docker-compose logs -f postgres

# Reset database (removes all data)
docker-compose down -v
docker-compose up -d
```

### Testing

### Quick Test Script

Run the automated test suite to verify all endpoints:

```bash
./test-docker-endpoints.sh
```

This script tests:
- Health check endpoint
- Database tables listing
- SQL execution (counts, queries, aggregations)
- Active products with stock
- Database statistics
- Cart analytics (abandonment, values)
- Reviews & ratings
- Marketing (coupons, campaigns)
- Complex analytics queries

### Manual Testing

Test individual queries:

```bash
# Product queries
curl -X POST http://localhost:8000/chat \
  -d '{"message": "show me all products in the Electronics category"}'

# Order analytics
curl -X POST http://localhost:8000/chat \
  -d '{"message": "what is the total revenue for this month"}'

# Customer insights
curl -X POST http://localhost:8000/chat \
  -d '{"message": "how many active customers do we have"}'

# Inventory management
curl -X POST http://localhost:8000/chat \
  -d '{"message": "which products need to be restocked"}'
```

## Configuration

Key environment variables:

- `OPENAI_API_KEY`: OpenAI API key (or `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`)
- `DATABASE_URL`: PostgreSQL connection string
- `DATABASE_TYPE`: Database type (POSTGRES, REDSHIFT, etc.)
- `SCHEMA_NAME`: Database schema name (default: `public`)

## Architecture

This example demonstrates the integration of three key technologies:

- **FastAPI**: Modern async Python web framework with automatic OpenAPI documentation
- **Strands Agents**: AWS's AI agent framework with tool calling capabilities
- **nlp2sql**: Natural language to SQL conversion library with multiple AI provider support
- **PostgreSQL**: Relational database (via Docker Compose)
- **Python 3.13+**: Runtime environment

## Documentation

- **[README.md](./README.md)** - Main project documentation (this file)
- **[DOCKER_SETUP.md](./DOCKER_SETUP.md)** - Complete Docker setup guide with test results (1500+ lines)
- **[DOCKER_README.md](./DOCKER_README.md)** - Quick Docker reference
- **[test-docker-endpoints.sh](./test-docker-endpoints.sh)** - Automated test suite

## Project Structure

```
strands-fastapi-agent/
├── main.py                         # FastAPI application with Strands Agent
├── pyproject.toml                  # Python dependencies
├── Dockerfile                      # Multi-stage Docker build
├── docker-compose.yml              # Full stack orchestration (API + DB)
├── .dockerignore                   # Docker build optimization
├── docker/
│   └── init-ecommerce-schema.sql   # E-commerce database schema (25 tables)
├── .env.example                    # Environment variables template
├── README.md                       # Main documentation
├── DOCKER_SETUP.md                 # Complete Docker guide with tests
├── DOCKER_README.md                # Docker quick reference
└── test-docker-endpoints.sh        # Automated test suite
```

## Key Concepts Demonstrated

1. **Tool Calling**: Strands Agent uses decorated Python functions as tools
2. **Async Integration**: Proper async/await handling between FastAPI and Strands
3. **Natural Language Processing**: Converting questions to SQL with confidence scoring
4. **REST API Design**: Clean endpoint structure for different use cases
5. **Docker Development**: Local database setup with sample schema

## Technologies Used

- [Strands Agents](https://github.com/strands-agents/sdk-python) - AI agent framework
- [nlp2sql](https://github.com/luiscarbonel/nlp2sql) - Natural language to SQL
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [PostgreSQL](https://www.postgresql.org/) - Database

## License

MIT
