const { Pool } = require('pg');

// Central place for DB config. Every service connects the same way so a
// future discovery/monitoring layer can reason about them consistently.
const pool = new Pool({
  host: process.env.PGHOST || 'postgres',
  port: process.env.PGPORT || 5432,
  user: process.env.PGUSER || 'store',
  password: process.env.PGPASSWORD || 'store',
  database: process.env.PGDATABASE || 'storedb',
  max: 10,
  idleTimeoutMillis: 30000,
});

pool.on('error', (err) => {
  // eslint-disable-next-line no-console
  console.error('[product-service] Unexpected DB pool error:', err.message);
});

module.exports = { pool };
