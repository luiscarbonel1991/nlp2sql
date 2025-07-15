"""Example using the simplified one-line API for SQL generation."""
import asyncio
import os
from nlp2sql import generate_sql_from_db, create_and_initialize_service


async def test_one_line_api():
    """Test the simplest possible API usage."""
    
    database_url = "postgresql://odoo:odoo@localhost:5433/postgres"
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ Please set OPENAI_API_KEY environment variable")
        return
    
    print("🚀 nlp2sql - Simplified API Example")
    print("=" * 40)
    print("📋 One-line SQL generation from natural language")
    print()
    
    # Example 1: Single query with one-line API
    print("1️⃣ One-line API Example:")
    print("-" * 30)
    
    try:
        result = await generate_sql_from_db(
            database_url,
            "Count how many active users we have",
            api_key=api_key
        )
        
        print(f"❓ Question: Count how many active users we have")
        print(f"📝 SQL: {result['sql']}")
        print(f"📊 Confidence: {result['confidence']}")
        print()
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    # Example 2: Multiple queries with pre-initialized service
    print("\n2️⃣ Pre-initialized Service Example:")
    print("-" * 30)
    
    try:
        # Initialize once
        print("⚡ Initializing service once...")
        service = await create_and_initialize_service(
            database_url,
            api_key=api_key
        )
        print("✅ Service ready for multiple queries")
        print()
        
        # Use many times without re-loading schema
        questions = [
            "Show me all companies",
            "Find partners without phone numbers",
            "List users created today"
        ]
        
        for question in questions:
            print(f"❓ Question: {question}")
            result = await service.generate_sql(question)
            print(f"📝 SQL: {result['sql']}")
            print()
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    print("🎉 Benefits of the simplified API:")
    print("   ✅ One line for simple queries")
    print("   ✅ Pre-initialize for better performance")
    print("   ✅ Automatic schema loading")
    print("   ✅ Clean and simple code")


async def test_advanced_options():
    """Test with advanced options."""
    
    database_url = "postgresql://odoo:odoo@localhost:5433/postgres"
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return
    
    print("\n3️⃣ Advanced Options Example:")
    print("-" * 30)
    
    # One-line with custom parameters
    result = await generate_sql_from_db(
        database_url,
        "Find the top 10 most active users based on login count",
        api_key=api_key,
        max_tokens=1000,
        temperature=0.0,  # More deterministic
        include_explanation=True
    )
    
    print(f"❓ Question: Find the top 10 most active users based on login count")
    print(f"📝 SQL: {result['sql']}")
    print(f"💡 Explanation: {result.get('explanation', 'N/A')[:100]}...")


if __name__ == "__main__":
    print("🔧 Simple API Examples")
    print("=" * 20)
    print()
    
    asyncio.run(test_one_line_api())
    asyncio.run(test_advanced_options())