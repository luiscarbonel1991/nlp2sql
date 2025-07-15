"""Basic usage example for nlp2sql library."""
import asyncio
import os
from nlp2sql import create_query_service, DatabaseType


async def main():
    """Demonstrate basic usage of nlp2sql library."""
    
    # Configuration
    database_url = "postgresql://user:password@localhost:5432/mydb"
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return
    
    try:
        # Create service
        service = create_query_service(
            database_url=database_url,
            ai_provider="openai",
            api_key=openai_api_key,
            database_type=DatabaseType.POSTGRES
        )
        
        # Initialize service
        await service.initialize(DatabaseType.POSTGRES)
        
        # Example questions
        questions = [
            "Show me all customers from New York",
            "Count how many orders were placed last month",
            "Find the top 5 products by sales",
            "Get customers who haven't placed any orders",
            "Show me monthly sales trends"
        ]
        
        print("🚀 nlp2sql Demo - Converting Natural Language to SQL")
        print("=" * 60)
        
        for i, question in enumerate(questions, 1):
            print(f"\n{i}. Question: {question}")
            print("-" * 40)
            
            try:
                # Generate SQL
                result = await service.generate_sql(
                    question=question,
                    database_type=DatabaseType.POSTGRES,
                    include_explanation=True
                )
                
                # Display results
                print(f"✅ SQL Generated (Confidence: {result['confidence']:.2f})")
                print(f"🔍 SQL Query:")
                print(f"   {result['sql']}")
                
                if result['explanation']:
                    print(f"💡 Explanation:")
                    print(f"   {result['explanation']}")
                
                print(f"📊 Stats:")
                print(f"   - Provider: {result['provider']}")
                print(f"   - Tokens used: {result['tokens_used']}")
                print(f"   - Generation time: {result['generation_time_ms']:.1f}ms")
                print(f"   - Valid: {result['validation'].get('is_valid', False)}")
                
                if result['validation'].get('warnings'):
                    print(f"⚠️  Warnings:")
                    for warning in result['validation']['warnings']:
                        print(f"   - {warning}")
                
            except Exception as e:
                print(f"❌ Error: {str(e)}")
        
        # Demonstrate query suggestions
        print(f"\n\n🔮 Query Suggestions Demo")
        print("=" * 60)
        
        partial_queries = ["show me customers", "count orders", "find products"]
        
        for partial in partial_queries:
            print(f"\nPartial input: '{partial}'")
            suggestions = await service.get_query_suggestions(
                partial_question=partial,
                database_type=DatabaseType.POSTGRES,
                max_suggestions=3
            )
            
            for i, suggestion in enumerate(suggestions, 1):
                print(f"  {i}. {suggestion['text']} (relevance: {suggestion['relevance']:.2f})")
        
        # Demonstrate query explanation
        print(f"\n\n📚 Query Explanation Demo")
        print("=" * 60)
        
        example_sql = "SELECT c.name, COUNT(o.id) as order_count FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name HAVING COUNT(o.id) > 5"
        
        explanation = await service.explain_query(
            sql=example_sql,
            database_type=DatabaseType.POSTGRES
        )
        
        print(f"SQL Query: {example_sql}")
        print(f"Explanation: {explanation['explanation']}")
        
        # Service statistics
        print(f"\n\n📈 Service Statistics")
        print("=" * 60)
        
        stats = await service.get_service_stats()
        print(f"Provider: {stats['provider']}")
        print(f"Context size: {stats['provider_context_size']} tokens")
        print(f"Cache enabled: {stats['cache_enabled']}")
        print(f"Optimizer enabled: {stats['optimizer_enabled']}")
        
    except Exception as e:
        print(f"❌ Setup error: {str(e)}")
        print("Make sure your database is running and accessible")


if __name__ == "__main__":
    asyncio.run(main())