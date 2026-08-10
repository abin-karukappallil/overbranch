import { router, projectProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { comments, user } from '@/db/schema';
import { eq, and, desc, isNull } from 'drizzle-orm';
import { serverBroadcast } from '@/lib/supabase';

export const realtimeCommentsRouter = router({
  /**
   * List comments for a document (spec section 10).
   */
  list: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
    }))
    .query(async ({ input, ctx }) => {
      const list = await db
        .select({
          id: comments.id,
          documentId: comments.documentId,
          parentId: comments.parentId,
          content: comments.content,
          status: comments.status,
          resolved: comments.resolved,
          mentionedUserIds: comments.mentionedUserIds,
          createdAt: comments.createdAt,
          authorId: comments.authorId,
          authorName: user.name,
          authorEmail: user.email,
          authorImage: user.image,
        })
        .from(comments)
        .innerJoin(user, eq(comments.authorId, user.id))
        .where(
          and(
            eq(comments.projectId, ctx.project.id),
            eq(comments.documentId!, input.documentId)
          )
        )
        .orderBy(desc(comments.createdAt));

      return list.map((c) => ({
        ...c,
        authorAvatar:
          c.authorImage ||
          `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(c.authorName || "U")}`,
      }));
    }),

  /**
   * Create a new comment on a document (spec section 10).
   */
  create: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
      content: z.string().min(1),
    }))
    .mutation(async ({ input, ctx }) => {
      const commentId = crypto.randomUUID();

      const [newComment] = await db
        .insert(comments)
        .values({
          id: commentId,
          projectId: ctx.project.id,
          documentId: input.documentId,
          authorId: ctx.user.id,
          content: input.content,
          status: "open",
          resolved: false,
        })
        .returning();

      await serverBroadcast(
        `document:${input.documentId}`,
        "comment.created",
        {
          id: newComment.id,
          documentId: newComment.documentId,
          authorId: newComment.authorId,
          authorName: ctx.user.name,
          authorImage: (ctx.user as any).image || null,
          content: newComment.content,
          status: newComment.status,
          createdAt: newComment.createdAt?.toISOString(),
        }
      );

      return {
        id: newComment.id,
        content: newComment.content,
        status: newComment.status,
        authorName: ctx.user.name,
        createdAt: newComment.createdAt,
      };
    }),

  /**
   * Reply to a comment (threaded, spec section 10).
   */
  reply: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
      parentId: z.string().min(1),
      content: z.string().min(1),
    }))
    .mutation(async ({ input, ctx }) => {
      const commentId = crypto.randomUUID();

      const [newReply] = await db
        .insert(comments)
        .values({
          id: commentId,
          projectId: ctx.project.id,
          documentId: input.documentId,
          parentId: input.parentId,
          authorId: ctx.user.id,
          content: input.content,
          status: "open",
          resolved: false,
        })
        .returning();

      await serverBroadcast(
        `document:${input.documentId}`,
        "comment.replied",
        {
          id: newReply.id,
          documentId: newReply.documentId,
          parentId: newReply.parentId,
          authorId: newReply.authorId,
          authorName: ctx.user.name,
          content: newReply.content,
          createdAt: newReply.createdAt?.toISOString(),
        }
      );

      return {
        id: newReply.id,
        parentId: newReply.parentId,
        content: newReply.content,
        authorName: ctx.user.name,
        createdAt: newReply.createdAt,
      };
    }),

  /**
   * Resolve a comment (spec section 10).
   */
  resolve: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
      commentId: z.string().min(1),
    }))
    .mutation(async ({ input, ctx }) => {
      await db
        .update(comments)
        .set({ status: "resolved", resolved: true, updatedAt: new Date() })
        .where(
          and(
            eq(comments.id, input.commentId),
            eq(comments.projectId, ctx.project.id)
          )
        );

      await serverBroadcast(
        `document:${input.documentId}`,
        "comment.resolved",
        {
          commentId: input.commentId,
          documentId: input.documentId,
          resolvedBy: ctx.user.id,
          resolvedByName: ctx.user.name,
        }
      );

      return { success: true };
    }),

  /**
   * Reopen a resolved comment (spec section 10).
   */
  reopen: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
      commentId: z.string().min(1),
    }))
    .mutation(async ({ input, ctx }) => {
      await db
        .update(comments)
        .set({ status: "open", resolved: false, updatedAt: new Date() })
        .where(
          and(
            eq(comments.id, input.commentId),
            eq(comments.projectId, ctx.project.id)
          )
        );

      await serverBroadcast(
        `document:${input.documentId}`,
        "comment.reopened",
        {
          commentId: input.commentId,
          documentId: input.documentId,
          reopenedBy: ctx.user.id,
        }
      );

      return { success: true };
    }),

  /**
   * Delete a comment (spec section 10).
   */
  delete: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
      commentId: z.string().min(1),
    }))
    .mutation(async ({ input, ctx }) => {
      // Only the author or project owner can delete
      const [comment] = await db
        .select()
        .from(comments)
        .where(eq(comments.id, input.commentId));

      if (!comment) {
        throw new Error("Comment not found");
      }

      if (comment.authorId !== ctx.user.id && ctx.memberRole !== "Owner") {
        throw new Error("Not authorized to delete this comment");
      }

      await db.delete(comments).where(eq(comments.id, input.commentId));

      await serverBroadcast(
        `document:${input.documentId}`,
        "comment.deleted",
        {
          commentId: input.commentId,
          documentId: input.documentId,
          deletedBy: ctx.user.id,
        }
      );

      return { success: true };
    }),
});
