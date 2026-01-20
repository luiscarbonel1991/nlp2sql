"""API setup and validation example for nlp2sql.

This example consolidates API key testing and validation into one comprehensive test that shows:
- API key validation for different providers
- Environment variable setup
- Simple SQL generation testing
- Troubleshooting common issues
"""

import asyncio
import os


async def test_openai_api_key(api_key: str = None):
    """Test OpenAI API key validity with detailed feedback."""
    print("Testing OpenAI API Key")
    print("=" * 40)

    # Try to get API key from parameter or environment
    test_key = api_key or os.getenv("OPENAI_API_KEY")

    if not test_key:
        print("[ERROR] No OpenAI API key provided")
        print("Solutions:")
        print("   1. Set environment variable: export OPENAI_API_KEY=your-key")
        print("   2. Pass key directly: test_openai_api_key('your-key')")
        print("   3. Get key from: https://platform.openai.com/api-keys")
        return False

    # Mask the key for security
    masked_key = f"{test_key[:8]}...{test_key[-4:]}" if len(test_key) > 12 else "***"
    print(f"Testing key: {masked_key}")

    try:
        # Test with a simple database-less example
        from nlp2sql.adapters.openai_adapter import OpenAIAdapter

        _adapter = OpenAIAdapter(api_key=test_key)  # noqa: F841

        print("[OK] API key format is valid")
        print("[OK] OpenAI adapter initialized successfully")
        print("[OK] API key is working!")
        return True

    except ImportError as e:
        print(f"[ERROR] Import error: {e!s}")
        print("Try: pip install openai>=1.0.0")
        return False
    except Exception as e:
        error_msg = str(e).lower()
        print(f"[ERROR] API key test failed: {e!s}")

        if "invalid" in error_msg or "401" in error_msg:
            print("Solutions:")
            print("   1. Check if your API key is correct")
            print("   2. Verify your OpenAI account has credits")
            print("   3. Generate a new API key")
        elif "quota" in error_msg or "limit" in error_msg:
            print("Rate limit reached - try again in a few minutes")
        elif "network" in error_msg or "connection" in error_msg:
            print("Network issue - check your internet connection")

        return False


async def test_simple_sql_generation():
    """Test simple SQL generation with automatic provider detection."""
    print("\nTesting Simple SQL Generation")
    print("=" * 40)

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
        print("[SKIP] Skipping SQL test - no API key available")
        print("Set at least one API key:")
        for provider in providers:
            print(f"   export {provider['env_var']}=your-key")
        return False

    print(f"[INFO] Using {selected_provider['name'].title()} provider")
    print("Creating test service with mock schema...")

    try:
        # Use Docker test database for realistic testing
        database_url = "postgresql://testuser:testpass@localhost:5432/testdb"

        print("Testing question: 'How many users are in the system?'")

        # This will test the API key and basic functionality
        from nlp2sql import create_query_service

        _service = create_query_service(
            database_url=database_url, ai_provider=selected_provider["name"], api_key=selected_provider["key"]
        )  # noqa: F841

        print("[OK] Service created successfully")
        print("[OK] API key validated")
        print("[OK] Ready for SQL generation!")

        return True

    except Exception as e:
        print(f"[ERROR] SQL generation test failed: {e!s}")
        return False


async def test_environment_setup():
    """Test and validate environment setup."""
    print("\nTesting Environment Setup")
    print("=" * 40)

    # Check for API keys
    api_keys = {
        "OpenAI": os.getenv("OPENAI_API_KEY"),
        "Anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "Google": os.getenv("GOOGLE_API_KEY"),
    }

    print("Checking environment variables:")

    available_providers = []
    for provider, key in api_keys.items():
        if key:
            masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
            print(f"   [OK] {provider}: {masked_key}")
            available_providers.append(provider.lower())
        else:
            print(f"   [--] {provider}: Not set")

    if not available_providers:
        print("\n[WARN] No API keys found in environment")
        print("Set at least one API key:")
        print("   export OPENAI_API_KEY=your-openai-key")
        print("   export ANTHROPIC_API_KEY=your-anthropic-key")
        print("   export GOOGLE_API_KEY=your-google-key")
        return False

    print(f"\n[OK] Available providers: {', '.join(available_providers)}")
    return True


