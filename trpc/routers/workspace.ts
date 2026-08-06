import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';

const mockWorkspaces = [
  {
    id: "ws-1",
    name: "Stanford & OverBranch Research Team",
    slug: "stanford-overbranch",
    plan: "Pro Team",
    membersCount: 12,
    role: "Owner",
    avatarUrl: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80",
  },
  {
    id: "ws-2",
    name: "Acme Scientific Computing",
    slug: "acme-scientific",
    plan: "Enterprise",
    membersCount: 34,
    role: "Admin",
    avatarUrl: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80",
  },
];

const mockMembers = [
  { id: "mem-1", name: "Dr. Alice Vance", email: "alice@overbranch.dev", role: "Owner", avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80" },
  { id: "mem-2", name: "Prof. Bob Chen", email: "bob@stanford.edu", role: "Admin", avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80" },
  { id: "mem-3", name: "Carol Zhang", email: "carol@overbranch.dev", role: "Member", avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80" },
];

export const workspaceRouter = router({
  listWorkspaces: publicProcedure.query(async () => {
    return mockWorkspaces;
  }),

  getMembers: publicProcedure
    .input(z.object({ workspaceId: z.string().optional() }))
    .query(async () => {
      return mockMembers;
    }),

  inviteMember: publicProcedure
    .input(z.object({ email: z.string().email(), role: z.enum(["Owner", "Admin", "Member"]).default("Member") }))
    .mutation(async ({ input }) => {
      return { success: true, invitation: { email: input.email, role: input.role, status: "pending" } };
    }),

  switchWorkspace: publicProcedure
    .input(z.object({ id: z.string() }))
    .mutation(async ({ input }) => {
      const selected = mockWorkspaces.find(w => w.id === input.id) || mockWorkspaces[0];
      return { success: true, activeWorkspace: selected };
    }),

  updateWorkspaceSettings: publicProcedure
    .input(z.object({ name: z.string().min(2), slug: z.string().min(2) }))
    .mutation(async ({ input }) => {
      return { success: true, workspace: input };
    }),
});
