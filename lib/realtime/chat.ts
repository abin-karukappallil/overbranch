"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getSupabaseClient } from "@/lib/supabase-client";
import type { RealtimeChannel } from "@supabase/supabase-js";

// ─── Chat Message Types ─────────────────────────────────────────────

export interface RealtimeChatMessage {
  id: string;
  projectId: string;
  authorId: string;
  authorName: string | null;
  authorEmail: string | null;
  authorImage: string | null;
  authorAvatar: string;
  body: string;
  mentionedUserIds: string[];
  createdAt: string;
  status?: "sending" | "sent" | "failed";
}

// ─── useProjectChat (spec sections 5, 6, 7) ─────────────────────────

/**
 * Subscribe to project-level chat Broadcast events.
 * Merges live broadcast messages with tRPC query cache.
 * Deduplicates by message UUID (spec section 5).
 */
export function useProjectChat(
  projectId: string | null,
  currentUserId: string | null
) {
  const [liveMessages, setLiveMessages] = useState<RealtimeChatMessage[]>([]);
  const seenIds = useRef(new Set<string>());
  const channelRef = useRef<RealtimeChannel | null>(null);

  useEffect(() => {
    if (!projectId) return;

    const supabase = getSupabaseClient();
    const channelName = `project:${projectId}`;

    // Reuse the project channel if it exists, otherwise create one
    const channel = supabase.channel(channelName, {
      config: {
        broadcast: { self: false },
      },
    });

    channelRef.current = channel;

    // Listen for new chat messages
    channel.on("broadcast", { event: "chat.message" }, (payload) => {
      const msg = payload.payload as RealtimeChatMessage;
      if (!msg?.id) return;

      // Deduplicate (spec section 5)
      if (seenIds.current.has(msg.id)) return;
      seenIds.current.add(msg.id);

      const message: RealtimeChatMessage = {
        ...msg,
        authorAvatar:
          msg.authorImage ||
          `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(msg.authorName || "U")}`,
        status: "sent",
      };

      setLiveMessages((prev) => [...prev, message]);
    });

    // Listen for reaction updates
    channel.on("broadcast", { event: "chat.reaction.add" }, (_payload) => {
      // Reaction updates handled by the reactions query invalidation
    });

    channel.on("broadcast", { event: "chat.reaction.remove" }, (_payload) => {
      // Reaction updates handled by the reactions query invalidation
    });

    channel.subscribe();

    return () => {
      supabase.removeChannel(channel);
      channelRef.current = null;
    };
  }, [projectId]);

  /**
   * Mark a message as seen (for dedup on reconnect).
   */
  const markSeen = useCallback((messageId: string) => {
    seenIds.current.add(messageId);
  }, []);

  /**
   * Check if the current user was mentioned in a message.
   */
  const isMentioned = useCallback(
    (message: RealtimeChatMessage) => {
      if (!currentUserId) return false;
      return message.mentionedUserIds?.includes(currentUserId) ?? false;
    },
    [currentUserId]
  );

  return {
    liveMessages,
    markSeen,
    isMentioned,
  };
}

// ─── useTypingIndicator (spec section 6) ─────────────────────────────

interface TypingUser {
  userId: string;
  userName: string;
}

/**
 * Typing indicator over Supabase Broadcast (ephemeral, never persisted).
 * Sends chat.typing.start on first keystroke, auto-sends chat.typing.stop
 * after 2.5s of inactivity or on send/blur.
 */
export function useTypingIndicator(
  projectId: string | null,
  currentUser: { id: string; name: string } | null
) {
  const [typingUsers, setTypingUsers] = useState<TypingUser[]>([]);
  const channelRef = useRef<RealtimeChannel | null>(null);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTypingRef = useRef(false);
  const typingTimeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    if (!projectId) return;

    const supabase = getSupabaseClient();
    const channelName = `project:${projectId}`;

    const channel = supabase.channel(`${channelName}:typing`, {
      config: {
        broadcast: { self: false },
      },
    });

    channelRef.current = channel;

    // Listen for typing events from other users
    channel.on("broadcast", { event: "chat.typing.start" }, (payload) => {
      const { userId, userName } = payload.payload as TypingUser;
      if (userId === currentUser?.id) return;

      setTypingUsers((prev) => {
        if (prev.some((u) => u.userId === userId)) return prev;
        return [...prev, { userId, userName }];
      });

      // Auto-clear after 3s if no stop event received
      const existing = typingTimeoutsRef.current.get(userId);
      if (existing) clearTimeout(existing);

      typingTimeoutsRef.current.set(
        userId,
        setTimeout(() => {
          setTypingUsers((prev) => prev.filter((u) => u.userId !== userId));
          typingTimeoutsRef.current.delete(userId);
        }, 3000)
      );
    });

    channel.on("broadcast", { event: "chat.typing.stop" }, (payload) => {
      const { userId } = payload.payload as { userId: string };

      setTypingUsers((prev) => prev.filter((u) => u.userId !== userId));

      const timeout = typingTimeoutsRef.current.get(userId);
      if (timeout) {
        clearTimeout(timeout);
        typingTimeoutsRef.current.delete(userId);
      }
    });

    channel.subscribe();

    return () => {
      supabase.removeChannel(channel);
      channelRef.current = null;
      typingTimeoutsRef.current.forEach((t) => clearTimeout(t));
      typingTimeoutsRef.current.clear();
    };
  }, [projectId, currentUser?.id]);

  /**
   * Call this on keystroke in the chat composer.
   * Debounces: sends start on first key, auto-sends stop after 2.5s.
   */
  const onKeystroke = useCallback(() => {
    if (!channelRef.current || !currentUser) return;

    // Send start only if not already typing
    if (!isTypingRef.current) {
      isTypingRef.current = true;
      channelRef.current.send({
        type: "broadcast",
        event: "chat.typing.start",
        payload: { userId: currentUser.id, userName: currentUser.name },
      });
    }

    // Reset stop timer
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current);
    stopTimerRef.current = setTimeout(() => {
      stopTyping();
    }, 2500);
  }, [currentUser]);

  /**
   * Explicitly stop typing (call on send or blur).
   */
  const stopTyping = useCallback(() => {
    if (!channelRef.current || !currentUser) return;

    if (isTypingRef.current) {
      isTypingRef.current = false;
      channelRef.current.send({
        type: "broadcast",
        event: "chat.typing.stop",
        payload: { userId: currentUser.id },
      });
    }

    if (stopTimerRef.current) {
      clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
  }, [currentUser]);

  return {
    typingUsers,
    onKeystroke,
    stopTyping,
  };
}

// ─── useUnreadCount (spec section 7) ─────────────────────────────────

/**
 * Client-side unread count computed from lastReadMessageId vs incoming messages.
 */
export function useUnreadCount(
  liveMessages: RealtimeChatMessage[],
  lastReadMessageId: string | null | undefined,
  isPanelOpen: boolean
) {
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (isPanelOpen) {
      setUnreadCount(0);
      return;
    }

    if (!lastReadMessageId) {
      setUnreadCount(liveMessages.length);
      return;
    }

    // Count messages that arrived after the last read message
    const lastReadIndex = liveMessages.findIndex((m) => m.id === lastReadMessageId);
    if (lastReadIndex === -1) {
      setUnreadCount(liveMessages.length);
    } else {
      setUnreadCount(liveMessages.length - lastReadIndex - 1);
    }
  }, [liveMessages, lastReadMessageId, isPanelOpen]);

  return unreadCount;
}
