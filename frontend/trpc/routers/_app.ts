import { createTRPCRouter, publicProcedure } from "../init";
import { latexRouter } from "./latex";
import { projectRouter } from "./project";
import { projectFileRouter } from "./projectFile";
import { projectAssetRouter } from "./projectAsset";

export const appRouter = createTRPCRouter({
  test: publicProcedure.query(async () => {
    return { status: "success" };
  }),
  latex: latexRouter,
  project: projectRouter,
  projectFile: projectFileRouter,
  projectAsset: projectAssetRouter,
});

export type AppRouter = typeof appRouter;