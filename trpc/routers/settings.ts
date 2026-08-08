import { router, protectedProcedure } from '../init';
import { z } from 'zod';

export const settingsRouter = router({
  getSettings: protectedProcedure.query(async ({ ctx }) => {
    return {
      workspaceName: `${ctx.user.name || 'User'}'s OverBranch Workspace`,
      workspaceSlug: `${(ctx.user.name || 'user').toLowerCase().replace(/\s+/g, '-')}-workspace`,
      googleOAuthEnabled: true,
      sessionDurationDays: 30,
      apiKey: `ob_live_pk_${ctx.user.id.slice(0, 12)}`,
    };
  }),

  updateGeneral: protectedProcedure
    .input(z.object({ workspaceName: z.string().min(2), workspaceSlug: z.string().min(2) }))
    .mutation(async ({ input }) => {
      return { success: true, settings: input };
    }),

  generateApiKey: protectedProcedure.mutation(async () => {
    return { apiKey: `ob_live_pk_${Math.random().toString(36).substring(2, 15)}${Math.random().toString(36).substring(2, 15)}` };
  }),
});
