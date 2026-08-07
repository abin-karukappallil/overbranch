import { router, projectProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { comments, user } from '@/db/schema';
import { eq, desc, and } from 'drizzle-orm';

export const commentsRouter = router({
  listComments: projectProcedure.query(async ({ ctx }) => {
    const projectId = ctx.project.id;

    const list = await db
      .select({
        id: comments.id,
        content: comments.content,
        resolved: comments.resolved,
        createdAt: comments.createdAt,
        authorId: comments.authorId,
        authorName: user.name,
        authorEmail: user.email,
        authorImage: user.image,
      })
      .from(comments)
      .innerJoin(user, eq(comments.authorId, user.id))
      .where(eq(comments.projectId, projectId))
      .orderBy(desc(comments.createdAt));

    return list.map((c) => ({
      ...c,
      authorAvatar: c.authorImage || `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(c.authorName || 'Author')}`,
      createdAtFormatted: c.createdAt ? new Date(c.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now",
    }));
  }),

  createComment: projectProcedure
    .input(z.object({
      content: z.string().min(1),
    }))
    .mutation(async ({ input, ctx }) => {
      const commentId = crypto.randomUUID();

      const [newComment] = await db
        .insert(comments)
        .values({
          id: commentId,
          projectId: ctx.project.id,
          authorId: ctx.user.id,
          content: input.content,
          resolved: false,
        })
        .returning();

      return {
        id: newComment.id,
        content: newComment.content,
        resolved: newComment.resolved,
        createdAt: newComment.createdAt,
        authorName: ctx.user.name,
        authorEmail: ctx.user.email,
      };
    }),

  resolveComment: projectProcedure
    .input(z.object({ commentId: z.string().uuid() }))
    .mutation(async ({ input, ctx }) => {
      await db
        .update(comments)
        .set({ resolved: true, updatedAt: new Date() })
        .where(and(eq(comments.id, input.commentId), eq(comments.projectId, ctx.project.id)));

      return { success: true, id: input.commentId };
    }),
});
