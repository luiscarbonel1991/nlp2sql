-- nlp2sql Test Database Schema
-- Expanded e-commerce example for local integration and semantic validation

-- Store dimension
CREATE TABLE stores (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    domain VARCHAR(120) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    region VARCHAR(100) NOT NULL,
    country VARCHAR(100) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Marketing channel dimension
CREATE TABLE marketing_channels (
    id SERIAL PRIMARY KEY,
    channel_name VARCHAR(100) NOT NULL,
    source_category VARCHAR(100) NOT NULL,
    traffic_type VARCHAR(50) NOT NULL,
    is_paid BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true
);

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    city VARCHAR(100),
    country VARCHAR(100),
    region VARCHAR(100),
    customer_segment VARCHAR(50) DEFAULT 'standard',
    preferred_store_id INTEGER REFERENCES stores(id)
);

-- Categories table
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES categories(id),
    is_active BOOLEAN DEFAULT true
);

-- Products table
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    brand VARCHAR(100) NOT NULL,
    product_line VARCHAR(100),
    price DECIMAL(10,2) NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    stock_quantity INTEGER DEFAULT 0,
    sku VARCHAR(50) UNIQUE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orders table
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    store_id INTEGER REFERENCES stores(id),
    channel_id INTEGER REFERENCES marketing_channels(id),
    total_amount DECIMAL(10,2) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shipping_address TEXT,
    payment_method VARCHAR(50),
    promo_code VARCHAR(50),
    notes TEXT
);

-- Order items table
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(10,2) NOT NULL
);

-- Reviews table
CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    user_id INTEGER REFERENCES users(id),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    title VARCHAR(200),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_verified BOOLEAN DEFAULT false
);

-- Daily aggregate table used to test business-aware table selection
CREATE TABLE daily_channel_metrics (
    metric_date DATE NOT NULL,
    store_id INTEGER REFERENCES stores(id),
    channel_id INTEGER REFERENCES marketing_channels(id),
    sessions INTEGER NOT NULL,
    add_to_cart_sessions INTEGER NOT NULL,
    checkout_sessions INTEGER NOT NULL,
    orders_count INTEGER NOT NULL,
    revenue DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (metric_date, store_id, channel_id)
);

-- Seed stores
INSERT INTO stores (code, domain, name, region, country, currency, is_active) VALUES
('na_flagship', 'demo-flagship.com', 'Demo Flagship', 'North America', 'United States', 'USD', true),
('eu_boutique', 'demo-boutique.eu', 'Demo Boutique Europe', 'Europe', 'Germany', 'EUR', true),
('ca_outlet', 'demo-outlet.ca', 'Demo Outlet Canada', 'North America', 'Canada', 'CAD', true);

-- Seed channels
INSERT INTO marketing_channels (channel_name, source_category, traffic_type, is_paid, is_active) VALUES
('Email', 'Email', 'owned', false, true),
('Organic Search', 'Organic Search', 'organic', false, true),
('Paid Search', 'Paid Search', 'paid', true, true),
('Paid Social', 'Paid Social', 'paid', true, true),
('Affiliate', 'Affiliate', 'partner', false, true);

-- Seed users
INSERT INTO users (
    email, first_name, last_name, phone, city, country, region,
    is_active, customer_segment, preferred_store_id
) VALUES
('john.doe@email.com', 'John', 'Doe', '+1234567890', 'New York', 'United States', 'North America', true, 'vip', 1),
('jane.smith@email.com', 'Jane', 'Smith', '+1234567891', 'Berlin', 'Germany', 'Europe', true, 'standard', 2),
('carlos.garcia@email.com', 'Carlos', 'Garcia', '+1234567892', 'Toronto', 'Canada', 'North America', true, 'growth', 3),
('anna.muller@email.com', 'Anna', 'Muller', '+1234567893', 'Munich', 'Germany', 'Europe', true, 'vip', 2),
('mike.johnson@email.com', 'Mike', 'Johnson', '+1234567894', 'Chicago', 'United States', 'North America', false, 'standard', 1),
('lisa.wong@email.com', 'Lisa', 'Wong', '+1234567895', 'Vancouver', 'Canada', 'North America', true, 'growth', 3),
('omar.hassan@email.com', 'Omar', 'Hassan', '+1234567896', 'Austin', 'United States', 'North America', true, 'vip', 1),
('sofia.rossi@email.com', 'Sofia', 'Rossi', '+1234567897', 'Hamburg', 'Germany', 'Europe', true, 'standard', 2);

-- Seed categories
INSERT INTO categories (name, description, is_active) VALUES
('Electronics', 'Electronic devices and gadgets', true),
('Books', 'Physical and digital books', true),
('Clothing', 'Fashion and apparel', true),
('Home & Garden', 'Home improvement and garden supplies', true),
('Sports', 'Sports equipment and accessories', true);

