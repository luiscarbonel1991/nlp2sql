-- nlp2sql Large Schema Example
-- Enterprise-scale database for testing large schema handling

-- Create multiple schemas
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS hr;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS analytics;

-- SALES SCHEMA
CREATE TABLE sales.customers (
    id SERIAL PRIMARY KEY,
    customer_code VARCHAR(20) UNIQUE NOT NULL,
    company_name VARCHAR(200) NOT NULL,
    contact_person VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(20),
    address TEXT,
    city VARCHAR(100),
    country VARCHAR(100),
    industry VARCHAR(100),
    credit_limit DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE sales.sales_reps (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    territory VARCHAR(100),
    commission_rate DECIMAL(5,4),
    hire_date DATE,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE sales.opportunities (
    id SERIAL PRIMARY KEY,
    opportunity_name VARCHAR(200) NOT NULL,
    customer_id INTEGER REFERENCES sales.customers(id),
    sales_rep_id INTEGER REFERENCES sales.sales_reps(id),
    stage VARCHAR(50) DEFAULT 'prospecting',
    value DECIMAL(15,2),
    probability INTEGER CHECK (probability >= 0 AND probability <= 100),
    expected_close_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.quotes (
    id SERIAL PRIMARY KEY,
    quote_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id INTEGER REFERENCES sales.customers(id),
    opportunity_id INTEGER REFERENCES sales.opportunities(id),
    total_amount DECIMAL(15,2),
    valid_until DATE,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.contracts (
    id SERIAL PRIMARY KEY,
    contract_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id INTEGER REFERENCES sales.customers(id),
    quote_id INTEGER REFERENCES sales.quotes(id),
    start_date DATE,
    end_date DATE,
    contract_value DECIMAL(15,2),
    payment_terms VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    signed_date DATE
);

-- HR SCHEMA
CREATE TABLE hr.departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    manager_id INTEGER,
    budget DECIMAL(12,2),
    location VARCHAR(100)
);

CREATE TABLE hr.employees (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(20),
    department_id INTEGER REFERENCES hr.departments(id),
    position VARCHAR(100),
    salary DECIMAL(12,2),
    hire_date DATE,
    manager_id INTEGER REFERENCES hr.employees(id),
    employment_status VARCHAR(20) DEFAULT 'active',
    address TEXT,
    birth_date DATE
);

CREATE TABLE hr.performance_reviews (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES hr.employees(id),
    review_period VARCHAR(20),
    reviewer_id INTEGER REFERENCES hr.employees(id),
    overall_rating INTEGER CHECK (overall_rating >= 1 AND overall_rating <= 5),
    goals_met INTEGER CHECK (goals_met >= 0 AND goals_met <= 100),
    comments TEXT,
    review_date DATE,
    next_review_date DATE
);

CREATE TABLE hr.time_tracking (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES hr.employees(id),
    work_date DATE,
    hours_worked DECIMAL(4,2),
    overtime_hours DECIMAL(4,2),
    project_code VARCHAR(20),
    description TEXT,
    approved BOOLEAN DEFAULT false
);

-- FINANCE SCHEMA
CREATE TABLE finance.accounts (
    id SERIAL PRIMARY KEY,
    account_code VARCHAR(20) UNIQUE NOT NULL,
    account_name VARCHAR(200) NOT NULL,
    account_type VARCHAR(50),
    parent_account_id INTEGER REFERENCES finance.accounts(id),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE finance.transactions (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(50) UNIQUE NOT NULL,
    account_id INTEGER REFERENCES finance.accounts(id),
    amount DECIMAL(15,2) NOT NULL,
    transaction_type VARCHAR(20) CHECK (transaction_type IN ('debit', 'credit')),
    description TEXT,
    reference VARCHAR(100),
    transaction_date DATE,
    posted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending'
);

CREATE TABLE finance.invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id INTEGER,
    contract_id INTEGER,
    amount DECIMAL(15,2),
    tax_amount DECIMAL(15,2),
    total_amount DECIMAL(15,2),
    invoice_date DATE,
    due_date DATE,
    payment_status VARCHAR(20) DEFAULT 'unpaid',
    payment_date DATE
);

CREATE TABLE finance.payments (
    id SERIAL PRIMARY KEY,
    payment_id VARCHAR(50) UNIQUE NOT NULL,
    invoice_id INTEGER REFERENCES finance.invoices(id),
    amount DECIMAL(15,2),
    payment_method VARCHAR(50),
    payment_date DATE,
    reference VARCHAR(100),
    status VARCHAR(20) DEFAULT 'completed'
);

-- INVENTORY SCHEMA
CREATE TABLE inventory.warehouses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    address TEXT,
    city VARCHAR(100),
    country VARCHAR(100),
    capacity INTEGER,
    manager_id INTEGER
);

CREATE TABLE inventory.product_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES inventory.product_categories(id)
);

CREATE TABLE inventory.products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category_id INTEGER REFERENCES inventory.product_categories(id),
    cost_price DECIMAL(10,2),
    selling_price DECIMAL(10,2),
    weight DECIMAL(8,3),
    dimensions VARCHAR(50),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE inventory.stock_levels (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES inventory.products(id),
    warehouse_id INTEGER REFERENCES inventory.warehouses(id),
    quantity_on_hand INTEGER DEFAULT 0,
    reserved_quantity INTEGER DEFAULT 0,
    reorder_point INTEGER DEFAULT 0,
    max_stock_level INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory.stock_movements (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES inventory.products(id),
    warehouse_id INTEGER REFERENCES inventory.warehouses(id),
    movement_type VARCHAR(20) CHECK (movement_type IN ('in', 'out', 'transfer', 'adjustment')),
    quantity INTEGER NOT NULL,
    reference VARCHAR(100),
    notes TEXT,
    movement_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100)
);

-- ANALYTICS SCHEMA
CREATE TABLE analytics.sales_metrics (
    id SERIAL PRIMARY KEY,
    metric_date DATE,
    total_sales DECIMAL(15,2),
    total_orders INTEGER,
    average_order_value DECIMAL(10,2),
    new_customers INTEGER,
    returning_customers INTEGER,
    conversion_rate DECIMAL(5,4)
);

CREATE TABLE analytics.customer_segments (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER,
    segment_name VARCHAR(100),
    segment_score DECIMAL(8,4),
    last_purchase_date DATE,
    total_spent DECIMAL(15,2),
    purchase_frequency INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE analytics.product_performance (
    id SERIAL PRIMARY KEY,
    product_id INTEGER,
    period_start DATE,
    period_end DATE,
    units_sold INTEGER,
    revenue DECIMAL(15,2),
    profit_margin DECIMAL(5,4),
    return_rate DECIMAL(5,4),
    customer_rating DECIMAL(3,2)
);

-- Insert sample data for testing
INSERT INTO sales.customers (customer_code, company_name, contact_person, email, city, country, industry, credit_limit) VALUES
('CUST001', 'TechCorp Inc', 'John Smith', 'john@techcorp.com', 'San Francisco', 'USA', 'Technology', 100000.00),
('CUST002', 'Global Solutions Ltd', 'Sarah Johnson', 'sarah@globalsol.com', 'London', 'UK', 'Consulting', 75000.00),
('CUST003', 'Manufacturing Plus', 'Carlos Rodriguez', 'carlos@manplus.com', 'Barcelona', 'Spain', 'Manufacturing', 150000.00);

INSERT INTO sales.sales_reps (employee_id, first_name, last_name, email, territory, commission_rate, hire_date) VALUES
('REP001', 'Mike', 'Wilson', 'mike.wilson@company.com', 'North America', 0.05, '2023-01-15'),
('REP002', 'Emma', 'Davis', 'emma.davis@company.com', 'Europe', 0.045, '2023-03-10'),
('REP003', 'David', 'Chen', 'david.chen@company.com', 'Asia Pacific', 0.055, '2023-02-20');

INSERT INTO hr.departments (name, description, budget, location) VALUES
('Sales', 'Revenue generation and customer acquisition', 500000.00, 'New York'),
('Engineering', 'Product development and technical innovation', 800000.00, 'San Francisco'),
('Marketing', 'Brand promotion and market research', 300000.00, 'Chicago'),
('Finance', 'Financial planning and accounting', 200000.00, 'New York'),
('Human Resources', 'Employee management and development', 150000.00, 'Austin');

INSERT INTO hr.employees (employee_id, first_name, last_name, email, department_id, position, salary, hire_date) VALUES
('EMP001', 'Alice', 'Johnson', 'alice.johnson@company.com', 1, 'Sales Manager', 85000.00, '2022-05-15'),
('EMP002', 'Bob', 'Smith', 'bob.smith@company.com', 2, 'Senior Developer', 95000.00, '2021-08-20'),
('EMP003', 'Carol', 'Brown', 'carol.brown@company.com', 3, 'Marketing Director', 100000.00, '2020-03-10'),
('EMP004', 'Daniel', 'Wilson', 'daniel.wilson@company.com', 4, 'Financial Analyst', 70000.00, '2023-01-05');

INSERT INTO inventory.warehouses (name, address, city, country, capacity) VALUES
('Main Warehouse', '123 Industrial Ave', 'Los Angeles', 'USA', 10000),
('European Hub', '456 Logistics St', 'Hamburg', 'Germany', 8000),
('Asia Pacific Center', '789 Trade Blvd', 'Singapore', 'Singapore', 6000);

INSERT INTO inventory.product_categories (name, description) VALUES
('Electronics', 'Electronic components and devices'),
('Software', 'Software products and licenses'),
('Services', 'Professional and consulting services'),
('Hardware', 'Physical computing hardware');

-- Create indexes for performance
CREATE INDEX idx_customers_code ON sales.customers(customer_code);
CREATE INDEX idx_customers_active ON sales.customers(is_active);
CREATE INDEX idx_employees_dept ON hr.employees(department_id);
CREATE INDEX idx_employees_status ON hr.employees(employment_status);
CREATE INDEX idx_transactions_date ON finance.transactions(transaction_date);
CREATE INDEX idx_stock_product ON inventory.stock_levels(product_id);
CREATE INDEX idx_stock_warehouse ON inventory.stock_levels(warehouse_id);

-- Add table comments for AI understanding
COMMENT ON SCHEMA sales IS 'Customer relationship management and sales data';
COMMENT ON SCHEMA hr IS 'Human resources and employee management';
COMMENT ON SCHEMA finance IS 'Financial transactions and accounting';
COMMENT ON SCHEMA inventory IS 'Product inventory and warehouse management';
COMMENT ON SCHEMA analytics IS 'Business intelligence and analytics data';

COMMENT ON TABLE sales.customers IS 'Customer master data and contact information';
COMMENT ON TABLE sales.opportunities IS 'Sales pipeline and opportunity tracking';
COMMENT ON TABLE hr.employees IS 'Employee information and organizational structure';
COMMENT ON TABLE finance.transactions IS 'Financial transaction records';
COMMENT ON TABLE inventory.products IS 'Product catalog and specifications';
COMMENT ON TABLE inventory.stock_levels IS 'Current inventory levels by warehouse';