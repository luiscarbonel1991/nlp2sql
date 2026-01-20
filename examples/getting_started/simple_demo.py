"""Simple demonstration of nlp2sql library."""

from nlp2sql.adapters.openai_adapter import OpenAIAdapter
from nlp2sql.core.entities import DatabaseType
from nlp2sql.ports.ai_provider import QueryContext, QueryResponse


def demo_basic_functionality():
    """Demonstrate basic functionality without real API calls."""

    print("nlp2sql Library Demo")
    print("=" * 50)

    # 1. Database types
    print("\n1. Supported Database Types:")
    for db_type in DatabaseType:
        print(f"   - {db_type.value}")

    # 2. Query Context
    print("\n2. Creating Query Context:")
    context = QueryContext(
        question="Show me all customers from Madrid",
        database_type=DatabaseType.POSTGRES.value,
        schema_context="""
        CREATE TABLE customers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255),
            city VARCHAR(100),
            country VARCHAR(100)
        );
        """,
        examples=[{"question": "Show all users", "sql": "SELECT * FROM users"}],
        max_tokens=1000,
    )

    print(f"   Question: {context.question}")
    print(f"   Database: {context.database_type}")
    print(f"   Max tokens: {context.max_tokens}")

    # 3. Query Response
    print("\n3. Example Query Response:")
    response = QueryResponse(
        sql="SELECT * FROM customers WHERE city = 'Madrid'",
        explanation="This query selects all customers from the city of Madrid",
        confidence=0.95,
        tokens_used=150,
        provider="openai",
    )

    print(f"   SQL: {response.sql}")
    print(f"   Explanation: {response.explanation}")
    print(f"   Confidence: {response.confidence}")
    print(f"   Tokens used: {response.tokens_used}")
    print(f"   Provider: {response.provider}")

    # 4. OpenAI Adapter (without real API call)
    print("\n4. OpenAI Adapter Configuration:")
    try:
        adapter = OpenAIAdapter(
            api_key="demo-key",  # Demo key
            model="gpt-4-turbo-preview",
            temperature=0.1,
        )

        print(f"   Provider type: {adapter.provider_type.value}")
        print(f"   Model: {adapter.model}")
        print(f"   Temperature: {adapter.temperature}")
        print(f"   Max context size: {adapter.get_max_context_size()} tokens")

        # Test token counting
        sample_text = "Show me all customers from Madrid"
        token_count = adapter.get_token_count(sample_text)
        print(f"   Token count for '{sample_text}': {token_count}")

    except Exception as e:
        print(f"   Note: {e}")

    print("\n5. Architecture Overview:")
    print("   - Clean Architecture with Ports & Adapters")
    print("   - Async/await support for better performance")
    print("   - Multiple AI providers (OpenAI, Anthropic, Gemini, etc.)")
    print("   - Advanced schema handling for large databases")
    print("   - Intelligent caching and query optimization")

    print("\n6. Key Features:")
    print("   [x] Natural language to SQL conversion")
    print("   [x] Schema-aware query generation")
    print("   [x] Multi-provider support")
    print("   [x] Large database schema handling")
    print("   [x] Query validation and optimization")
    print("   [x] Intelligent caching")
    print("   [x] Vector embeddings for semantic search")

    print("\nDemo completed successfully!")
    print("\nNext steps:")
    print("1. Set up your database connection")
    print("2. Configure your AI provider API key")
    print("3. Initialize the service with: create_query_service()")
    print("4. Start converting natural language to SQL!")


if __name__ == "__main__":
    demo_basic_functionality()
