import { router, protectedProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { notifications, user } from '@/db/schema';
import { eq, and, desc } from 'drizzle-orm';

export const notificationsRouter = router({
  listNotifications: protectedProcedure.query(async ({ ctx }) => {
    const userId = ctx.user.id;

    const list = await db
      .select({
        id: notifications.id,
        title: notifications.title,
        message: notifications.message,
        type: notifications.type,
        isRead: notifications.isRead,
        createdAt: notifications.createdAt,
        projectId: notifications.projectId,
        senderId: notifications.senderId,
        senderName: user.name,
        senderEmail: user.email,
        senderImage: user.image,
      })
      .from(notifications)
      .leftJoin(user, eq(notifications.senderId, user.id))
      .where(eq(notifications.receiverId, userId))
      .orderBy(desc(notifications.createdAt));

    return list.map((n) => ({
      ...n,
      createdAtFormatted: n.createdAt ? new Date(n.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now",
    }));
  }),

  unreadCount: protectedProcedure.query(async ({ ctx }) => {
    const userId = ctx.user.id;

    const unread = await db
      .select()
      .from(notifications)
      .where(and(eq(notifications.receiverId, userId), eq(notifications.isRead, false)));

    return unread.length;
  }),

  markAsRead: protectedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .mutation(async ({ input, ctx }) => {
      await db
        .update(notifications)
        .set({ isRead: true })
        .where(and(eq(notifications.id, input.id), eq(notifications.receiverId, ctx.user.id)));

      return { success: true, id: input.id };
    }),

  markAllAsRead: protectedProcedure.mutation(async ({ ctx }) => {
    await db
      .update(notifications)
      .set({ isRead: true })
      .where(eq(notifications.receiverId, ctx.user.id));

    return { success: true };
  }),
});
