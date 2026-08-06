import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';
import { authRouter } from './auth';
import { userRouter } from './user';
import { dashboardRouter } from './dashboard';
import { projectsRouter } from './projects';
import { workspaceRouter } from './workspace';
import { settingsRouter } from './settings';
import { preferencesRouter } from './preferences';
import { templatesRouter } from './templates';
import { notificationsRouter } from './notifications';

export const appRouter = router({
  hello: publicProcedure
    .input(z.object({ text: z.string() }).optional())
    .query(({ input }) => {
      return {
        greeting: `Hello ${input?.text ?? 'World'}`,
      };
    }),
  secretMessage: protectedProcedure.query(({ ctx }) => {
    return {
      message: `Hello ${ctx.session.user.name}, you are logged in!`,
    };
  }),

  auth: authRouter,
  user: userRouter,
  dashboard: dashboardRouter,
  projects: projectsRouter,
  workspace: workspaceRouter,
  settings: settingsRouter,
  preferences: preferencesRouter,
  templates: templatesRouter,
  notifications: notificationsRouter,
});

export type AppRouter = typeof appRouter;