# Amazon Redshift Support

nlp2sql provides comprehensive support for Amazon Redshift data warehouses, enabling natural language to SQL generation for enterprise analytics workloads. The implementation leverages Redshift's PostgreSQL compatibility while optimizing for data warehouse-specific features.

## Features

- **Native Redshift Support**: Direct connection using `redshift://` URLs
- **PostgreSQL Compatibility**: Also accepts `postgresql://` connection strings
- **Data Warehouse Optimizations**: Uses `svv_table_info` for accurate metadata
- **Schema Filtering**: Advanced filtering for large enterprise schemas
- **LocalStack Testing**: Complete testing infrastructure with Docker Compose

## Getting Started

### Python API

```python
import asyncio
import os
from nlp2sql import create_and_initialize_service, DatabaseType

async def main():
    # Connect to Amazon Redshift data warehouse
    service = await create_and_initialize_service(
        database_url="redshift://user:password@cluster.region.redshift.amazonaws.com:5439/analytics",
        ai_provider="anthropic",  # Claude excels with large data warehouse schemas
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        database_type=DatabaseType.REDSHIFT,
        schema_filters={
            "include_schemas": ["sales", "marketing", "finance"],
            "exclude_system_tables": True,
            "exclude_tables": ["temp_", "stg_", "test_"]  # Exclude staging/temp tables
        }
    )
    
    # Generate SQL optimized for Redshift analytics
    result = await service.generate_sql(
        question="What are the top 10 customer segments by revenue in Q4?",
        database_type=DatabaseType.REDSHIFT
    )
    
    print(f"Redshift SQL: {result['sql']}")
    print(f"Confidence: {result['confidence']}")

asyncio.run(main())
```

### CLI Usage

```bash
# Basic Redshift query
nlp2sql query \
  --database-url redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/analytics \
  --question "What are our best performing product categories?" \
  --provider anthropic

# Query with schema filtering
nlp2sql query \
  --database-url redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/analytics \
  --question "Show quarterly sales trends" \
  --schema-filters '{"include_schemas": ["sales", "analytics"]}'

# Inspect Redshift schema
nlp2sql inspect \
  --database-url redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/analytics \
  --schema sales \
  --format table
```

## Connection String Formats

**Standard Redshift Cluster:**
```bash
redshift://username:password@cluster-id.region.redshift.amazonaws.com:5439/database
```

**Redshift Serverless:**
```bash
redshift://username:password@workgroup.account.region.redshift-serverless.amazonaws.com:5439/database
```

**PostgreSQL-Compatible (also supported):**
```bash
postgresql://username:password@cluster-id.region.redshift.amazonaws.com:5439/database
```

## LocalStack Testing Infrastructure

For development and testing, nlp2sql includes a complete LocalStack setup that emulates Redshift behavior without requiring AWS resources.

### Quick Start

```bash
# Start LocalStack Redshift
cd docker && docker-compose up -d localstack

# Run test script
./test-redshift.sh

# Query test data
uv run nlp2sql query \
  --database-url redshift://testuser:testpass123@localhost:5439/testdb \
  --question "Show me all active users"
```

### LocalStack Examples

```bash
# Basic Redshift query
uv run nlp2sql query \
  --database-url redshift://testuser:testpass123@localhost:5439/testdb \
  --question "Show me all active users from the users table"

# Query with PostgreSQL-compatible URL
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass123@localhost:5439/testdb \
  --question "What are the top customers by transaction volume?" \
  --explain

# Query specific schema in Redshift
uv run nlp2sql query \
  --database-url redshift://testuser:testpass123@localhost:5439/testdb \
  --question "Show sales transactions by region" \
  --schema-filters '{"include_schemas": ["sales"]}'

# Inspect Redshift schema
uv run nlp2sql inspect \
  --database-url redshift://testuser:testpass123@localhost:5439/testdb \
  --schema sales \
  --format table

# Test multi-schema Redshift queries
uv run nlp2sql query \
  --database-url redshift://testuser:testpass123@localhost:5439/testdb \
  --question "Compare sales performance with analytics summary data" \
  --schema-filters '{"include_schemas": ["sales", "analytics"]}'
```

## Test Database Schema

The LocalStack Redshift instance includes a multi-schema test database:

```
testdb/
├── public/
│   ├── users (customer accounts)
│   ├── products (product catalog)
│   └── orders (customer orders)
├── sales/
│   ├── customers (customer master data)
│   └── transactions (sales transactions)
└── analytics/
    └── sales_summary (aggregated metrics)
```

## Example Test Questions

- "Show me all active users in the system"
- "What are the top customers by transaction volume?"
- "Calculate total revenue by sales rep"
- "Show sales trends from the analytics summary"
- "Which customers have the highest annual revenue?"
- "Compare transaction amounts by product category"

## Technical Implementation

### Redshift-Specific Optimizations

- **System Views**: Uses `svv_table_info` instead of PostgreSQL's `pg_stat_user_tables`
- **Index Handling**: Simplified approach for Redshift's distribution and sort keys
- **Connection Normalization**: Handles both native and PostgreSQL-compatible URLs
- **Schema Filtering**: Optimized for data warehouse schemas with proper system table filtering

### Database Type Detection

The CLI automatically detects Redshift from connection URLs:
- `redshift://` URLs automatically use `DatabaseType.REDSHIFT`
- `postgresql://` URLs with Redshift hostnames are also supported
- Manual override available with `--database-type` parameter

## Troubleshooting

### Common Issues

1. **Connection Timeout**: Ensure your Redshift cluster allows connections from your IP
2. **SSL Errors**: Redshift requires SSL by default, ensure your connection string includes appropriate SSL parameters
3. **Schema Access**: Verify your user has read permissions on the schemas you want to query
4. **LocalStack Issues**: Ensure Docker is running and LocalStack container is healthy

### Performance Tips

1. **Schema Filtering**: Use `include_schemas` to limit scope for faster metadata loading
2. **Table Exclusion**: Exclude temporary and staging tables with `exclude_tables`
3. **AI Provider**: Claude (Anthropic) often performs better with large data warehouse schemas
4. **Connection Pooling**: For production use, consider connection pooling for better performance

## Security Considerations

- Store credentials in environment variables, not in code
- Use IAM roles when possible for AWS connections
- Implement proper network security for Redshift access
- Consider using Redshift's query logging for audit trails

## Next Steps

- See [API Reference](API.md) for Python API and CLI documentation
- Check [Configuration](CONFIGURATION.md) for environment variables and schema filters
- Review [examples/](../examples/) for more code samples