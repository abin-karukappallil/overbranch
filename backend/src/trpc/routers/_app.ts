import { router } from "../init";
import { latexRouter } from "./latexRouter";
import { aiRouter } from "./aiRouter";
import { projectFileRouter } from "./projectFileRouter";
import { projectRouter } from "./projectRouter";
import { projectAssetRouter } from "./projectAssetRouter";

export const appRouter = router({
    latex: latexRouter,
    ai: aiRouter,
    projectFile: projectFileRouter,
    project: projectRouter,
    projectAsset: projectAssetRouter,
});




export type AppRouter = typeof appRouter;

