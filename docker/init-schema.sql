-- nlp2sql Test Database Schema
-- Simple e-commerce example for testing SQL generation

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
    country VARCHAR(100)
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
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shipping_address TEXT,
    payment_method VARCHAR(50),
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

-- Insert sample data
INSERT INTO users (email, first_name, last_name, phone, city, country, is_active) VALUES
('john.doe@email.com', 'John', 'Doe', '+1234567890', 'New York', 'USA', true),
('jane.smith@email.com', 'Jane', 'Smith', '+1234567891', 'London', 'UK', true),
('carlos.garcia@email.com', 'Carlos', 'Garcia', '+1234567892', 'Madrid', 'Spain', true),
('anna.muller@email.com', 'Anna', 'Muller', '+1234567893', 'Berlin', 'Germany', true),
('mike.johnson@email.com', 'Mike', 'Johnson', '+1234567894', 'Toronto', 'Canada', false);

INSERT INTO categories (name, description, is_active) VALUES
('Electronics', 'Electronic devices and gadgets', true),
('Books', 'Physical and digital books', true),
('Clothing', 'Fashion and apparel', true),
('Home & Garden', 'Home improvement and garden supplies', true),
('Sports', 'Sports equipment and accessories', true);

INSERT INTO products (name, description, price, category_id, stock_quantity, sku, is_active) VALUES
('Laptop Pro 15"', 'High-performance laptop for professionals', 1299.99, 1, 25, 'LAPTOP-PRO-15', true),
('Wireless Headphones', 'Noise-cancelling wireless headphones', 299.99, 1, 50, 'WH-NC-001', true),
('Programming Guide', 'Complete guide to modern programming', 49.99, 2, 100, 'BOOK-PROG-001', true),
('Cotton T-Shirt', 'Comfortable cotton t-shirt', 19.99, 3, 200, 'TSHIRT-COT-001', true),
('Running Shoes', 'Professional running shoes', 129.99, 5, 75, 'SHOES-RUN-001', true),
('Garden Tool Set', 'Complete garden tool set', 89.99, 4, 30, 'GARDEN-TOOLS-001', true),
('Smartphone', 'Latest smartphone with advanced features', 899.99, 1, 40, 'PHONE-ADV-001', true),
('Cooking Book', 'International cooking recipes', 29.99, 2, 60, 'BOOK-COOK-001', true);

INSERT INTO orders (user_id, total_amount, status, order_date, shipping_address, payment_method) VALUES
(1, 1349.98, 'completed', '2024-01-15 10:30:00', '123 Main St, New York, NY', 'credit_card'),
(2, 319.98, 'shipped', '2024-01-16 14:20:00', '456 Oak Ave, London, UK', 'paypal'),
(3, 49.99, 'completed', '2024-01-17 09:15:00', '789 Pine St, Madrid, Spain', 'credit_card'),
(1, 149.98, 'pending', '2024-01-18 16:45:00', '123 Main St, New York, NY', 'debit_card'),
(4, 929.98, 'processing', '2024-01-19 11:30:00', '321 Elm St, Berlin, Germany', 'credit_card');

INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price) VALUES
(1, 1, 1, 1299.99, 1299.99),
(1, 4, 2, 19.99, 39.98),
(1, 3, 1, 49.99, 49.99),
(2, 2, 1, 299.99, 299.99),
(2, 4, 1, 19.99, 19.99),
(3, 3, 1, 49.99, 49.99),
(4, 5, 1, 129.99, 129.99),
(4, 4, 1, 19.99, 19.99),
(5, 7, 1, 899.99, 899.99),
(5, 8, 1, 29.99, 29.99);

INSERT INTO reviews (product_id, user_id, rating, title, comment, is_verified) VALUES
(1, 1, 5, 'Excellent laptop!', 'Great performance and build quality. Highly recommended for professionals.', true),
(2, 2, 4, 'Good headphones', 'Sound quality is great, but could be more comfortable for long use.', true),
(3, 3, 5, 'Very helpful book', 'Clear explanations and practical examples. Perfect for beginners.', true),
(4, 1, 3, 'Average quality', 'The fabric is okay but not as soft as expected.', false),
(5, 4, 5, 'Perfect running shoes', 'Comfortable and durable. Great for daily running.', true);

-- Create indexes for better query performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_active ON products(is_active);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_reviews_product ON reviews(product_id);
CREATE INDEX idx_reviews_user ON reviews(user_id);

-- Create a view for order summaries
CREATE VIEW order_summaries AS
SELECT 
    o.id as order_id,
    u.first_name || ' ' || u.last_name as customer_name,
    u.email as customer_email,
    o.total_amount,
    o.status,
    o.order_date,
    COUNT(oi.id) as item_count
FROM orders o
JOIN users u ON o.user_id = u.id
LEFT JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id, u.first_name, u.last_name, u.email, o.total_amount, o.status, o.order_date;

-- Add some comments for AI understanding
COMMENT ON TABLE users IS 'Customer information and user accounts';
COMMENT ON TABLE products IS 'Product catalog with inventory and pricing';
COMMENT ON TABLE orders IS 'Customer orders with status and payment info';
COMMENT ON TABLE order_items IS 'Individual items within each order';
COMMENT ON TABLE reviews IS 'Product reviews and ratings from customers';
COMMENT ON TABLE categories IS 'Product categorization hierarchy';