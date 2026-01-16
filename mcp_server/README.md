# nlp2sql MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that enables AI assistants to query databases using natural language.

## Overview

This MCP server provides **5 simple, idiomatic tools** optimized for BI analysts, executives, and developers:

| Tool | Description |
|------|-------------|
| `ask_database` | Ask questions in natural language, get SQL and optional results |
| `explore_schema` | Discover tables and columns in your database |
| `run_sql` | Execute SQL queries directly (read-only) |
| `list_databases` | List available database connections |
| `explain_sql` | Explain what a SQL query does in plain English |

## Features

- **Natural Language Queries**: Convert questions to SQL using AI
- **Direct Execution**: Execute queries and get results (read-only, secure)
- **Schema Discovery**: Explore database structure interactively
- **Multi-Provider Support**: OpenAI, Anthropic, Google Gemini
- **Performance Optimized**: Service caching for fast subsequent calls (~5s vs ~50s)
- **Security First**: SQL injection protection, read-only enforcement

## Installation

```bash
# Install from PyPI
pip install nlp2sql mcp

# Or with uv
uv add nlp2sql mcp
```

## Configuration

### Claude Desktop / Claude Code

Add to your configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Claude Code**: `.mcp.json` in your project root

```json
{
  "mcpServers": {
    "nlp2sql": {
      "command": "python",
      "args": ["/path/to/nlp2sql/mcp_server/server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        "GOOGLE_API_KEY": "${GOOGLE_API_KEY}",
        "NLP2SQL_DEFAULT_DB_URL": "postgresql://user:pass@localhost:5432/mydb",
        "NLP2SQL_DEMO_DB_URL": "postgresql://user:pass@localhost:5432/demo",
        "NLP2SQL_PROD_DB_URL": "postgresql://user:pass@prod-server:5432/production",
        "NLP2SQL_EMBEDDINGS_DIR": "/path/to/nlp2sql/embeddings"
      }
    }
  }
}
```

**Note:** `NLP2SQL_EMBEDDINGS_DIR` is required for Claude Desktop to avoid read-only filesystem errors. Set it to a writable directory where embedding indexes will be stored.

### Database Aliases

Configure databases using environment variables for security:

| Alias | Environment Variable | Use Case |
|-------|---------------------|----------|
| `default` | `NLP2SQL_DEFAULT_DB_URL` | Primary database |
| `demo` | `NLP2SQL_DEMO_DB_URL` | Demo/sandbox database |
| `local` | `NLP2SQL_LOCAL_DB_URL` | Local development |
| `test` | `NLP2SQL_TEST_DB_URL` | Test database |
| `prod` / `production` | `NLP2SQL_PROD_DB_URL` | Production database |

## Tools Reference

### 1. `ask_database` - Main Tool

Ask questions in natural language and get SQL queries with optional execution.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `question` | string | required | Your question in plain English |
| `database` | string | `"default"` | Database alias or connection URL |
| `schema` | string | `"public"` | Database schema to query (for non-public schemas) |
| `execute` | boolean | `false` | Execute the SQL and return results |
| `limit` | integer | `100` | Max rows to return (max: 1000) |

**Examples:**

```
# Generate SQL only
ask_database("How many customers do we have?")

# Generate and execute
ask_database("Show top 10 products by revenue", execute=True)

# Use specific schema (non-public)
ask_database("How many chats are there?", schema="alpha_ui", execute=True)

# Use specific database and schema
ask_database("Count active users", database="prod", schema="sales", execute=True)

# With row limit
ask_database("List all orders", execute=True, limit=500)
```

**Response (execute=false):**
```json
{
  "sql": "SELECT COUNT(*) FROM customers",
  "explanation": "Counts total customers in the database",
  "confidence": 0.95
}
```

**Response (execute=true):**
```json
{
  "sql": "SELECT COUNT(*) FROM customers",
  "explanation": "Counts total customers in the database",
  "confidence": 0.95,
  "results": [{"count": 15234}],
  "row_count": 1,
  "execution_time_ms": 45.2
}
```

### 2. `explore_schema` - Schema Discovery

Explore database structure to understand available tables and columns.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `database` | string | `"default"` | Database alias or connection URL |
| `schema` | string | `"public"` | Database schema to explore |
| `table` | string | `null` | Get detailed info for specific table |
| `search` | string | `null` | Search tables by name pattern |

**Examples:**

```
# List all tables in public schema
explore_schema()

# List tables in a specific schema
explore_schema(schema="alpha_ui")

# Get specific table details
explore_schema(table="orders")

# Search for tables in a specific schema
explore_schema(schema="sales", search="customer")

# On specific database
explore_schema(database="prod", schema="analytics", search="user")
```

**Response (list tables):**
```json
{
  "database": "default",
  "total_tables": 25,
  "tables": [
    {"name": "customers", "columns": 12, "description": "Customer records"},
    {"name": "orders", "columns": 8, "description": "Order transactions"},
    {"name": "products", "columns": 15, "description": "Product catalog"}
  ]
}
```

**Response (table details):**
```json
{
  "table": "orders",
  "schema": "public",
  "description": "Order transactions",
  "columns": [
    {"name": "id", "type": "integer", "nullable": false, "description": "Primary key"},
    {"name": "customer_id", "type": "integer", "nullable": false, "description": "FK to customers"},
    {"name": "total_amount", "type": "numeric(10,2)", "nullable": false, "description": "Order total"},
    {"name": "created_at", "type": "timestamp", "nullable": false, "description": "Creation date"}
  ],
  "primary_keys": ["id"],
  "foreign_keys": [
    {"column": "customer_id", "references": "customers.id"}
  ],
  "row_count": 50000
}
```

