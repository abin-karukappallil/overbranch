import { z } from "zod";
import { createTRPCRouter, publicProcedure } from "../init";

export const latexRouter = createTRPCRouter({
    compile: publicProcedure
        .input(
            z.object({
                latex: z.string().min(1, "LaTeX content cannot be empty"),
            })
        )
        .mutation(async ({ input }) => {
            // Forward the compile request to your LaTeX compilation service
            // Replace this URL with your actual LaTeX compiler endpoint
            const COMPILE_SERVICE_URL =
                process.env.LATEX_COMPILE_URL || "http://localhost:8080/compile";

            const response = await fetch(COMPILE_SERVICE_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ latex: input.latex }),
            });

            if (!response.ok) {
                const contentType = response.headers.get("content-type") || "";
                let errorMsg = `Compilation failed (HTTP ${response.status})`;

                if (contentType.includes("application/json")) {
                    const json = await response.json();
                    errorMsg = json.error || json.message || errorMsg;
                } else if (contentType.includes("text/plain")) {
                    errorMsg = await response.text();
                }

                throw new Error(errorMsg);
            }

            const contentType = response.headers.get("content-type") || "";
            if (!contentType.includes("application/pdf")) {
                throw new Error(
                    "Compile service did not return a PDF. Check your service configuration."
                );
            }

            // Convert the PDF to base64 to send over tRPC
            const arrayBuffer = await response.arrayBuffer();
            const base64 = Buffer.from(arrayBuffer).toString("base64");

            return {
                pdf: base64,
                contentType: "application/pdf",
            };
        }),
});
