import { router, protectedProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { userPreferences, editorPreferences } from '@/db/schema';
import { eq } from 'drizzle-orm';

export const preferencesRouter = router({
  getPreferences: protectedProcedure.query(async ({ ctx }) => {
    const userId = ctx.user.id;
    const [uPref] = await db.select().from(userPreferences).where(eq(userPreferences.userId, userId));
    const [ePref] = await db.select().from(editorPreferences).where(eq(editorPreferences.userId, userId));

    return {
      theme: uPref?.theme || "dark",
      fontSize: ePref?.fontSize || 14,
      tabSize: ePref?.tabSize || 2,
      wordWrap: ePref?.wordWrap ?? true,
      autoCompile: ePref?.autoCompile ?? true,
      engine: ePref?.engine || "pdfLaTeX",
      emailNotifications: uPref?.emailNotifications ?? true,
      securityAlerts: uPref?.securityAlerts ?? true,
      lineNumbers: ePref?.lineNumbers ?? true,
    };
  }),

  updatePreferences: protectedProcedure
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
    .mutation(async ({ ctx, input }) => {
      const userId = ctx.user.id;

      if (input.theme !== undefined || input.emailNotifications !== undefined || input.securityAlerts !== undefined) {
        await db.insert(userPreferences)
          .values({
            id: crypto.randomUUID(),
            userId,
            theme: input.theme || "dark",
            emailNotifications: input.emailNotifications ?? true,
            securityAlerts: input.securityAlerts ?? true,
          })
          .onConflictDoUpdate({
            target: userPreferences.userId,
            set: {
              ...(input.theme !== undefined && { theme: input.theme }),
              ...(input.emailNotifications !== undefined && { emailNotifications: input.emailNotifications }),
              ...(input.securityAlerts !== undefined && { securityAlerts: input.securityAlerts }),
              updatedAt: new Date(),
            },
          });
      }

      if (
        input.fontSize !== undefined ||
        input.tabSize !== undefined ||
        input.wordWrap !== undefined ||
        input.autoCompile !== undefined ||
        input.engine !== undefined ||
        input.lineNumbers !== undefined
      ) {
        await db.insert(editorPreferences)
          .values({
            id: crypto.randomUUID(),
            userId,
            fontSize: input.fontSize || 14,
            tabSize: input.tabSize || 2,
            wordWrap: input.wordWrap ?? true,
            autoCompile: input.autoCompile ?? true,
            engine: input.engine || "pdfLaTeX",
            lineNumbers: input.lineNumbers ?? true,
          })
          .onConflictDoUpdate({
            target: editorPreferences.userId,
            set: {
              ...(input.fontSize !== undefined && { fontSize: input.fontSize }),
              ...(input.tabSize !== undefined && { tabSize: input.tabSize }),
              ...(input.wordWrap !== undefined && { wordWrap: input.wordWrap }),
              ...(input.autoCompile !== undefined && { autoCompile: input.autoCompile }),
              ...(input.engine !== undefined && { engine: input.engine }),
              ...(input.lineNumbers !== undefined && { lineNumbers: input.lineNumbers }),
            },
          });
      }

      return { success: true, preferences: input };
    }),
});
