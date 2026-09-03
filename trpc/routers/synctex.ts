import { router, protectedProcedure } from '../init';
import { z } from 'zod';
import { TRPCError } from '@trpc/server';

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

export const synctexRouter = router({
  forward: protectedProcedure
    .input(
      z.object({
        projectId: z.string().optional(),
        file: z.string().min(1),
        line: z.number().int().positive(),
        column: z.number().int().nonnegative().optional(),
      })
    )
    .mutation(async ({ input }) => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/synctex/forward`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: input.projectId || "",
            file: input.file,
            line: input.line,
            column: input.column || 1,
          }),
        });

        if (!res.ok) {
          const errText = await res.text();
          let parsed = errText;
          try {
            const j = JSON.parse(errText);
            parsed = j.detail || j.message || errText;
          } catch (_) {}
          throw new TRPCError({
            code: res.status === 404 ? 'NOT_FOUND' : 'BAD_REQUEST',
            message: parsed || "SyncTeX forward lookup failed",
          });
        }

        const data = await res.json();
        return data;
      } catch (err: any) {
        if (err instanceof TRPCError) throw err;
        throw new TRPCError({
          code: 'INTERNAL_SERVER_ERROR',
          message: err?.message || "SyncTeX forward service error",
        });
      }
    }),

  backward: protectedProcedure
    .input(
      z.object({
        projectId: z.string().optional(),
        page: z.number().int().positive(),
        x: z.number(),
        y: z.number(),
      })
    )
    .mutation(async ({ input }) => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/synctex/backward`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: input.projectId || "",
            page: input.page,
            x: input.x,
            y: input.y,
          }),
        });

        if (!res.ok) {
          const errText = await res.text();
          let parsed = errText;
          try {
            const j = JSON.parse(errText);
            parsed = j.detail || j.message || errText;
          } catch (_) {}
          throw new TRPCError({
            code: res.status === 404 ? 'NOT_FOUND' : 'BAD_REQUEST',
            message: parsed || "SyncTeX backward lookup failed",
          });
        }

        const data = await res.json();
        return data;
      } catch (err: any) {
        if (err instanceof TRPCError) throw err;
        throw new TRPCError({
          code: 'INTERNAL_SERVER_ERROR',
          message: err?.message || "SyncTeX backward service error",
        });
      }
    }),
});
