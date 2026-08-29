import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';
import { authRouter } from './auth';
import { userRouter } from './user';
import { dashboardRouter } from './dashboard';
import { projectsRouter } from './projects';
import { preferencesRouter } from './preferences';
import { notificationsRouter } from './notifications';
import { invitationsRouter } from './invitations';
import { commentsRouter } from './comments';
import { templatesRouter } from './templates';

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
  templates: templatesRouter,
  preferences: preferencesRouter,
  notifications: notificationsRouter,
  invitations: invitationsRouter,
  comments: commentsRouter,
});

export type AppRouter = typeof appRouter;