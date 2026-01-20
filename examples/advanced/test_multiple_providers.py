"""Example showing multiple AI providers support."""

import asyncio
import os

from nlp2sql import DatabaseType, create_and_initialize_service


async def test_multiple_ai_providers():
    """Test different AI providers for SQL generation."""

    # Use Docker test database
    database_url = "postgresql://testuser:testpass@localhost:5432/testdb"
    question = "How many users are registered in our system?"

    print("nlp2sql - Multiple AI Providers Support")
    print("=" * 50)
    print(f"Question: {question}")
    print("Testing with different AI providers...")
    print()

    # Test configuration for each provider
    providers = [
        {
            "name": "OpenAI GPT-4",
            "provider": "openai",
            "api_key": os.getenv("OPENAI_API_KEY"),
            "env_var": "OPENAI_API_KEY",
        },
        {
            "name": "Anthropic Claude",
            "provider": "anthropic",
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
            "env_var": "ANTHROPIC_API_KEY",
        },
        {
            "name": "Google Gemini",
            "provider": "gemini",
            "api_key": os.getenv("GOOGLE_API_KEY"),
            "env_var": "GOOGLE_API_KEY",
        },
    ]

    results = []

    for provider_config in providers:
        print(f"Testing {provider_config['name']}...")

        if not provider_config["api_key"]:
            print(f"   [SKIP] No API key (set {provider_config['env_var']} env var)")
            print()
            continue

        try:
            # Create service with specific provider
            service = await create_and_initialize_service(
                database_url=database_url, ai_provider=provider_config["provider"], api_key=provider_config["api_key"]
            )

            # Generate SQL
            result = await service.generate_sql(
                question=question, database_type=DatabaseType.POSTGRES, max_tokens=500, temperature=0.1
            )

            print("   [OK] Success!")
            print(f"   SQL: {result['sql']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Tokens: {result['tokens_used']}")
            print(f"   Provider: {result['provider']}")

            results.append(
                {
                    "provider": provider_config["name"],
                    "sql": result["sql"],
                    "confidence": result["confidence"],
                    "tokens": result["tokens_used"],
                }
            )

        except ImportError as e:
            print(f"   [ERROR] Import Error: {e!s}")
            print(f"   Install with: pip install nlp2sql[{provider_config['provider']}]")
        except Exception as e:
            print(f"   [ERROR] {e!s}")

        print()

    # Compare results
    if len(results) > 1:
        print("Provider Comparison:")
        print("-" * 30)

        for result in results:
            print(f"{result['provider']}:")
            print(f"   SQL: {result['sql']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Tokens: {result['tokens']}")
            print()

        # Find most confident result
        best_result = max(results, key=lambda x: x["confidence"])
        print(f"Highest Confidence: {best_result['provider']} ({best_result['confidence']})")

        # Check SQL consistency
        unique_sqls = set(result["sql"].strip().lower() for result in results)
        if len(unique_sqls) == 1:
            print("[OK] All providers generated identical SQL!")
        else:
            print(f"[INFO] Generated {len(unique_sqls)} different SQL variants")

    print("\n" + "=" * 50)
    print("Multi-Provider Benefits:")
    print("   [x] No vendor lock-in")
    print("   [x] Compare AI model performance")
    print("   [x] Fallback options for reliability")
    print("   [x] Cost optimization opportunities")
    print("   [x] Different models for different use cases")


async def demo_provider_selection():
    """Demonstrate how to choose providers based on use case."""

    print("\nProvider Selection Guide:")
    print("-" * 30)

    use_cases = [
        {
            "use_case": "High accuracy complex queries",
            "recommended": "OpenAI GPT-4",
            "reason": "Most sophisticated reasoning",
        },
        {
            "use_case": "Cost-effective high volume",
            "recommended": "Google Gemini",
            "reason": "Good performance, competitive pricing",
        },
        {
            "use_case": "Long context/large schemas",
            "recommended": "Anthropic Claude",
            "reason": "200K token context window",
        },
        {
            "use_case": "Privacy-sensitive data",
            "recommended": "Self-hosted options",
            "reason": "Data doesn't leave your infrastructure",
        },
    ]

    for case in use_cases:
        print(f"{case['use_case']}:")
        print(f"   Recommended: {case['recommended']}")
        print(f"   Reason: {case['reason']}")
        print()

    print("Cost Comparison (approx):")
    print("   OpenAI GPT-4: $0.03/1K tokens")
    print("   Anthropic Claude: $0.015/1K tokens")
    print("   Google Gemini: $0.001/1K tokens")
    print()
    print("Context Limits:")
    print("   OpenAI GPT-4 Turbo: 128K tokens")
    print("   Anthropic Claude: 200K tokens")
    print("   Google Gemini Pro: 30K tokens")


if __name__ == "__main__":
    print("Multi-Provider Setup:")
    print("   export OPENAI_API_KEY=your-openai-key")
    print("   export ANTHROPIC_API_KEY=your-anthropic-key")
    print("   export GOOGLE_API_KEY=your-google-key")
    print("   pip install nlp2sql[all-providers]")
    print()

    asyncio.run(test_multiple_ai_providers())
    asyncio.run(demo_provider_selection())
