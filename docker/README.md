# Docker Setup for nlp2sql Testing

This directory contains Docker configurations for testing nlp2sql with PostgreSQL databases.

## Available Databases

### 1. Simple Test Database (Port 5432)
- **Connection**: `postgresql://testuser:testpass@localhost:5432/testdb`
- **Schema**: Simple e-commerce with users, products, orders
- **Tables**: 6 main tables with sample data
- **Use case**: Basic testing and development

### 2. Large Enterprise Database (Port 5433)
- **Connection**: `postgresql://demo:demo123@localhost:5433/enterprise`
- **Schema**: Multi-schema enterprise setup
- **Tables**: 20+ tables across 5 schemas (sales, hr, finance, inventory, analytics)
- **Use case**: Testing large schema handling and filtering

### 3. LocalStack Redshift (Port 5439)
- **Connection**: `redshift://testuser:testpass123@localhost:5439/testdb`
- **Alt Connection**: `postgresql://testuser:testpass123@localhost:5439/testdb`
- **Schema**: Multi-schema setup with sales and analytics schemas
- **Tables**: Test tables optimized for data warehouse patterns
- **Use case**: Testing Redshift-specific functionality and compatibility

## Quick Start

### Default Setup (No Configuration Needed)
```bash
cd docker
docker-compose up -d
```

### Custom Configuration
```bash
# Copy and customize environment file
cp .env.example .env
# Edit .env with your preferred settings
nano .env

# Start with custom configuration
docker-compose up -d
```

### Start Specific Database
```bash
# Only simple database
docker-compose up -d postgres

# Only large database
docker-compose up -d postgres-large

# Only LocalStack Redshift
docker-compose up -d localstack

# PostgreSQL databases only (skip Redshift)
docker-compose up -d postgres postgres-large
```

### Stop Databases
```bash
docker-compose down
```

### Reset Data (Remove Volumes)
```bash
docker-compose down -v
```

## Customization Options

All settings have sensible defaults and can be customized via environment variables:

### Available Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_VERSION` | `16` | PostgreSQL version to use |
| `SIMPLE_DB_USER` | `testuser` | Simple database username |
| `SIMPLE_DB_PASSWORD` | `testpass` | Simple database password |
| `SIMPLE_DB_NAME` | `testdb` | Simple database name |
| `SIMPLE_DB_PORT` | `5432` | Simple database port |
| `LARGE_DB_USER` | `demo` | Large database username |
| `LARGE_DB_PASSWORD` | `demo123` | Large database password |
| `LARGE_DB_NAME` | `enterprise` | Large database name |
| `LARGE_DB_PORT` | `5433` | Large database port |
| `LOCALSTACK_CONTAINER_NAME` | `nlp2sql-localstack` | LocalStack container name |
| `REDSHIFT_PORT` | `5439` | LocalStack Redshift port |

### Quick Customization Examples

**Different Ports (avoid conflicts):**
```bash
export SIMPLE_DB_PORT=15432
export LARGE_DB_PORT=15433
docker-compose up -d
```

**Production-like Credentials:**
```bash
export SIMPLE_DB_USER=postgres
export SIMPLE_DB_PASSWORD=secretpassword
export SIMPLE_DB_NAME=myapp_dev
docker-compose up -d
```

**Different PostgreSQL Version:**
```bash
export POSTGRES_VERSION=15
docker-compose up -d
```

## Test with nlp2sql CLI

### Simple Database Examples
```bash
# Basic query
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Show me all active users"

# With explanation
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "What are the top 5 products by sales?" \
  --explain

# Inspect schema
uv run nlp2sql inspect \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --format table
```

### Large Database Examples
```bash
# Query with schema filters
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Show me sales performance by rep" \
  --schema-filters '{"include_schemas": ["sales"], "exclude_system_tables": true}'

# Inspect large schema with filters
uv run nlp2sql inspect \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --schema sales \
  --exclude-system \
  --max-tables 20 \
  --format json

# Benchmark with large schema
uv run nlp2sql benchmark \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --schema-filters '{"include_schemas": ["sales", "hr", "finance", "inventory", "analytics"]}'

# Save benchmark results to a JSON file
uv run nlp2sql benchmark \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --schema-filters '{"include_schemas": ["sales", "hr", "finance", "inventory", "analytics"]}' \
  --output-file benchmarks/enterprise_benchmark_results.json
```

### LocalStack Redshift Examples

For comprehensive Redshift testing examples and setup, see the [Redshift documentation](../docs/Redshift.md).

## Database Schemas

### Simple Database (testdb)
```
testdb/
├── users (customers)
├── categories (product categories)
├── products (product catalog)
├── orders (customer orders)
├── order_items (order line items)
└── reviews (product reviews)
```

### Large Database (enterprise)
```
enterprise/
├── sales/
│   ├── customers
│   ├── sales_reps
│   ├── opportunities
│   ├── quotes
│   └── contracts
├── hr/
│   ├── departments
│   ├── employees
│   ├── performance_reviews
│   └── time_tracking
├── finance/
│   ├── accounts
│   ├── transactions
│   ├── invoices
│   └── payments
├── inventory/
│   ├── warehouses
│   ├── product_categories
│   ├── products
│   ├── stock_levels
│   └── stock_movements
└── analytics/
    ├── sales_metrics
    ├── customer_segments
    └── product_performance
```



## Example Questions to Test

### Simple Database
- "How many active users do we have?"
- "What are the top 5 best-selling products?"
- "Show me orders from the last month"
- "Which products have the highest ratings?"
- "Calculate total revenue by category"

### Large Database
- "Show me sales performance by territory"
- "Which employees need performance reviews?"
- "What's our current inventory turnover?"
- "Find customers with overdue invoices"
- "Show me department budgets vs actual spending"



## Database Connection Details

### Default Configuration
| Database | Host | Port | User | Password | Database | Connection URL |
|----------|------|------|------|----------|----------|----------------|
| Simple | localhost | 5432 | testuser | testpass | testdb | `postgresql://testuser:testpass@localhost:5432/testdb` |
| Large | localhost | 5433 | demo | demo123 | enterprise | `postgresql://demo:demo123@localhost:5433/enterprise` |
| Redshift | localhost | 5439 | testuser | testpass123 | testdb | `redshift://testuser:testpass123@localhost:5439/testdb` |

### With Custom Configuration
If you customize environment variables, update your connection URLs accordingly:
```bash
# Example with custom ports
postgresql://${SIMPLE_DB_USER}:${SIMPLE_DB_PASSWORD}@localhost:${SIMPLE_DB_PORT}/${SIMPLE_DB_NAME}
postgresql://${LARGE_DB_USER}:${LARGE_DB_PASSWORD}@localhost:${LARGE_DB_PORT}/${LARGE_DB_NAME}
```

### Helper Script
Use the helper script to get current connection URLs based on your configuration:
```bash
./get-db-urls.sh
```

This will show you the exact URLs to use with your current environment variables.

## Notes

- Both databases use PostgreSQL 16
- Data is persisted in Docker volumes
- Schemas are automatically created on first startup
- Sample data is included for immediate testing
- All tables have proper indexes and foreign keys
- Table comments are added for better AI understanding
