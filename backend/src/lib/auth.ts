import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import * as schema from "../../../frontend/db/schema";
import { bearer } from "better-auth/plugins";

const client = postgres(process.env.DATABASE_URL!);``
const db = drizzle(client, { schema });

export const auth = betterAuth({
    secret: process.env.BETTER_AUTH_SECRET,
    trustedOrigins: ["*"],
    baseURL: process.env.BETTER_AUTH_BASE_URL,
    advanced: {
        cookiePrefix: "overbranch",
    },
    database: drizzleAdapter(db, {
        provider: "pg",
        schema,
    }),
    emailAndPassword: {
        enabled: true,
    },
    plugins: [
        bearer(),
    ],
});
