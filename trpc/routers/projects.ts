import { router, publicProcedure, protectedProcedure, projectProcedure, ownerProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { projects, projectMembers, user, notifications } from '@/db/schema';
import { eq, and, or, ilike, desc } from 'drizzle-orm';
import { TRPCError } from '@trpc/server';

export const projectsRouter = router({
  listProjects: protectedProcedure
    .input(z.object({
      search: z.string().optional(),
      template: z.string().optional(),
      favoritesOnly: z.boolean().optional(),
    }).optional())
    .query(async ({ ctx, input }) => {
      const userId = ctx.user.id;

      const owned = await db.select().from(projects).where(eq(projects.ownerId, userId));

      const sharedRecords = await db
        .select({
          project: projects,
          role: projectMembers.role,
        })
        .from(projectMembers)
        .innerJoin(projects, eq(projectMembers.projectId, projects.id))
        .where(eq(projectMembers.userId, userId));

      const ownedList = owned.map((p) => ({
        id: p.id,
        name: p.name,
        description: p.description || "",
        repository: p.repository || "",
        branch: p.defaultBranch || "main.tex",
        template: p.template || "IEEEtran",
        status: p.status || "active",
        isFavorite: p.isFavorite || false,
        role: "Owner" as "Owner" | "Editor" | "Viewer",
        collaboratorsCount: 1,
        stars: p.starsCount || 0,
        updatedAt: p.updatedAt ? new Date(p.updatedAt).toLocaleDateString() : "Recently",
        color: "from-indigo-500/20 to-purple-500/20",
        badgeVariant: "glow" as const,
        isOwner: true,
      }));

      const sharedList = sharedRecords.map(({ project: p, role }) => ({
        id: p.id,
        name: p.name,
        description: p.description || "",
        repository: p.repository || "",
        branch: p.defaultBranch || "main.tex",
        template: p.template || "IEEEtran",
        status: p.status || "active",
        isFavorite: p.isFavorite || false,
        role: role as "Owner" | "Editor" | "Viewer",
        collaboratorsCount: 2,
        stars: p.starsCount || 0,
        updatedAt: p.updatedAt ? new Date(p.updatedAt).toLocaleDateString() : "Recently",
        color: "from-purple-500/20 to-cyan-500/20",
        badgeVariant: "glow" as const,
        isOwner: false,
      }));

      const combinedMap = new Map<string, typeof ownedList[number]>();
      ownedList.forEach((p) => combinedMap.set(p.id, p));
      sharedList.forEach((p) => {
        if (!combinedMap.has(p.id)) {
          combinedMap.set(p.id, p);
        }
      });

      let allProjects = Array.from(combinedMap.values());

      if (input?.search) {
        const q = input.search.toLowerCase();
        allProjects = allProjects.filter(
          (p) => p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q)
        );
      }

      if (input?.template && input.template !== "all") {
        allProjects = allProjects.filter((p) => p.template === input.template);
      }

      if (input?.favoritesOnly) {
        allProjects = allProjects.filter((p) => p.isFavorite);
      }

      return allProjects;
    }),

  getById: projectProcedure.query(async ({ ctx }) => {
    return {
      ...ctx.project,
      role: ctx.memberRole as "Owner" | "Editor" | "Viewer",
      isOwner: ctx.memberRole === "Owner",
    };
  }),

  createProject: protectedProcedure
    .input(
      z.object({
        name: z.string().min(2),
        template: z.string().default("IEEEtran"),
        description: z.string().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const userId = ctx.user.id;
      const projId = crypto.randomUUID();
      const memberId = crypto.randomUUID();

      const [newP] = await db.insert(projects).values({
        id: projId,
        ownerId: userId,
        name: input.name,
        description: input.description || "Scientific LaTeX Document",
        template: input.template,
        repository: `prostack/${input.name.toLowerCase().replace(/\s+/g, '-')}`,
        defaultBranch: "main.tex",
        status: "active",
        isFavorite: false,
      }).returning();

      await db.insert(projectMembers).values({
        id: memberId,
        projectId: projId,
        userId: userId,
        role: "Owner",
      });

      return {
        id: newP.id,
        name: newP.name,
        description: newP.description || "",
        template: newP.template,
        isFavorite: newP.isFavorite,
        role: "Owner",
        collaboratorsCount: 1,
        updatedAt: "Just now",
      };
    }),

  renameProject: ownerProcedure
    .input(z.object({ name: z.string().min(2) }))
    .mutation(async ({ input, ctx }) => {
      await db.update(projects).set({ name: input.name, updatedAt: new Date() }).where(eq(projects.id, ctx.project.id));
      return { success: true, id: ctx.project.id, name: input.name };
    }),

  toggleFavorite: projectProcedure
    .input(z.object({ isFavorite: z.boolean() }))
    .mutation(async ({ input, ctx }) => {
      await db.update(projects).set({ isFavorite: input.isFavorite, updatedAt: new Date() }).where(eq(projects.id, ctx.project.id));
      return { success: true, id: ctx.project.id, isFavorite: input.isFavorite };
    }),

  deleteProject: ownerProcedure
    .mutation(async ({ ctx }) => {
      await db.delete(projects).where(eq(projects.id, ctx.project.id));
      return { success: true, id: ctx.project.id };
    }),

  getMembers: projectProcedure
    .query(async ({ ctx }) => {
      const projectId = ctx.project.id;

      const [ownerUser] = await db.select().from(user).where(eq(user.id, ctx.project.ownerId));

      const memberRecords = await db
        .select({
          memberId: projectMembers.id,
          role: projectMembers.role,
          joinedAt: projectMembers.joinedAt,
          userId: user.id,
          name: user.name,
          email: user.email,
          image: user.image,
        })
        .from(projectMembers)
        .innerJoin(user, eq(projectMembers.userId, user.id))
        .where(eq(projectMembers.projectId, projectId));

      const list = memberRecords.map((m) => ({
        id: m.userId,
        name: m.name,
        email: m.email,
        role: m.userId === ctx.project.ownerId ? "Owner" : m.role,
        avatar: m.image || `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(m.name || 'User')}`,
        isOwner: m.userId === ctx.project.ownerId,
      }));

      if (ownerUser && !list.some((m) => m.id === ownerUser.id)) {
        list.unshift({
          id: ownerUser.id,
          name: ownerUser.name,
          email: ownerUser.email,
          role: "Owner",
          avatar: ownerUser.image || `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(ownerUser.name || 'Owner')}`,
          isOwner: true,
        });
      }

      list.sort((a, b) => (a.isOwner ? -1 : b.isOwner ? 1 : 0));

      return list;
    }),

  removeMember: ownerProcedure
    .input(z.object({ memberUserId: z.string() }))
    .mutation(async ({ input, ctx }) => {
      if (input.memberUserId === ctx.project.ownerId) {
        throw new TRPCError({ code: 'FORBIDDEN', message: 'Project owner cannot be removed' });
      }

      await db
        .delete(projectMembers)
        .where(and(eq(projectMembers.projectId, ctx.project.id), eq(projectMembers.userId, input.memberUserId)));

      await db.insert(notifications).values({
        id: crypto.randomUUID(),
        receiverId: input.memberUserId,
        senderId: ctx.user.id,
        projectId: ctx.project.id,
        type: 'MemberRemoved',
        title: 'Removed from Project',
        message: `You were removed from ${ctx.project.name} by the owner.`,
      });

      return { success: true, removedUserId: input.memberUserId };
    }),

  transferOwnership: ownerProcedure
    .input(z.object({ newOwnerUserId: z.string() }))
    .mutation(async ({ input, ctx }) => {
      const projectId = ctx.project.id;
      const currentOwnerId = ctx.user.id;
      const newOwnerId = input.newOwnerUserId;

      if (currentOwnerId === newOwnerId) {
        throw new TRPCError({ code: 'BAD_REQUEST', message: 'You are already the owner of this project' });
      }

      const [newOwnerUser] = await db.select().from(user).where(eq(user.id, newOwnerId));
      if (!newOwnerUser) {
        throw new TRPCError({ code: 'NOT_FOUND', message: 'Target user does not exist' });
      }

      await db.transaction(async (tx) => {
        await tx.update(projects).set({ ownerId: newOwnerId, updatedAt: new Date() }).where(eq(projects.id, projectId));

        await tx
          .insert(projectMembers)
          .values({
            id: crypto.randomUUID(),
            projectId,
            userId: newOwnerId,
            role: "Owner",
          })
          .onConflictDoUpdate({
            target: [projectMembers.projectId, projectMembers.userId],
            set: { role: "Owner" },
          });

        await tx
          .update(projectMembers)
          .set({ role: "Editor" })
          .where(and(eq(projectMembers.projectId, projectId), eq(projectMembers.userId, currentOwnerId)));

        await tx.insert(notifications).values({
          id: crypto.randomUUID(),
          receiverId: newOwnerId,
          senderId: currentOwnerId,
          projectId,
          type: 'OwnershipTransferred',
          title: 'Project Ownership Transferred',
          message: `You are now the owner of project ${ctx.project.name}.`,
        });
      });

      return { success: true, newOwnerUserId: newOwnerId };
    }),
});
