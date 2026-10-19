import { db } from '@/db';
import { user as userTable, guestSessions, projects } from '@/db/schema';
import { eq, and, lt, gt, or, like } from 'drizzle-orm';
import fs from 'fs';
import path from 'path';

/**
 * Removes all expired guest sessions and their corresponding guest users from the user table.
 * Also removes any orphaned guest users that have no active unexpired session.
 */
export async function cleanupExpiredGuestUsers() {
  const now = new Date();
  let purgedUsersCount = 0;
  let purgedSessionsCount = 0;

  try {
    // 1. Find all expired guest sessions
    const expiredSessions = await db
      .select({ id: guestSessions.id })
      .from(guestSessions)
      .where(lt(guestSessions.expiresAt, now));

    for (const s of expiredSessions) {
      const guestUserId = `guest_${s.id}`;

      // Clean up projects directory on disk if any exist
      try {
        const guestProjectsList = await db
          .select({ id: projects.id })
          .from(projects)
          .where(eq(projects.ownerId, guestUserId));

        for (const p of guestProjectsList) {
          const diskPath = path.resolve(process.cwd(), 'uploads', 'projects', p.id);
          if (fs.existsSync(diskPath)) {
            fs.rmSync(diskPath, { recursive: true, force: true });
          }
        }
      } catch (fsErr) {
        console.warn(`[guest-cleanup] Error removing disk paths for ${guestUserId}:`, fsErr);
      }

      // Delete from user table and guest_sessions table
      await db.delete(userTable).where(eq(userTable.id, guestUserId));
      await db.delete(guestSessions).where(eq(guestSessions.id, s.id));
      purgedUsersCount++;
      purgedSessionsCount++;
    }

    // 2. Sweep any orphaned guest users in the user table whose session is expired or missing
    const guestUsers = await db
      .select({ id: userTable.id })
      .from(userTable)
      .where(or(like(userTable.id, 'guest_%'), eq(userTable.role, 'guest')));

    for (const gu of guestUsers) {
      const sid = gu.id.startsWith('guest_') ? gu.id.replace('guest_', '') : null;
      if (sid) {
        const [activeSession] = await db
          .select({ id: guestSessions.id })
          .from(guestSessions)
          .where(and(eq(guestSessions.id, sid), gt(guestSessions.expiresAt, now)));

        if (!activeSession) {
          try {
            const guestProjectsList = await db
              .select({ id: projects.id })
              .from(projects)
              .where(eq(projects.ownerId, gu.id));

            for (const p of guestProjectsList) {
              const diskPath = path.resolve(process.cwd(), 'uploads', 'projects', p.id);
              if (fs.existsSync(diskPath)) {
                fs.rmSync(diskPath, { recursive: true, force: true });
              }
            }
          } catch (pErr) {
            console.warn(`[guest-cleanup] Error cleaning projects for ${gu.id}:`, pErr);
          }

          await db.delete(userTable).where(eq(userTable.id, gu.id));
          purgedUsersCount++;
        }
      } else {
        await db.delete(userTable).where(eq(userTable.id, gu.id));
        purgedUsersCount++;
      }
    }
  } catch (err) {
    console.warn('[guest-cleanup] Error during cleanup:', err);
  }

  return { success: true, purgedUsersCount, purgedSessionsCount };
}
