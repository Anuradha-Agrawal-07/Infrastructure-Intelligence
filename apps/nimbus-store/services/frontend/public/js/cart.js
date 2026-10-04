// Cart lives entirely client-side (localStorage). Only checkout talks
// to the backend, via order-service through the gateway.
const Cart = {
  KEY: 'ii_demo_cart',

  read() {
    try {
      return JSON.parse(localStorage.getItem(this.KEY)) || [];
    } catch {
      return [];
    }
  },

  write(items) {
    localStorage.setItem(this.KEY, JSON.stringify(items));
    this.updateBadge();
  },

  add(product, quantity) {
    const items = this.read();
    const existing = items.find((i) => i.product_id === product.id);
    if (existing) {
      existing.quantity += quantity;
    } else {
      items.push({
        product_id: product.id,
        name: product.name,
        emoji: product.image_emoji,
        price_cents: product.price_cents,
        quantity,
      });
    }
    this.write(items);
  },

  setQuantity(productId, quantity) {
    let items = this.read();
    if (quantity <= 0) {
      items = items.filter((i) => i.product_id !== productId);
    } else {
      const item = items.find((i) => i.product_id === productId);
      if (item) item.quantity = quantity;
    }
    this.write(items);
  },

  remove(productId) {
    this.write(this.read().filter((i) => i.product_id !== productId));
  },

  clear() {
    this.write([]);
  },

  count() {
    return this.read().reduce((sum, i) => sum + i.quantity, 0);
  },

  totalCents() {
    return this.read().reduce((sum, i) => sum + i.quantity * i.price_cents, 0);
  },

  updateBadge() {
    const el = document.getElementById('cart-count');
    if (el) el.textContent = this.count();
  },
};

document.addEventListener('DOMContentLoaded', () => Cart.updateBadge());
