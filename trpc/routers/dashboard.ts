import { router, publicProcedure, protectedProcedure } from '../init';

export const dashboardRouter = router({
  getStats: publicProcedure.query(async () => {
    return {
      totalProjects: 8,
      activeCoAuthors: 12,
      compilationEngineStatus: "Sub-10ms pdfLaTeX",
      authStatus: "Better Auth + Drizzle Active",
      monthlyCompiles: 1420,
    };
  }),

  getOverview: publicProcedure.query(async () => {
    return {
      workspaceName: "Stanford & OverBranch Research Team",
      workspaceId: "ws_latex_pro",
      recentActivities: [
        { id: "act-1", title: "Compiled main.tex", time: "10 mins ago", author: "Dr. Alice Vance" },
        { id: "act-2", title: "Imported references.bib", time: "1 hour ago", author: "Prof. Bob Chen" },
        { id: "act-3", title: "Created project IEEE_Paper_OverBranch_v1", time: "Yesterday", author: "Carol Zhang" },
      ],
    };
  }),
});
