import { auth } from '@/lib/auth';
import { headers, cookies } from 'next/headers';
import { db } from '@/db';
import { session as sessionTable, user as userTable } from '@/db/schema';
import { eq, and, gt } from 'drizzle-orm';

export interface ServerUser {
  id: string;
  name: string;
  email: string;
  emailVerified: boolean;
  image?: string | null;
  role?: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface ServerSession {
  user: ServerUser;
  session: {
    id: string;
    token: string;
    userId: string;
    expiresAt: Date;
    createdAt: Date;
    updatedAt: Date;
    ipAddress?: string | null;
    userAgent?: string | null;
  };
}

export async function getServerSession(): Promise<ServerSession | null> {
  const reqHeaders = await headers();
  let sessionResult: any = null;

  try {
    sessionResult = await Promise.race([
      auth.api.getSession({
        headers: reqHeaders,
      }),
      new Promise<null>((resolve) => {
        const timer = setTimeout(() => resolve(null), 3000);
        if (typeof timer === 'object' && 'unref' in timer) {
          (timer as any).unref();
        }
      }),
    ]);
  } catch (err) {
    console.warn('[getServerSession] Failed to get session via auth.api:', err);
    sessionResult = null;
  }

  if (sessionResult?.user) {
    return sessionResult as ServerSession;
  }

  // Fallback: direct DB lookup using session token cookie
  try {
    const cookieStore = await cookies();
    const sessionCookie =
      cookieStore.get('__Secure-better-auth.session_token')?.value ||
      cookieStore.get('better-auth.session_token')?.value ||
      cookieStore.get('session_token')?.value;

    if (sessionCookie) {
      const rawToken = sessionCookie.split('.')[0];
      const [dbSession] = await db
        .select()
        .from(sessionTable)
        .where(and(eq(sessionTable.token, rawToken), gt(sessionTable.expiresAt, new Date())));

      if (dbSession) {
        const [dbUser] = await db
          .select()
          .from(userTable)
          .where(eq(userTable.id, dbSession.userId));

        if (dbUser) {
          return {
            user: dbUser,
            session: dbSession,
          };
        }
      }
    }
  } catch (err) {
    console.warn('[getServerSession] Fallback session lookup failed:', err);
  }

  return null;
}
