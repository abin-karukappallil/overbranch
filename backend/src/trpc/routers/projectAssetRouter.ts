import { z } from "zod";
import { eq } from "drizzle-orm";
import { router, protectedProcedure } from "../init";
import { db } from "../../lib/db";
import { projectAssets, projects } from "../../../../frontend/db/schema";
import { writeFile, mkdir, unlink } from "fs/promises";
import path from "path";

// Adjust upload dir to reach the frontend's public folder from backend
const UPLOAD_DIR = path.join(__dirname, "../../../../../frontend/public/uploads");

export const projectAssetRouter = router({
    list: protectedProcedure
        .input(z.object({ projectId: z.string().uuid() }))
        .query(async ({ ctx, input }) => {
            const project = await db.query.projects.findFirst({
                where: eq(projects.id, input.projectId),
            });

            if (!project || project.userId !== (ctx.user as any).id) {
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
            const project = await db.query.projects.findFirst({
                where: eq(projects.id, input.projectId),
            });

            if (!project || project.userId !== (ctx.user as any).id) {
                throw new Error("Unauthorized");
            }

            const projectDir = path.join(UPLOAD_DIR, input.projectId);
            await mkdir(projectDir, { recursive: true });

            const buffer = Buffer.from(input.base64Data, "base64");
            const filePath = path.join(projectDir, input.assetName);
            await writeFile(filePath, buffer);

            const assetUrl = `/uploads/${input.projectId}/${input.assetName}`;

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
});
