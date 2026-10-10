/**
 * lib/collab/log.ts — Client-side structured collaboration logging
 * ================================================================
 * Mirrors the backend's event vocabulary (`backend/collab/events.py`) so a
 * session can be read end to end. Off unless
 * `NEXT_PUBLIC_COLLAB_DEBUG=1`, or `localStorage.ob_collab_debug = "1"` —
 * the latter so a specific user's browser can be put into debug without a
 * redeploy. Connection-level failures are always warned about.
 */

export type CollabEvent =
  | "COLLAB_CONNECT"
  | "COLLAB_DISCONNECT"
  | "COLLAB_JOIN"
  | "COLLAB_LEAVE"
  | "COLLAB_SYNC"
  | "COLLAB_PERSIST"
  | "COLLAB_RECONNECT"
  | "COLLAB_AUTH_FAILURE"
  | "COLLAB_CONFLICT"
  | "COLLAB_BIND"
  | "COLLAB_UNBIND"
  | "COLLAB_AI_EDIT"
  | "COLLAB_ERROR";

const ALWAYS_VISIBLE: ReadonlySet<CollabEvent> = new Set<CollabEvent>([
  "COLLAB_AUTH_FAILURE",
  "COLLAB_ERROR",
]);

let cachedFlag: boolean | null = null;

export function collabDebugEnabled(): boolean {
  if (cachedFlag !== null) return cachedFlag;
  let enabled = process.env.NEXT_PUBLIC_COLLAB_DEBUG === "1";
  if (!enabled && typeof window !== "undefined") {
    try {
      enabled = window.localStorage.getItem("ob_collab_debug") === "1";
    } catch {
      // Private mode / blocked storage: keep logging off.
    }
  }
  cachedFlag = enabled;
  return enabled;
}

export function collabLog(event: CollabEvent, fields: Record<string, unknown> = {}): void {
  if (ALWAYS_VISIBLE.has(event)) {
    console.warn(`[collab] ${event}`, fields);
    return;
  }
  if (!collabDebugEnabled()) return;
  console.info(`[collab] ${event}`, fields);
}
