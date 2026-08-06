import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';

const mockNotifications = [
  {
    id: "notif-1",
    title: "PDF Compilation Complete",
    message: "IEEE_Paper_OverBranch_v1 main.tex compiled cleanly in 8ms.",
    type: "success",
    isRead: false,
    createdAt: "10 mins ago",
  },
  {
    id: "notif-2",
    title: "New Co-Author Joined",
    message: "Prof. Bob Chen joined project arXiv_Quantum_Intelligence_2026.",
    type: "info",
    isRead: false,
    createdAt: "1 hour ago",
  },
  {
    id: "notif-3",
    title: "BibTeX Synced",
    message: "Updated references.bib with 14 new DOI citations.",
    type: "info",
    isRead: true,
    createdAt: "Yesterday",
  },
];

export const notificationsRouter = router({
  listNotifications: publicProcedure.query(async () => {
    return mockNotifications;
  }),

  markAsRead: publicProcedure
    .input(z.object({ id: z.string() }))
    .mutation(async ({ input }) => {
      return { success: true, id: input.id };
    }),

  markAllAsRead: publicProcedure.mutation(async () => {
    return { success: true };
  }),
});
