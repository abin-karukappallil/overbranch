import { router, protectedProcedure, projectProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { projects, projectMembers, projectInvitations, notifications, user } from '@/db/schema';
import { eq, and } from 'drizzle-orm';
import { TRPCError } from '@trpc/server';

import { serverBroadcast } from '@/lib/supabase';

export const invitationsRouter = router({
  sendInvite: projectProcedure
    .input(z.object({
      email: z.string().email(),
      role: z.enum(["Editor", "Viewer"]).default("Editor"),
    }))
    .mutation(async ({ input, ctx }) => {
      if (ctx.memberRole === 'Viewer') {
        throw new TRPCError({
          code: 'FORBIDDEN',
          message: 'Viewers do not have permission to send project invitations.',
        });
      }

      const email = input.email.trim().toLowerCase();

      const [targetUser] = await db.select().from(user).where(eq(user.email, email));
      if (!targetUser) {
        throw new TRPCError({
          code: 'NOT_FOUND',
          message: 'No account exists with this email.',
        });
      }

      if (targetUser.id === ctx.project.ownerId) {
        throw new TRPCError({
          code: 'BAD_REQUEST',
          message: 'User is the project owner.',
        });
      }

      if (targetUser.id === ctx.user.id) {
        throw new TRPCError({
          code: 'BAD_REQUEST',
          message: 'You cannot invite yourself.',
        });
      }

      const [existingMember] = await db
        .select()
        .from(projectMembers)
        .where(and(eq(projectMembers.projectId, ctx.project.id), eq(projectMembers.userId, targetUser.id)));

      if (existingMember) {
        throw new TRPCError({
          code: 'BAD_REQUEST',
          message: 'User is already a collaborator on this project.',
        });
      }

      const [existingInvite] = await db
        .select()
        .from(projectInvitations)
        .where(
          and(
            eq(projectInvitations.projectId, ctx.project.id),
            eq(projectInvitations.receiverId, targetUser.id),
            eq(projectInvitations.status, 'Pending')
          )
        );

      if (existingInvite) {
        throw new TRPCError({
          code: 'BAD_REQUEST',
          message: 'An invitation is already pending for this user.',
        });
      }

      const inviteId = crypto.randomUUID();
      const notifId = crypto.randomUUID();

      await db.transaction(async (tx) => {
        await tx.insert(projectInvitations).values({
          id: inviteId,
          projectId: ctx.project.id,
          senderId: ctx.user.id,
          receiverId: targetUser.id,
          email: targetUser.email,
          role: input.role,
          status: 'Pending',
        });

        await tx.insert(notifications).values({
          id: notifId,
          receiverId: targetUser.id,
          senderId: ctx.user.id,
          projectId: ctx.project.id,
          type: 'ProjectInvite',
          title: 'Project Invitation',
          message: `${ctx.user.name || ctx.user.email} invited you to co-author "${ctx.project.name}".`,
        });
      });

      // Real-time server broadcast to target user's personal channel
      serverBroadcast(`user:${targetUser.id}`, 'notification.new', {
        type: 'ProjectInvite',
        title: 'Project Invitation',
        message: `${ctx.user.name || ctx.user.email} invited you to co-author "${ctx.project.name}".`,
      }).catch((err) => console.warn('Failed to broadcast invite notification:', err));

      return {
        success: true,
        invitationId: inviteId,
        receiverName: targetUser.name,
        receiverEmail: targetUser.email,
      };
    }),

  listPending: protectedProcedure.query(async ({ ctx }) => {
    const userId = ctx.user.id;

    const pendingInvites = await db
      .select({
        id: projectInvitations.id,
        projectId: projectInvitations.projectId,
        role: projectInvitations.role,
        createdAt: projectInvitations.createdAt,
        projectName: projects.name,
        projectDescription: projects.description,
        senderName: user.name,
        senderEmail: user.email,
      })
      .from(projectInvitations)
      .innerJoin(projects, eq(projectInvitations.projectId, projects.id))
      .innerJoin(user, eq(projectInvitations.senderId, user.id))
      .where(and(eq(projectInvitations.receiverId, userId), eq(projectInvitations.status, 'Pending')));

    return pendingInvites;
  }),

  acceptInvite: protectedProcedure
    .input(z.object({ invitationId: z.string().uuid() }))
    .mutation(async ({ input, ctx }) => {
      const userId = ctx.user.id;

      const [invitation] = await db
        .select()
        .from(projectInvitations)
        .where(
          and(
            eq(projectInvitations.id, input.invitationId),
            eq(projectInvitations.receiverId, userId),
            eq(projectInvitations.status, 'Pending')
          )
        );

      if (!invitation) {
        throw new TRPCError({
          code: 'NOT_FOUND',
          message: 'Invitation not found or already processed.',
        });
      }

      const [project] = await db.select().from(projects).where(eq(projects.id, invitation.projectId));

      await db.transaction(async (tx) => {
        await tx.insert(projectMembers).values({
          id: crypto.randomUUID(),
          projectId: invitation.projectId,
          userId: userId,
          role: invitation.role,
        });

        await tx
          .update(projectInvitations)
          .set({ status: 'Accepted', updatedAt: new Date() })
          .where(eq(projectInvitations.id, invitation.id));

        await tx
          .update(notifications)
          .set({ isRead: true })
          .where(
            and(
              eq(notifications.receiverId, userId),
              eq(notifications.projectId, invitation.projectId),
              eq(notifications.type, 'ProjectInvite')
            )
          );

        await tx.insert(notifications).values({
          id: crypto.randomUUID(),
          receiverId: invitation.senderId,
          senderId: userId,
          projectId: invitation.projectId,
          type: 'ProjectAccepted',
          title: 'Invitation Accepted',
          message: `${ctx.user.name || ctx.user.email} accepted your invitation to co-author "${project?.name || 'project'}".`,
        });
      });

      return { success: true, projectId: invitation.projectId };
    }),

  declineInvite: protectedProcedure
    .input(z.object({ invitationId: z.string().uuid() }))
    .mutation(async ({ input, ctx }) => {
      const userId = ctx.user.id;

      const [invitation] = await db
        .select()
        .from(projectInvitations)
        .where(
          and(
            eq(projectInvitations.id, input.invitationId),
            eq(projectInvitations.receiverId, userId),
            eq(projectInvitations.status, 'Pending')
          )
        );

      if (!invitation) {
        throw new TRPCError({
          code: 'NOT_FOUND',
          message: 'Invitation not found or already processed.',
        });
      }

      await db.transaction(async (tx) => {
        await tx
          .update(projectInvitations)
          .set({ status: 'Declined', updatedAt: new Date() })
          .where(eq(projectInvitations.id, invitation.id));

        await tx
          .update(notifications)
          .set({ isRead: true })
          .where(
            and(
              eq(notifications.receiverId, userId),
              eq(notifications.projectId, invitation.projectId),
              eq(notifications.type, 'ProjectInvite')
            )
          );

        await tx.insert(notifications).values({
          id: crypto.randomUUID(),
          receiverId: invitation.senderId,
          senderId: userId,
          projectId: invitation.projectId,
          type: 'ProjectDeclined',
          title: 'Invitation Declined',
          message: `${ctx.user.name || ctx.user.email} declined your invitation to co-author project.`,
        });
      });

      return { success: true };
    }),
});
