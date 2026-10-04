// Every request from the browser goes to the api-gateway only.
// The gateway is responsible for routing to product-service / order-service.
const Api = {
  base() {
    return window.API_BASE_URL || 'http://localhost:8080';
  },

  async getProducts(category) {
    const url = new URL(`${this.base()}/api/products`);
    if (category) url.searchParams.set('category', category);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load products (${res.status})`);
    return res.json();
  },

  async getProduct(id) {
    const res = await fetch(`${this.base()}/api/products/${id}`);
    if (!res.ok) throw new Error(`Failed to load product (${res.status})`);
    return res.json();
  },

  async createOrder(payload) {
    const res = await fetch(`${this.base()}/api/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok) {
      const err = new Error(body.error || `Failed to place order (${res.status})`);
      err.body = body;
      throw err;
    }
    return body;
  },

  async getOrders() {
    const res = await fetch(`${this.base()}/api/orders`);
    if (!res.ok) throw new Error(`Failed to load orders (${res.status})`);
    return res.json();
  },

  async getOrder(id) {
    const res = await fetch(`${this.base()}/api/orders/${id}`);
    if (!res.ok) throw new Error(`Failed to load order (${res.status})`);
    return res.json();
  },
};

function formatPrice(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}
