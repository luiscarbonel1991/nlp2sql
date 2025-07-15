# nlp2sql Examples

This directory contains organized examples demonstrating various nlp2sql capabilities.

## 🚀 Getting Started

Start here if you're new to nlp2sql:

### [`getting_started/`](getting_started/)
- **`test_api_setup.py`** - Validate API keys and environment setup
- **`basic_usage.py`** - Comprehensive demo of all features
- **`simple_demo.py`** - Minimal example for beginners

```bash
# Test your setup first
python examples/getting_started/test_api_setup.py

# Then try the basic example
python examples/getting_started/basic_usage.py
```

## 🔧 Advanced Features

Explore advanced capabilities:

### [`advanced/`](advanced/)
- **`test_multiple_providers.py`** - Compare OpenAI, Anthropic, and Gemini
- **`test_schema_filters.py`** - Handle large databases (1000+ tables)
- **`test_simple_api.py`** - One-line API usage patterns

```bash
# Test multiple AI providers
python examples/advanced/test_multiple_providers.py

# Test large schema handling
python examples/advanced/test_schema_filters.py
```

## 📊 Schema Management

Learn schema handling strategies:

### [`schema_management/`](schema_management/)
- **`test_auto_schema.py`** - Automatic schema loading from database
- **`test_schema_only.py`** - Schema intelligence without AI provider

```bash
# Test automatic schema discovery
python examples/schema_management/test_auto_schema.py
```

## 🗄️ Database-Specific

Real-world database integrations:

### [`database_specific/`](database_specific/)
- **`test_odoo_integration.py`** - Comprehensive Odoo PostgreSQL integration

```bash
# Test with Odoo database
python examples/database_specific/test_odoo_integration.py
```

## 📚 Documentation

Educational examples and guides:

### [`documentation/`](documentation/)
- **`real_world_example.py`** - Complete real-world scenario

## 🔑 Environment Setup

Before running examples, set up your environment:

```bash
# Required for OpenAI (default provider)
export OPENAI_API_KEY=your-openai-key

# Optional for multi-provider support
export ANTHROPIC_API_KEY=your-anthropic-key
export GOOGLE_API_KEY=your-google-key

# Database connection (for database examples)
export DATABASE_URL=postgresql://user:pass@localhost:5432/db
```

## 📋 Example Workflow

1. **Setup & Validation**
   ```bash
   python examples/getting_started/test_api_setup.py
   ```

2. **Learn Basics**
   ```bash
   python examples/getting_started/simple_demo.py
   python examples/getting_started/basic_usage.py
   ```

3. **Explore Advanced Features**
   ```bash
   python examples/advanced/test_multiple_providers.py
   python examples/advanced/test_schema_filters.py
   ```

4. **Database Integration**
   ```bash
   python examples/database_specific/test_odoo_integration.py
   ```

## 🛠️ Troubleshooting

### Common Issues

**API Key Errors:**
```bash
# Run the setup test to diagnose
python examples/getting_started/test_api_setup.py
```

**Database Connection:**
```bash
# Check your database URL format
postgresql://username:password@host:port/database
```

**Import Errors:**
```bash
# Install missing providers
pip install nlp2sql[anthropic,gemini]
# Or install all providers
pip install nlp2sql[all-providers]
```

## 📈 Performance Tips

1. **Use Pre-Initialized Services** for multiple queries
2. **Apply Schema Filters** for large databases
3. **Cache Service Instances** in production
4. **Choose the Right Provider** for your use case

See [`USAGE.md`](../USAGE.md) for detailed usage patterns and best practices.
