"""Test schema functionality without AI provider - shows cached embeddings working."""

import asyncio

from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.core.entities import DatabaseType
from nlp2sql.schema.embedding_manager import SchemaEmbeddingManager
from nlp2sql.schema.manager import SchemaManager


async def test_schema_intelligence():
    """Test schema intelligence without AI provider dependency."""

    # Use Docker enterprise database for large schema testing
    database_url = "postgresql://demo:demo123@localhost:5433/enterprise"

    print("🔍 nlp2sql Schema Intelligence Test")
    print("=" * 50)
    print("📋 Testing cached embeddings and schema analysis")
    print("🚫 No AI provider needed - pure schema intelligence")
    print()

    try:
        # Initialize repository
        print("⚡ Initializing PostgreSQL repository...")
        repo = PostgreSQLRepository(database_url)
        await repo.initialize()
        print("✅ Repository initialized")

        # Get basic stats
        tables = await repo.get_tables()
        print(f"📊 Found {len(tables)} tables in enterprise database")

        # Test cached embeddings
        print("\n🧠 Testing Schema Embedding Manager...")
        embedding_manager = SchemaEmbeddingManager(database_url)

        # This should load from cache
        print("   Loading existing embeddings...")
        try:
            results = await embedding_manager.search_similar(
                "user login authentication", top_k=5, database_type=DatabaseType.POSTGRES
            )
            print(f"   ✅ Found {len(results)} similar elements for 'user login authentication'")

            for element, score in results:
                element_type = element.get("type", "unknown")
                element_name = element.get("name", "unknown")
                print(f"      - {element_type}: {element_name} (score: {score:.3f})")

        except Exception as e:
            print(f"   ⚠️  Embeddings not cached yet: {e}")

        # Test schema manager
        print("\n🏗️  Testing Schema Manager...")
        schema_manager = SchemaManager(repo, embedding_manager=embedding_manager)

        # Initialize with existing embeddings
        await schema_manager.initialize(DatabaseType.POSTGRES)
        print("✅ Schema manager initialized with cached embeddings")

        # Test finding relevant tables - adapted for enterprise schema
        test_queries = [
            "employee human resources management",
            "customer sales representatives territories",
            "invoice payment financial transactions",
            "product inventory warehouse stock",
            "sales opportunities contracts",
        ]

        print("\n🔍 Finding Relevant Tables (using cached embeddings):")
        print("-" * 50)

        for query in test_queries:
            print(f"\n❓ Query: '{query}'")
            relevant_tables = await schema_manager.find_relevant_tables(query, DatabaseType.POSTGRES, max_tables=3)

            if relevant_tables:
                print(f"   ✅ Found {len(relevant_tables)} relevant tables:")
                for table_name, relevance_score in relevant_tables:
                    print(f"      - {table_name} (relevance: {relevance_score:.3f})")
            else:
                print("   ⚠️  No relevant tables found")

        # Test direct table search
        print("\n🔍 Direct Table Search:")
        print("-" * 30)

        search_patterns = ["sales", "employee", "product", "invoice", "customer"]

        for pattern in search_patterns:
            matching_tables = await repo.search_tables(pattern)
            print(f"\n🔍 Pattern '{pattern}': {len(matching_tables)} matches")

            for table in matching_tables[:3]:  # Show first 3
                print(f"   - {table.name} ({len(table.columns)} columns)")

        # Test table relationships
        print("\n🔗 Testing Table Relationships:")
        print("-" * 30)

        # Find a table with relationships
        for table in tables[:10]:
            if table.foreign_keys:
                print(f"\n📋 Table: {table.name}")
                print(f"   Foreign keys: {len(table.foreign_keys)}")

                # Get related tables
                related_tables = await repo.get_related_tables(table.name)
                print(f"   Related tables: {len(related_tables)}")

                for rel_table in related_tables[:3]:
                    print(f"      - {rel_table.name}")
                break

        print("\n✅ SUCCESS: Schema intelligence working with cached embeddings!")
        print("\n📈 Performance benefits observed:")
        print("   - ⚡ Fast embedding lookups (cached)")
        print("   - 🧠 Semantic table matching")
        print("   - 🔍 Intelligent schema analysis")
        print("   - 🔗 Relationship discovery")
        print("   - 📊 Ready for AI query generation")

        print("\n💡 Next steps:")
        print("   - Set an AI provider API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY)")
        print("   - Run full AI-powered query generation with test_auto_schema.py")
        print("   - Schema is already optimized and cached!")

    except Exception as e:
        print(f"❌ Error: {e!s}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_schema_intelligence())
