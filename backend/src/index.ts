import express from "express";
import * as trpcExpress from "@trpc/server/adapters/express";
import cors from "cors";
import { appRouter } from "./trpc/routers/_app";

const app = express();
const port = 8080;

app.use(cors());

app.use(
    "/trpc",
    trpcExpress.createExpressMiddleware({
        router: appRouter,
        createContext: () => ({}),
    })
);

app.listen(port, () => {
    console.log(`tRPC server listening at http://localhost:${port}`);
});
