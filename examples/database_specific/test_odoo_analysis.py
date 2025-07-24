#!/usr/bin/env python3
"""
Test script for nlp2sql with Odoo database
Tests schema analysis and query generation capabilities
"""

import asyncio
import os

from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.config.settings import Settings
from nlp2sql.core.entities import DatabaseType
from nlp2sql.schema.analyzer import SchemaAnalyzer
from nlp2sql.schema.manager import SchemaManager
from nlp2sql.services.query_service import QueryGenerationService

# Database connection settings for Odoo
ODOO_DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "odoo",  # Replace with your actual Odoo database name
    "username": "odoo",  # Replace with your actual username
    "password": "odoo",  # Replace with your actual password
}

# Test questions for Odoo
TEST_QUESTIONS = [
    "Show me all active users",
    "List all products with their categories",
    "Find all invoices from this month",
    "Show customers with their total sales",
    "List all employees and their departments",
    "Find all purchase orders that are pending",
]


class OdooNLP2SQLTester:
    def __init__(self):
        self.settings = Settings()
        self.schema_repo = None
        self.schema_analyzer = None
        self.schema_manager = None
        self.query_service = None

    async def initialize(self):
        """Initialize all components"""
        print("🚀 Initializing nlp2sql for Odoo database analysis...")

        # Initialize schema repository
        self.schema_repo = PostgreSQLRepository(
            host=ODOO_DB_CONFIG["host"],
            port=ODOO_DB_CONFIG["port"],
            database=ODOO_DB_CONFIG["database"],
            username=ODOO_DB_CONFIG["username"],
            password=ODOO_DB_CONFIG["password"],
        )

        # Initialize schema analyzer
        self.schema_analyzer = SchemaAnalyzer(self.schema_repo)

        # Initialize schema manager
        self.schema_manager = SchemaManager(schema_repository=self.schema_repo, schema_analyzer=self.schema_analyzer)

        # Initialize AI provider (OpenAI)
        if not os.getenv("OPENAI_API_KEY"):
            print("⚠️  Warning: OPENAI_API_KEY not set. Set it for query generation testing.")
            print("   You can still test schema analysis without it.")

        try:
            ai_adapter = OpenAIAdapter()
            self.query_service = QueryGenerationService(ai_provider=ai_adapter, schema_manager=self.schema_manager)
        except Exception as e:
            print(f"⚠️  Could not initialize AI provider: {e}")

        print("✅ Initialization complete!")

    async def test_database_connection(self):
        """Test database connection"""
        print("\n📡 Testing database connection...")
        try:
            # Test connection by getting database info
            await self.schema_repo.connect()
            print(f"✅ Successfully connected to Odoo database at {ODOO_DB_CONFIG['host']}:{ODOO_DB_CONFIG['port']}")
            await self.schema_repo.disconnect()
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            print("Please check your database credentials and ensure Odoo is running.")
            return False
        return True

    async def analyze_schema(self):
        """Analyze the Odoo database schema"""
        print("\n🔍 Analyzing Odoo database schema...")

        try:
            await self.schema_repo.connect()

            # Get all tables
            tables = await self.schema_repo.get_tables()
            print(f"📊 Found {len(tables)} tables in the database")

            # Show some key Odoo tables
            odoo_core_tables = [
                table
                for table in tables
                if any(
                    keyword in table.name.lower()
                    for keyword in [
                        "res_users",
                        "res_partner",
                        "product_",
                        "sale_",
                        "purchase_",
                        "account_",
                        "hr_",
                        "stock_",
                    ]
                )
            ][:10]  # Limit to first 10

            print("\n🏢 Key Odoo tables found:")
            for table in odoo_core_tables:
                columns = await self.schema_repo.get_columns(table.name)
                print(f"  📋 {table.name} ({len(columns)} columns)")

            # Test schema analysis on a specific table
            if odoo_core_tables:
                test_table = odoo_core_tables[0]
                print(f"\n🔬 Detailed analysis of '{test_table.name}':")

                columns = await self.schema_repo.get_columns(test_table.name)
                for col in columns[:5]:  # Show first 5 columns
                    print(f"    - {col.name}: {col.data_type}")

                # Get relationships
                relationships = await self.schema_repo.get_relationships(test_table.name)
                if relationships:
                    print(f"  🔗 Relationships: {len(relationships)} found")
                    for rel in relationships[:3]:  # Show first 3
                        print(f"    - {rel.source_table}.{rel.source_column} -> {rel.target_table}.{rel.target_column}")

            await self.schema_repo.disconnect()

        except Exception as e:
            print(f"❌ Schema analysis failed: {e}")
            return False

        return True

    async def test_schema_manager(self):
        """Test schema manager functionality"""
        print("\n🧠 Testing schema manager...")

        try:
            await self.schema_repo.connect()

            # Test schema loading with filters
            test_context = "users and customers"
            relevant_tables = await self.schema_manager.get_relevant_schema(query_context=test_context, max_tables=5)

            print(f"📋 Found {len(relevant_tables)} relevant tables for context: '{test_context}'")
            for table in relevant_tables:
                print(f"  - {table.name}")

            await self.schema_repo.disconnect()

        except Exception as e:
            print(f"❌ Schema manager test failed: {e}")
            return False

        return True

    async def test_query_generation(self):
        """Test query generation with sample questions"""
        if not self.query_service:
            print("\n⚠️  Skipping query generation test (no AI provider configured)")
            return True

        print("\n🤖 Testing query generation...")

        try:
            await self.schema_repo.connect()

            for i, question in enumerate(TEST_QUESTIONS[:3], 1):  # Test first 3 questions
                print(f"\n📝 Question {i}: {question}")

                try:
                    result = await self.query_service.generate_query(
                        natural_language_query=question, database_type=DatabaseType.POSTGRES
                    )

                    print("✅ Generated SQL:")
                    print(f"```sql\n{result.sql_query}\n```")

                    if result.explanation:
                        print(f"💡 Explanation: {result.explanation}")

                except Exception as e:
                    print(f"❌ Failed to generate query: {e}")

            await self.schema_repo.disconnect()

        except Exception as e:
            print(f"❌ Query generation test failed: {e}")
            return False

        return True

    async def run_all_tests(self):
        """Run all tests"""
        print("🧪 Starting nlp2sql tests with Odoo database\n")

        # Initialize
        await self.initialize()

        # Test database connection
        if not await self.test_database_connection():
            return

        # Analyze schema
        if not await self.analyze_schema():
            return

        # Test schema manager
        if not await self.test_schema_manager():
            return

        # Test query generation
        await self.test_query_generation()

        print("\n🎉 All tests completed!")
        print("\n💡 Tips:")
        print("  - Set OPENAI_API_KEY environment variable to test query generation")
        print("  - Modify ODOO_DB_CONFIG if your database settings are different")
        print("  - Check the generated SQL queries for accuracy")


async def main():
    """Main function"""
    tester = OdooNLP2SQLTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
