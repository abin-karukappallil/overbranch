import { router, projectProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { chatMessages, chatReadState, user, projectMembers } from '@/db/schema';
import { eq, and, desc, lt } from 'drizzle-orm';
import { serverBroadcast } from '@/lib/supabase';

export const chatRouter = router({
  /**
   * Send a chat message (spec section 5).
   * DB-write-then-broadcast — message history and live delivery never disagree.
   */
  sendMessage: projectProcedure
    .input(z.object({
      body: z.string().min(1).max(10000),
    }))
    .mutation(async ({ input, ctx }) => {
      // Parse @mentions from message body against project member list (spec section 9)
      const mentionPattern = /@(\S+)/g;
      const mentionMatches = input.body.match(mentionPattern) || [];
      let mentionedUserIds: string[] = [];

      if (mentionMatches.length > 0) {
        // Get all project members to match mentions
        const members = await db
          .select({ userId: projectMembers.userId, name: user.name, email: user.email })
          .from(projectMembers)
          .innerJoin(user, eq(projectMembers.userId, user.id))
          .where(eq(projectMembers.projectId, ctx.project.id));

        for (const mention of mentionMatches) {
          const mentionName = mention.slice(1).toLowerCase();
          const matched = members.find(
            (m) =>
              m.name?.toLowerCase() === mentionName ||
              m.email?.toLowerCase().split("@")[0] === mentionName
          );
          if (matched) {
            mentionedUserIds.push(matched.userId);
          }
        }

        // Deduplicate
        mentionedUserIds = [...new Set(mentionedUserIds)];
      }

      const messageId = crypto.randomUUID();

      const [newMessage] = await db
        .insert(chatMessages)
        .values({
          id: messageId,
          projectId: ctx.project.id,
          authorId: ctx.user.id,
          body: input.body,
          mentionedUserIds,
        })
        .returning();

      // Broadcast the message to all project subscribers
      await serverBroadcast(
        `project:${ctx.project.id}`,
        "chat.message",
        {
          id: newMessage.id,
          projectId: newMessage.projectId,
          authorId: newMessage.authorId,
          authorName: ctx.user.name,
          authorEmail: ctx.user.email,
          authorImage: (ctx.user as any).image || null,
          body: newMessage.body,
          mentionedUserIds: newMessage.mentionedUserIds,
          createdAt: newMessage.createdAt?.toISOString(),
        }
      );

      return {
        id: newMessage.id,
        body: newMessage.body,
        authorId: newMessage.authorId,
        authorName: ctx.user.name,
        mentionedUserIds,
        createdAt: newMessage.createdAt,
      };
    }),

  /**
   * Get chat messages with cursor-based pagination (spec section 5).
   */
  getMessages: projectProcedure
    .input(z.object({
      cursor: z.string().optional(), // message ID for cursor-based pagination
      limit: z.number().min(1).max(100).default(50),
    }))
    .query(async ({ input, ctx }) => {
      let query = db
        .select({
          id: chatMessages.id,
          body: chatMessages.body,
          authorId: chatMessages.authorId,
          authorName: user.name,
          authorEmail: user.email,
          authorImage: user.image,
          mentionedUserIds: chatMessages.mentionedUserIds,
          createdAt: chatMessages.createdAt,
        })
        .from(chatMessages)
        .innerJoin(user, eq(chatMessages.authorId, user.id))
        .where(eq(chatMessages.projectId, ctx.project.id))
        .orderBy(desc(chatMessages.createdAt))
        .limit(input.limit + 1); // fetch one extra to determine if there are more

      if (input.cursor) {
        // Get the cursor message's timestamp
        const [cursorMsg] = await db
          .select({ createdAt: chatMessages.createdAt })
          .from(chatMessages)
          .where(eq(chatMessages.id, input.cursor));

        if (cursorMsg?.createdAt) {
          query = db
            .select({
              id: chatMessages.id,
              body: chatMessages.body,
              authorId: chatMessages.authorId,
              authorName: user.name,
              authorEmail: user.email,
              authorImage: user.image,
              mentionedUserIds: chatMessages.mentionedUserIds,
              createdAt: chatMessages.createdAt,
            })
            .from(chatMessages)
            .innerJoin(user, eq(chatMessages.authorId, user.id))
            .where(
              and(
                eq(chatMessages.projectId, ctx.project.id),
                lt(chatMessages.createdAt, cursorMsg.createdAt)
              )
            )
            .orderBy(desc(chatMessages.createdAt))
            .limit(input.limit + 1);
        }
      }

      const results = await query;
      const hasMore = results.length > input.limit;
      const messages = hasMore ? results.slice(0, input.limit) : results;

      return {
        messages: messages.map((m) => ({
          ...m,
          authorAvatar:
            m.authorImage ||
            `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(m.authorName || "U")}`,
        })),
        nextCursor: hasMore ? messages[messages.length - 1]?.id : null,
      };
    }),

  /**
   * Mark messages as read (spec section 7).
   */
  markRead: projectProcedure
    .input(z.object({
      lastReadMessageId: z.string().min(1),
    }))
    .mutation(async ({ input, ctx }) => {
      const existing = await db
        .select()
        .from(chatReadState)
        .where(
          and(
            eq(chatReadState.userId, ctx.user.id),
            eq(chatReadState.projectId, ctx.project.id)
          )
        );

      if (existing.length > 0) {
        await db
          .update(chatReadState)
          .set({
            lastReadMessageId: input.lastReadMessageId,
            updatedAt: new Date(),
          })
          .where(
            and(
              eq(chatReadState.userId, ctx.user.id),
              eq(chatReadState.projectId, ctx.project.id)
            )
          );
      } else {
        await db.insert(chatReadState).values({
          id: crypto.randomUUID(),
          userId: ctx.user.id,
          projectId: ctx.project.id,
          lastReadMessageId: input.lastReadMessageId,
        });
      }

      // Broadcast read receipt so other tabs/clients sync
      await serverBroadcast(
        `project:${ctx.project.id}`,
        "chat.read",
        {
          userId: ctx.user.id,
          lastReadMessageId: input.lastReadMessageId,
        }
      );

      return { success: true };
    }),

  /**
   * Get the user's read state for a project (spec section 7).
   */
  getReadState: projectProcedure
    .query(async ({ ctx }) => {
      const [state] = await db
        .select()
        .from(chatReadState)
        .where(
          and(
            eq(chatReadState.userId, ctx.user.id),
            eq(chatReadState.projectId, ctx.project.id)
          )
        );

      return state?.lastReadMessageId || null;
    }),
});
