import { router } from "../init";
import { latexRouter } from "./latexRouter";

export const appRouter = router({
    latex: latexRouter,
});

export type AppRouter = typeof appRouter;
