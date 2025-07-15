# nlp2sql CLI Guide

The nlp2sql CLI provides a comprehensive interface for natural language to SQL conversion with advanced features for development and production use.

## 🚀 Quick Setup

### Install for Development
```bash
# Clone and install
git clone https://github.com/luiscarbonel1991/nlp2sql.git
cd nlp2sql
./install-dev.sh
```

### Set API Keys
```bash
export OPENAI_API_KEY=your-openai-key
export ANTHROPIC_API_KEY=your-anthropic-key  # optional
export GOOGLE_API_KEY=your-google-key        # optional
```

### Setup Test Databases (Optional)
```bash
# Start PostgreSQL test databases
cd docker
docker-compose up -d

# This creates:
# - Simple database: postgresql://testuser:testpass@localhost:5432/testdb
# - Large database: postgresql://demo:demo123@localhost:5433/enterprise
```

### Verify Installation
```bash
uv run nlp2sql --help
uv run nlp2sql setup     # Interactive setup
uv run nlp2sql validate  # Validate configuration

# Test with sample database
uv run nlp2sql inspect \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb
```
uv run nlp2sql query \
--database-url "postgresql://screenshotuser:screenshotpass@localhost:5434/screenshotapi" \
--question "How many users are there?" \
--provider openai
## 📋 Command Reference

### Setup & Validation

#### `nlp2sql setup`
Interactive setup and configuration wizard.
```bash
uv run nlp2sql setup
```
- Checks API key status
- Offers to test providers
- Interactive database configuration

#### `nlp2sql validate`
Validates your complete configuration.
```bash
uv run nlp2sql validate [-v]
```
- Tests all configured API keys
- Validates database connections
- Shows comprehensive status report

### AI Provider Management

#### `nlp2sql providers list`
Lists all available AI providers and their status.
```bash
uv run nlp2sql providers list
```

#### `nlp2sql providers test`
Tests provider connections.
```bash
# Test all configured providers
uv run nlp2sql providers test

# Test specific provider
uv run nlp2sql providers test --provider openai
```

### SQL Query Generation

#### `nlp2sql query`
Generate SQL from natural language with advanced options.

**Basic Usage:**
```bash
# Simple test database (use docker/docker-compose.yml)
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Show me all active users"

# Large enterprise database
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Show me sales performance by rep"
```

**Advanced Usage:**
```bash
# Using Anthropic with large schema and filters
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Calculate monthly revenue by product category" \
  --provider anthropic \
  --explain \
  --temperature 0.1 \
  --max-tokens 1500 \
  --schema-filters '{"include_schemas": ["sales"], "exclude_system_tables": true}'
```

**Options:**
- `--provider`: Choose AI provider (`openai`, `anthropic`, `gemini`)
- `--api-key`: API key (or use environment variables)
- `--explain`: Include detailed explanation
- `--temperature`: Model creativity (0.0-1.0)
- `--max-tokens`: Maximum response tokens
- `--schema-filters`: JSON string with schema filters

**Examples:**
```bash
# Using OpenAI with explanation
uv run nlp2sql query \
  --database-url postgresql://localhost/sales \
  --question "Top 10 customers by revenue" \
  --provider openai \
  --explain

# Using Anthropic for large schema
uv run nlp2sql query \
  --database-url postgresql://localhost/enterprise \
  --question "Find customers with unusual patterns" \
  --provider anthropic \
  --schema-filters '{"include_tables": ["customers", "orders", "payments"]}'

# Using Gemini for cost efficiency
uv run nlp2sql query \
  --database-url postgresql://localhost/analytics \
  --question "Count active users today" \
  --provider gemini
```

### Database Schema Inspection

#### `nlp2sql inspect`
Inspect database schema with advanced filtering.

**Basic Usage:**
```bash
uv run nlp2sql inspect --database-url postgresql://user:pass@localhost/db
```

**Advanced Filtering:**
```bash
uv run nlp2sql inspect \
  --database-url postgresql://localhost/enterprise \
  --exclude-system \
  --min-rows 1000 \
  --max-tables 50 \
  --sort-by size \
  --format json \
  --output schema.json
```

**Options:**
- `--include-tables`: Comma-separated list of tables to include
- `--exclude-tables`: Comma-separated list of tables to exclude
- `--exclude-system`: Exclude system tables
- `--min-rows`: Only show tables with at least N rows
- `--max-tables`: Limit number of tables shown
- `--sort-by`: Sort by `name`, `rows`, `size`, or `columns`
- `--format`: Output format (`summary`, `json`, `table`, `csv`)

**Examples:**
```bash
# Business tables only
uv run nlp2sql inspect \
  --database-url postgresql://localhost/crm \
  --include-tables customers,orders,products,invoices \
  --format table

# Large tables analysis
uv run nlp2sql inspect \
  --database-url postgresql://localhost/warehouse \
  --min-rows 10000 \
  --sort-by size \
  --format json
```

### Performance Benchmarking

#### `nlp2sql benchmark`
Benchmark different AI providers for performance comparison.

