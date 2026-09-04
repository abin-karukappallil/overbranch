import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { db } from "@/db";
import * as schema from "@/db/schema";

const googleClientId = process.env.GOOGLE_CLIENT_ID?.trim();
const googleClientSecret = process.env.GOOGLE_CLIENT_SECRET?.trim();

const socialProviders: Record<string, any> = {};
if (googleClientId && googleClientSecret) {
  socialProviders.google = {
    clientId: googleClientId,
    clientSecret: googleClientSecret,
  };
} else if (typeof window === "undefined") {
  console.warn(
    "[Better-Auth] GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is missing. Google social sign-in will be disabled until set in Cloudflare secrets."
  );
}

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "pg",
    schema,
  }),
  baseURL:
    process.env.BETTER_AUTH_URL ||
    process.env.NEXT_PUBLIC_APP_URL ||
    "https://overbranch.abinthomas.dev",
  secret:
    process.env.BETTER_AUTH_SECRET ||
    "overbranch-secret-key-replace-in-production-min-32-chars",
  emailAndPassword: {
    enabled: true,
  },
  socialProviders,
});