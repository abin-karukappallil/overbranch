import { z } from "zod";
import { eq } from "drizzle-orm";
import { router, protectedProcedure } from "../init";
import { db } from "../../lib/db";
import { projectFiles, projects } from "../../../../frontend/db/schema";

export const projectFileRouter = router({
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

            if (!file || file.project.userId !== (ctx.user as any).id) {
                throw new Error("Unauthorized");
            }

            const [updated] = await db
                .update(projectFiles)
                .set({ content: input.content })
                .where(eq(projectFiles.id, input.id))
                .returning();

            return updated;
        }),
    // Adding context for other common operations to avoid more errors
    list: protectedProcedure
        .input(z.object({ projectId: z.string().uuid() }))
        .query(async ({ ctx, input }) => {
            const project = await db.query.projects.findFirst({
                where: eq(projects.id, input.projectId),
            });

            if (!project || project.userId !== (ctx.user as any).id) {
                throw new Error("Unauthorized");
            }

            const files = await db
                .select()
                .from(projectFiles)
                .where(eq(projectFiles.projectId, input.projectId));

            return files;
        }),
});
