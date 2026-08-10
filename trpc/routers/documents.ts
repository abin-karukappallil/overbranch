import { router, projectProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { documentSnapshots } from '@/db/schema';
import { eq, and, desc } from 'drizzle-orm';

export const documentsRouter = router({
  /**
   * Fetch the latest Yjs binary snapshot for a document.
   */
  getSnapshot: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
    }))
    .query(async ({ input, ctx }) => {
      const [snapshot] = await db
        .select()
        .from(documentSnapshots)
        .where(
          and(
            eq(documentSnapshots.projectId, ctx.project.id),
            eq(documentSnapshots.documentId, input.documentId)
          )
        )
        .orderBy(desc(documentSnapshots.createdAt))
        .limit(1);

      return snapshot || null;
    }),

  /**
   * Save a Yjs state snapshot (debounced persistence, spec section 1).
   * Creates a new snapshot row — old ones are compacted periodically.
   */
  saveSnapshot: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
      snapshot: z.string().min(1), // base64-encoded Yjs state
    }))
    .mutation(async ({ input, ctx }) => {
      // Get current version
      const [latest] = await db
        .select({ version: documentSnapshots.version })
        .from(documentSnapshots)
        .where(
          and(
            eq(documentSnapshots.projectId, ctx.project.id),
            eq(documentSnapshots.documentId, input.documentId)
          )
        )
        .orderBy(desc(documentSnapshots.version))
        .limit(1);

      const nextVersion = (latest?.version ?? 0) + 1;

      const [saved] = await db
        .insert(documentSnapshots)
        .values({
          id: crypto.randomUUID(),
          projectId: ctx.project.id,
          documentId: input.documentId,
          snapshot: input.snapshot,
          version: nextVersion,
          savedBy: ctx.user.id,
        })
        .returning();

      return { id: saved.id, version: saved.version };
    }),

  /**
   * Compact old snapshots — keep the latest + N recent (default 5).
   * Call periodically to prevent unbounded growth.
   */
  compactSnapshots: projectProcedure
    .input(z.object({
      documentId: z.string().min(1),
      keepCount: z.number().min(1).max(50).default(5),
    }))
    .mutation(async ({ input, ctx }) => {
      const allSnapshots = await db
        .select({ id: documentSnapshots.id })
        .from(documentSnapshots)
        .where(
          and(
            eq(documentSnapshots.projectId, ctx.project.id),
            eq(documentSnapshots.documentId, input.documentId)
          )
        )
        .orderBy(desc(documentSnapshots.createdAt));

      if (allSnapshots.length <= input.keepCount) {
        return { deleted: 0 };
      }

      const toDelete = allSnapshots.slice(input.keepCount);
      let deleted = 0;

      for (const snap of toDelete) {
        await db.delete(documentSnapshots).where(eq(documentSnapshots.id, snap.id));
        deleted++;
      }

      return { deleted };
    }),
});
