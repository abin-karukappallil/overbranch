import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';
import { cache } from 'react';

function createDbClient() {
  let connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error(
      '[DATABASE_ERROR] DATABASE_URL is not set. Please add the DATABASE_URL secret in Cloudflare Workers.'
    );
  }

  // In Cloudflare Workers / Serverless, Supabase Pooler MUST use port 6543 (Transaction Mode)
  // Port 5432 is Session mode, which exhausts connection slots and causes requests to hang.
  if (connectionString.includes('pooler.supabase.com:5432')) {
    connectionString = connectionString.replace('pooler.supabase.com:5432', 'pooler.supabase.com:6543');
  }

  const client = postgres(connectionString, {
    prepare: false, // Required for transaction pooler / PgBouncer
    max: 1, // Serverless isolate uses at most 1 connection per request
    idle_timeout: 1, // Close connection after 1s of inactivity (0 is a no-op in postgres.js)
    connect_timeout: 5, // Fail fast if DB host cannot be reached within 5s
    max_lifetime: 10, // Recycle connection within 10s
  });

  return drizzle(client, { schema });
}

// React cache ensures getDb() returns a memoized DB client for the duration of the
// current request lifecycle, and is discarded when the request completes.
// This prevents dead TCP sockets from being reused across requests in Cloudflare Workers.
export const getDb = cache(() => {
  return createDbClient();
});

export const db = new Proxy({} as ReturnType<typeof createDbClient>, {
  get(_target, prop) {
    const d = getDb();
    const val = (d as any)[prop];
    return typeof val === 'function' ? val.bind(d) : val;
  },
});