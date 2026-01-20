#!/bin/bash

# Test Redshift LocalStack setup
echo "Testing Redshift LocalStack Setup"
echo "===================================="

cd "$(dirname "$0")"

# Function to check if service is running
check_service() {
    local service_name=$1
    local check_command=$2

    echo "Checking $service_name..."
    if eval "$check_command" > /dev/null 2>&1; then
        echo "[OK] $service_name is running"
        return 0
    else
        echo "[ERROR] $service_name is not running"
        return 1
    fi
}

# Function to wait for service
wait_for_service() {
    local service_name=$1
    local check_command=$2
    local max_attempts=30
    local attempt=1

    echo "Waiting for $service_name to be ready..."
    while [ $attempt -le $max_attempts ]; do
        if eval "$check_command" > /dev/null 2>&1; then
            echo "[OK] $service_name is ready"
            return 0
        fi
        echo "[...] Attempt $attempt/$max_attempts - waiting for $service_name..."
        sleep 10
        attempt=$((attempt + 1))
    done

    echo "[ERROR] $service_name failed to start after $max_attempts attempts"
    return 1
}

# Start LocalStack if not running
echo "Starting LocalStack..."
docker-compose up -d localstack

# Wait for LocalStack to be ready
if wait_for_service "LocalStack" "curl -f http://localhost:4566/_localstack/health"; then
    echo "LocalStack is ready!"
else
    echo "Failed to start LocalStack"
    exit 1
fi

# Wait a bit more for Redshift to be initialized
echo "Waiting for Redshift cluster to be ready..."
sleep 30

# Test Redshift connection
echo ""
echo "-- Testing Redshift Connection"
echo "=============================="

# Test with psql (PostgreSQL-compatible)
echo "Testing PostgreSQL-compatible connection..."
if PGPASSWORD=testpass123 psql -h localhost -p 5439 -U testuser -d testdb -c "SELECT version();" > /dev/null 2>&1; then
    echo "[OK] PostgreSQL-compatible connection successful"

    # Test schema discovery
    echo "Testing schema discovery..."
    PGPASSWORD=testpass123 psql -h localhost -p 5439 -U testuser -d testdb -c "
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname IN ('public', 'sales', 'analytics')
        ORDER BY schemaname, tablename;
    "

    # Test sample data
    echo ""
    echo "Testing sample data..."
    PGPASSWORD=testpass123 psql -h localhost -p 5439 -U testuser -d testdb -c "
        SELECT 'users' as table_name, count(*) as row_count FROM users
        UNION ALL
        SELECT 'products', count(*) FROM products
        UNION ALL
        SELECT 'orders', count(*) FROM orders
        UNION ALL
        SELECT 'sales.customers', count(*) FROM sales.customers
        UNION ALL
        SELECT 'sales.transactions', count(*) FROM sales.transactions
        UNION ALL
        SELECT 'analytics.sales_summary', count(*) FROM analytics.sales_summary;
    "
else
    echo "[ERROR] PostgreSQL-compatible connection failed"
    echo "Check LocalStack logs:"
    docker-compose logs localstack | tail -20
    exit 1
fi

# Test with Python integration
echo ""
echo "-- Testing Python Integration"
echo "============================="

# Create a simple test script
cat > /tmp/test_redshift_localstack.py << 'EOF'
import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath('../src'))

from nlp2sql.adapters.redshift_adapter import RedshiftRepository
from nlp2sql.core.entities import DatabaseType

async def test_redshift():
    print("Testing RedshiftRepository with LocalStack...")

    # Test both connection formats
    redshift_url = "redshift://testuser:testpass123@localhost:5439/testdb"
    postgres_url = "postgresql://testuser:testpass123@localhost:5439/testdb"

    for url, name in [(redshift_url, "Redshift URL"), (postgres_url, "PostgreSQL URL")]:
        print(f"\n-- Testing {name}: {url}")

        try:
            repo = RedshiftRepository(url)
            await repo.initialize()
            print(f"[OK] {name} connection successful")

            # Test schema discovery
            schema_info = await repo.get_tables()
            print(f"[OK] Schema discovery successful - found {len(schema_info)} tables")

            # Print table info
            for table in schema_info[:5]:  # Show first 5 tables
                print(f"   - {table.get('schema_name', 'unknown')}.{table.get('table_name', 'unknown')}")

            await repo.close()

        except Exception as e:
            print(f"[ERROR] {name} failed: {e}")
            return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_redshift())
    sys.exit(0 if success else 1)
EOF

# Run Python test
cd ..
if python /tmp/test_redshift_localstack.py; then
    echo "[OK] Python integration test passed"
else
    echo "[ERROR] Python integration test failed"
    exit 1
fi

echo ""
echo "[SUCCESS] All Redshift LocalStack tests passed!"
echo ""
echo "-- Summary"
echo "=========="
echo "[OK] LocalStack is running on http://localhost:4566"
echo "[OK] Redshift is available on localhost:5439"
echo "[OK] Connection URLs:"
echo "   - redshift://testuser:testpass123@localhost:5439/testdb"
echo "   - postgresql://testuser:testpass123@localhost:5439/testdb"
echo "[OK] Schemas: public, sales, analytics"
echo ""
echo "[READY] Ready for nlp2sql Redshift testing!"
