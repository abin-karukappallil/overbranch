import { z } from "zod";
import { eq, desc } from "drizzle-orm";
import { createTRPCRouter, protectedProcedure } from "../init";
import { db } from "@/db/index";
import { projects, projectFiles } from "@/db/schema";

const DEFAULT_TEX = `\\documentclass{article}
\\begin{document}
Hello World
\\end{document}`;

export const projectRouter = createTRPCRouter({
    list: protectedProcedure.query(async ({ ctx }) => {
        const userProjects = await db
            .select()
            .from(projects)
            .where(eq(projects.userId, ctx.user.id))
            .orderBy(desc(projects.updatedAt));
        return userProjects;
    }),

    getById: protectedProcedure
        .input(z.object({ id: z.string().uuid() }))
        .query(async ({ ctx, input }) => {
            const project = await db.query.projects.findFirst({
                where: eq(projects.id, input.id),
                with: {
                    files: true,
                    assets: true,
                },
            });

            if (!project) {
                throw new Error("Project not found");
            }

            if (project.userId !== ctx.user.id) {
                throw new Error("Unauthorized: You do not own this project");
            }

            return project;
        }),

    create: protectedProcedure
        .input(
            z.object({
                name: z.string().min(1).max(100),
                description: z.string().max(500).optional(),
            })
        )
        .mutation(async ({ ctx, input }) => {
            const [project] = await db
                .insert(projects)
                .values({
                    userId: ctx.user.id,
                    name: input.name,
                    description: input.description || "",
                })
                .returning();

            // Create a default main.tex file
            await db.insert(projectFiles).values({
                projectId: project.id,
                fileName: "main.tex",
                fileType: "tex",
                content: DEFAULT_TEX,
            });

            return project;
        }),

    update: protectedProcedure
        .input(
            z.object({
                id: z.string().uuid(),
                name: z.string().min(1).max(100).optional(),
                description: z.string().max(500).optional(),
            })
        )
        .mutation(async ({ ctx, input }) => {
            // Verify ownership
            const existing = await db.query.projects.findFirst({
                where: eq(projects.id, input.id),
            });

            if (!existing || existing.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            const [updated] = await db
                .update(projects)
                .set({
                    ...(input.name !== undefined && { name: input.name }),
                    ...(input.description !== undefined && { description: input.description }),
                })
                .where(eq(projects.id, input.id))
                .returning();

            return updated;
        }),

    delete: protectedProcedure
        .input(z.object({ id: z.string().uuid() }))
        .mutation(async ({ ctx, input }) => {
            const existing = await db.query.projects.findFirst({
                where: eq(projects.id, input.id),
            });

            if (!existing || existing.userId !== ctx.user.id) {
                throw new Error("Unauthorized");
            }

            await db.delete(projects).where(eq(projects.id, input.id));
            return { success: true };
        }),
});
