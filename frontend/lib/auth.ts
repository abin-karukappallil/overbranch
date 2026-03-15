import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { db } from "@/db/index";
import * as schema from "@/db/schema";

export const auth = betterAuth({
  baseURL: process.env.BETTER_AUTH_BASE_URL + "/api/auth",
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
  sendOnSignUp: true,
  autoSignInAfterVerification: true,
  expiresIn: 3600,
}
);