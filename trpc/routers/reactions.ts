import { router, projectProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { messageReactions, chatMessages, user } from '@/db/schema';
import { eq, and, sql } from 'drizzle-orm';
import { serverBroadcast } from '@/lib/supabase';

export const reactionsRouter = router({
  /**
   * Add a reaction to a chat message (spec section 8).
   * DB-write-then-broadcast pattern.
   */
  addReaction: projectProcedure
    .input(z.object({
      messageId: z.string().min(1),
      emoji: z.string().min(1).max(10),
    }))
    .mutation(async ({ input, ctx }) => {
      // Verify the message belongs to this project
      const [message] = await db
        .select()
        .from(chatMessages)
        .where(
          and(
            eq(chatMessages.id, input.messageId),
            eq(chatMessages.projectId, ctx.project.id)
          )
        );

      if (!message) {
        throw new Error("Message not found in this project");
      }

      // Upsert the reaction (unique constraint handles duplicates)
      try {
        await db.insert(messageReactions).values({
          id: crypto.randomUUID(),
          messageId: input.messageId,
          userId: ctx.user.id,
          emoji: input.emoji,
        });
      } catch (err: any) {
        // If unique constraint violation, reaction already exists — skip
        if (err?.code === "23505") {
          return { success: true, action: "already_exists" };
        }
        throw err;
      }

      // Get aggregate counts for the message
      const aggregates = await getReactionAggregates(input.messageId);

      // Broadcast the reaction
      await serverBroadcast(
        `project:${ctx.project.id}`,
        "chat.reaction.add",
        {
          messageId: input.messageId,
          userId: ctx.user.id,
          userName: ctx.user.name,
          emoji: input.emoji,
          aggregates,
        }
      );

      return { success: true, action: "added", aggregates };
    }),

  /**
   * Remove a reaction from a chat message (spec section 8).
   */
  removeReaction: projectProcedure
    .input(z.object({
      messageId: z.string().min(1),
      emoji: z.string().min(1).max(10),
    }))
    .mutation(async ({ input, ctx }) => {
      await db
        .delete(messageReactions)
        .where(
          and(
            eq(messageReactions.messageId, input.messageId),
            eq(messageReactions.userId, ctx.user.id),
            eq(messageReactions.emoji, input.emoji)
          )
        );

      const aggregates = await getReactionAggregates(input.messageId);

      await serverBroadcast(
        `project:${ctx.project.id}`,
        "chat.reaction.remove",
        {
          messageId: input.messageId,
          userId: ctx.user.id,
          emoji: input.emoji,
          aggregates,
        }
      );

      return { success: true, action: "removed", aggregates };
    }),

  /**
   * Get all reactions for a list of message IDs.
   */
  getReactions: projectProcedure
    .input(z.object({
      messageIds: z.array(z.string()).min(1).max(100),
    }))
    .query(async ({ input }) => {
      const reactions = await db
        .select({
          messageId: messageReactions.messageId,
          emoji: messageReactions.emoji,
          userId: messageReactions.userId,
          userName: user.name,
        })
        .from(messageReactions)
        .innerJoin(user, eq(messageReactions.userId, user.id))
        .where(
          sql`${messageReactions.messageId} IN ${input.messageIds}`
        );

      // Group by messageId → emoji → users
      const grouped: Record<string, Record<string, { count: number; users: { id: string; name: string | null }[] }>> = {};

      for (const r of reactions) {
        if (!grouped[r.messageId]) grouped[r.messageId] = {};
        if (!grouped[r.messageId][r.emoji]) {
          grouped[r.messageId][r.emoji] = { count: 0, users: [] };
        }
        grouped[r.messageId][r.emoji].count++;
        grouped[r.messageId][r.emoji].users.push({ id: r.userId, name: r.userName });
      }

      return grouped;
    }),
});

async function getReactionAggregates(messageId: string) {
  const reactions = await db
    .select({
      emoji: messageReactions.emoji,
      userId: messageReactions.userId,
      userName: user.name,
    })
    .from(messageReactions)
    .innerJoin(user, eq(messageReactions.userId, user.id))
    .where(eq(messageReactions.messageId, messageId));

  const aggregates: Record<string, { count: number; users: { id: string; name: string | null }[] }> = {};

  for (const r of reactions) {
    if (!aggregates[r.emoji]) {
      aggregates[r.emoji] = { count: 0, users: [] };
    }
    aggregates[r.emoji].count++;
    aggregates[r.emoji].users.push({ id: r.userId, name: r.userName });
  }

  return aggregates;
}
