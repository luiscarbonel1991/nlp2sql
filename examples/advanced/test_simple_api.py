"""Example using the simplified one-line API for SQL generation."""

import asyncio
import os

from nlp2sql import create_and_initialize_service, generate_sql_from_db


async def test_one_line_api():
    """Test the simplest possible API usage."""

    # Use Docker simple database for basic API testing
    database_url = "postgresql://testuser:testpass@localhost:5432/testdb"

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
    ai_provider = selected_provider["name"]
    api_key = selected_provider["key"]

    print("nlp2sql - Simplified API Example")
    print("=" * 40)
    print("One-line SQL generation from natural language")
    print()

    # Example 1: Single query with one-line API
    print("1. One-line API Example:")
    print("-" * 30)

    try:
        result = await generate_sql_from_db(
            database_url, "Count how many users we have in the system", ai_provider=ai_provider, api_key=api_key
        )

        print("Question: Count how many users we have in the system")
        print(f"SQL: {result['sql']}")
        print(f"Confidence: {result['confidence']}")
        print()

    except Exception as e:
        print(f"[ERROR] {e!s}")

    # Example 2: Multiple queries with pre-initialized service
    print("\n2. Pre-initialized Service Example:")
    print("-" * 30)

    try:
        # Initialize once
        print("Initializing service once...")
        service = await create_and_initialize_service(database_url, ai_provider=ai_provider, api_key=api_key)
        print("[OK] Service ready for multiple queries")
        print()

        # Use many times without re-loading schema
        questions = [
            "Show me all products with their categories",
            "Find users without phone numbers",
            "List all orders placed today",
        ]

        for question in questions:
            print(f"Question: {question}")
            result = await service.generate_sql(question, database_type="postgres")
            print(f"SQL: {result['sql']}")
            print()

    except Exception as e:
        print(f"[ERROR] {e!s}")

    print("Benefits of the simplified API:")
    print("   [x] One line for simple queries")
    print("   [x] Pre-initialize for better performance")
    print("   [x] Automatic schema loading")
    print("   [x] Clean and simple code")


async def test_advanced_options():
    """Test with advanced options."""

    # Use Docker simple database for basic API testing
    database_url = "postgresql://testuser:testpass@localhost:5432/testdb"

    # Detect available AI provider (same logic as above)
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
        return  # Skip if no provider available

    ai_provider = selected_provider["name"]
    api_key = selected_provider["key"]

    print("\n3. Advanced Options Example:")
    print("-" * 30)

    # One-line with custom parameters
    result = await generate_sql_from_db(
        database_url,
        "Find the top 5 users who have placed the most orders",
        ai_provider=ai_provider,
        api_key=api_key,
        max_tokens=1000,
        temperature=0.0,  # More deterministic
        include_explanation=True,
    )

    print("Question: Find the top 5 users who have placed the most orders")
    print(f"SQL: {result['sql']}")
    print(f"Explanation: {result.get('explanation', 'N/A')[:100]}...")


if __name__ == "__main__":
    print("Simple API Examples")
    print("=" * 20)
    print()

    asyncio.run(test_one_line_api())
    asyncio.run(test_advanced_options())
