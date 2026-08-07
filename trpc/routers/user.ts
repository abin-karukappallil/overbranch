import { router, protectedProcedure } from '../init';
import { z } from 'zod';
import { db } from '@/db';
import { user } from '@/db/schema';
import { ilike, ne, and, eq } from 'drizzle-orm';

export const userRouter = router({
  getProfile: protectedProcedure.query(async ({ ctx }) => {
    const [u] = await db.select().from(user).where(eq(user.id, ctx.user.id));
    return {
      id: ctx.user.id,
      name: u?.name || ctx.user.name || "LaTeX User",
      email: u?.email || ctx.user.email,
      image: u?.image || ctx.user.image || `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(ctx.user.name || 'User')}`,
      role: u?.role || "user",
    };
  }),

  searchByEmail: protectedProcedure
    .input(z.object({ query: z.string().min(1) }))
    .query(async ({ input, ctx }) => {
      const searchTerm = `%${input.query.trim().toLowerCase()}%`;

      const results = await db
        .select({
          id: user.id,
          name: user.name,
          email: user.email,
          image: user.image,
        })
        .from(user)
        .where(
          and(
            ilike(user.email, searchTerm),
            ne(user.id, ctx.user.id)
          )
        )
        .limit(8);

      return results.map((u) => ({
        ...u,
        avatar: u.image || `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(u.name || 'User')}`,
      }));
    }),

  updateProfile: protectedProcedure
    .input(z.object({
      name: z.string().min(2),
      email: z.string().email(),
    }))
    .mutation(async ({ input, ctx }) => {
      await db.update(user).set({ name: input.name, email: input.email }).where(eq(user.id, ctx.user.id));
      return { success: true, user: input };
    }),
});
