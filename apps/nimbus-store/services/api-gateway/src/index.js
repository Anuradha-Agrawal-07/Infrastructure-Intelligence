const express = require('express');
const cors = require('cors');
const { createProxyMiddleware } = require('http-proxy-middleware');

const SERVICE_NAME = 'api-gateway';
const PORT = process.env.PORT || 8080;
const PRODUCT_SERVICE_URL = process.env.PRODUCT_SERVICE_URL || 'http://product-service:4001';
const ORDER_SERVICE_URL = process.env.ORDER_SERVICE_URL || 'http://order-service:4002';

const app = express();
app.use(cors());

app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    console.log(
      `[${SERVICE_NAME}] ${req.method} ${req.originalUrl} -> ${res.statusCode} (${Date.now() - start}ms)`
    );
  });
  next();
});

// Gateway's own liveness check.
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: SERVICE_NAME, timestamp: new Date().toISOString() });
});

// Deep health check: gateway asks each downstream service directly.
// This is real service-to-service traffic and a preview of what a
// future discovery/monitoring layer would automate across many services.
app.get('/health/deep', async (req, res) => {
  const check = async (name, url) => {
    try {
      const r = await fetch(`${url}/health`, { signal: AbortSignal.timeout(3000) });
      const body = await r.json().catch(() => ({}));
      return { service: name, url, reachable: r.ok, ...body };
    } catch (err) {
      return { service: name, url, reachable: false, error: err.message };
    }
  };

  const [productHealth, orderHealth] = await Promise.all([
    check('product-service', PRODUCT_SERVICE_URL),
    check('order-service', ORDER_SERVICE_URL),
  ]);

  const allUp = productHealth.reachable && orderHealth.reachable;
  res.status(allUp ? 200 : 503).json({
    status: allUp ? 'ok' : 'degraded',
    service: SERVICE_NAME,
    dependencies: [productHealth, orderHealth],
    timestamp: new Date().toISOString(),
  });
});

app.get('/info', (req, res) => {
  res.json({
    service: SERVICE_NAME,
    version: '1.0.0',
    routes: {
      '/api/products*': PRODUCT_SERVICE_URL,
      '/api/orders*': ORDER_SERVICE_URL,
    },
  });
});

// Proxy everything under /api/products to product-service, and
// everything under /api/orders to order-service. The frontend never
// talks to those services directly - the gateway is the only public door.
app.use(
  '/api/products',
  createProxyMiddleware({
    target: PRODUCT_SERVICE_URL,
    changeOrigin: true,
    pathRewrite: { '^/api/products': '/products' },
  })
);

app.use(
  '/api/orders',
  createProxyMiddleware({
    target: ORDER_SERVICE_URL,
    changeOrigin: true,
    pathRewrite: { '^/api/orders': '/orders' },
  })
);

app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

app.listen(PORT, () => {
  console.log(`[${SERVICE_NAME}] listening on port ${PORT}`);
  console.log(`[${SERVICE_NAME}] -> product-service: ${PRODUCT_SERVICE_URL}`);
  console.log(`[${SERVICE_NAME}] -> order-service:   ${ORDER_SERVICE_URL}`);
});
