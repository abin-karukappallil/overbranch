import { router, protectedProcedure } from '../init';
import { z } from 'zod';
import { TRPCError } from '@trpc/server';

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

export interface ModelOption {
  id: string;
  label: string;
  default?: boolean;
}

export interface ProviderGroup {
  name: string;
  models: ModelOption[];
}

export const aiRouter = router({
  models: protectedProcedure.query(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/models`, {
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error(`Failed to fetch models: ${res.statusText}`);
      }
      const data: ProviderGroup[] = await res.json();
      return data;
    } catch (err: any) {
      console.error("Error fetching models from backend via tRPC:", err);
      return [];
    }
  }),

  analyzeFile: protectedProcedure
    .input(
      z.object({
        filename: z.string(),
        fileBase64: z.string(),
        mimeType: z.string().optional(),
        prompt: z.string().min(1),
        provider: z.string().optional(),
        model: z.string().optional(),
      })
    )
    .mutation(async ({ input }) => {
      try {
        const buffer = Buffer.from(input.fileBase64, 'base64');
        const blob = new Blob([buffer], { type: input.mimeType || 'application/octet-stream' });
        const formData = new FormData();
        formData.append('file', blob, input.filename);
        formData.append('prompt', input.prompt);
        if (input.provider) formData.append('provider', input.provider);
        if (input.model) formData.append('model', input.model);
        formData.append('stream', 'false');

        const res = await fetch(`${BACKEND_URL}/api/ai/analyze-file`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          const errText = await res.text();
          let parsed = errText;
          try {
            const j = JSON.parse(errText);
            parsed = j.detail || j.error || errText;
          } catch (_) {}
          throw new TRPCError({
            code: 'BAD_REQUEST',
            message: parsed || 'File analysis failed',
          });
        }

        const data = await res.json();
        return data;
      } catch (err: any) {
        if (err instanceof TRPCError) throw err;
        throw new TRPCError({
          code: 'INTERNAL_SERVER_ERROR',
          message: err?.message || 'File analysis failed',
        });
      }
    }),
});
