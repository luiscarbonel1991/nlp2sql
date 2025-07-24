"""Example showing schema filtering for large databases."""

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

from nlp2sql import DatabaseType, create_and_initialize_service


async def test_schema_filtering():
    """Demonstrate schema filtering for large databases."""

    # Use Docker enterprise database for large schema testing
    database_url = "postgresql://demo:demo123@localhost:5433/enterprise"

    # Detect available AI provider
    providers = [
        {"name": "openai", "env_var": "OPENAI_API_KEY", "key": os.getenv("OPENAI_API_KEY")},
        {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY", "key": os.getenv("ANTHROPIC_API_KEY")},
        {"name": "gemini", "env_var": "GOOGLE_API_KEY", "key": os.getenv("GOOGLE_API_KEY")},
    ]

    selected_provider = None
    for provider in providers:
        if provider["key"]:
            selected_provider = provider
            break

    if not selected_provider:
        print("❌ No AI provider API key found. Set one of:")
        for provider in providers:
            print(f"   export {provider['env_var']}=your-key")
        return

    print(f"🤖 Using {selected_provider['name'].title()} provider")
    ai_provider = selected_provider["name"]
    api_key = selected_provider["key"]

    print("🚀 nlp2sql - Schema Filtering Example")
    print("=" * 45)
    print("📋 Optimizing for large databases with 1000+ tables")
    print()

    # Example 1: No filters (all tables)
    print("1️⃣ No Filters - All Tables:")
    print("-" * 30)

    try:
        service_all = await create_and_initialize_service(database_url, ai_provider=ai_provider, api_key=api_key)

        tables_all = await service_all.schema_repository.get_tables()
        print(f"✅ Loaded {len(tables_all)} tables (unfiltered)")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Example 2: Exclude system tables
    print("\n2️⃣ Exclude System Tables:")
    print("-" * 30)

    try:
        filters_no_system = {
            "exclude_system_tables": True,
            "excluded_tables": [
                "web_tour_tour",
                "web_tour_tour_step",  # Tour tables
                "ir_ui_view",
                "ir_ui_menu",  # UI metadata
                "ir_model_data",
                "ir_module_module",  # System metadata
            ],
        }

        service_filtered = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=filters_no_system
        )

        print("✅ System tables excluded")
        print(f"   Filters applied: {list(filters_no_system.keys())}")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Example 3: Focus on business tables only
    print("\n3️⃣ Business Tables Only:")
    print("-" * 30)

    try:
        # Include patterns that match business logic for enterprise database
        business_filters = {
            "include_schemas": ["sales", "hr"],  # Focus on sales and HR schemas
            "exclude_system_tables": True,
        }

        service_business = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=business_filters
        )

        print("✅ Business tables only")
        print(f"   Included schemas: {business_filters['include_schemas']}")

        # Test a query with filtered schema
        result = await service_business.generate_sql(
            "Show me all sales representatives with their territories", database_type=DatabaseType.POSTGRES
        )

        print(f"   📝 Generated SQL: {result['sql']}")
        print(f"   📊 Confidence: {result['confidence']}")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Example 4: Schema-based filtering (for multi-tenant systems)
    print("\n4️⃣ Schema-Based Filtering:")
    print("-" * 30)

    try:
        # Focus on specific schemas
        schema_filters = {
            "include_schemas": ["public"],  # Only public schema
            "excluded_tables": [
                "base_import_import",
                "base_import_mapping",  # Import tables
                "base_language_export",
                "base_language_import",  # Language tables
            ],
        }

        service_schema = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=schema_filters
        )

        print("✅ Schema-based filtering applied")
        print(f"   Included schemas: {schema_filters['include_schemas']}")
        print(f"   Excluded tables: {len(schema_filters['excluded_tables'])} tables")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    print("\n" + "=" * 45)
    print("🎯 Schema Filtering Benefits:")
    print("   ✅ Faster initialization (less tables to process)")
    print("   ✅ Reduced memory usage")
    print("   ✅ More focused AI responses")
    print("   ✅ Better performance with large schemas")
    print("   ✅ Exclude irrelevant system tables")

    print("\n💡 Filter Options Available:")
    print("   • include_schemas: List of schemas to include")
    print("   • exclude_schemas: List of schemas to exclude")
    print("   • include_tables: List of specific tables to include")
    print("   • exclude_tables: List of specific tables to exclude")
    print("   • exclude_system_tables: Boolean to exclude system tables")

    print("\n🚀 For Large Databases (1000+ tables):")
    print("   1. Start with exclude_system_tables=True")
    print("   2. Use include_tables for specific modules")
    print("   3. Group related tables by business domain")
    print("   4. Use include_schemas for multi-tenant setups")


async def demo_large_database_strategy():
    """Demonstrate strategy for very large databases."""

    print("\n" + "=" * 45)
    print("📊 Large Database Strategy Demo")
    print("-" * 45)

    # Simulate filtering for a 1000+ table database
    large_db_filters = {
        "exclude_system_tables": True,
        # Focus on core business entities from enterprise schema
        "include_schemas": ["sales", "hr", "finance"],
        "include_tables": [
            # Sales
            "sales.customers",
            "sales.sales_reps",
            "sales.opportunities",
            "sales.quotes",
            "sales.contracts",
            # HR
            "hr.employees",
            "hr.departments",
            "hr.performance_reviews",
            # Finance
            "finance.invoices",
            "finance.payments",
            "finance.transactions",
            # Inventory
            "inventory.products",
            "inventory.stock_levels",
        ],
        # Exclude verbose/temporary tables
        "excluded_tables": [
            "mail_message",
            "mail_tracking_value",  # Audit logs
            "ir_attachment",
            "ir_logging",  # System logs
            "bus_bus",
            "bus_presence",  # Real-time messaging
        ],
    }

    print("🎯 Strategy for 1000+ Table Database:")
    print(f"   ✅ Include only: {len(large_db_filters['include_tables'])} core tables")
    print(f"   ✅ Exclude: {len(large_db_filters['excluded_tables'])} verbose tables")
    print("   ✅ Exclude all system tables")
    print()
    print("📈 Expected Performance Gains:")
    print("   • 95% reduction in tables processed")
    print("   • 10x faster initialization")
    print("   • 80% less memory usage")
    print("   • More accurate AI responses")


if __name__ == "__main__":
    asyncio.run(test_schema_filtering())
    asyncio.run(demo_large_database_strategy())