-- Seed products
INSERT INTO products (
    name, description, brand, product_line, price, category_id,
    stock_quantity, sku, is_active
) VALUES
('Laptop Pro 15"', 'High-performance laptop for professionals', 'Northwind', 'Pro Computing', 1299.99, 1, 25, 'LAPTOP-PRO-15', true),
('Wireless Headphones', 'Noise-cancelling wireless headphones', 'Northwind', 'Audio Plus', 299.99, 1, 50, 'WH-NC-001', true),
('Programming Guide', 'Complete guide to modern programming', 'PageTurner', 'Developer Library', 49.99, 2, 100, 'BOOK-PROG-001', true),
('Cotton T-Shirt', 'Comfortable cotton t-shirt', 'Evergreen', 'Core Basics', 19.99, 3, 200, 'TSHIRT-COT-001', true),
('Running Shoes', 'Professional running shoes', 'Evergreen', 'Motion', 129.99, 5, 75, 'SHOES-RUN-001', true),
('Garden Tool Set', 'Complete garden tool set', 'HomeCraft', 'Outdoor Living', 89.99, 4, 30, 'GARDEN-TOOLS-001', true),
('Smartphone', 'Latest smartphone with advanced features', 'Northwind', 'Mobile X', 899.99, 1, 40, 'PHONE-ADV-001', true),
('Cooking Book', 'International cooking recipes', 'PageTurner', 'Kitchen Stories', 29.99, 2, 60, 'BOOK-COOK-001', true),
('Fitness Tracker', 'Wearable tracker for active customers', 'Northwind', 'Motion', 199.99, 5, 90, 'TRACKER-FIT-001', true),
('Premium Hoodie', 'Heavyweight premium hoodie', 'Evergreen', 'Core Basics', 59.99, 3, 120, 'HOODIE-PREM-001', true);

-- Seed orders
INSERT INTO orders (
    user_id, store_id, channel_id, total_amount, discount_amount,
    status, order_date, shipping_address, payment_method, promo_code
) VALUES
(1, 1, 3, 1349.98, 0.00, 'completed', '2024-01-15 10:30:00', '123 Main St, New York, NY', 'credit_card', NULL),
(2, 2, 1, 319.98, 20.00, 'shipped', '2024-01-16 14:20:00', '456 Oak Ave, Berlin, Germany', 'paypal', 'WELCOME20'),
(3, 3, 2, 49.99, 0.00, 'completed', '2024-01-17 09:15:00', '789 Pine St, Toronto, Canada', 'credit_card', NULL),
(1, 1, 4, 149.98, 10.00, 'completed', '2024-01-18 16:45:00', '123 Main St, New York, NY', 'debit_card', 'SOCIAL10'),
(4, 2, 3, 929.98, 0.00, 'processing', '2024-01-19 11:30:00', '321 Elm St, Munich, Germany', 'credit_card', NULL),
(6, 3, 5, 219.98, 0.00, 'completed', '2024-01-19 18:20:00', '654 Queen St, Vancouver, Canada', 'credit_card', NULL),
(7, 1, 2, 199.99, 0.00, 'completed', '2024-01-20 08:05:00', '987 Lake Ave, Austin, TX', 'paypal', NULL),
(8, 2, 4, 79.98, 5.00, 'pending', '2024-01-20 12:10:00', '741 Birch Rd, Hamburg, Germany', 'credit_card', 'NEW5'),
(1, 1, 1, 59.99, 0.00, 'completed', '2024-01-21 09:25:00', '123 Main St, New York, NY', 'credit_card', NULL),
(3, 3, 2, 899.99, 50.00, 'completed', '2024-01-21 16:00:00', '789 Pine St, Toronto, Canada', 'bank_transfer', 'SEARCH50'),
(2, 2, 3, 259.98, 0.00, 'completed', '2024-01-22 10:45:00', '456 Oak Ave, Berlin, Germany', 'credit_card', NULL),
(7, 1, 4, 159.98, 0.00, 'completed', '2024-01-22 15:35:00', '987 Lake Ave, Austin, TX', 'paypal', NULL);

-- Seed order items
INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price) VALUES
(1, 1, 1, 1299.99, 1299.99),
(1, 3, 1, 49.99, 49.99),
(2, 2, 1, 299.99, 299.99),
(2, 4, 1, 19.99, 19.99),
(3, 3, 1, 49.99, 49.99),
(4, 5, 1, 129.99, 129.99),
(4, 4, 1, 19.99, 19.99),
(5, 7, 1, 899.99, 899.99),
(5, 8, 1, 29.99, 29.99),
(6, 9, 1, 199.99, 199.99),
(6, 8, 1, 29.99, 29.99),
(7, 9, 1, 199.99, 199.99),
(8, 4, 1, 19.99, 19.99),
(8, 8, 2, 29.99, 59.98),
(9, 10, 1, 59.99, 59.99),
(10, 7, 1, 899.99, 899.99),
(11, 2, 1, 299.99, 299.99),
(11, 8, 1, 29.99, 29.99),
(12, 5, 1, 129.99, 129.99),
(12, 4, 1, 19.99, 19.99);

