import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';
import { cache } from 'react';

function createDbClient() {
  let connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error(
      '[DATABASE_ERROR] DATABASE_URL is not set. Please configure DATABASE_URL in Vercel environment variables or .env file.'
    );
  }

  // In Serverless Functions, Supabase Pooler MUST use port 6543 (Transaction Mode)
  // Port 5432 is Session mode, which exhausts connection slots and causes requests to hang.
  if (connectionString.includes('pooler.supabase.com:5432')) {
    connectionString = connectionString.replace('pooler.supabase.com:5432', 'pooler.supabase.com:6543');
  }

  const isServerless = process.env.VERCEL === '1' || process.env.AWS_LAMBDA_FUNCTION_NAME !== undefined;

  const client = postgres(connectionString, {
    prepare: false, // Required for transaction pooler / PgBouncer
    max: isServerless ? 1 : 10, // Docker: pool of 10 connections. Serverless: 1.
    idle_timeout: isServerless ? 1 : 20, // Keep pooled connections alive 20s
    connect_timeout: 10, // 10s connect timeout for cross-region latency
    max_lifetime: isServerless ? 10 : 60 * 30, // Recycle connection after 30 mins
  });

  return drizzle(client, { schema });
}

let _serverClient: ReturnType<typeof createDbClient> | null = null;

// React cache ensures getDb() returns a memoized DB client for request lifecycle.
// In long-running Node/Docker environments, we maintain a persistent pool singleton.
export const getDb = () => {
  const isServerless = process.env.VERCEL === '1' || process.env.AWS_LAMBDA_FUNCTION_NAME !== undefined;
  if (!isServerless) {
    if (!_serverClient) {
      _serverClient = createDbClient();
    }
    return _serverClient;
  }
  return createDbClient();
};

export const db = new Proxy({} as ReturnType<typeof createDbClient>, {
  get(_target, prop) {
    const d = getDb();
    const val = (d as any)[prop];
    return typeof val === 'function' ? val.bind(d) : val;
  },
  has(_target, prop) {
    const d = getDb();
    return prop in d;
  },
});