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
# At least one required - CLI will auto-detect available providers
export OPENAI_API_KEY=your-openai-key
export ANTHROPIC_API_KEY=your-anthropic-key  # optional
export GOOGLE_API_KEY=your-google-key        # optional (Note: GOOGLE_API_KEY, not GEMINI_API_KEY)
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

# Test CLI with Docker database (auto-detects available provider)
uv run nlp2sql query \
  --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
  --question "How many users are there?"

# Or specify provider explicitly
uv run nlp2sql query \
  --database-url "postgresql://testuser:testpass@localhost:5432/testdb" \
  --question "How many users are there?" \
  --provider openai

# Inspect database schema
uv run nlp2sql inspect \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb
```
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
Tests provider connections with proper environment variable mapping.
```bash
# Test all configured providers (auto-detects OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY)
uv run nlp2sql providers test

# Test specific provider
uv run nlp2sql providers test --provider openai
uv run nlp2sql providers test --provider anthropic  
uv run nlp2sql providers test --provider gemini     # Uses GOOGLE_API_KEY
```

### SQL Query Generation

#### `nlp2sql query`
Generate SQL from natural language with advanced options.

**Basic Usage:**
```bash
# Simple test database (auto-detects available provider)
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Show me all active users"

# Large enterprise database with provider selection
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Show me sales performance by rep" \
  --provider anthropic  # Good for large schemas

# Test all three providers quickly
for provider in openai anthropic gemini; do
  echo "Testing $provider..."
  uv run nlp2sql query \
    --database-url postgresql://testuser:testpass@localhost:5432/testdb \
    --question "Count total users" \
    --provider $provider
done
```

**Advanced Usage:**
```bash
# Using Anthropic with large schema and comprehensive filters
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Calculate monthly revenue by product category" \
  --provider anthropic \
  --explain \
  --temperature 0.1 \
  --max-tokens 1500 \
  --schema-filters '{"include_schemas": ["sales", "finance"], "exclude_system_tables": true, "include_tables": ["customers", "orders", "products"], "exclude_tables": ["audit_logs"]}'

# Using Gemini for cost-effective high-volume queries
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Find users who registered this week" \
  --provider gemini \
  --temperature 0.0  # More deterministic
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
# Using OpenAI with explanation (Docker simple database)
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Top 5 products with highest ratings" \
  --provider openai \
  --explain

# Using Anthropic for large schema (Docker enterprise database)
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Find customers with unusual purchasing patterns" \
  --provider anthropic \
  --schema-filters '{"include_schemas": ["sales"], "include_tables": ["customers", "orders", "payments"], "exclude_system_tables": true}'

# Using Gemini for cost efficiency
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Count active users today" \
  --provider gemini
  
# Smart provider detection (uses first available)
uv run nlp2sql query \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --question "Show me user analytics" \
  --explain  # No --provider specified, auto-detects
```

### Database Schema Inspection

#### `nlp2sql inspect`
Inspect database schema with advanced filtering.

**Basic Usage:**
```bash
# Inspect simple Docker database
uv run nlp2sql inspect --database-url postgresql://testuser:testpass@localhost:5432/testdb

# Inspect enterprise Docker database
uv run nlp2sql inspect --database-url postgresql://demo:demo123@localhost:5433/enterprise
```

**Advanced Filtering:**
```bash
# Enterprise database with comprehensive filtering
uv run nlp2sql inspect \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --exclude-system \
  --min-rows 1000 \
  --max-tables 50 \
  --sort-by size \
  --format json \
  --output enterprise_schema.json

# Business tables only from simple database
uv run nlp2sql inspect \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --include-tables users,products,orders,reviews \
  --format table
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
# Business tables only (Docker simple database)
uv run nlp2sql inspect \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --include-tables users,products,orders,categories \
  --format table

# Large tables analysis (Docker enterprise database)
uv run nlp2sql inspect \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --min-rows 1000 \
  --sort-by size \
  --format json \
  --output large_tables.json

# Compare schemas between databases
uv run nlp2sql inspect --database-url postgresql://testuser:testpass@localhost:5432/testdb --format json > simple_schema.json
uv run nlp2sql inspect --database-url postgresql://demo:demo123@localhost:5433/enterprise --format json > enterprise_schema.json
```

### Performance Benchmarking

#### `nlp2sql benchmark`
Benchmark different AI providers for performance comparison.

**Basic Usage:**
```bash
# Benchmark all available providers with simple database
uv run nlp2sql benchmark \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb

# Benchmark with enterprise database
uv run nlp2sql benchmark \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise
```

**Advanced Benchmarking:**
```bash
# Compare all three providers with custom questions
uv run nlp2sql benchmark \
  --database-url postgresql://testuser:testpass@localhost:5432/testdb \
  --questions benchmark_questions.txt \
  --providers openai,anthropic,gemini \
  --iterations 3

