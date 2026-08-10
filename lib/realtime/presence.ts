"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getSupabaseClient } from "@/lib/supabase-client";
import type { RealtimeChannel } from "@supabase/supabase-js";

// ─── Color Assignment (spec section 2) ─────────────────────────────

const COLLABORATOR_COLORS = [
  "#6366f1", // indigo
  "#f43f5e", // rose
  "#10b981", // emerald
  "#f59e0b", // amber
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#84cc16", // lime
  "#ef4444", // red
  "#14b8a6", // teal
  "#a855f7", // purple
  "#f97316", // orange
];

/**
 * Deterministic color assignment from userId (spec section 2).
 * Stable across sessions — same user always gets the same color.
 */
export function getCollaboratorColor(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = (hash << 5) - hash + userId.charCodeAt(i);
    hash |= 0; // Convert to 32-bit integer
  }
  return COLLABORATOR_COLORS[Math.abs(hash) % COLLABORATOR_COLORS.length];
}

// ─── Presence Types ─────────────────────────────────────────────────

export interface PresenceUser {
  userId: string;
  name: string;
  avatarUrl: string | null;
  color: string;
  status: "active" | "idle";
  currentDocumentId?: string;
}

export interface CursorPresence extends PresenceUser {
  cursorPos: { lineNumber: number; column: number } | null;
  selection: {
    startLineNumber: number;
    startColumn: number;
    endLineNumber: number;
    endColumn: number;
  } | null;
}

// ─── Document Presence (cursors + selections, spec sections 2, 4) ──

/**
 * Subscribe to Supabase Presence on `document:{documentId}` for cursor and selection tracking.
 * Throttles cursor position updates to ~30ms via requestAnimationFrame.
 */
export function useDocumentPresence(
  documentId: string | null,
  currentUser: { id: string; name: string; image?: string | null } | null
) {
  const [remoteCursors, setRemoteCursors] = useState<CursorPresence[]>([]);
  const channelRef = useRef<RealtimeChannel | null>(null);
  const trackThrottleRef = useRef<number | null>(null);
  const lastTrackedRef = useRef<Record<string, unknown>>({});
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isIdle, setIsIdle] = useState(false);

  useEffect(() => {
    if (!documentId || !currentUser) return;

    const supabase = getSupabaseClient();
    const channelName = `document:${documentId}`;
    const color = getCollaboratorColor(currentUser.id);

    const channel = supabase.channel(channelName, {
      config: {
        presence: { key: currentUser.id },
      },
    });

    channelRef.current = channel;

    // Handle presence sync
    channel.on("presence", { event: "sync" }, () => {
      const state = channel.presenceState<CursorPresence>();
      const users: CursorPresence[] = [];

      for (const [key, presences] of Object.entries(state)) {
        if (key === currentUser.id) continue; // Skip self
        const latest = presences[presences.length - 1];
        if (latest) {
          users.push(latest as CursorPresence);
        }
      }

      setRemoteCursors(users);
    });

    // Subscribe and track initial presence
    channel.subscribe(async (status) => {
      if (status === "SUBSCRIBED") {
        await channel.track({
          userId: currentUser.id,
          name: currentUser.name,
          avatarUrl: currentUser.image || null,
          color,
          cursorPos: null,
          selection: null,
          status: "active",
        });
      }
    });

    return () => {
      if (trackThrottleRef.current) cancelAnimationFrame(trackThrottleRef.current);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      supabase.removeChannel(channel);
      channelRef.current = null;
    };
  }, [documentId, currentUser]);

  /**
   * Update cursor position — throttled to requestAnimationFrame (~16ms).
   */
  const updateCursor = useCallback(
    (pos: { lineNumber: number; column: number } | null) => {
      if (!channelRef.current || !currentUser) return;

      // Reset idle timer on any cursor activity
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      if (isIdle) setIsIdle(false);

      idleTimerRef.current = setTimeout(() => {
        setIsIdle(true);
        channelRef.current?.track({
          ...lastTrackedRef.current,
          status: "idle",
        });
      }, 30000); // 30s idle

      // Throttle via rAF
      if (trackThrottleRef.current) return;

      trackThrottleRef.current = requestAnimationFrame(() => {
        trackThrottleRef.current = null;

        const payload = {
          ...lastTrackedRef.current,
          cursorPos: pos,
          status: "active" as const,
        };
        lastTrackedRef.current = payload;
        channelRef.current?.track(payload);
      });
    },
    [currentUser, isIdle]
  );

  /**
   * Update selection range.
   */
  const updateSelection = useCallback(
    (selection: CursorPresence["selection"]) => {
      if (!channelRef.current || !currentUser) return;

      const payload = {
        ...lastTrackedRef.current,
        selection,
      };
      lastTrackedRef.current = payload;
      channelRef.current?.track(payload);
    },
    [currentUser]
  );

  return {
    remoteCursors,
    updateCursor,
    updateSelection,
    isIdle,
  };
}

// ─── Project Presence (header avatar stack, spec section 3) ─────────

/**
 * Subscribe to Supabase Presence on `project:{projectId}` for the header avatar stack.
 * Shows everyone active anywhere in the project, not just the current document.
 */
export function useProjectPresence(
  projectId: string | null,
  currentUser: { id: string; name: string; image?: string | null } | null,
  currentDocumentId?: string
) {
  const [onlineUsers, setOnlineUsers] = useState<PresenceUser[]>([]);
  const channelRef = useRef<RealtimeChannel | null>(null);

  useEffect(() => {
    if (!projectId || !currentUser) return;

    const supabase = getSupabaseClient();
    const channelName = `project:${projectId}`;
    const color = getCollaboratorColor(currentUser.id);

    const channel = supabase.channel(channelName, {
      config: {
        presence: { key: currentUser.id },
      },
    });

    channelRef.current = channel;

    channel.on("presence", { event: "sync" }, () => {
      const state = channel.presenceState<PresenceUser>();
      const users: PresenceUser[] = [];

      for (const [key, presences] of Object.entries(state)) {
        const latest = presences[presences.length - 1];
        if (latest) {
          users.push(latest as PresenceUser);
        }
      }

      setOnlineUsers(users);
    });

    channel.subscribe(async (status) => {
      if (status === "SUBSCRIBED") {
        await channel.track({
          userId: currentUser.id,
          name: currentUser.name,
          avatarUrl: currentUser.image || null,
          color,
          status: "active",
          currentDocumentId: currentDocumentId || undefined,
        });
      }
    });

    return () => {
      supabase.removeChannel(channel);
      channelRef.current = null;
    };
  }, [projectId, currentUser, currentDocumentId]);

  // Update the tracked currentDocumentId when it changes
  useEffect(() => {
    if (!channelRef.current || !currentUser) return;

    channelRef.current.track({
      userId: currentUser.id,
      name: currentUser.name,
      avatarUrl: currentUser.image || null,
      color: getCollaboratorColor(currentUser.id),
      status: "active",
      currentDocumentId: currentDocumentId || undefined,
    });
  }, [currentDocumentId, currentUser]);

  return { onlineUsers };
}
