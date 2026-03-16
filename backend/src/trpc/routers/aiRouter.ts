import { z } from "zod";
import { router, protectedProcedure } from "../init";
import { TRPCError } from "@trpc/server";

const messageSchema = z.object({
    role: z.enum(["system", "user", "assistant"]),
    content: z.string(),
});

const MAX_RETRIES = 3;

async function callGroqWithRetry(
    apiKey: string,
    model: string,
    messages: z.infer<typeof messageSchema>[],
    attempt: number = 1
): Promise<{ content: string; model: string }> {
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
                max_tokens: 32768,
            }),
        }
    );

    if (!response.ok) {
        const errorBody = await response.text();
        let errorMessage = `Groq API error (${response.status})`;
        let retryAfterSeconds = 0;
        let isMaxTokensError = false;

        try {
            const parsed = JSON.parse(errorBody);
            errorMessage = parsed?.error?.message || errorMessage;

            // Extract retry delay from rate limit error message
            const retryMatch = errorMessage.match(/try again in (\d+\.?\d*)s/i);
            if (retryMatch) {
                retryAfterSeconds = Math.ceil(parseFloat(retryMatch[1]));
            }

            // Detect if model doesn't support 32k max_tokens (e.g. gpt-oss-120b limit is 16384)
            if (errorMessage.includes("max_tokens") && errorMessage.includes("less than or equal to")) {
                isMaxTokensError = true;
            }
        } catch {
            // use default
        }

        // Auto-retry on rate limit (429) if we have retries left
        if (response.status === 429 && attempt <= MAX_RETRIES) {
            const waitTime = Math.max(retryAfterSeconds, 5) * 1000; // minimum 5s
            console.log(`[AI] Rate limited on ${model}. Retrying in ${waitTime / 1000}s (attempt ${attempt}/${MAX_RETRIES})...`);
            await new Promise((resolve) => setTimeout(resolve, waitTime));
            return callGroqWithRetry(apiKey, model, messages, attempt + 1);
        }

        // Auto fallback if we hit a hard token limit structural error
        if (isMaxTokensError && attempt === 1) {
            console.log(`[AI] Model ${model} rejected 32k max_tokens. Falling back to safe 8192 limit...`);
            // To achieve this without rewriting the entire function signature, we'll just slice the body
            const fallbackResponse = await fetch(
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
            if (!fallbackResponse.ok) {
                const fallbackError = await fallbackResponse.text();
                throw new TRPCError({ code: "BAD_REQUEST", message: `Fallback failed: ${fallbackError}` });
            }
            const data = (await fallbackResponse.json()) as any;
            return { content: data?.choices?.[0]?.message?.content || "", model: data?.model || model };
        }

        throw new TRPCError({
            code: response.status === 429 ? "TOO_MANY_REQUESTS" : "BAD_REQUEST",
            message: errorMessage,
        });
    }

    const data = (await response.json()) as any;
    const content = data?.choices?.[0]?.message?.content || "";

    return { content, model: data?.model || model };
}

export const aiRouter = router({
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
                return await callGroqWithRetry(apiKey, model, messages);
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
