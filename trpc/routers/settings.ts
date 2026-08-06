import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';

export const settingsRouter = router({
  getSettings: publicProcedure.query(async () => {
    return {
      workspaceName: "Acme OverBranch",
      workspaceSlug: "acme-overbranch",
      googleOAuthEnabled: true,
      sessionDurationDays: 30,
      apiKey: "ob_live_pk_994827103847",
    };
  }),

  updateGeneral: publicProcedure
    .input(z.object({ workspaceName: z.string().min(2), workspaceSlug: z.string().min(2) }))
    .mutation(async ({ input }) => {
      return { success: true, settings: input };
    }),

  generateApiKey: publicProcedure.mutation(async () => {
    return { apiKey: `ob_live_pk_${Math.random().toString(36).substring(2, 15)}${Math.random().toString(36).substring(2, 15)}` };
  }),
});
