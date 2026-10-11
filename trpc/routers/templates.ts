import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';
import { TRPCError } from '@trpc/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface PptTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  thumbnail: string;
  hasThumbnail: boolean;
}

export const templatesRouter = router({
  listTemplates: publicProcedure
    .input(
      z.object({
        category: z.string().optional(),
        search: z.string().optional(),
      }).optional()
    )
    .query(async ({ input }) => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/templates/ppt`, {
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error(`Failed to fetch templates: ${res.statusText}`);
        }
        let list: PptTemplate[] = await res.json();

        // Convert thumbnail path to absolute URL if relative
        list = list.map((t) => ({
          ...t,
          thumbnail: t.thumbnail.startsWith("http") ? t.thumbnail : `${BACKEND_URL}${t.thumbnail}`,
        }));

        if (input?.category && input.category !== "all") {
          list = list.filter((t) => t.category.toLowerCase() === input.category!.toLowerCase());
        }

        if (input?.search && input.search.trim()) {
          const q = input.search.toLowerCase().trim();
          list = list.filter(
            (t) => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
          );
        }

        return list;
      } catch (error) {
        console.error("Error fetching templates from backend:", error);
        return [];
      }
    }),

  getById: publicProcedure
    .input(z.object({ id: z.string() }))
    .query(async ({ input }) => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/templates/ppt`, {
          cache: "no-store",
        });
        if (!res.ok) return null;
        const list: PptTemplate[] = await res.json();
        const found = list.find((t) => t.id === input.id);
        if (found) {
          return {
            ...found,
            thumbnail: found.thumbnail.startsWith("http") ? found.thumbnail : `${BACKEND_URL}${found.thumbnail}`,
          };
        }
        return null;
      } catch {
        return null;
      }
    }),

  useTemplate: publicProcedure
    .input(
      z.object({
        templateId: z.string(),
        name: z.string().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const user = ctx.session?.user;
      let userId = user?.id;

      if (!userId && ctx.guestToken && ctx.guestSessionId) {
        userId = `guest_${ctx.guestSessionId}`;
      }

      if (!userId) {
        throw new TRPCError({
          code: "UNAUTHORIZED",
          message: "Authentication required. Please sign in or provide guest cookies.",
        });
      }

      const forwardHeaders: Record<string, string> = {
        "Content-Type": "application/json",
      };

      if (ctx.rawCookieHeader) {
        forwardHeaders["Cookie"] = ctx.rawCookieHeader;
      }

      if (ctx.sessionToken) {
        const cleanToken = ctx.sessionToken.includes(".")
          ? ctx.sessionToken.split(".")[0].trim()
          : ctx.sessionToken.trim();
        forwardHeaders["Authorization"] = `Bearer ${cleanToken}`;
      } else if (ctx.guestToken) {
        forwardHeaders["X-Guest-Token"] = ctx.guestToken;
      }

      forwardHeaders["X-User-Id"] = userId;

      const res = await fetch(`${BACKEND_URL}/api/templates/ppt/${encodeURIComponent(input.templateId)}/use`, {
        method: "POST",
        headers: forwardHeaders,
        body: JSON.stringify({
          user_id: userId,
          name: input.name,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: "Failed to use template" }));
        throw new Error(errJson.detail || "Failed to create project from template");
      }

      const result = await res.json();
      return result as { success: boolean; projectId: string; id: string; name: string; template: string };
    }),
});
