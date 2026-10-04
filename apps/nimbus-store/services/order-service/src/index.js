const express = require('express');
const cors = require('cors');
const { pool } = require('./db');
const productClient = require('./productClient');

const SERVICE_NAME = 'order-service';
const PORT = process.env.PORT || 4002;

const app = express();
app.use(cors());
app.use(express.json());

app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    console.log(
      `[${SERVICE_NAME}] ${req.method} ${req.originalUrl} -> ${res.statusCode} (${Date.now() - start}ms)`
    );
  });
  next();
});

app.get('/health', async (req, res) => {
  try {
    await pool.query('SELECT 1');
    const productServiceUp = await productClient.checkHealth();
    res.json({
      status: 'ok',
      service: SERVICE_NAME,
      db: 'ok',
      dependencies: { 'product-service': productServiceUp ? 'ok' : 'unreachable' },
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    res.status(503).json({ status: 'error', service: SERVICE_NAME, db: 'unreachable', error: err.message });
  }
});

app.get('/info', (req, res) => {
  res.json({ service: SERVICE_NAME, version: '1.0.0' });
});

app.get('/orders', async (req, res) => {
  try {
    const orders = await pool.query('SELECT * FROM orders ORDER BY created_at DESC');
    res.json(orders.rows);
  } catch (err) {
    console.error(`[${SERVICE_NAME}] Error fetching orders:`, err.message);
    res.status(500).json({ error: 'Failed to fetch orders' });
  }
});

app.get('/orders/:id', async (req, res) => {
  try {
    const order = await pool.query('SELECT * FROM orders WHERE id = $1', [req.params.id]);
    if (order.rows.length === 0) {
      return res.status(404).json({ error: 'Order not found' });
    }
    const items = await pool.query('SELECT * FROM order_items WHERE order_id = $1', [req.params.id]);
    res.json({ ...order.rows[0], items: items.rows });
  } catch (err) {
    console.error(`[${SERVICE_NAME}] Error fetching order ${req.params.id}:`, err.message);
    res.status(500).json({ error: 'Failed to fetch order' });
  }
});

// Placing an order is the clearest example of real cross-service work:
// 1. Look up each product on product-service (price, existence).
// 2. Reserve stock on product-service for each item (decrement over HTTP).
// 3. Persist the order + line items in this service's own tables.
// If step 3 fails after stock was already reserved, we compensate by
// restoring the stock we took, rather than leaving things inconsistent.
app.post('/orders', async (req, res) => {
  const { customer_name, customer_email, items } = req.body;

  if (!customer_name || !customer_email || !Array.isArray(items) || items.length === 0) {
    return res.status(400).json({ error: 'customer_name, customer_email and a non-empty items array are required' });
  }
  for (const item of items) {
    if (!item.product_id || !Number.isInteger(item.quantity) || item.quantity <= 0) {
      return res.status(400).json({ error: 'Each item needs product_id and a positive integer quantity' });
    }
  }

  const resolvedItems = [];
  try {
    for (const item of items) {
      const product = await productClient.getProduct(item.product_id);
      if (!product) {
        return res.status(404).json({ error: `Product ${item.product_id} not found` });
      }
      resolvedItems.push({
        product_id: product.id,
        product_name: product.name,
        unit_price_cents: product.price_cents,
        quantity: item.quantity,
      });
    }
  } catch (err) {
    console.error(`[${SERVICE_NAME}] Error contacting product-service:`, err.message);
    return res.status(502).json({ error: 'Could not reach product-service to validate items' });
  }

  const reserved = [];
  try {
    for (const item of resolvedItems) {
      await productClient.adjustStock(item.product_id, -item.quantity);
      reserved.push(item);
    }
  } catch (err) {
    // Roll back any stock we already reserved before this one failed.
    for (const item of reserved) {
      try {
        await productClient.adjustStock(item.product_id, item.quantity);
      } catch (compErr) {
        console.error(`[${SERVICE_NAME}] Failed to compensate stock for product ${item.product_id}:`, compErr.message);
      }
    }
    if (err.status === 409) {
      return res.status(409).json({ error: err.body.error, product_id: err.body });
    }
    console.error(`[${SERVICE_NAME}] Error reserving stock:`, err.message);
    return res.status(502).json({ error: 'Failed to reserve stock on product-service' });
  }

  const totalCents = resolvedItems.reduce((sum, i) => sum + i.unit_price_cents * i.quantity, 0);

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const orderResult = await client.query(
      'INSERT INTO orders (customer_name, customer_email, status, total_cents) VALUES ($1, $2, $3, $4) RETURNING *',
      [customer_name, customer_email, 'confirmed', totalCents]
    );
    const order = orderResult.rows[0];

    for (const item of resolvedItems) {
      await client.query(
        'INSERT INTO order_items (order_id, product_id, product_name, unit_price_cents, quantity) VALUES ($1, $2, $3, $4, $5)',
        [order.id, item.product_id, item.product_name, item.unit_price_cents, item.quantity]
      );
    }

    await client.query('COMMIT');
    res.status(201).json({ ...order, items: resolvedItems });
  } catch (err) {
    await client.query('ROLLBACK');
    // Order row failed to persist even though stock was already reserved
    // on product-service - compensate to keep the two services consistent.
    for (const item of resolvedItems) {
      try {
        await productClient.adjustStock(item.product_id, item.quantity);
      } catch (compErr) {
        console.error(`[${SERVICE_NAME}] Failed to compensate stock for product ${item.product_id}:`, compErr.message);
      }
    }
    console.error(`[${SERVICE_NAME}] Error saving order:`, err.message);
    res.status(500).json({ error: 'Failed to save order' });
  } finally {
    client.release();
  }
});

app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

app.listen(PORT, () => {
  console.log(`[${SERVICE_NAME}] listening on port ${PORT}, product-service at ${productClient.PRODUCT_SERVICE_URL}`);
});
