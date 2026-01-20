"""Real-world example showing nlp2sql usage patterns."""


def show_usage_patterns():
    """Show different usage patterns for nlp2sql."""

    print("nlp2sql - Real World Usage Examples")
    print("=" * 60)

    # Example 1: Basic setup with automatic provider detection
    print("\n1. Basic Setup with Smart Provider Detection:")
    print("```python")
    print("from nlp2sql import create_query_service, DatabaseType")
    print("import os")
    print()
    print("# Detect available AI provider automatically")
    print("providers = [")
    print("    {'name': 'openai', 'key': os.getenv('OPENAI_API_KEY')},")
    print("    {'name': 'anthropic', 'key': os.getenv('ANTHROPIC_API_KEY')},")
    print("    {'name': 'gemini', 'key': os.getenv('GOOGLE_API_KEY')}")
    print("]")
    print("provider = next((p for p in providers if p['key']), None)")
    print()
    print("# Create service with detected provider")
    print("service = create_query_service(")
    print("    database_url='postgresql://testuser:testpass@localhost:5432/testdb',")
    print("    ai_provider=provider['name'],")
    print("    api_key=provider['key'],")
    print("    database_type=DatabaseType.POSTGRES")
    print(")")
    print()
    print("# Initialize")
    print("await service.initialize(DatabaseType.POSTGRES)")
    print("```")

    # Example 2: Query generation with real examples
    print("\n2. Query Generation:")
    print("```python")
    print("# Generate SQL from natural language")
    print("result = await service.generate_sql(")
    print("    question='Show me users who have placed more than 5 orders',")
    print("    database_type=DatabaseType.POSTGRES")
    print(")")
    print()
    print("print(f'SQL: {result[\"sql\"]}')")
    print("print(f'Confidence: {result[\"confidence\"]}')")
    print("print(f'Explanation: {result[\"explanation\"]}')")
    print("```")

    # Example 3: Real queries adapted for Docker testdb schema
    print("\n3. Example Natural Language Queries:")
    english_queries = [
        "How many users are registered in our system?",
        "Show me all products with their categories",
        "Find the top 5 best-selling products by quantity",
        "Which users haven't placed any orders?",
        "Show me orders placed this month",
        "What's the most expensive product in each category?",
        "Users who have placed more than 3 orders",
        "Show me all product reviews with ratings above 4",
    ]

    print("   Queries the library can handle:")
    for i, query in enumerate(english_queries, 1):
        print(f"   {i}. {query}")

    # Example 4: Expected SQL outputs
    print("\n4. Expected SQL Output (PostgreSQL):")
    expected_sqls = [
        "SELECT * FROM customers WHERE city = 'Madrid'",
        "SELECT COUNT(*) FROM orders WHERE order_date >= date_trunc('month', CURRENT_DATE - interval '1 month')",
        (
            "SELECT p.name, SUM(oi.quantity) as total_sold FROM products p "
            "JOIN order_items oi ON p.id = oi.product_id GROUP BY p.id, p.name ORDER BY total_sold DESC LIMIT 5"
        ),
        "SELECT c.* FROM customers c LEFT JOIN orders o ON c.id = o.customer_id WHERE o.id IS NULL",
        (
            "SELECT city, SUM(total_amount) as total_sales FROM customers c "
            "JOIN orders o ON c.id = o.customer_id GROUP BY city"
        ),
    ]

    for i, sql in enumerate(expected_sqls, 1):
        print(f"   {i}. {sql}")

    # Example 5: Advanced features
    print("\n5. Advanced Features:")
    print("```python")
    print("# Query validation")
    print("validation = await service.validate_sql(")
    print("    sql='SELECT * FROM customers WHERE city = \"Madrid\"',")
    print("    database_type=DatabaseType.POSTGRES")
    print(")")
    print()
    print("# Query suggestions")
    print("suggestions = await service.get_query_suggestions(")
    print("    partial_question='show customers',")
    print("    database_type=DatabaseType.POSTGRES")
    print(")")
    print()
    print("# Explain existing query")
    print("explanation = await service.explain_query(")
    print("    sql='SELECT COUNT(*) FROM orders WHERE status = \"completed\"',")
    print("    database_type=DatabaseType.POSTGRES")
    print(")")
    print("```")

    # Example 6: Configuration options
    print("\n6. Configuration Options:")
    print("```python")
    print("# Environment variables")
    print("export OPENAI_API_KEY='your-openai-key'")
    print("export DATABASE_URL='postgresql://user:pass@localhost:5432/db'")
    print("export NLP2SQL_MAX_SCHEMA_TOKENS=10000")
    print("export NLP2SQL_CACHE_ENABLED=true")
    print("export NLP2SQL_LOG_LEVEL=INFO")
    print()
    print("# Programmatic configuration")
    print("from nlp2sql.config.settings import settings")
    print("settings.max_schema_tokens = 12000")
    print("settings.default_temperature = 0.1")
    print("```")

    # Example 7: Error handling
    print("\n7. Error Handling:")
    print("```python")
    print("try:")
    print("    result = await service.generate_sql(")
    print("        question='very complex query',")
    print("        database_type=DatabaseType.POSTGRES")
    print("    )")
    print("except TokenLimitException as e:")
    print("    print(f'Token limit exceeded: {e.tokens_used}/{e.max_tokens}')")
    print("except QueryGenerationException as e:")
    print("    print(f'SQL generation error: {e}')")
    print("except ValidationException as e:")
    print("    print(f'Invalid SQL: {e}')")
    print("```")

    print("\n8. Key Benefits:")
    print("   [x] Handles large schemas (1000+ tables)")
    print("   [x] Multiple AI providers - no vendor lock-in")
    print("   [x] Intelligent caching - fast responses")
    print("   [x] Automatic query optimization")
    print("   [x] SQL syntax validation")
    print("   [x] Relevance scoring for tables")
    print("   [x] Schema compression for tokens")
    print("   [x] Semantic search with embeddings")
    print("   [x] Async support for better performance")
    print("   [x] Clean, extensible architecture")

    print("\nPerfect Use Cases:")
    print("   1. Companies with complex database schemas")
    print("   2. Teams needing to democratize data access")
    print("   3. Applications requiring dynamic queries")
    print("   4. BI and analytics systems")
    print("   5. Dashboards with natural language queries")

    print("\nComparison with Existing Solutions:")
    print("   vs Simple Text-to-SQL:")
    print("   [x] Large schema handling")
    print("   [x] Multiple providers")
    print("   [x] Caching and optimization")
    print("   [x] Automatic validation")
    print()
    print("   vs Enterprise solutions:")
    print("   [x] Open source and customizable")
    print("   [x] Modern architecture")
    print("   [x] Easy integration")
    print("   [x] No vendor lock-in")

    print("\nReady for production use!")


if __name__ == "__main__":
    show_usage_patterns()
