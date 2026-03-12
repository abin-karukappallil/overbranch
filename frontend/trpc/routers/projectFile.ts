import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { createTRPCRouter, protectedProcedure } from "../init";
import { db } from "@/db/index";
import { projects, projectFiles } from "@/db/schema";

export const projectFileRouter = createTRPCRouter({
    list: protectedProcedure
        .input(z.object({ projectId: z.string().uuid() }))
        .query(async ({ ctx, input }) => {
            // Verify project ownership
            const project = await db.query.projects.findFirst({
                where: eq(projects.id, input.projectId),
            });

            if (!project || project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            const files = await db
                .select()
                .from(projectFiles)
                .where(eq(projectFiles.projectId, input.projectId));

            return files;
        }),

    getContent: protectedProcedure
        .input(z.object({ id: z.string().uuid() }))
        .query(async ({ ctx, input }) => {
            const file = await db.query.projectFiles.findFirst({
                where: eq(projectFiles.id, input.id),
                with: { project: true },
            });

            if (!file || file.project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            return file;
        }),

    create: protectedProcedure
        .input(
            z.object({
                projectId: z.string().uuid(),
                fileName: z.string().min(1).max(255),
                fileType: z.string().default("tex"),
                content: z.string().default(""),
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

            const [file] = await db
                .insert(projectFiles)
                .values({
                    projectId: input.projectId,
                    fileName: input.fileName,
                    fileType: input.fileType,
                    content: input.content,
                })
                .returning();

            return file;
        }),

    update: protectedProcedure
        .input(
            z.object({
                id: z.string().uuid(),
                content: z.string(),
            })
        )
        .mutation(async ({ ctx, input }) => {
            const file = await db.query.projectFiles.findFirst({
                where: eq(projectFiles.id, input.id),
                with: { project: true },
            });

            if (!file || file.project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            const [updated] = await db
                .update(projectFiles)
                .set({ content: input.content })
                .where(eq(projectFiles.id, input.id))
                .returning();

            return updated;
        }),

    rename: protectedProcedure
        .input(
            z.object({
                id: z.string().uuid(),
                fileName: z.string().min(1).max(255),
            })
        )
        .mutation(async ({ ctx, input }) => {
            const file = await db.query.projectFiles.findFirst({
                where: eq(projectFiles.id, input.id),
                with: { project: true },
            });

            if (!file || file.project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            const [updated] = await db
                .update(projectFiles)
                .set({ fileName: input.fileName })
                .where(eq(projectFiles.id, input.id))
                .returning();

            return updated;
        }),

    delete: protectedProcedure
        .input(z.object({ id: z.string().uuid() }))
        .mutation(async ({ ctx, input }) => {
            const file = await db.query.projectFiles.findFirst({
                where: eq(projectFiles.id, input.id),
                with: { project: true },
            });

            if (!file || file.project.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            await db.delete(projectFiles).where(eq(projectFiles.id, input.id));
            return { success: true };
        }),
});
