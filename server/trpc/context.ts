import { auth } from '@/lib/auth';
import { headers } from 'next/headers';

export const createContext = async () => {
  const requestHeaders = await headers();
  let session = null;
  try {
    session = await Promise.race([
      auth.api.getSession({
        headers: requestHeaders,
      }),
      new Promise<null>((resolve) => {
        const timer = setTimeout(() => resolve(null), 5000);
        if (typeof timer === 'object' && 'unref' in timer) {
          (timer as any).unref();
        }
      }),
    ]);
  } catch (err) {
    console.warn('[tRPC Context] Failed to get session:', err);
  }

  return {
    session,
    user: session?.user || null,
  };
};

export type Context = Awaited<ReturnType<typeof createContext>>;
