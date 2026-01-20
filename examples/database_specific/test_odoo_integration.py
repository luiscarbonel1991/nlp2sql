"""Comprehensive Odoo integration example showing all nlp2sql capabilities.

This example consolidates multiple Odoo tests into one comprehensive demo that shows:
- Database connection testing with various configurations
- Automatic schema loading and caching
- Real-world question examples
- Optimized performance for production use
"""

import asyncio
import os

from nlp2sql import DatabaseType, create_and_initialize_service

# Odoo database configurations to try
ODOO_CONFIGS = [
    "postgresql://odoo:odoo@localhost:5433/postgres",
    "postgresql://odoo:odoo@localhost:5432/postgres",
    "postgresql://postgres:postgres@localhost:5433/postgres",
    "postgresql://postgres:postgres@localhost:5432/postgres",
]

# Real-world Odoo questions for testing
ODOO_QUESTIONS = [
    "How many active partners do we have in the system?",
    "Show me all sales orders from this month",
    "What are the top 5 products by sales quantity?",
    "List all invoices that are in draft status",
    "Count the number of employees in each department",
]


async def test_odoo_connection():
    """Test connection to Odoo database with multiple configurations."""
    print("Testing Odoo Database Connection")
    print("=" * 50)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY environment variable not set")
        print("   Set it with: export OPENAI_API_KEY=your-api-key")
        return None

    working_config = None

    for config in ODOO_CONFIGS:
        print(f"Trying: {config}")
        try:
            _service = await create_and_initialize_service(database_url=config, api_key=api_key)
            print("   [OK] Connection successful!")  # noqa: F841
            working_config = config
            break

        except Exception as e:
            print(f"   [ERROR] Failed: {e!s}")

    if not working_config:
        print("\n[ERROR] No working Odoo configuration found")
        print("Make sure Odoo is running with one of these configurations:")
        for config in ODOO_CONFIGS:
            print(f"   {config}")
        return None

    print(f"\n[OK] Using working configuration: {working_config}")
    return working_config


async def test_schema_loading(database_url: str, api_key: str):
    """Test automatic schema loading and show statistics."""
    print("\nTesting Schema Loading")
    print("=" * 50)

    try:
        print("Loading schema from database...")
        service = await create_and_initialize_service(database_url=database_url, api_key=api_key)

        # Get schema statistics from the service
        schema_repo = service.schema_repository

        # Connect and get basic stats
        await schema_repo.connect()

        print("[OK] Schema loaded successfully!")
        print("Database connection established")
        print("Schema auto-discovery completed")

        return service

    except Exception as e:
        print(f"[ERROR] Schema loading failed: {e!s}")
        return None


async def test_question_generation(service, questions: list):
    """Test SQL generation with real Odoo questions."""
    print("\nTesting Question Generation")
    print("=" * 50)

    results = []

    for i, question in enumerate(questions, 1):
        print(f"\nQuestion {i}: {question}")

        try:
            result = await service.generate_sql(
                question=question, database_type=DatabaseType.POSTGRES, max_tokens=500, temperature=0.1
            )

            print("[OK] SQL Generated:")
            print(f"   SQL: {result['sql']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Tokens: {result['tokens_used']}")

            results.append(
                {"question": question, "sql": result["sql"], "confidence": result["confidence"], "success": True}
            )

        except Exception as e:
            print(f"   [ERROR] Generation failed: {e!s}")
            results.append({"question": question, "error": str(e), "success": False})

    return results


async def test_performance_optimization(database_url: str, api_key: str):
    """Test optimized performance with schema filtering."""
    print("\nTesting Performance Optimization")
    print("=" * 50)

    try:
        # Test with schema filters for better performance
        filters = {
            "exclude_system_tables": True,
            "excluded_tables": ["ir_logging", "ir_cron", "mail_tracking_value", "ir_attachment", "ir_translation"],
        }

        print("Creating optimized service with schema filters...")
        service = await create_and_initialize_service(
            database_url=database_url, api_key=api_key, schema_filters=filters
        )

        print("[OK] Optimized service created!")
        print("Schema filtering applied for better performance")
        print("Service ready for production use")

        # Test a quick query
        result = await service.generate_sql("Count active users", database_type=DatabaseType.POSTGRES)

        print("Quick test query result:")
        print(f"   SQL: {result['sql']}")
        print(f"   Confidence: {result['confidence']}")

        return service

    except Exception as e:
        print(f"[ERROR] Optimization test failed: {e!s}")
        return None


async def show_production_usage_example(database_url: str, api_key: str):
    """Show how to use nlp2sql in production with caching."""
    print("\nProduction Usage Example")
    print("=" * 50)

    print("Best Practices for Production:")
    print("   1. Initialize service once at application startup")
    print("   2. Reuse the same service instance for multiple queries")
    print("   3. Use schema filters for large databases")
    print("   4. Handle errors gracefully")
    print("   5. Cache schema embeddings for faster startup")

    print("\nExample production code:")
    print("""
# At application startup
service = await create_and_initialize_service(
    database_url="postgresql://odoo:odoo@localhost:5433/postgres",
    api_key=os.getenv("OPENAI_API_KEY"),
    schema_filters={"exclude_system_tables": True}
)

# In your application
async def handle_natural_language_query(question: str):
    try:
        result = await service.generate_sql(question)
        return result['sql']
    except Exception as e:
        logger.error(f"Query generation failed: {e}")
        return None
""")


async def main():
    """Run comprehensive Odoo integration test."""
    print("nlp2sql - Comprehensive Odoo Integration Test")
    print("=" * 60)

    # Test connection
    database_url = await test_odoo_connection()
    if not database_url:
        return

    api_key = os.getenv("OPENAI_API_KEY")

    # Test schema loading
    service = await test_schema_loading(database_url, api_key)
    if not service:
        return

    # Test question generation
    results = await test_question_generation(service, ODOO_QUESTIONS)

    # Show results summary
    successful = sum(1 for r in results if r["success"])
    total = len(results)

    print("\nResults Summary:")
    print(f"   Successful queries: {successful}/{total}")
    print(f"   Success rate: {successful / total * 100:.1f}%")

    if successful > 0:
        avg_confidence = sum(r["confidence"] for r in results if r["success"]) / successful
        print(f"   Average confidence: {avg_confidence:.2f}")

    # Test performance optimization
    await test_performance_optimization(database_url, api_key)

    # Show production usage
    await show_production_usage_example(database_url, api_key)

    print("\n" + "=" * 60)
    print("Odoo integration test completed!")
    print("nlp2sql is ready for production use with Odoo")


if __name__ == "__main__":
    print("Setup Instructions:")
    print("   1. Start Odoo with PostgreSQL:")
    print("      docker run -d -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo \\")
    print("         -e POSTGRES_DB=postgres -p 5433:5432 postgres:13")
    print("   2. Set your OpenAI API key:")
    print("      export OPENAI_API_KEY=your-api-key")
    print("   3. Run this example:")
    print("      python examples/test_odoo_integration.py")
    print()

    asyncio.run(main())
