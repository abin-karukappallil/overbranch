import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';

const mockProjects = [
  {
    id: "proj-1",
    name: "IEEE_Paper_OverBranch_v1",
    description: "Architectural Foundations for Collaborative LaTeX Editors with real-time PDF recompilation.",
    repository: "overbranch/ieee-paper-2026",
    branch: "main.tex",
    template: "IEEEtran",
    status: "active",
    isFavorite: true,
    collaboratorsCount: 3,
    stars: 142,
    updatedAt: "10 mins ago",
    color: "from-indigo-500/20 to-purple-500/20",
    members: [
      { id: "mem-1", name: "Dr. Alice Vance", email: "alice@overbranch.dev", role: "Owner", avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80" },
      { id: "mem-2", name: "Prof. Bob Chen", email: "bob@stanford.edu", role: "Editor", avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80" },
      { id: "mem-3", name: "Carol Zhang", email: "carol@overbranch.dev", role: "Viewer", avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80" },
    ],
  },
  {
    id: "proj-2",
    name: "arXiv_Quantum_Intelligence_2026",
    description: "Multi-file LaTeX project tree for neural symbol parsing and quantum state matrix formulations.",
    repository: "overbranch/arxiv-quantum-draft",
    branch: "sections/abstract.tex",
    template: "arXiv",
    status: "compiling",
    isFavorite: false,
    collaboratorsCount: 2,
    stars: 88,
    updatedAt: "1 hour ago",
    color: "from-cyan-500/20 to-blue-500/20",
    members: [
      { id: "mem-1", name: "Dr. Alice Vance", email: "alice@overbranch.dev", role: "Owner", avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80" },
      { id: "mem-2", name: "Prof. Bob Chen", email: "bob@stanford.edu", role: "Editor", avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80" },
    ],
  },
  {
    id: "proj-3",
    name: "PhD_Dissertation_Thesis",
    description: "Distributed real-time document synchronization algorithms with BibTeX reference citation manager.",
    repository: "overbranch/phd-dissertation-v2",
    branch: "chapters/ch3_results.tex",
    template: "Book / Thesis",
    status: "active",
    isFavorite: true,
    collaboratorsCount: 4,
    stars: 210,
    updatedAt: "Yesterday",
    color: "from-emerald-500/20 to-teal-500/20",
    members: [
      { id: "mem-1", name: "Dr. Alice Vance", email: "alice@overbranch.dev", role: "Owner", avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80" },
    ],
  },
];

export const projectsRouter = router({
  listProjects: publicProcedure
    .input(z.object({
      search: z.string().optional(),
      template: z.string().optional(),
      favoritesOnly: z.boolean().optional(),
    }).optional())
    .query(async ({ input }) => {
      let filtered = [...mockProjects];
      if (input?.search) {
        const query = input.search.toLowerCase();
        filtered = filtered.filter(p => p.name.toLowerCase().includes(query) || p.description.toLowerCase().includes(query));
      }
      if (input?.template && input.template !== "all") {
        filtered = filtered.filter(p => p.template.toLowerCase().includes(input.template!.toLowerCase()));
      }
      if (input?.favoritesOnly) {
        filtered = filtered.filter(p => p.isFavorite);
      }
      return filtered;
    }),

  getById: publicProcedure
    .input(z.object({ id: z.string() }))
    .query(async ({ input }) => {
      const found = mockProjects.find(p => p.id === input.id);
      return found || mockProjects[0];
    }),

  getMembers: publicProcedure
    .input(z.object({ projectId: z.string() }))
    .query(async ({ input }) => {
      const found = mockProjects.find(p => p.id === input.projectId);
      return found?.members || mockProjects[0].members;
    }),

  inviteMember: publicProcedure
    .input(z.object({
      projectId: z.string(),
      email: z.string().email(),
      role: z.enum(["Editor", "Viewer"]).default("Editor"),
    }))
    .mutation(async ({ input }) => {
      return {
        success: true,
        invitation: { email: input.email, role: input.role, projectId: input.projectId, status: "pending" },
      };
    }),

  removeMember: publicProcedure
    .input(z.object({ projectId: z.string(), memberId: z.string() }))
    .mutation(async ({ input }) => {
      return { success: true, memberId: input.memberId };
    }),

  generateShareLink: publicProcedure
    .input(z.object({ projectId: z.string() }))
    .mutation(async ({ input }) => {
      return { shareUrl: `https://overbranch.dev/editor/${input.projectId}?invite=${Math.random().toString(36).substring(2, 10)}` };
    }),

  createProject: publicProcedure
    .input(z.object({
      name: z.string().min(2),
      description: z.string().optional(),
      template: z.string().default("IEEEtran"),
    }))
    .mutation(async ({ input }) => {
      const newProj = {
        id: `proj-${Date.now()}`,
        name: input.name,
        description: input.description || "Custom scientific manuscript",
        repository: `overbranch/${input.name.toLowerCase().replace(/\s+/g, '-')}`,
        branch: "main.tex",
        template: input.template,
        status: "active",
        isFavorite: false,
        collaboratorsCount: 1,
        stars: 0,
        updatedAt: "Just now",
        color: "from-indigo-500/20 to-cyan-500/20",
        members: [
          { id: "mem-me", name: "You", email: "author@overbranch.dev", role: "Owner", avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80" },
        ],
      };
      return newProj;
    }),

  renameProject: publicProcedure
    .input(z.object({ id: z.string(), name: z.string().min(2) }))
    .mutation(async ({ input }) => {
      return { success: true, id: input.id, name: input.name };
    }),

  toggleFavorite: publicProcedure
    .input(z.object({ id: z.string(), isFavorite: z.boolean() }))
    .mutation(async ({ input }) => {
      return { success: true, id: input.id, isFavorite: input.isFavorite };
    }),

  deleteProject: publicProcedure
    .input(z.object({ id: z.string() }))
    .mutation(async ({ input }) => {
      return { success: true, id: input.id };
    }),

  duplicateProject: publicProcedure
    .input(z.object({ id: z.string() }))
    .mutation(async ({ input }) => {
      return { success: true, id: `proj-${Date.now()}`, message: "Project duplicated successfully" };
    }),
});
