import { router, protectedProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { sql } from 'drizzle-orm';

export const projectRouter = router({
  getProjectCode: protectedProcedure
    .input(z.object({
      projectId: z.string(),
      filePath: z.string().default('main.tex'),
    }))
    .query(async ({ ctx, input }) => {
      const result = await db.execute<{
        id: string;
        project_id: string;
        file_path: string;
        raw_code: string;
        updated_at: string;
      }>(sql`
        SELECT id, project_id, file_path, raw_code, updated_at
        FROM latex_documents
        WHERE project_id = ${input.projectId}::uuid AND file_path = ${input.filePath}
        LIMIT 1
      `);

      const rows = Array.isArray(result) ? result : (result as any).rows ?? [];

      if (rows.length === 0) {
        return {
          projectId: input.projectId,
          filePath: input.filePath,
          rawCode: null,
          updatedAt: null,
        };
      }

      const doc = rows[0];
      return {
        projectId: doc.project_id,
        filePath: doc.file_path,
        rawCode: doc.raw_code,
        updatedAt: doc.updated_at,
      };
    }),

  saveProjectCode: protectedProcedure
    .input(z.object({
      projectId: z.string(),
      filePath: z.string().default('main.tex'),
      rawCode: z.string(),
    }))
    .mutation(async ({ ctx, input }) => {
      const existing = await db.execute<{ id: string }>(sql`
        SELECT id FROM latex_documents
        WHERE project_id = ${input.projectId}::uuid AND file_path = ${input.filePath}
        LIMIT 1
      `);

      const existingRows = Array.isArray(existing) ? existing : (existing as any).rows ?? [];

      if (existingRows.length > 0) {
        await db.execute(sql`
          UPDATE latex_documents
          SET raw_code = ${input.rawCode}, updated_at = NOW()
          WHERE project_id = ${input.projectId}::uuid AND file_path = ${input.filePath}
        `);
      } else {
        await db.execute(sql`
          INSERT INTO latex_documents (project_id, file_path, raw_code, updated_at)
          VALUES (${input.projectId}::uuid, ${input.filePath}, ${input.rawCode}, NOW())
        `);
      }

      try {
        const backendUrl = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');
        await fetch(`${backendUrl}/api/compile`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tex_content: input.rawCode,
            engine: 'pdfLaTeX',
          }),
        });
      } catch { }

      return {
        success: true,
        projectId: input.projectId,
        filePath: input.filePath,
      };
    }),
});
