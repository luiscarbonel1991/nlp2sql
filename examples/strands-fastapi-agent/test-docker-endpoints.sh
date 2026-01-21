#!/bin/bash

echo "=== Strands FastAPI Agent - Complete Test Suite ==="
echo ""

# Test 1: Health Check
echo "1. Testing Health Endpoint..."
curl -s http://localhost:8000/health | jq .
echo ""

# Test 2: List Tables
echo "2. Testing Tables Endpoint (showing first 5 tables)..."
curl -s http://localhost:8000/tables | jq '.tables[0:5] | .[] | {name, columns}'
echo ""

# Test 3: Count Products
echo "3. Testing Execute SQL - Count Products..."
curl -s -X POST http://localhost:8000/tools/execute-sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT COUNT(*) as total_products FROM products;"}' | jq .
echo ""

# Test 4: Top Products by Price
echo "4. Testing Execute SQL - Top Products..."
curl -s -X POST http://localhost:8000/tools/execute-sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT name, price FROM products ORDER BY price DESC LIMIT 3;"}' | jq .
echo ""

# Test 5: Products by Category
echo "5. Testing Execute SQL - Products by Category..."
curl -s -X POST http://localhost:8000/tools/execute-sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT c.name as category, COUNT(p.id) as product_count FROM categories c LEFT JOIN products p ON c.id = p.category_id GROUP BY c.name ORDER BY product_count DESC LIMIT 5;"}' | jq .
echo ""

# Test 6: Database Statistics
echo "6. Testing Multiple Counts..."
echo -n "Products: "
curl -s -X POST http://localhost:8000/tools/execute-sql -H "Content-Type: application/json" -d '{"sql": "SELECT COUNT(*) FROM products;"}' | jq -r '.data[0] | to_entries[0].value'
echo -n "Users: "
curl -s -X POST http://localhost:8000/tools/execute-sql -H "Content-Type: application/json" -d '{"sql": "SELECT COUNT(*) FROM users;"}' | jq -r '.data[0] | to_entries[0].value'
echo -n "Orders: "
curl -s -X POST http://localhost:8000/tools/execute-sql -H "Content-Type: application/json" -d '{"sql": "SELECT COUNT(*) FROM orders;"}' | jq -r '.data[0] | to_entries[0].value'
echo -n "Categories: "
curl -s -X POST http://localhost:8000/tools/execute-sql -H "Content-Type: application/json" -d '{"sql": "SELECT COUNT(*) FROM categories;"}' | jq -r '.data[0] | to_entries[0].value'
echo ""

# Test 7: Active Products with Stock
echo "7. Testing Active Products with Stock..."
curl -s -X POST http://localhost:8000/tools/execute-sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT name, price, stock_quantity FROM products WHERE is_active = true AND stock_quantity > 0 ORDER BY stock_quantity ASC;"}' | jq '.data'
echo ""

echo "=== Natural Language Query Tests (NLP2SQL) ==="
echo ""

# Test 8: NLP - Generate SQL only
echo "8. Testing NLP2SQL - Generate SQL (no execution)..."
curl -s -X POST http://localhost:8000/tools/generate-sql \
  -H "Content-Type: application/json" \
  -d '{"question": "how many orders were placed last month"}' | jq .
echo ""

# Test 9: NLP - Query with execution
echo "9. Testing NLP2SQL - Query (generate + execute)..."
curl -s -X POST http://localhost:8000/tools/query \
  -H "Content-Type: application/json" \
  -d '{"question": "show me the top 5 products by price"}' | jq .
echo ""

# Test 10: NLP - Complex query
echo "10. Testing NLP2SQL - Complex query..."
curl -s -X POST http://localhost:8000/tools/query \
  -H "Content-Type: application/json" \
  -d '{"question": "what is the total revenue from all orders"}' | jq .
echo ""

# Test 11: NLP - Inventory query
echo "11. Testing NLP2SQL - Inventory query..."
curl -s -X POST http://localhost:8000/tools/query \
  -H "Content-Type: application/json" \
  -d '{"question": "which products have low stock less than 50 units"}' | jq .
echo ""

# Test 12: Strands Agent Chat
echo "12. Testing Strands Agent - Chat..."
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many users are registered?"}' | jq .
echo ""

# Test 13: Strands Agent - Complex question
echo "13. Testing Strands Agent - Complex question..."
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the top 3 most expensive products and their categories?"}' | jq .
echo ""

echo "=== All Tests Complete ==="
