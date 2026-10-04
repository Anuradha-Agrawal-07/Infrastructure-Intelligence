-- Infrastructure Intelligence demo store schema

CREATE TABLE IF NOT EXISTS products (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    description  TEXT NOT NULL,
    category     VARCHAR(100) NOT NULL,
    price_cents  INTEGER NOT NULL CHECK (price_cents >= 0),
    stock        INTEGER NOT NULL CHECK (stock >= 0),
    image_emoji  VARCHAR(10) DEFAULT '📦',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    customer_name   VARCHAR(200) NOT NULL,
    customer_email  VARCHAR(200) NOT NULL,
    status          VARCHAR(30) NOT NULL DEFAULT 'confirmed',
    total_cents     INTEGER NOT NULL CHECK (total_cents >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    id             SERIAL PRIMARY KEY,
    order_id       INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id     INTEGER NOT NULL,
    product_name   VARCHAR(200) NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    quantity       INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

INSERT INTO products (name, description, category, price_cents, stock, image_emoji) VALUES
('Wireless Mechanical Keyboard', 'Hot-swappable switches, RGB backlight, USB-C.', 'Electronics', 8999, 42, '⌨️'),
('Noise-Cancelling Headphones', 'Over-ear, 30hr battery, active noise cancellation.', 'Electronics', 14999, 25, '🎧'),
('4K Webcam', '4K30 video, auto-focus, built-in ring light.', 'Electronics', 5999, 60, '📷'),
('Ergonomic Office Chair', 'Adjustable lumbar support, breathable mesh back.', 'Furniture', 24999, 15, '🪑'),
('Standing Desk Converter', 'Sit-stand desktop riser, gas-spring lift.', 'Furniture', 17999, 20, '🖥️'),
('Stainless Steel Water Bottle', 'Insulated, keeps drinks cold for 24 hours.', 'Lifestyle', 2499, 120, '🧴'),
('Ceramic Pour-Over Coffee Set', 'Dripper, server, and 2 mugs.', 'Kitchen', 4499, 35, '☕'),
('Portable Bluetooth Speaker', 'Waterproof, 12hr battery, punchy bass.', 'Electronics', 3999, 80, '🔊'),
('Canvas Weekender Bag', 'Water-resistant canvas, leather trim, 45L.', 'Lifestyle', 8499, 30, '🎒'),
('Smart LED Desk Lamp', 'Adjustable color temperature, app control.', 'Electronics', 3499, 55, '💡'),
('Yoga Mat Pro', 'Non-slip, 6mm thick, carrying strap included.', 'Fitness', 3999, 90, '🧘'),
('Adjustable Dumbbell Set', '5-25kg per dumbbell, quick-change dial.', 'Fitness', 19999, 12, '🏋️');