### 3. `run_sql` - Execute SQL Directly

Execute SQL queries directly with security protections.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `sql` | string | required | SQL query to execute (SELECT only) |
| `database` | string | `"default"` | Database alias or connection URL |
| `schema` | string | `"public"` | Database schema context |
| `limit` | integer | `100` | Max rows to return (max: 1000) |

**Examples:**

```
# Simple query
run_sql("SELECT * FROM users WHERE active = true LIMIT 10")

# Query on specific schema
run_sql("SELECT COUNT(*) FROM alpha_ui.chat", schema="alpha_ui")

# Aggregate query
run_sql("SELECT status, COUNT(*) FROM orders GROUP BY status")

# On specific database
run_sql("SELECT name, email FROM customers", database="prod")
```

**Response:**
```json
{
  "results": [
    {"status": "completed", "count": 4521},
    {"status": "pending", "count": 234},
    {"status": "cancelled", "count": 89}
  ],
  "columns": ["status", "count"],
  "row_count": 3,
  "execution_time_ms": 32.1
}
```

**Security:**
- Only `SELECT`, `WITH`, and `EXPLAIN` queries allowed
- `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc. are blocked
- Multiple statements (SQL injection) are blocked
- Row limit enforced (max 1000)
- Query timeout: 30 seconds

### 4. `list_databases` - Show Connections

List all configured database connections.

**Parameters:** None

**Example:**

```
list_databases()
```

**Response:**
```json
{
  "databases": [
    {"alias": "default", "status": "configured", "type": "postgres", "env_var": "NLP2SQL_DEFAULT_DB_URL"},
    {"alias": "demo", "status": "configured", "type": "postgres", "env_var": "NLP2SQL_DEMO_DB_URL"},
    {"alias": "prod", "status": "not_configured", "type": null, "env_var": "NLP2SQL_PROD_DB_URL"}
  ],
  "default": "default",
  "hint": "Use database alias in other tools, e.g., ask_database(..., database='demo')"
}
```

### 5. `explain_sql` - Query Explanation

Get a plain English explanation of what a SQL query does.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `sql` | string | required | SQL query to explain |
| `database` | string | `"default"` | Database context for accurate explanations |

**Example:**

```
explain_sql("SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.name HAVING COUNT(o.id) > 5")
```

**Response:**
```json
{
  "explanation": "This query retrieves user names and their order counts, showing only users with more than 5 orders. It uses a LEFT JOIN to include all users, even those without orders.",
  "tables_used": ["users", "orders"],
  "complexity": "moderate"
}
```

## Usage Workflows

### For BI Analysts

```
1. list_databases()                              # See available databases
2. explore_schema(database="prod")               # Understand the data
3. explore_schema(table="sales")                 # Dive into specific tables
4. ask_database("Monthly revenue trend", execute=True)  # Get insights
```

### For Executives

```
# Single question, immediate answer
ask_database("What's our top selling product this quarter?", execute=True)
ask_database("How many new customers last month?", execute=True)
```

### For Developers

```
1. explore_schema(table="users")                 # Check table structure
2. ask_database("Find users inactive for 30 days")  # Get SQL suggestion
3. run_sql("SELECT ... WITH custom modifications")  # Execute refined query
```

## Performance

The MCP server uses intelligent caching for optimal performance:

| Call | Time | Notes |
|------|------|-------|
| First call | ~50s | Initializes AI service, loads schema, builds embeddings |
| Subsequent calls | ~5s | Uses cached service and schema |

**Why caching matters:**
- Schema embedding index is expensive to build
- AI provider initialization takes time
- Database metadata queries are cached

**Cache invalidation:**
- Restart the MCP server to clear cache
- Each database+provider combination has its own cache

## Security

### SQL Injection Protection

All SQL execution goes through security validation:

```python
# Allowed
"SELECT * FROM users"
"WITH active AS (SELECT ...) SELECT * FROM active"
"EXPLAIN SELECT * FROM orders"

# Blocked
"DELETE FROM users"
"SELECT * FROM users; DROP TABLE users"
"UPDATE users SET admin = true"
"INSERT INTO logs VALUES (...)"
```

### Blocked Operations

- `INSERT`, `UPDATE`, `DELETE`
- `DROP`, `TRUNCATE`, `ALTER`
- `CREATE`, `GRANT`, `REVOKE`
- `COPY`, `EXEC`, `CALL`
- Multiple statements (`;` injection)

### Row Limits

- Default: 100 rows
- Maximum: 1000 rows
- Enforced server-side

## Troubleshooting

### "No AI provider configured"

Set at least one API key:
```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export GOOGLE_API_KEY="..."
```

### "Database alias not configured"

Add the database URL to your config:
```json
{
  "env": {
    "NLP2SQL_DEFAULT_DB_URL": "postgresql://..."
  }
}
```

### "Query rejected: Only SELECT queries allowed"

The `run_sql` tool only allows read-only queries for security. Use your database client directly for write operations.

### Slow first call

The first call takes ~50s to initialize. Subsequent calls are ~5s. This is expected behavior due to:
- Loading database schema
- Building embedding index
- Initializing AI provider

## Supported Databases

- **PostgreSQL** - Full support
- **Amazon Redshift** - Full support
- MySQL, SQLite, Oracle - Coming soon

## Database URL Examples

```bash
# PostgreSQL
postgresql://username:password@localhost:5432/database

# PostgreSQL with schema
postgresql://username:password@localhost:5432/database?options=-csearch_path=myschema

# Amazon Redshift
redshift://username:password@cluster.region.redshift.amazonaws.com:5439/database

# With SSL
postgresql://username:password@localhost:5432/database?sslmode=require
```

## License

MIT License - same as nlp2sql
