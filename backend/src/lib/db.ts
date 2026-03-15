import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from '../../../frontend/db/schema';
import dotenv from 'dotenv';

dotenv.config();

const client = postgres(process.env.DATABASE_URL!);
export const db = drizzle(client, { schema });
