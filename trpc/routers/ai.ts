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

const DEFAULT_PROVIDER_GROUPS: ProviderGroup[] = [
  {
    name: "Gemini Web2API",
    models: [
      { id: "gemini-3.7-flash", label: "Gemini 3.7 Flash", default: true },
      { id: "gemini-3.6-flash", label: "Gemini 3.6 Flash", default: false },
      { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash", default: false },
      { id: "gemini-3.5-flash-thinking", label: "Gemini 3.5 Flash Thinking", default: false },
      { id: "gemini-3.5-flash-thinking-lite", label: "Gemini 3.5 Flash Thinking Lite", default: false },
    ],
  },
  {
    name: "FreeLLM API",
    models: [
      { id: "auto:smart", label: "FreeLLM Auto Smart", default: false },
      { id: "auto", label: "FreeLLM Auto Router", default: false },
      { id: "auto:fast", label: "FreeLLM Auto Fast", default: false },
      { id: "openai/gpt-oss-120b", label: "GPT-OSS-120B", default: false },
    ],
  },
];

export const aiRouter = router({
  models: protectedProcedure.query(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/models`, {
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        const providers: ProviderGroup[] = Array.isArray(data)
          ? data
          : Array.isArray(data?.providers)
          ? data.providers
          : DEFAULT_PROVIDER_GROUPS;

        const defaultModel: string =
          data?.default_model || "gemini-3.7-flash";

        return {
          providers: providers.length > 0 ? providers : DEFAULT_PROVIDER_GROUPS,
          defaultModel,
        };
      }
    } catch (err: any) {
      console.error("Error fetching models from backend via tRPC:", err);
    }

    return {
      providers: DEFAULT_PROVIDER_GROUPS,
      defaultModel: "gemini-3.7-flash",
    };
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
