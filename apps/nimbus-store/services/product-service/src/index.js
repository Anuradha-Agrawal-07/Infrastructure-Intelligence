const express = require('express');
const cors = require('cors');
const { pool } = require('./db');

const SERVICE_NAME = 'product-service';
const PORT = process.env.PORT || 4001;

const app = express();
app.use(cors());
app.use(express.json());

// --- Basic request log, useful once a monitoring platform is watching ---
app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    console.log(
      `[${SERVICE_NAME}] ${req.method} ${req.originalUrl} -> ${res.statusCode} (${Date.now() - start}ms)`
    );
  });
  next();
});

// --- Health & metadata endpoints (kept uniform across services so a ---
// --- future discovery system can probe every service the same way) ---
app.get('/health', async (req, res) => {
  try {
    await pool.query('SELECT 1');
    res.json({ status: 'ok', service: SERVICE_NAME, db: 'ok', timestamp: new Date().toISOString() });
  } catch (err) {
    res.status(503).json({ status: 'error', service: SERVICE_NAME, db: 'unreachable', error: err.message });
  }
});

app.get('/info', (req, res) => {
  res.json({ service: SERVICE_NAME, version: '1.0.0' });
});

// --- Product catalog ---
app.get('/products', async (req, res) => {
  try {
    const { category } = req.query;
    const result = category
      ? await pool.query('SELECT * FROM products WHERE category = $1 ORDER BY id', [category])
      : await pool.query('SELECT * FROM products ORDER BY id');
    res.json(result.rows);
  } catch (err) {
    console.error(`[${SERVICE_NAME}] Error fetching products:`, err.message);
    res.status(500).json({ error: 'Failed to fetch products' });
  }
});

app.get('/products/:id', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM products WHERE id = $1', [req.params.id]);
    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Product not found' });
    }
    res.json(result.rows[0]);
  } catch (err) {
    console.error(`[${SERVICE_NAME}] Error fetching product ${req.params.id}:`, err.message);
    res.status(500).json({ error: 'Failed to fetch product' });
  }
});

// Internal endpoint used by order-service to reserve/release stock.
// This is real service-to-service traffic: order-service calls this
// over HTTP whenever an order is placed.
app.patch('/products/:id/stock', async (req, res) => {
  const { delta } = req.body; // negative to reserve, positive to restock
  if (typeof delta !== 'number' || !Number.isInteger(delta)) {
    return res.status(400).json({ error: 'delta must be an integer' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const current = await client.query('SELECT stock FROM products WHERE id = $1 FOR UPDATE', [req.params.id]);
    if (current.rows.length === 0) {
      await client.query('ROLLBACK');
      return res.status(404).json({ error: 'Product not found' });
    }

    const newStock = current.rows[0].stock + delta;
    if (newStock < 0) {
      await client.query('ROLLBACK');
      return res.status(409).json({ error: 'Insufficient stock', available: current.rows[0].stock });
    }

    const updated = await client.query(
      'UPDATE products SET stock = $1 WHERE id = $2 RETURNING *',
      [newStock, req.params.id]
    );
    await client.query('COMMIT');
    res.json(updated.rows[0]);
  } catch (err) {
    await client.query('ROLLBACK');
    console.error(`[${SERVICE_NAME}] Error updating stock for ${req.params.id}:`, err.message);
    res.status(500).json({ error: 'Failed to update stock' });
  } finally {
    client.release();
  }
});

app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

app.listen(PORT, () => {
  console.log(`[${SERVICE_NAME}] listening on port ${PORT}`);
});
