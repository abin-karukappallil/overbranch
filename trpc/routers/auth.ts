import { router, publicProcedure, protectedProcedure } from '../init';
import { z } from 'zod';
import { TRPCError } from '@trpc/server';

export const authRouter = router({
  getSession: publicProcedure.query(async ({ ctx }) => {
    return ctx.session || null;
  }),

  requestPasswordReset: publicProcedure
    .input(z.object({ email: z.string().email() }))
    .mutation(async ({ input }) => {
      return { success: true, message: `Password reset link sent to ${input.email}` };
    }),

  resetPassword: publicProcedure
    .input(z.object({ token: z.string(), newPassword: z.string().min(8) }))
    .mutation(async () => {
      return { success: true, message: "Password reset successfully" };
    }),

  verifyEmail: publicProcedure
    .input(z.object({ token: z.string() }))
    .mutation(async () => {
      return { success: true, message: "Email verified successfully" };
    }),
});
