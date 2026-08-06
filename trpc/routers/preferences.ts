import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';

export const preferencesRouter = router({
  getPreferences: publicProcedure.query(async () => {
    return {
      theme: "dark",
      fontSize: 14,
      tabSize: 2,
      wordWrap: true,
      autoCompile: true,
      engine: "pdfLaTeX",
      emailNotifications: true,
      securityAlerts: true,
      lineNumbers: true,
    };
  }),

  updatePreferences: publicProcedure
    .input(z.object({
      theme: z.enum(["dark", "light", "system"]).optional(),
      fontSize: z.number().min(10).max(24).optional(),
      tabSize: z.number().min(2).max(8).optional(),
      wordWrap: z.boolean().optional(),
      autoCompile: z.boolean().optional(),
      engine: z.string().optional(),
      emailNotifications: z.boolean().optional(),
      securityAlerts: z.boolean().optional(),
      lineNumbers: z.boolean().optional(),
    }))
    .mutation(async ({ input }) => {
      return { success: true, preferences: input };
    }),
});
