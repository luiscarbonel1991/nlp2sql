"""Example showing automatic schema loading from database - no manual schema needed."""
import asyncio
import os
import logging
import structlog

# Disable debug logs for cleaner output
logging.basicConfig(level=logging.WARNING)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

from nlp2sql import create_query_service, DatabaseType


async def test_auto_schema_loading():
    """Demonstrate automatic schema loading from database."""
    
    # Configuration
    database_url = "postgresql://odoo:odoo@localhost:5433/postgres"
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ Please set OPENAI_API_KEY environment variable")
        return
    
    print("🚀 nlp2sql - Automatic Schema Loading Example")
    print("=" * 50)
    print("📋 The schema will be loaded automatically from your database")
    print("🔍 No manual schema definition needed!")
    print()
    
    try:
        # Step 1: Create service (no schema needed!)
        print("⚡ Creating query service...")
        service = create_query_service(
            database_url=database_url,
            ai_provider="openai",
            api_key=api_key,
            database_type=DatabaseType.POSTGRES
        )
        print("✅ Service created")
        
        # Step 2: Initialize - this loads the schema automatically
        print("\n🔄 Initializing service (loading schema from database)...")
        await service.initialize(DatabaseType.POSTGRES)
        print("✅ Schema loaded automatically!")
        print("   - Tables analyzed")
        print("   - Embeddings created/loaded")
        print("   - Ready for queries")
        
        # Step 3: Test with real questions - no schema context needed!
        questions = [
            "Show me all active users in the system",
            "List all partners that are companies with their contact info",
            "Find users created in the last 30 days",
            "Count total number of companies registered",
            "Show me partners without email addresses"
        ]
        
        print("\n🧠 Generating SQL from Natural Language:")
        print("-" * 50)
        
        for i, question in enumerate(questions, 1):
            print(f"\n{i}. ❓ Question: {question}")
            
            try:
                # Just ask the question - schema is already loaded!
                result = await service.generate_sql(
                    question=question,
                    database_type=DatabaseType.POSTGRES,
                    max_tokens=500,
                    temperature=0.1
                )
                
                print(f"   📝 Generated SQL:")
                print(f"      {result['sql']}")
                print(f"   📊 Confidence: {result['confidence']}")
                print(f"   ✅ Valid: {result['validation']['is_valid']}")
                
                # Show which tables were considered
                if 'metadata' in result and 'relevant_tables' in result['metadata']:
                    tables = result['metadata']['relevant_tables'][:3]
                    print(f"   🔍 Relevant tables: {', '.join(tables)}")
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)[:100]}...")
        
        print("\n" + "="*50)
        print("🎉 Success! Key advantages of automatic schema loading:")
        print("   ✅ No manual schema definition needed")
        print("   ✅ Always up-to-date with database changes")
        print("   ✅ Handles all tables and relationships automatically")
        print("   ✅ Optimized with embeddings for large schemas")
        print("   ✅ Cached for performance")
        
        # Demonstrate schema inspection
        print("\n📊 Schema Statistics:")
        schema_stats = await get_schema_statistics(service)
        print(f"   - Total tables: {schema_stats['total_tables']}")
        print(f"   - Total columns: {schema_stats['total_columns']}")
        print(f"   - Tables with foreign keys: {schema_stats['tables_with_fk']}")
        print(f"   - Most connected table: {schema_stats['most_connected']}")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
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
                        if fk.get('ref_table') == table.name:
                            connections += 1
            connection_counts[table.name] = connections
        
        most_connected = max(connection_counts.items(), key=lambda x: x[1])
        
        return {
            'total_tables': len(tables),
            'total_columns': total_columns,
            'tables_with_fk': tables_with_fk,
            'most_connected': f"{most_connected[0]} ({most_connected[1]} connections)"
        }
    except:
        return {
            'total_tables': 'N/A',
            'total_columns': 'N/A',
            'tables_with_fk': 'N/A',
            'most_connected': 'N/A'
        }


if __name__ == "__main__":
    print("🔧 Usage: python examples/test_auto_schema.py")
    print("   Make sure to set OPENAI_API_KEY environment variable")
    print("   Make sure PostgreSQL is running on localhost:5433")
    print()
    
    asyncio.run(test_auto_schema_loading())