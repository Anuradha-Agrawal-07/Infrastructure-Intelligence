// Thin HTTP client order-service uses to talk to product-service.
// This is the real service-to-service call path: every order placed
// causes order-service to fetch product data and adjust stock on
// product-service over the network.

const PRODUCT_SERVICE_URL = process.env.PRODUCT_SERVICE_URL || 'http://product-service:4001';

async function getProduct(productId) {
  const res = await fetch(`${PRODUCT_SERVICE_URL}/products/${productId}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`product-service returned ${res.status} for product ${productId}`);
  }
  return res.json();
}

async function adjustStock(productId, delta) {
  const res = await fetch(`${PRODUCT_SERVICE_URL}/products/${productId}/stock`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delta }),
  });
  const body = await res.json();
  if (!res.ok) {
    const err = new Error(body.error || `product-service returned ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

async function checkHealth() {
  try {
    const res = await fetch(`${PRODUCT_SERVICE_URL}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

module.exports = { getProduct, adjustStock, checkHealth, PRODUCT_SERVICE_URL };
