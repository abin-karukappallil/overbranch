import { initTRPC, TRPCError } from '@trpc/server';
import { auth } from '@/lib/auth';
import superjson from 'superjson';
import { headers, cookies } from 'next/headers';
import { db } from '@/db';
import { projects, projectMembers, session as sessionTable, user as userTable, guestProjects } from '@/db/schema';
import { eq, and, gt } from 'drizzle-orm';
import { z } from 'zod';
import { verifyGuestToken } from '@/lib/guest-token';
import crypto from 'crypto';

export const createContext = async () => {
  const reqHeaders = await headers();
  let session = null;
  try {
    session = await Promise.race([
      auth.api.getSession({
        headers: reqHeaders,
      }),
      new Promise<null>((resolve) => {
        const timer = setTimeout(() => resolve(null), 5000);
        if (typeof timer === 'object' && 'unref' in timer) {
          (timer as any).unref();
        }
      }),
    ]);
  } catch (err) {
    console.warn('[tRPC Context] Failed to get session:', err);
    session = null;
  }

  const cookieStore = await cookies();

  // If auth.api.getSession failed or returned null, try direct DB lookup using session token cookie as fallback
  if (!session?.user) {
    const sessionCookie =
      cookieStore.get('__Secure-better-auth.session_token')?.value ||
      cookieStore.get('better-auth.session_token')?.value ||
      cookieStore.get('session_token')?.value;

    if (sessionCookie) {
      const rawToken = sessionCookie.split('.')[0];
      try {
        const [dbSession] = await db
          .select()
          .from(sessionTable)
          .where(and(eq(sessionTable.token, rawToken), gt(sessionTable.expiresAt, new Date())));

        if (dbSession) {
          const [dbUser] = await db
            .select()
            .from(userTable)
            .where(eq(userTable.id, dbSession.userId));

          if (dbUser) {
            session = {
              user: dbUser,
              session: dbSession,
            };
          }
        }
      } catch (dbErr) {
        console.warn('[tRPC Context] Direct DB session fallback error:', dbErr);
      }
    }
  }

  const rawGuestToken = cookieStore.get('ob_guest_token')?.value;
  // Always verify guest token if present so guest projects can be linked/accessed/migrated
  const verifiedGuest = rawGuestToken ? verifyGuestToken(rawGuestToken) : null;

  return {
    session,
    guestToken: rawGuestToken || null,
    guestSessionId: verifiedGuest?.sessionId || null,
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
      // Check if project was created in user's guest session
      if (ctx.guestSessionId) {
        const [gp] = await db.select().from(guestProjects).where(
          and(
            eq(guestProjects.projectId, projectId),
            eq(guestProjects.guestSessionId, ctx.guestSessionId)
          )
        );
        if (gp) {
          // Auto-migrate project to authenticated user
          try {
            await db.update(projects).set({ ownerId: userId }).where(eq(projects.id, projectId));
            await db.insert(projectMembers).values({
              id: crypto.randomUUID(),
              projectId,
              userId,
              role: 'Owner',
            }).onConflictDoNothing();
            await db.update(guestProjects).set({
              migratedToUserId: userId,
              migratedAt: new Date(),
            }).where(eq(guestProjects.id, gp.id));
            return next({
              ctx: {
                ...ctx,
                project: { ...project, ownerId: userId },
                memberRole: 'Owner',
              },
            });
          } catch (migErr) {
            console.warn('[projectProcedure] Auto-migration error:', migErr);
          }
        }
      }

      // Check if project was created under "default-user" or guest prefix
      if (project.ownerId === 'default-user' || project.ownerId.startsWith('guest-')) {
        try {
          await db.update(projects).set({ ownerId: userId }).where(eq(projects.id, projectId));
          await db.insert(projectMembers).values({
            id: crypto.randomUUID(),
            projectId,
            userId,
            role: 'Owner',
          }).onConflictDoNothing();
          return next({
            ctx: {
              ...ctx,
              project: { ...project, ownerId: userId },
              memberRole: 'Owner',
            },
          });
        } catch (claimErr) {
          console.warn('[projectProcedure] Claim error:', claimErr);
        }
      }

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
      if (project.ownerId === 'default-user' || project.ownerId.startsWith('guest-')) {
        try {
          await db.update(projects).set({ ownerId: userId }).where(eq(projects.id, projectId));
          return next({
            ctx: {
              ...ctx,
              project: { ...project, ownerId: userId },
              memberRole: 'Owner' as const,
            },
          });
        } catch (_) {}
      }
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