**Basic Usage:**
```bash
uv run nlp2sql benchmark \
  --database-url postgresql://user:pass@localhost/db
```

**Advanced Benchmarking:**
```bash
uv run nlp2sql benchmark \
  --database-url postgresql://localhost/sales \
  --questions benchmark_questions.txt \
  --providers openai,anthropic,gemini \
  --iterations 5
```

**Options:**
- `--questions`: File with test questions (one per line)
- `--providers`: Comma-separated list of providers to test
- `--iterations`: Number of iterations per test (default: 3)

**Example Questions File:**
```text
Count total customers
Show monthly sales trends
Find top performing products
Calculate customer lifetime value
Identify at-risk customers
```

**Sample Output:**
```
🏁 nlp2sql Provider Benchmark
=====================================
📊 Testing 3 providers
❓ 5 questions
🔄 3 iterations each

📊 Benchmark Results
=========================

🤖 OpenAI:
   ✅ Success rate: 100.0%
   ⏱️  Avg response time: 2.34s
   🎯 Avg confidence: 0.89
   ⚡ Total tokens: 15,420

🤖 Anthropic:
   ✅ Success rate: 100.0%
   ⏱️  Avg response time: 1.87s
   🎯 Avg confidence: 0.92
   ⚡ Total tokens: 12,180

🏆 Best performer: Anthropic
```

### Cache Management

#### `nlp2sql cache info`
Show cache information and statistics.
```bash
uv run nlp2sql cache info
```

#### `nlp2sql cache clear`
Clear various cache files.
```bash
# Clear all cache
uv run nlp2sql cache clear --all

# Clear specific cache types
uv run nlp2sql cache clear --embeddings
uv run nlp2sql cache clear --queries
```

## 🛠️ Advanced Usage Patterns

### Multi-Provider Workflow
```bash
# 1. Setup and validate all providers
uv run nlp2sql setup
uv run nlp2sql validate

# 2. Compare providers for your use case
uv run nlp2sql benchmark --database-url $DB_URL

# 3. Use optimal provider for production
uv run nlp2sql query \
  --database-url $DB_URL \
  --question "Your complex query" \
  --provider anthropic \
  --explain
```

### Large Database Optimization
```bash
# 1. Inspect full schema
uv run nlp2sql inspect --database-url $DB_URL --format json > full_schema.json

# 2. Create filtered queries
uv run nlp2sql query \
  --database-url $DB_URL \
  --question "Business intelligence query" \
  --schema-filters '{"include_tables": ["users", "orders", "products"], "exclude_system_tables": true}'

# 3. Clear cache if schema changes
uv run nlp2sql cache clear --embeddings
```

### Production Deployment
```bash
# 1. Validate production environment
export OPENAI_API_KEY=prod-key
export DATABASE_URL=postgresql://prod-host/db
uv run nlp2sql validate

# 2. Benchmark in production environment
uv run nlp2sql benchmark \
  --database-url $DATABASE_URL \
  --questions production_queries.txt \
  --iterations 1

# 3. Monitor cache usage
uv run nlp2sql cache info
```

## 🔧 Configuration Options

### Environment Variables
```bash
# Required (at least one)
export OPENAI_API_KEY=your-openai-key
export ANTHROPIC_API_KEY=your-anthropic-key
export GOOGLE_API_KEY=your-google-key

# Optional database
export DATABASE_URL=postgresql://user:pass@host:port/db

# Optional settings
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_LOG_LEVEL=INFO
```

### Global CLI Options
- `-v, --verbose`: Enable verbose output
- `--config PATH`: Specify configuration file path

## 🚨 Troubleshooting

### Common Issues

**API Key Errors:**
```bash
# Diagnose API key issues
uv run nlp2sql setup
uv run nlp2sql providers test
```

**Database Connection:**
```bash
# Test database connection
uv run nlp2sql inspect --database-url postgresql://user:pass@host:port/db
```

**Performance Issues:**
```bash
# Clear cache and re-initialize
uv run nlp2sql cache clear --all
uv run nlp2sql cache info
```

**Import Errors:**
```bash
# Install missing provider dependencies
pip install nlp2sql[anthropic,gemini]
# Or install all providers
pip install nlp2sql[all-providers]
```

### Getting Help
```bash
# General help
uv run nlp2sql --help

# Command-specific help
uv run nlp2sql query --help
uv run nlp2sql inspect --help
uv run nlp2sql benchmark --help
```

## 📈 Best Practices

1. **Start with `setup` and `validate`** to ensure proper configuration
2. **Use `benchmark`** to choose the best provider for your use case
3. **Apply schema filters** for large databases to improve performance
4. **Monitor cache usage** with `cache info` to optimize performance
5. **Use verbose mode** (`-v`) for debugging and development
6. **Test different providers** to find the best balance of cost, speed, and accuracy

The nlp2sql CLI is designed to be both powerful and user-friendly, supporting everything from quick ad-hoc queries to enterprise-scale deployments.
