"""Basic usage example for nlp2sql library."""

import asyncio
import os

from nlp2sql import DatabaseType, create_query_service


async def main():
    """Demonstrate basic usage of nlp2sql library."""

    # Configuration - Using Docker test database
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

    try:
        # Create service
        service = create_query_service(
            database_url=database_url,
            ai_provider=selected_provider["name"],
            api_key=selected_provider["key"],
            database_type=DatabaseType.POSTGRES,
        )

        # Initialize service
        await service.initialize(DatabaseType.POSTGRES)

        # Example questions for Docker test database (testdb schema)
        questions = [
            "How many users are registered in our system?",
            "Show me all products with their categories",
            "Count how many orders were placed last month",
            "Find the top 5 products by sales revenue",
            "Which users have placed the most orders?",
        ]

        print("nlp2sql Demo - Converting Natural Language to SQL")
        print("=" * 60)

        for i, question in enumerate(questions, 1):
            print(f"\n{i}. Question: {question}")
            print("-" * 40)

            try:
                # Generate SQL
                result = await service.generate_sql(
                    question=question, database_type=DatabaseType.POSTGRES, include_explanation=True
                )

                # Display results
                print(f"[OK] SQL Generated (Confidence: {result['confidence']:.2f})")
                print("SQL Query:")
                print(f"   {result['sql']}")

                if result["explanation"]:
                    print("Explanation:")
                    print(f"   {result['explanation']}")

                print("Stats:")
                print(f"   - Provider: {result['provider']}")
                print(f"   - Tokens used: {result['tokens_used']}")
                print(f"   - Generation time: {result['generation_time_ms']:.1f}ms")
                print(f"   - Valid: {result['validation'].get('is_valid', False)}")

                if result["validation"].get("warnings"):
                    print("Warnings:")
                    for warning in result["validation"]["warnings"]:
                        print(f"   - {warning}")

            except Exception as e:
                print(f"[ERROR] {e!s}")

        # Demonstrate query suggestions
        print("\n\nQuery Suggestions Demo")
        print("=" * 60)

        partial_queries = ["show me users", "count orders", "find products"]

        for partial in partial_queries:
            print(f"\nPartial input: '{partial}'")
            suggestions = await service.get_query_suggestions(
                partial_question=partial, database_type=DatabaseType.POSTGRES, max_suggestions=3
            )

            for i, suggestion in enumerate(suggestions, 1):
                print(f"  {i}. {suggestion['text']} (relevance: {suggestion['relevance']:.2f})")

        # Demonstrate query explanation
        print("\n\nQuery Explanation Demo")
        print("=" * 60)

        example_sql = (
            "SELECT u.username, COUNT(o.order_id) as order_count FROM users u "
            "LEFT JOIN orders o ON u.user_id = o.user_id "
            "GROUP BY u.user_id, u.username HAVING COUNT(o.order_id) > 2"
        )

        explanation = await service.explain_query(sql=example_sql, database_type=DatabaseType.POSTGRES)

        print(f"SQL Query: {example_sql}")
        print(f"Explanation: {explanation['explanation']}")

        # Service statistics
        print("\n\nService Statistics")
        print("=" * 60)

        stats = await service.get_service_stats()
        print(f"Provider: {stats['provider']}")
        print(f"Context size: {stats['provider_context_size']} tokens")
        print(f"Cache enabled: {stats['cache_enabled']}")
        print(f"Optimizer enabled: {stats['optimizer_enabled']}")

    except Exception as e:
        print(f"[ERROR] Setup error: {e!s}")
        print("Make sure your database is running and accessible")


if __name__ == "__main__":
    asyncio.run(main())
