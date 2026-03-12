import { z } from "zod";
import { createTRPCRouter, protectedProcedure } from "../init";
import { createTRPCClient, httpBatchLink } from "@trpc/client";
import superjson from "superjson";
import { db } from "@/db";
import { projectFiles, projectAssets } from "@/db/schema";
import { eq, and, ne } from "drizzle-orm";
import type { AppRouter as BackendRouter } from "../../../backend/src/trpc/routers/_app";

export const latexRouter = createTRPCRouter({
    compile: protectedProcedure
        .input(
            z.object({
                projectId: z.string(),
                latex: z.string().min(1, "LaTeX content cannot be empty"),
                activeFileId: z.string(),
            })
        )
        .mutation(async ({ input }) => {
            const COMPILE_SERVICE_URL =
                process.env.LATEX_COMPILE_URL || "http://localhost:8080/trpc";

            const backendClient = createTRPCClient<BackendRouter>({
                links: [
                    httpBatchLink({
                        url: COMPILE_SERVICE_URL,
                        transformer: superjson,
                    }),
                ],
            });

            // Fetch other project files (excluding the active one which has unsaved changes potentially)
            const otherFiles = await db.query.projectFiles.findMany({
                where: and(
                    eq(projectFiles.projectId, input.projectId),
                    ne(projectFiles.id, input.activeFileId)
                ),
            });

            // Fetch all assets
            const assets = await db.query.projectAssets.findMany({
                where: eq(projectAssets.projectId, input.projectId),
            });

            const filesPayload = otherFiles.map((f) => ({
                filename: f.fileName,
                data: Buffer.from(f.content || "").toString("base64"),
            }));

            // Read actual asset files from disk and convert to base64
            const fs = await import("fs/promises");
            const path = await import("path");

            const imagesPayload = await Promise.all(
                assets.map(async (a) => {
                    try {
                        // assetUrl is like "/uploads/projectId/fileName.png"
                        const filePath = path.join(process.cwd(), "public", a.assetUrl);
                        const fileBuffer = await fs.readFile(filePath);
                        return {
                            filename: a.assetName,
                            data: fileBuffer.toString("base64"),
                        };
                    } catch (err) {
                        console.error(`Failed to read asset ${a.assetName}:`, err);
                        // Return empty data if file missing, compiler might still survive
                        return { filename: a.assetName, data: "" };
                    }
                })
            );

            try {
                const response = await backendClient.latex.compileLatex.mutate({
                    tex: input.latex,
                    files: filesPayload,
                    images: imagesPayload.filter(img => img.data !== ""), // Only send valid images
                });

                if (!response.success && !response.pdf) {
                    throw new Error(response.logs || "Compilation failed");
                }

                return {
                    pdf: response.pdf,
                    logs: response.logs,
                };
            } catch (err: any) {
                throw new Error(err.message || "Failed to reach compilation service");
            }
        }),
});
