import { createTRPCRouter, protectedProcedure } from "../init";
import { z } from "zod";
import { TRPCError } from "@trpc/server";

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
        .mutation(async ({ input }) => {
            const { apiKey, model, messages } = input;

            try {
                const response = await fetch(
                    "https://api.groq.com/openai/v1/chat/completions",
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${apiKey}`,
                        },
                        body: JSON.stringify({
                            model,
                            messages,
                            temperature: 0.3,
                            max_tokens: 8192,
                        }),
                    }
                );

                if (!response.ok) {
                    const errorBody = await response.text();
                    let errorMessage = `Groq API error (${response.status})`;
                    try {
                        const parsed = JSON.parse(errorBody);
                        errorMessage = parsed?.error?.message || errorMessage;
                    } catch {
                        // use default
                    }
                    throw new TRPCError({
                        code: "BAD_REQUEST",
                        message: errorMessage,
                    });
                }

                const data = await response.json();
                const content = data?.choices?.[0]?.message?.content || "";

                return { content, model: data?.model || model };
            } catch (error) {
                if (error instanceof TRPCError) throw error;
                throw new TRPCError({
                    code: "INTERNAL_SERVER_ERROR",
                    message:
                        error instanceof Error
                            ? error.message
                            : "Failed to communicate with Groq API",
                });
            }
        }),
});
