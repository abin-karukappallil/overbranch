import { z } from "zod";
import { eq } from "drizzle-orm";
import { createTRPCRouter, protectedProcedure } from "../init";
import { db } from "@/db/index";
import { projects, projectAssets } from "@/db/schema";
import { writeFile, mkdir, unlink } from "fs/promises";
import path from "path";

const UPLOAD_DIR = path.join(process.cwd(), "public", "uploads");

export const projectAssetRouter = createTRPCRouter({
    list: protectedProcedure
        .input(z.object({ projectId: z.string().uuid() }))
        .query(async ({ ctx, input }) => {
            const project = await db.query.projects.findFirst({
                where: eq(projects.id, input.projectId),
            });

            if (!project || project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            const assets = await db
                .select()
                .from(projectAssets)
                .where(eq(projectAssets.projectId, input.projectId));

            return assets;
        }),

    upload: protectedProcedure
        .input(
            z.object({
                projectId: z.string().uuid(),
                assetName: z.string().min(1),
                assetType: z.enum(["image", "file"]),
                base64Data: z.string(),
            })
        )
        .mutation(async ({ ctx, input }) => {
            // Verify project ownership
            const project = await db.query.projects.findFirst({
                where: eq(projects.id, input.projectId),
            });

            if (!project || project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            // Create upload directory
            const projectDir = path.join(UPLOAD_DIR, input.projectId);
            await mkdir(projectDir, { recursive: true });

            // Decode and save file
            const buffer = Buffer.from(input.base64Data, "base64");
            const filePath = path.join(projectDir, input.assetName);
            await writeFile(filePath, buffer);

            const assetUrl = `/uploads/${input.projectId}/${input.assetName}`;

            // Store metadata
            const [asset] = await db
                .insert(projectAssets)
                .values({
                    projectId: input.projectId,
                    assetName: input.assetName,
                    assetType: input.assetType,
                    assetUrl,
                })
                .returning();

            return asset;
        }),

    delete: protectedProcedure
        .input(z.object({ id: z.string().uuid() }))
        .mutation(async ({ ctx, input }) => {
            const asset = await db.query.projectAssets.findFirst({
                where: eq(projectAssets.id, input.id),
                with: { project: true },
            });

            if (!asset || asset.project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            // Delete the file from disk
            try {
                const filePath = path.join(process.cwd(), "public", asset.assetUrl);
                await unlink(filePath);
            } catch {
                // File may not exist, continue
            }

            await db.delete(projectAssets).where(eq(projectAssets.id, input.id));
            return { success: true };
        }),
});