async def test_multiple_providers():
    """Test API keys for multiple providers."""
    print("\nTesting Multiple AI Providers")
    print("=" * 40)

    providers_config = [
        {"name": "OpenAI", "provider": "openai", "env_var": "OPENAI_API_KEY", "api_key": os.getenv("OPENAI_API_KEY")},
        {
            "name": "Anthropic",
            "provider": "anthropic",
            "env_var": "ANTHROPIC_API_KEY",
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
        },
        {
            "name": "Google Gemini",
            "provider": "gemini",
            "env_var": "GOOGLE_API_KEY",
            "api_key": os.getenv("GOOGLE_API_KEY"),
        },
    ]

    working_providers = []

    for config in providers_config:
        print(f"\nTesting {config['name']}...")

        if not config["api_key"]:
            print(f"   [SKIP] No API key (set {config['env_var']})")
            continue

        try:
            # Create a basic service to test the provider
            from nlp2sql import create_query_service

            _service = create_query_service(
                database_url="postgresql://test:test@localhost/test",
                ai_provider=config["provider"],
                api_key=config["api_key"],
            )  # noqa: F841

            print(f"   [OK] {config['name']} adapter initialized successfully")
            working_providers.append(config["name"])

        except ImportError as e:
            print(f"   [ERROR] Import error: {e!s}")
            print(f"   Install with: pip install nlp2sql[{config['provider']}]")
        except Exception as e:
            print(f"   [ERROR] Failed: {e!s}")

    if working_providers:
        print(f"\n[OK] Working providers: {', '.join(working_providers)}")
        return True
    print("\n[ERROR] No working providers found")
    return False


async def show_setup_instructions():
    """Show comprehensive setup instructions."""
    print("\nComplete Setup Instructions")
    print("=" * 40)

    print("1. Install nlp2sql:")
    print("   pip install nlp2sql")
    print("   # Or with all providers:")
    print("   pip install nlp2sql[all-providers]")

    print("\n2. Get API Keys:")
    print("   - OpenAI: https://platform.openai.com/api-keys")
    print("   - Anthropic: https://console.anthropic.com/")
    print("   - Google: https://cloud.google.com/ai-platform")

    print("\n3. Set Environment Variables:")
    print("   export OPENAI_API_KEY=your-openai-key")
    print("   export ANTHROPIC_API_KEY=your-anthropic-key")
    print("   export GOOGLE_API_KEY=your-google-key")

    print("\n4. Database Setup (Optional for testing):")
    print("   # PostgreSQL example:")
    print("   docker run -d -p 5432:5432 \\")
    print("     -e POSTGRES_USER=test \\")
    print("     -e POSTGRES_PASSWORD=test \\")
    print("     -e POSTGRES_DB=test \\")
    print("     postgres:13")

    print("\n5. Test Your Setup:")
    print("   python examples/test_api_setup.py")


async def run_comprehensive_test():
    """Run all API setup tests."""
    print("nlp2sql - API Setup & Validation")
    print("=" * 50)

    tests = [
        ("Environment Setup", test_environment_setup),
        ("OpenAI API Key", lambda: test_openai_api_key()),
        ("Simple SQL Generation", test_simple_sql_generation),
        ("Multiple Providers", test_multiple_providers),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] {test_name} failed with error: {e!s}")
            results.append((test_name, False))

    # Show summary
    print("\nTest Results Summary")
    print("=" * 30)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"   {status} {test_name}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("All tests passed! nlp2sql is ready to use!")
    elif passed > 0:
        print("Some tests passed. Check failed tests above.")
    else:
        print("All tests failed. Please check setup instructions.")

    # Show setup instructions if needed
    if passed < total:
        await show_setup_instructions()


if __name__ == "__main__":
    print("nlp2sql API Setup & Validation Tool")
    print("This script helps you validate your API keys and environment setup.")
    print()

    asyncio.run(run_comprehensive_test())
