import { initTRPC, TRPCError } from "@trpc/server";
import superjson from "superjson";
import { auth } from "../lib/auth";

export const createTRPCContext = async ({ req, res }: { req: any; res: any }) => {
    const authHeader = req.headers.authorization;
    const cookieHeader = req.headers.cookie;
    console.log("[CONTEXT] Headers:", { authorization: !!authHeader, cookie: !!cookieHeader });

    try {
        const session = await auth.api.getSession({
            headers: req.headers,
        });

        if (!session) {
            console.log("[CONTEXT] No session found. Auth Header starts with:", authHeader?.substring(0, 15));
        } else {
            console.log("[CONTEXT] Session verified for user ID:", session.user.id);
        }
        return { session };
    } catch (error: any) {
        console.error("[CONTEXT] Error in getSession:", error);
        return { session: null };
    }
};

const t = initTRPC.context<typeof createTRPCContext>().create({
    transformer: superjson,
});

export const router = t.router;
export const publicProcedure = t.procedure;

export const protectedProcedure = t.procedure.use(async ({ ctx, next }) => {
    if (!ctx.session?.user) {
        throw new TRPCError({
            code: "UNAUTHORIZED",
            message: "You must be logged in to access this service",
        });
    }
    return next({
        ctx: {
            ...ctx,
            user: ctx.session.user,
        },
    });
});
