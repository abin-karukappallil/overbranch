import { createTRPCRouter, publicProcedure } from "../init";
import { latexRouter } from "./latex";

export const appRouter = createTRPCRouter({
  test: publicProcedure.query(async () => {
    return { status: "success" };
  }),
  latex: latexRouter,
});

export type AppRouter = typeof appRouter;