#!/bin/bash
echo "Initializing LocalStack Redshift for nlp2sql testing..."

# Wait for LocalStack to be ready
echo "Waiting for LocalStack to be ready..."
while ! curl -f http://localhost:4566/_localstack/health > /dev/null 2>&1; do
    echo "Waiting for LocalStack..."
    sleep 2
done

echo "LocalStack is ready, setting up Redshift cluster..."

# Create a Redshift cluster
aws --endpoint-url=http://localhost:4566 redshift create-cluster \
    --cluster-identifier nlp2sql-test-cluster \
    --node-type dc2.large \
    --master-username testuser \
    --master-user-password testpass123 \
    --db-name testdb \
    --cluster-type single-node \
    --publicly-accessible \
    --region us-east-1

echo "Waiting for Redshift cluster to be available..."
aws --endpoint-url=http://localhost:4566 redshift wait cluster-available \
    --cluster-identifier nlp2sql-test-cluster \
    --region us-east-1

echo "Redshift cluster is ready!"

# Create test schema and tables
echo "Creating test schema and tables..."

# Note: We'll use psql to connect since Redshift is PostgreSQL-compatible
export PGPASSWORD=testpass123
psql -h localhost -p 5439 -U testuser -d testdb << 'EOF'
-- Create test schema similar to our PostgreSQL setup
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Create tables in public schema (simple setup)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10,2),
    category_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    total_amount DECIMAL(10,2),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending'
);

-- Create tables in sales schema (Redshift-specific testing)
CREATE TABLE IF NOT EXISTS sales.customers (
    customer_id INTEGER PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    contact_name VARCHAR(255),
    industry VARCHAR(100),
    annual_revenue DECIMAL(15,2),
    region VARCHAR(50),
    created_date DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS sales.transactions (
    transaction_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    transaction_date DATE,
    amount DECIMAL(12,2),
    product_category VARCHAR(100),
    sales_rep VARCHAR(255)
);

-- Create analytics tables
CREATE TABLE IF NOT EXISTS analytics.sales_summary (
    summary_id INTEGER PRIMARY KEY,
    period_start DATE,
    period_end DATE,
    total_revenue DECIMAL(15,2),
    total_transactions INTEGER,
    avg_transaction_value DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample data
INSERT INTO users (id, name, email, status) VALUES
(1, 'John Doe', 'john@example.com', 'active'),
(2, 'Jane Smith', 'jane@example.com', 'active'),
(3, 'Bob Johnson', 'bob@example.com', 'inactive');

INSERT INTO products (id, name, description, price, category_id) VALUES
(1, 'Widget A', 'High-quality widget', 29.99, 1),
(2, 'Widget B', 'Premium widget', 49.99, 1),
(3, 'Gadget X', 'Innovative gadget', 99.99, 2);

INSERT INTO orders (id, user_id, total_amount, status) VALUES
(1, 1, 79.98, 'completed'),
(2, 2, 149.98, 'completed'),
(3, 1, 29.99, 'pending');

INSERT INTO sales.customers (customer_id, company_name, contact_name, industry, annual_revenue, region) VALUES
(1, 'TechCorp Inc', 'Alice Wilson', 'Technology', 5000000.00, 'North America'),
(2, 'Global Solutions', 'Bob Martinez', 'Consulting', 2000000.00, 'Europe'),
(3, 'StartupXYZ', 'Carol Brown', 'SaaS', 500000.00, 'North America');

INSERT INTO sales.transactions (transaction_id, customer_id, transaction_date, amount, product_category, sales_rep) VALUES
(1, 1, '2024-01-15', 25000.00, 'Software', 'Mike Johnson'),
(2, 2, '2024-01-20', 15000.00, 'Consulting', 'Sarah Davis'),
(3, 1, '2024-02-01', 35000.00, 'Software', 'Mike Johnson'),
(4, 3, '2024-02-10', 8000.00, 'SaaS', 'Tom Wilson');

INSERT INTO analytics.sales_summary (summary_id, period_start, period_end, total_revenue, total_transactions, avg_transaction_value) VALUES
(1, '2024-01-01', '2024-01-31', 40000.00, 2, 20000.00),
(2, '2024-02-01', '2024-02-29', 43000.00, 2, 21500.00);

-- Add table comments for better AI understanding (Redshift-style)
COMMENT ON TABLE users IS 'User accounts and customer information';
COMMENT ON TABLE products IS 'Product catalog with pricing and categories';
COMMENT ON TABLE orders IS 'Customer orders and transactions';
COMMENT ON TABLE sales.customers IS 'Customer master data for sales analytics';
COMMENT ON TABLE sales.transactions IS 'Sales transaction records for reporting';
COMMENT ON TABLE analytics.sales_summary IS 'Aggregated sales metrics by period';

EOF

echo "LocalStack Redshift setup complete!"
echo "Connection URL: redshift://testuser:testpass123@localhost:5439/testdb"
echo "PostgreSQL-compatible URL: postgresql://testuser:testpass123@localhost:5439/testdb"