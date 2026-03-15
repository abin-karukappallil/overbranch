import { z } from "zod";
import { eq, desc } from "drizzle-orm";
import { router, protectedProcedure } from "../init";
import { db } from "../../lib/db";
import { projects, projectFiles } from "../../../../frontend/db/schema";

const DEFAULT_TEX = `\\documentclass{article}
\\begin{document}
Hello World
\\end{document}`;

export const projectRouter = router({
    list: protectedProcedure.query(async ({ ctx }) => {
        const userProjects = await db
            .select()
            .from(projects)
            .where(eq(projects.userId, (ctx.user as any).id))
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

            if (project.userId !== (ctx.user as any).id) {
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
                    userId: (ctx.user as any).id,
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
});
