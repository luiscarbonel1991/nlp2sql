"""Example showing automatic schema loading from database - no manual schema needed."""

import asyncio
import logging
import os

import structlog

# Disable debug logs for cleaner output
logging.basicConfig(level=logging.WARNING)
structlog.configure(
    processors=[structlog.stdlib.filter_by_level, structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

from nlp2sql import DatabaseType, create_query_service  # noqa: E402


async def test_auto_schema_loading():
    """Demonstrate automatic schema loading from database."""

    # Use Docker enterprise database for large schema testing
    database_url = "postgresql://demo:demo123@localhost:5433/enterprise"

    # Detect available AI provider
    providers = [
        {"name": "openai", "env_var": "OPENAI_API_KEY", "key": os.getenv("OPENAI_API_KEY")},
        {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY", "key": os.getenv("ANTHROPIC_API_KEY")},
        {"name": "gemini", "env_var": "GOOGLE_API_KEY", "key": os.getenv("GOOGLE_API_KEY")},
    ]

    # Find first available provider
    selected_provider = None
    for provider in providers:
        if provider["key"]:
            selected_provider = provider
            break

    if not selected_provider:
        print("[ERROR] No AI provider API key found. Set one of:")
        for provider in providers:
            print(f"   export {provider['env_var']}=your-key")
        return

    print(f"[INFO] Using {selected_provider['name'].title()} provider")

    print("nlp2sql - Automatic Schema Loading Example")
    print("=" * 50)
    print("The schema will be loaded automatically from your database")
    print("No manual schema definition needed!")
    print()

    try:
        # Step 1: Create service (no schema needed!)
        print("Creating query service...")
        service = create_query_service(
            database_url=database_url,
            ai_provider=selected_provider["name"],
            api_key=selected_provider["key"],
            database_type=DatabaseType.POSTGRES,
        )
        print("[OK] Service created")

        # Step 2: Initialize - this loads the schema automatically
        print("\nInitializing service (loading schema from database)...")
        await service.initialize(DatabaseType.POSTGRES)
        print("[OK] Schema loaded automatically!")
        print("   - Tables analyzed")
        print("   - Embeddings created/loaded")
        print("   - Ready for queries")

        # Step 3: Test schema filtering first
        print("\nTesting Schema Filtering:")
        print("-" * 30)

        # Example of schema filtering for enterprise database
        schema_filters = {
            "exclude_system_tables": True,
            "include_schemas": ["sales", "hr", "finance"],
            "exclude_tables": ["audit_logs", "temp_tables"],
        }

        print("Schema filters applied:")
        print(f"   - Exclude system tables: {schema_filters['exclude_system_tables']}")
        print(f"   - Include schemas: {schema_filters['include_schemas']}")
        print(f"   - Exclude tables: {schema_filters['exclude_tables']}")

        # Create filtered service
        service_filtered = create_query_service(
            database_url=database_url,
            ai_provider=selected_provider["name"],
            api_key=selected_provider["key"],
            database_type=DatabaseType.POSTGRES,
            schema_filters=schema_filters,  # Apply filters
        )

        await service_filtered.initialize(DatabaseType.POSTGRES)
        print("[OK] Filtered service initialized")

        # Compare table counts
        tables_all = await service.schema_repository.get_tables()
        tables_filtered = await service_filtered.schema_repository.get_tables()

        print("Schema comparison:")
        print(f"   - All tables: {len(tables_all)}")
        print(f"   - Filtered tables: {len(tables_filtered)}")
        print(f"   - Reduction: {((len(tables_all) - len(tables_filtered)) / len(tables_all) * 100):.1f}%")

        # Step 4: Test with real questions adapted for enterprise schema - no schema context needed!
        questions = [
            "Show me all sales representatives with their territories",
            "List all customers from the sales schema with their contact info",
            "Find employees hired in the last year from HR department",
            "Count total number of active products in inventory",
            "Show me all unpaid invoices from the finance schema",
        ]

        print("\nGenerating SQL from Natural Language:")
        print("-" * 50)

        for i, question in enumerate(questions, 1):
            print(f"\n{i}. Question: {question}")

            try:
                # Just ask the question - schema is already loaded!
                result = await service.generate_sql(
                    question=question, database_type=DatabaseType.POSTGRES, max_tokens=500, temperature=0.1
                )

                print("   Generated SQL:")
                print(f"      {result['sql']}")
                print(f"   Confidence: {result['confidence']}")
                print(f"   Valid: {result['validation']['is_valid']}")

                # Show which tables were considered
                if "metadata" in result and "relevant_tables" in result["metadata"]:
                    tables = result["metadata"]["relevant_tables"][:3]
                    print(f"   Relevant tables: {', '.join(tables)}")

            except Exception as e:
                print(f"   [ERROR] {str(e)[:100]}...")

        print("\n" + "=" * 50)
        print("Success! Key advantages of automatic schema loading:")
        print("   [x] No manual schema definition needed")
        print("   [x] Always up-to-date with database changes")
        print("   [x] Handles all tables and relationships automatically")
        print("   [x] Optimized with embeddings for large schemas")
        print("   [x] Cached for performance")

        # Demonstrate schema inspection
        print("\nSchema Statistics:")
        schema_stats = await get_schema_statistics(service)
        print(f"   - Total tables: {schema_stats['total_tables']}")
        print(f"   - Total columns: {schema_stats['total_columns']}")
        print(f"   - Tables with foreign keys: {schema_stats['tables_with_fk']}")
        print(f"   - Most connected table: {schema_stats['most_connected']}")

    except Exception as e:
        print(f"\n[ERROR] {e!s}")
        import traceback

        traceback.print_exc()


async def get_schema_statistics(service):
    """Get statistics about the loaded schema."""
    try:
        # Access schema through the repository
        tables = await service.schema_repository.get_tables()

        total_columns = sum(len(t.columns) for t in tables)
        tables_with_fk = sum(1 for t in tables if t.foreign_keys)

        # Find most connected table
        connection_counts = {}
        for table in tables:
            connections = len(table.foreign_keys or [])
            # Count tables that reference this one
            for other_table in tables:
                if other_table.foreign_keys:
                    for fk in other_table.foreign_keys:
                        if fk.get("ref_table") == table.name:
                            connections += 1
            connection_counts[table.name] = connections

        most_connected = max(connection_counts.items(), key=lambda x: x[1])

        return {
            "total_tables": len(tables),
            "total_columns": total_columns,
            "tables_with_fk": tables_with_fk,
            "most_connected": f"{most_connected[0]} ({most_connected[1]} connections)",
        }
    except Exception:
        return {"total_tables": "N/A", "total_columns": "N/A", "tables_with_fk": "N/A", "most_connected": "N/A"}


if __name__ == "__main__":
    print("Usage: python examples/schema_management/test_auto_schema.py")
    print("   Set at least one AI provider API key:")
    print("   - export OPENAI_API_KEY=your-openai-key")
    print("   - export ANTHROPIC_API_KEY=your-anthropic-key")
    print("   - export GOOGLE_API_KEY=your-google-key")
    print("   Make sure Docker enterprise database is running:")
    print("   - docker-compose -f docker/docker-compose.yml up postgres-large")
    print()

    asyncio.run(test_auto_schema_loading())
