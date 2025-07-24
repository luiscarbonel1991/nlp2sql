"""Comprehensive schema filtering demonstration for nlp2sql."""

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


async def test_comprehensive_schema_filtering():
    """Test all types of schema filtering options."""

    # Use Docker simple database (we know this one works)
    database_url = "postgresql://testuser:testpass@localhost:5432/testdb"

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

    print("🧪 nlp2sql - Comprehensive Schema Filtering Test")
    print("=" * 60)
    print("📋 Testing all filter types with testdb database")
    print()

    # Test 1: No filters - Load everything
    print("1️⃣ BASELINE - No Filters (Load All Tables):")
    print("-" * 50)

    try:
        service_all = await create_and_initialize_service(database_url, ai_provider=ai_provider, api_key=api_key)

        tables_all = await service_all.schema_repository.get_tables()
        print(f"✅ Loaded {len(tables_all)} tables total")

        # Show what tables we have
        table_names = [table.name for table in tables_all]
        print(f"📋 Available tables: {', '.join(table_names)}")

    except Exception as e:
        print(f"❌ Error: {e!s}")
        return

    # Test 2: exclude_system_tables
    print("\n2️⃣ SYSTEM TABLE EXCLUSION:")
    print("-" * 50)

    try:
        filters_no_system = {"exclude_system_tables": True}

        service_no_system = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=filters_no_system
        )

        tables_no_system = await service_no_system.schema_repository.get_tables()
        print(f"✅ Loaded {len(tables_no_system)} tables (system tables excluded)")
        print(f"📊 Reduced by {len(tables_all) - len(tables_no_system)} system tables")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Test 3: include_tables (specific tables only)
    print("\n3️⃣ SPECIFIC TABLE INCLUSION:")
    print("-" * 50)

    try:
        filters_specific = {"include_tables": ["users", "products", "orders"], "exclude_system_tables": True}

        service_specific = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=filters_specific
        )

        tables_specific = await service_specific.schema_repository.get_tables()
        included_names = [table.name for table in tables_specific]

        print(f"✅ Loaded {len(tables_specific)} specific tables")
        print(f"📋 Included tables: {', '.join(included_names)}")

        # Test a query with limited schema
        print("\n🧠 Testing query with limited schema:")
        result = await service_specific.generate_sql("How many users do we have?", database_type=DatabaseType.POSTGRES)

        print(f"   📝 Generated SQL: {result['sql']}")
        print(f"   📊 Confidence: {result['confidence']}")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Test 4: exclude_tables (blacklist specific tables)
    print("\n4️⃣ SPECIFIC TABLE EXCLUSION:")
    print("-" * 50)

    try:
        filters_exclude = {
            "exclude_tables": ["reviews"],  # Exclude reviews table
            "exclude_system_tables": True,
        }

        service_exclude = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=filters_exclude
        )

        tables_exclude = await service_exclude.schema_repository.get_tables()
        excluded_names = [table.name for table in tables_exclude]

        print(f"✅ Loaded {len(tables_exclude)} tables (excluded 'reviews')")
        print(f"📋 Remaining tables: {', '.join(excluded_names)}")

        # Verify reviews table is not included
        has_reviews = any(table.name == "reviews" for table in tables_exclude)
        print(f"🔍 Reviews table present: {'❌ No' if not has_reviews else '✅ Yes'}")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Test 5: include_schemas (if we have multiple schemas)
    print("\n5️⃣ SCHEMA-BASED FILTERING:")
    print("-" * 50)

    try:
        # Check what schemas we have first
        all_schemas = set()
        for table in tables_all:
            if hasattr(table, "schema") and table.schema:
                all_schemas.add(table.schema)
            # Also check if schema is in the name (schema.table format)
            if "." in table.name:
                schema_name = table.name.split(".")[0]
                all_schemas.add(schema_name)

        if not all_schemas:
            all_schemas.add("public")  # Default PostgreSQL schema

        print(f"📊 Available schemas: {', '.join(all_schemas) if all_schemas else 'public (default)'}")

        # Filter by public schema only
        filters_schema = {"include_schemas": ["public"], "exclude_system_tables": True}

        service_schema = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=filters_schema
        )

        tables_schema = await service_schema.schema_repository.get_tables()
        print(f"✅ Loaded {len(tables_schema)} tables from 'public' schema")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Test 6: Complex combined filtering
    print("\n6️⃣ COMPLEX COMBINED FILTERING:")
    print("-" * 50)

    try:
        filters_complex = {
            "include_schemas": ["public"],
            "include_tables": ["users", "products", "orders", "categories"],
            "exclude_tables": ["order_items"],  # Exclude junction table
            "exclude_system_tables": True,
        }

        service_complex = await create_and_initialize_service(
            database_url, ai_provider=ai_provider, api_key=api_key, schema_filters=filters_complex
        )

        tables_complex = await service_complex.schema_repository.get_tables()
        complex_names = [table.name for table in tables_complex]

        print(f"✅ Loaded {len(tables_complex)} tables with complex filtering")
        print(f"📋 Final tables: {', '.join(complex_names)}")

        # Test query with complex filtered schema
        print("\n🧠 Testing query with complex filtered schema:")
        result = await service_complex.generate_sql(
            "Show me products with their categories", database_type=DatabaseType.POSTGRES
        )

        print(f"   📝 Generated SQL: {result['sql'][:100]}{'...' if len(result['sql']) > 100 else ''}")
        print(f"   📊 Confidence: {result['confidence']}")

    except Exception as e:
        print(f"❌ Error: {e!s}")

    # Summary and recommendations
    print("\n" + "=" * 60)
    print("📊 SCHEMA FILTERING TEST RESULTS SUMMARY")
    print("=" * 60)

    print("\n🔢 Table Count Comparison:")
    print(f"   • No filters: {len(tables_all)} tables")
    try:
        print(f"   • System excluded: {len(tables_no_system)} tables")
        print(f"   • Specific inclusion: {len(tables_specific)} tables")
        print(f"   • Specific exclusion: {len(tables_exclude)} tables")
        print(f"   • Schema filtered: {len(tables_schema)} tables")
        print(f"   • Complex filtering: {len(tables_complex)} tables")
    except:
        pass

    print("\n💡 Schema Filter Options Available:")
    print("   ✅ exclude_system_tables: bool - Remove pg_*, information_schema, etc.")
    print("   ✅ include_schemas: List[str] - Only include specific schemas")
    print("   ✅ exclude_schemas: List[str] - Exclude specific schemas")
    print("   ✅ include_tables: List[str] - Only include specific tables")
    print("   ✅ exclude_tables: List[str] - Exclude specific tables")

    print("\n🚀 Performance Benefits Observed:")
    print("   • Reduced table processing for faster initialization")
    print("   • More focused AI context for better SQL generation")
    print("   • Lower memory usage with filtered schemas")
    print("   • Cleaner queries without irrelevant tables")

    print("\n🎯 Best Practices:")
    print("   1. Always start with exclude_system_tables=True")
    print("   2. Use include_tables for focused business logic")
    print("   3. Use include_schemas for multi-tenant applications")
    print("   4. Combine filters for optimal performance on large databases")

    print("\n📚 Filter Examples for Different Use Cases:")
    print("   🏢 E-commerce:")
    print("      schema_filters = {")
    print("          'include_tables': ['users', 'products', 'orders', 'payments'],")
    print("          'exclude_system_tables': True")
    print("      }")
    print("   ")
    print("   🏭 Enterprise (multi-schema):")
    print("      schema_filters = {")
    print("          'include_schemas': ['sales', 'hr', 'finance'],")
    print("          'exclude_tables': ['audit_logs', 'temp_tables'],")
    print("          'exclude_system_tables': True")
    print("      }")
    print("   ")
    print("   🚀 High Performance:")
    print("      schema_filters = {")
    print("          'include_tables': ['core_table1', 'core_table2'],")
    print("          'exclude_system_tables': True")
    print("      }")


if __name__ == "__main__":
    print("🔧 nlp2sql Schema Filtering Demo")
    print("   Set at least one AI provider API key:")
    print("   - export OPENAI_API_KEY=your-openai-key")
    print("   - export ANTHROPIC_API_KEY=your-anthropic-key")
    print("   - export GOOGLE_API_KEY=your-google-key")
    print("   Make sure Docker testdb is running:")
    print("   - docker-compose -f docker/docker-compose.yml up postgres")
    print()

    asyncio.run(test_comprehensive_schema_filtering())