# Enterprise database benchmark with schema filtering
uv run nlp2sql benchmark \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --questions enterprise_questions.txt \
  --providers anthropic,gemini \
  --schema-filters '{"include_schemas": ["sales", "finance"], "exclude_system_tables": true}' \
  --iterations 2
```

**Options:**
- `--questions`: File with test questions (one per line)
- `--providers`: Comma-separated list of providers to test
- `--iterations`: Number of iterations per test (default: 3)

**Example Questions File (benchmark_questions.txt):**
```text
How many users are there?
Show me all products with their categories
Find the top 5 products by average rating
Count orders placed this month
Show users who have never placed an order
What are the most popular product categories?
```

**Enterprise Questions File (enterprise_questions.txt):**
```text
Show sales performance by representative
Calculate monthly revenue trends
Find customers with highest lifetime value
Identify at-risk accounts with no recent activity
Show product performance by category
Analyze customer acquisition costs by channel
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
export OPENAI_API_KEY=your-openai-key
export ANTHROPIC_API_KEY=your-anthropic-key  
export GOOGLE_API_KEY=your-google-key

uv run nlp2sql setup
uv run nlp2sql validate

# 2. Compare providers with Docker databases
uv run nlp2sql benchmark --database-url postgresql://testuser:testpass@localhost:5432/testdb
uv run nlp2sql benchmark --database-url postgresql://demo:demo123@localhost:5433/enterprise

# 3. Use optimal provider for production
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Show quarterly sales performance by region" \
  --provider anthropic \
  --schema-filters '{"include_schemas": ["sales"], "exclude_system_tables": true}' \
  --explain
```

### Large Database Optimization
```bash
# 1. Inspect full enterprise schema
uv run nlp2sql inspect --database-url postgresql://demo:demo123@localhost:5433/enterprise --format json > enterprise_full_schema.json

# 2. Create filtered queries for better performance
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Analyze customer purchasing patterns" \
  --provider anthropic \
  --schema-filters '{
    "include_schemas": ["sales", "finance"],
    "include_tables": ["customers", "orders", "products", "payments"],
    "exclude_tables": ["audit_logs", "system_logs"],
    "exclude_system_tables": true
  }'

# 3. Performance comparison: filtered vs unfiltered
echo "Unfiltered query:"
time uv run nlp2sql query --database-url postgresql://demo:demo123@localhost:5433/enterprise --question "Show customer analytics"

echo "\nFiltered query:"
time uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Show customer analytics" \
  --schema-filters '{"include_tables": ["customers", "orders"], "exclude_system_tables": true}'

# 4. Clear cache if schema changes
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
# AI Provider API Keys (at least one required)
# CLI will auto-detect and use first available
export OPENAI_API_KEY=your-openai-key
export ANTHROPIC_API_KEY=your-anthropic-key
export GOOGLE_API_KEY=your-google-key      # Note: GOOGLE_API_KEY for Gemini provider

# Docker Database URLs (for development/testing)
export DATABASE_URL=postgresql://testuser:testpass@localhost:5432/testdb        # Simple DB
# export DATABASE_URL=postgresql://demo:demo123@localhost:5433/enterprise      # Enterprise DB

# Optional Performance Settings
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_LOG_LEVEL=INFO
export TOKENIZERS_PARALLELISM=false  # Suppress tokenizer warnings
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

# Check specific provider
uv run nlp2sql providers test --provider gemini  # Uses GOOGLE_API_KEY
```

**Database Connection:**
```bash
# Test Docker database connections
uv run nlp2sql inspect --database-url postgresql://testuser:testpass@localhost:5432/testdb
uv run nlp2sql inspect --database-url postgresql://demo:demo123@localhost:5433/enterprise

# Ensure Docker containers are running
cd docker && docker-compose ps
```

**Performance Issues:**
```bash
# Clear cache and re-initialize
uv run nlp2sql cache clear --all
uv run nlp2sql cache info

# Use schema filtering for large databases
uv run nlp2sql query \
  --database-url postgresql://demo:demo123@localhost:5433/enterprise \
  --question "Your query" \
  --schema-filters '{"exclude_system_tables": true, "include_schemas": ["sales"]}'
```

**JSON Parsing Errors (Anthropic):**
```bash
# These are handled gracefully, but if you see:
# "Query validation failed error='Expecting value: line 1 column 1 (char 0)'"
# The query still works, validation just falls back to default

# To minimize these errors, use simpler queries or different providers
uv run nlp2sql query --question "Simple query" --provider openai
```

**Provider-Specific Issues:**
```bash
# Install missing provider dependencies
uv add anthropic  # For Anthropic support
uv add google-generativeai  # For Gemini support

# Or install all providers at once
uv sync  # Installs all dependencies from pyproject.toml
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
