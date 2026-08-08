import { initTRPC, TRPCError } from '@trpc/server';
import { auth } from '@/lib/auth';
import superjson from 'superjson';
import { headers } from 'next/headers';
import { db } from '@/db';
import { projects, projectMembers } from '@/db/schema';
import { eq, and } from 'drizzle-orm';
import { z } from 'zod';

export const createContext = async () => {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  return {
    session,
  };
};

const t = initTRPC.context<typeof createContext>().create({
  transformer: superjson,
});

export const router = t.router;
export const publicProcedure = t.procedure;

export const protectedProcedure = t.procedure.use(({ ctx, next }) => {
  if (!ctx.session?.user) {
    throw new TRPCError({ code: 'UNAUTHORIZED', message: 'Authentication required. Please sign in.' });
  }
  return next({
    ctx: {
      session: ctx.session,
      user: ctx.session.user,
    },
  });
});

export const projectProcedure = protectedProcedure
  .input(z.object({ projectId: z.string().min(1) }).passthrough())
  .use(async ({ ctx, input, next }) => {
    const userId = ctx.user.id;
    const projectId = input.projectId;

    const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
    if (!project) {
      throw new TRPCError({ code: 'NOT_FOUND', message: 'Project not found' });
    }

    if (project.ownerId === userId) {
      return next({
        ctx: {
          ...ctx,
          project,
          memberRole: 'Owner' as 'Owner' | 'Editor' | 'Viewer',
        },
      });
    }

    const [member] = await db.select().from(projectMembers).where(
      and(eq(projectMembers.projectId, projectId), eq(projectMembers.userId, userId))
    );

    if (!member) {
      throw new TRPCError({ code: 'FORBIDDEN', message: 'You do not have access to this project' });
    }

    return next({
      ctx: {
        ...ctx,
        project,
        memberRole: member.role as 'Owner' | 'Editor' | 'Viewer',
      },
    });
  });

export const ownerProcedure = protectedProcedure
  .input(z.object({ projectId: z.string().min(1) }).passthrough())
  .use(async ({ ctx, input, next }) => {
    const userId = ctx.user.id;
    const projectId = input.projectId;

    const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
    if (!project) {
      throw new TRPCError({ code: 'NOT_FOUND', message: 'Project not found' });
    }

    if (project.ownerId !== userId) {
      throw new TRPCError({ code: 'FORBIDDEN', message: 'Only the project owner can perform this operation' });
    }

    return next({
      ctx: {
        ...ctx,
        project,
        memberRole: 'Owner' as const,
      },
    });
  });