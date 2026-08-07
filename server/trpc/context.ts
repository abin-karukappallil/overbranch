import { initTRPC, TRPCError } from '@trpc/server';
import { auth } from '@/lib/auth';
import superjson from 'superjson';
import { headers } from 'next/headers';

export const createContext = async () => {
  const requestHeaders = await headers();
  const session = await auth.api.getSession({
    headers: requestHeaders,
  });

  return {
    session,
    user: session?.user || null,
  };
};

export type Context = Awaited<ReturnType<typeof createContext>>;
