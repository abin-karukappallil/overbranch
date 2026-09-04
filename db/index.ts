import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';

let client: ReturnType<typeof postgres> | null = null;
let dbInstance: ReturnType<typeof drizzle<typeof schema>> | null = null;

export function getDb() {
  if (!dbInstance) {
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

    client = postgres(connectionString, {
      prepare: false, // Required for transaction pooler / PgBouncer
      max: 1, // Edge isolate should use at most 1 connection
      idle_timeout: 0, // Closes idle connection to avoid stale TCP sockets in frozen isolates
      connect_timeout: 10, // Prevent hanging if database is unreachable
    });

    dbInstance = drizzle(client, { schema });
  }
  return dbInstance;
}

export const db = new Proxy({} as ReturnType<typeof drizzle<typeof schema>>, {
  get(_target, prop) {
    const d = getDb();
    const val = (d as any)[prop];
    return typeof val === 'function' ? val.bind(d) : val;
  },
});