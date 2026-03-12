import { createTRPCRouter, protectedProcedure } from "../init";
import { latexRouter } from "./latex";
import { projectRouter } from "./project";
import { projectFileRouter } from "./projectFile";
import { projectAssetRouter } from "./projectAsset";

export const appRouter = createTRPCRouter({
  test: protectedProcedure.query(async () => {
    return { status: "success" };
  }),
  latex: latexRouter,
  project: projectRouter,
  projectFile: projectFileRouter,
  projectAsset: projectAssetRouter,
});

export type AppRouter = typeof appRouter;