import dotenv from "dotenv";
dotenv.config();
import express from "express";
import * as trpcExpress from "@trpc/server/adapters/express";
import cors from "cors";
import { appRouter } from "./trpc/routers/_app";
import { createTRPCContext } from "./trpc/init";

const app = express();
const port = 8080;

console.log("[BACKEND] Starting with BETTER_AUTH_URL:", process.env.BETTER_AUTH_URL);
console.log("[BACKEND] BETTER_AUTH_SECRET present:", !!process.env.BETTER_AUTH_SECRET);

app.use(cors());
app.use(express.json({ limit: "50mb" }));
app.use(express.urlencoded({ extended: true, limit: "50mb" }));

app.use(
    "/trpc",
    trpcExpress.createExpressMiddleware({
        router: appRouter,
        createContext: createTRPCContext,
    })
);

app.listen(port, () => {
    console.log(`tRPC server listening at http://localhost:${port}`);
});
