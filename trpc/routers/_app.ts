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
import { documentsRouter } from './documents';
import { chatRouter } from './chat';
import { reactionsRouter } from './reactions';
import { realtimeCommentsRouter } from './realtime-comments';

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
  preferences: preferencesRouter,
  notifications: notificationsRouter,
  invitations: invitationsRouter,
  comments: commentsRouter,

  // Real-time collaboration routers
  documents: documentsRouter,
  chat: chatRouter,
  reactions: reactionsRouter,
  realtimeComments: realtimeCommentsRouter,
});

export type AppRouter = typeof appRouter;