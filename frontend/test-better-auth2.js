const { betterAuth } = require("better-auth");

process.env.BETTER_AUTH_URL = "https://overbranch.abinthomas.dev";

// 1. Without baseURL
const auth1 = betterAuth({
  trustedOrigins: ["*"],
  database: { provider: "pg", url: "postgres://a:b@c/d" },
  emailAndPassword: { enabled: true }
});

// 2. With baseURL as just domain
const auth2 = betterAuth({
  trustedOrigins: ["*"],
  baseURL: "https://overbranch.abinthomas.dev",
  database: { provider: "pg", url: "postgres://a:b@c/d" },
  emailAndPassword: { enabled: true }
});

// 3. With baseURL as domain + /api/auth
const auth3 = betterAuth({
  trustedOrigins: ["*"],
  baseURL: "https://overbranch.abinthomas.dev/api/auth",
  database: { provider: "pg", url: "postgres://a:b@c/d" },
  emailAndPassword: { enabled: true }
});

console.log("auth1 baseURL:", auth1.options.baseURL);
console.log("auth2 baseURL:", auth2.options.baseURL);
console.log("auth3 baseURL:", auth3.options.baseURL);
