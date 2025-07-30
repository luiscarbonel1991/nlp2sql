# nlp2sql MCP Server

This MCP (Model Context Protocol) server exposes nlp2sql functionality as tools that can be used by AI assistants like Claude.

## Features

- **Natural Language to SQL**: Convert questions to SQL queries using multiple AI providers
- **Schema Analysis**: Analyze database structure and get detailed statistics  
- **Schema Selection**: Support for specific PostgreSQL schema selection (e.g., public, custom_schema)
- **Query Explanation**: Explain SQL queries in natural language
- **Example Generation**: Generate example queries for your database
- **Multi-Provider Support**: OpenAI, Anthropic, and Google Gemini
- **Secure Database Access**: Use aliases instead of exposing URLs

## Installation

```bash
# Install dependencies
pip install mcp nlp2sql

# Or install nlp2sql from TestPyPI for testing
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple nlp2sql
```

## Configuration

### Claude Desktop Configuration

Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nlp2sql": {
      "command": "python",
      "args": ["/path/to/nlp2sql/mcp_server/server.py"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key",
        "ANTHROPIC_API_KEY": "your-anthropic-key",
        "GOOGLE_API_KEY": "your-gemini-key",
        "NLP2SQL_DEMO_DB_URL": "postgresql://user:pass@localhost:5432/demo_db",
        "NLP2SQL_LOCAL_DB_URL": "postgresql://user:pass@localhost:5432/local_db",
        "NLP2SQL_TEST_DB_URL": "postgresql://user:pass@localhost:5432/test_db"
      }
    }
  }
}
```

## Available Tools

### Main Tools (Using Database Aliases)

#### 1. nlp_to_sql
Convert natural language to SQL using secure database aliases:

```json
{
  "tool": "nlp_to_sql",
  "arguments": {
    "database_alias": "demo",
    "question": "Show me all active users created this month",
    "ai_provider": "openai"
  }
}
```

#### 2. analyze_schema
Analyze database schema with optional schema selection:

```json
{
  "tool": "analyze_schema",
  "arguments": {
    "database_alias": "demo",
    "ai_provider": "openai",
    "schema_name": "custom_schema"
  }
}
```

#### 3. list_database_aliases
List configured database aliases:

```json
{
  "tool": "list_database_aliases",
  "arguments": {}
}
```

### Alternative Tools (Direct Database URLs)

#### 1. nlp_to_sql_with_database_url
Convert natural language to SQL with direct URL:

```json
{
  "tool": "nlp_to_sql_with_database_url",
  "arguments": {
    "database_url": "postgresql://user:pass@localhost/db",
    "question": "Show me all orders from last week",
    "ai_provider": "openai"
  }
}
```

#### 2. analyze_database_schema
Get database schema statistics with direct URL:

```json
{
  "tool": "analyze_database_schema",
  "arguments": {
    "database_url": "postgresql://user:pass@localhost/db",
    "ai_provider": "openai"
  }
}
```

#### 3. explain_sql_query
Explain what a SQL query does:

```json
{
  "tool": "explain_sql_query",
  "arguments": {
    "database_url": "postgresql://user:pass@localhost/db",
    "sql": "SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id",
    "ai_provider": "openai"
  }
}
```

#### 4. generate_example_queries
Generate example queries for your database:

```json
{
  "tool": "generate_example_queries",
  "arguments": {
    "database_url": "postgresql://user:pass@localhost/db",
    "topic": "user analytics",
    "ai_provider": "openai"
  }
}
```

#### 5. benchmark_ai_providers
Benchmark different AI providers performance:

```json
{
  "tool": "benchmark_ai_providers",
  "arguments": {
    "database_alias": "demo",
    "questions": ["Count total users", "Show recent orders"],
    "providers": ["openai", "anthropic"],
    "iterations": 3
  }
}
```

## Database Configuration

### Using Aliases (Recommended)

Configure database aliases in your Claude Desktop config for security:

- `NLP2SQL_DEMO_DB_URL` - Demo database
- `NLP2SQL_LOCAL_DB_URL` - Local development database  
- `NLP2SQL_TEST_DB_URL` - Test database

Benefits:
- **Security**: Credentials not exposed in tool calls
- **Simplicity**: Use simple aliases like "demo" instead of full URLs
- **Flexibility**: Change database URLs without updating queries

### Database URL Examples

```bash
# PostgreSQL
postgresql://username:password@localhost:5432/database

# PostgreSQL with specific schema
postgresql://username:password@localhost:5432/database?options=-csearch_path=myschema

# PostgreSQL with SSL
postgresql://username:password@localhost:5432/database?sslmode=require

# MySQL
mysql://username:password@localhost:3306/database

# SQLite
sqlite:///path/to/database.db
```

## Usage Examples

### Basic Usage

1. **Convert natural language to SQL**:
   ```
   Use nlp_to_sql with database_alias "demo" to show me all orders from last week
   ```

2. **Analyze database schema**:
   ```
   Use analyze_schema on database_alias "demo" with schema_name "custom_schema"
   ```

3. **List available databases**:
   ```
   Use list_database_aliases to show configured databases
   ```

### Real-World Examples

```sql
-- Question: "Show me customers who haven't ordered in the last 30 days"
SELECT DISTINCT c.*
FROM customers c
WHERE NOT EXISTS (
    SELECT 1 FROM orders o 
    WHERE o.customer_id = c.id 
    AND o.created_at > CURRENT_DATE - INTERVAL '30 days'
)

-- Question: "What's our monthly revenue trend for this year?"
SELECT 
    DATE_TRUNC('month', created_at) as month,
    SUM(total_amount) as revenue
FROM orders
WHERE created_at >= DATE_TRUNC('year', CURRENT_DATE)
AND status = 'completed'
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month
```

## Schema Filtering

Control which parts of your database schema are accessible:

```json
{
  "schema_filters": {
    "include_schemas": ["public", "sales"],
    "exclude_tables": ["logs", "sessions", "temp_*"]
  }
}
```

## Troubleshooting

1. **"No API key found"**: Set the appropriate environment variable
2. **"Connection refused"**: Check database URL and network connectivity
3. **"Schema too large"**: Use schema filters to limit scope
4. **"Database alias not configured"**: Add the alias to your Claude Desktop config

## Performance Tips

1. **Use database aliases** for better security and performance
2. **Apply schema filters** to limit the scope to relevant tables
3. **Choose AI providers** based on your needs:
   - OpenAI: Best general performance
   - Anthropic: Better for complex queries  
   - Gemini: Good for analytical queries

## License

MIT License - same as nlp2sql
