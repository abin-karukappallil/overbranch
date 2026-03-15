import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { db } from "./db";
import * as schema from "../../../frontend/db/schema";
import { bearer } from "better-auth/plugins";


export const auth = betterAuth({

    secret: process.env.BETTER_AUTH_SECRET,
    baseURL: process.env.BETTER_AUTH_BASE_URL,
    trustedOrigins: ["*"],
    trustHost: true,
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
