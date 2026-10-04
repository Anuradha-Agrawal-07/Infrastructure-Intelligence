# Nimbus Store — Infrastructure Intelligence demo app

A small, real, multi-service e-commerce app. This is **only the target
application** — the thing a future monitoring/observability platform
("Infrastructure Intelligence") will watch. No monitoring, anomaly
detection, correlation, discovery, or failure injection lives here yet.

## Architecture

```
 browser
   │
   ▼
 frontend (Express static server, :3000)
   │  fetch() calls to /api/*
   ▼
 api-gateway (:8080)  ── single public entry point, proxies:
   │  /api/products*  →  product-service
   │  /api/orders*    →  order-service
   ├──────────────────────────┬─────────────────────────┐
   ▼                          ▼                          
 product-service (:4001)   order-service (:4002)
   │  catalog + inventory     │  places/reads orders
   │                          │  calls product-service over
   │                          │  HTTP to validate items and
   │                          │  reserve/release stock
   ▼                          ▼
        postgres (:5432, database "storedb")
```

Real service-to-service traffic: placing an order makes **order-service**
call **product-service** over HTTP to fetch each product's price, reserve
stock (`PATCH /products/:id/stock`), and roll the stock back if the order
can't be completed. The **api-gateway** also does its own live check of
both backends via `GET /health/deep`.

### Why it's structured this way

- Every service exposes a uniform `GET /health` (and `GET /info`), and
  the gateway exposes `GET /health/deep` which fans out to its
  dependencies. That uniformity is what a discovery/monitoring layer
  will eventually rely on.
- All inter-service URLs are environment variables, never hardcoded —
  see each service's `Dockerfile`/`docker-compose.yml` entry.
- `services.json` at the repo root is a static topology manifest
  (names, URLs, health endpoints, dependency edges). Nothing reads it
  yet; it's a known-good baseline for later automatic discovery to
  compare itself against.
- Services don't share code or a database schema/ORM — each owns its
  own DB access, so they can be discovered/monitored independently.

## Services

| Service          | Port | Responsibility                                   |
|-------------------|------|---------------------------------------------------|
| `frontend`        | 3000 | Static storefront (HTML/CSS/vanilla JS)            |
| `api-gateway`     | 8080 | Single public entry point, proxies to backends     |
| `product-service` | 4001 | Product catalog + inventory (stock reservation)    |
| `order-service`   | 4002 | Order placement/history, calls product-service     |
| `postgres`        | 5432 | Shared Postgres instance, `storedb` database        |

## Running it

Requires Docker and Docker Compose.

```bash
docker compose up --build
```

Then open:
- Storefront: http://localhost:3000
- API gateway: http://localhost:8080/health and http://localhost:8080/health/deep
- Product service directly: http://localhost:4001/products
- Order service directly: http://localhost:4002/orders

Stop everything with `docker compose down` (add `-v` to also drop the
Postgres volume and reset seed data).

## API summary

**product-service** (via gateway at `/api/products`)
- `GET /products` — list, optional `?category=`
- `GET /products/:id` — single product
- `PATCH /products/:id/stock` — internal, body `{ "delta": -2 }`

**order-service** (via gateway at `/api/orders`)
- `GET /orders` — list all orders
- `GET /orders/:id` — order detail with line items
- `POST /orders` — place an order:
  ```json
  {
    "customer_name": "Ada Lovelace",
    "customer_email": "ada@example.com",
    "items": [{ "product_id": 1, "quantity": 2 }]
  }
  ```

## Not built yet (by design)

This repo intentionally stops at "a real app that works." The
monitoring platform, anomaly detection, cross-service correlation,
root-cause analysis, automatic service discovery, and failure
injection are separate, future pieces of Infrastructure Intelligence.
