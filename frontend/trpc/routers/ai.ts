import { createTRPCRouter, protectedProcedure } from "../init";
import { z } from "zod";
import { createTRPCClient, httpBatchLink } from "@trpc/client";
import superjson from "superjson";
import type { AppRouter as BackendRouter } from "../../../backend/src/trpc/routers/_app";

const messageSchema = z.object({
    role: z.enum(["system", "user", "assistant"]),
    content: z.string(),
});

export const aiRouter = createTRPCRouter({
    chat: protectedProcedure
        .input(
            z.object({
                apiKey: z.string().min(1, "API key is required"),
                model: z.string().default("qwen-qwq-32b"),
                messages: z.array(messageSchema).min(1),
            })
        )
        .mutation(async ({ ctx, input }) => {
            const COMPILE_SERVICE_URL =
                process.env.NEXT_PUBLIC_LATEX_COMPILE_URL || "http://localhost:8080/trpc";

            const backendClient = createTRPCClient<BackendRouter>({
                links: [
                    httpBatchLink({
                        url: COMPILE_SERVICE_URL,
                        transformer: superjson,
                        headers: () => {
                            return {
                                authorization: `Bearer ${ctx.session?.session.token}`,
                            };
                        },
                    }),
                ],
            });

            return backendClient.ai.chat.mutate(input);
        }),
});