-- Seed reviews
INSERT INTO reviews (product_id, user_id, rating, title, comment, is_verified) VALUES
(1, 1, 5, 'Excellent laptop!', 'Great performance and build quality. Highly recommended for professionals.', true),
(2, 2, 4, 'Good headphones', 'Sound quality is great, but could be more comfortable for long use.', true),
(3, 3, 5, 'Very helpful book', 'Clear explanations and practical examples. Perfect for beginners.', true),
(4, 1, 3, 'Average quality', 'The fabric is okay but not as soft as expected.', false),
(5, 4, 5, 'Perfect running shoes', 'Comfortable and durable. Great for daily running.', true),
(9, 6, 4, 'Helpful tracker', 'Solid activity tracking and battery life.', true),
(10, 7, 5, 'Great hoodie', 'Warm, premium feel, and true to size.', true);

-- Seed daily aggregate facts
INSERT INTO daily_channel_metrics (
    metric_date, store_id, channel_id, sessions, add_to_cart_sessions,
    checkout_sessions, orders_count, revenue
) VALUES
('2024-01-15', 1, 3, 320, 74, 45, 18, 3150.00),
('2024-01-15', 1, 4, 280, 61, 36, 14, 2210.00),
('2024-01-16', 1, 1, 190, 42, 27, 11, 980.00),
('2024-01-16', 2, 1, 150, 30, 20, 9, 720.00),
('2024-01-17', 3, 2, 210, 39, 25, 10, 860.00),
('2024-01-18', 1, 4, 295, 68, 40, 15, 2445.00),
('2024-01-19', 2, 3, 260, 55, 33, 13, 2010.00),
('2024-01-19', 3, 5, 130, 22, 15, 7, 560.00),
('2024-01-20', 1, 2, 240, 48, 30, 12, 1180.00),
('2024-01-20', 2, 4, 205, 36, 24, 8, 760.00),
('2024-01-21', 1, 1, 215, 44, 28, 12, 1040.00),
('2024-01-21', 3, 2, 225, 43, 27, 11, 990.00),
('2024-01-22', 2, 3, 270, 59, 35, 14, 2140.00),
('2024-01-22', 1, 4, 305, 72, 44, 16, 2580.00);

-- Create indexes for better query performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active);
CREATE INDEX idx_users_store ON users(preferred_store_id);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_store_id ON orders(store_id);
CREATE INDEX idx_orders_channel_id ON orders(channel_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_brand ON products(brand);
CREATE INDEX idx_products_active ON products(is_active);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_reviews_product ON reviews(product_id);
CREATE INDEX idx_reviews_user ON reviews(user_id);
CREATE INDEX idx_daily_channel_metrics_store_date ON daily_channel_metrics(store_id, metric_date);
CREATE INDEX idx_daily_channel_metrics_channel_date ON daily_channel_metrics(channel_id, metric_date);

-- Create views for richer reporting examples
CREATE VIEW order_summaries AS
SELECT
    o.id AS order_id,
    s.code AS store_code,
    s.domain AS store_domain,
    s.region,
    s.country,
    mc.channel_name,
    mc.source_category,
    u.first_name || ' ' || u.last_name AS customer_name,
    u.email AS customer_email,
    o.total_amount,
    o.discount_amount,
    o.status,
    o.order_date,
    COUNT(oi.id) AS item_count
FROM orders o
JOIN users u ON o.user_id = u.id
JOIN stores s ON o.store_id = s.id
JOIN marketing_channels mc ON o.channel_id = mc.id
LEFT JOIN order_items oi ON o.id = oi.order_id
GROUP BY
    o.id, s.code, s.domain, s.region, s.country,
    mc.channel_name, mc.source_category,
    u.first_name, u.last_name, u.email,
    o.total_amount, o.discount_amount, o.status, o.order_date;

CREATE VIEW store_channel_sales AS
SELECT
    DATE(o.order_date) AS metric_date,
    s.code AS store_code,
    s.region,
    s.country,
    mc.source_category,
    COUNT(DISTINCT o.id) AS orders_count,
    ROUND(SUM(o.total_amount)::numeric, 2) AS revenue
FROM orders o
JOIN stores s ON o.store_id = s.id
JOIN marketing_channels mc ON o.channel_id = mc.id
GROUP BY DATE(o.order_date), s.code, s.region, s.country, mc.source_category;

-- Add comments for AI understanding
COMMENT ON TABLE stores IS 'Storefront dimension with business region and country metadata';
COMMENT ON TABLE marketing_channels IS 'Marketing channel dimension with business source categories and paid vs non-paid classification';
COMMENT ON TABLE users IS 'Customer information, region, segment, and preferred storefront';
COMMENT ON TABLE products IS 'Product catalog with brand, category, inventory and pricing';
COMMENT ON TABLE orders IS 'Transactional orders tied to stores and marketing channels';
COMMENT ON TABLE order_items IS 'Individual items within each order';
COMMENT ON TABLE reviews IS 'Product reviews and ratings from customers';
COMMENT ON TABLE categories IS 'Product categorization hierarchy';
COMMENT ON TABLE daily_channel_metrics IS 'Daily aggregated ecommerce funnel and revenue metrics by store and marketing channel';