import { router, protectedProcedure, publicProcedure } from '../init';
import { z } from 'zod';

export const userRouter = router({
  getProfile: protectedProcedure.query(async ({ ctx }) => {
    return {
      id: ctx.session.user.id || "usr_overbranch_demo",
      name: ctx.session.user.name || "Alex Rivers",
      email: ctx.session.user.email || "alex@overbranch.dev",
      image: ctx.session.user.image || "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80",
      role: "owner",
      bio: "Senior Scientific Systems Architect & LaTeX Author",
      company: "OverBranch Engineering",
      location: "San Francisco, CA",
    };
  }),

  updateProfile: protectedProcedure
    .input(z.object({
      name: z.string().min(2),
      email: z.string().email(),
      bio: z.string().optional(),
      company: z.string().optional(),
      location: z.string().optional(),
    }))
    .mutation(async ({ input }) => {
      return { success: true, user: input };
    }),
});
