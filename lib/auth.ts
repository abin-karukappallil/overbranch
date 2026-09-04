import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { db } from "@/db";
import * as schema from "@/db/schema";
import { cache } from "react";

function createAuth() {
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

  return betterAuth({
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
}

// React cache ensures auth is created once per request, dynamically picking up
// runtime environment variables and binding to the request-scoped DB instance.
export const getAuth = cache(() => {
  return createAuth();
});

export const auth = new Proxy({} as ReturnType<typeof createAuth>, {
  get(_target, prop) {
    const instance = getAuth();
    const val = (instance as any)[prop];
    return typeof val === "function" ? val.bind(instance) : val;
  },
});