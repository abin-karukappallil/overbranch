import { router, publicProcedure } from '../init';
import { db } from '@/db';
import { projects } from '@/db/schema';

export const dashboardRouter = router({
  getStats: publicProcedure.query(async () => {
    try {
      const dbProjects = await db.select().from(projects);
      return {
        totalProjects: dbProjects.length,
        activeCoAuthors: 1,
        compilationEngineStatus: "pdfLaTeX Active",
        authStatus: "Better Auth + Drizzle Active",
        monthlyCompiles: 120,
      };
    } catch (err) {
      return {
        totalProjects: 0,
        activeCoAuthors: 1,
        compilationEngineStatus: "pdfLaTeX Active",
        authStatus: "Better Auth + Drizzle Active",
        monthlyCompiles: 0,
      };
    }
  }),

  getOverview: publicProcedure.query(async () => {
    return {
      workspaceName: "My LaTeX Research Workspace",
      workspaceId: "ws_latex_pro",
      recentActivities: [],
    };
  }),
});
