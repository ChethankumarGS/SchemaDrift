"""Built-in example pair so the demo works on first load."""

OLD_SQL = """-- v1: production today
CREATE TABLE users (
  id BIGINT PRIMARY KEY,
  email VARCHAR(100) NOT NULL,
  name VARCHAR(80),
  age SMALLINT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE orders (
  id INT PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  total DECIMAL(10,2) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'new',
  notes TEXT
);

CREATE INDEX idx_orders_user ON orders (user_id);

CREATE TABLE legacy_audit (
  id INT PRIMARY KEY,
  payload TEXT
);
"""

NEW_SQL = """-- v2: proposed migration
CREATE TABLE users (
  id BIGINT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  full_name VARCHAR(80),
  age INT,
  phone VARCHAR(20),
  tenant_id INT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_users_email ON users (email);

CREATE TABLE orders (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  total DECIMAL(8,2) NOT NULL,
  status VARCHAR(20) NOT NULL,
  notes TEXT NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'USD'
);

CREATE TABLE invoices (
  id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id)
);
"""
