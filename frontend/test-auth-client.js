const { createAuthClient } = require("better-auth/react");
const client = createAuthClient({ baseURL: "https://overbranch.abinthomas.dev" });
console.log("Client options:", client.$store);
