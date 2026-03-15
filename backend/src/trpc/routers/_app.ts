import { router } from "../init";
import { latexRouter } from "./latexRouter";
import { aiRouter } from "./aiRouter";

export const appRouter = router({
    latex: latexRouter,
    ai: aiRouter,
});

export type AppRouter = typeof appRouter;

