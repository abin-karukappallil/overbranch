"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { MessageSquare, Send, X, SmilePlus, AtSign, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { trpc } from "@/trpc/client";
import { useProjectChat, useTypingIndicator, useUnreadCount, type RealtimeChatMessage } from "@/lib/realtime/chat";
import { authClient } from "@/lib/auth-client";

interface ChatPanelProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
}

const EMOJI_QUICK_PICKS = ["👍", "❤️", "😂", "🎉", "🤔", "👀", "🔥", "✅"];

export function ChatPanel({ projectId, isOpen, onClose }: ChatPanelProps) {
  const [message, setMessage] = useState("");
  const [showEmojiPicker, setShowEmojiPicker] = useState<string | null>(null); // messageId or null
  const [optimisticMessages, setOptimisticMessages] = useState<RealtimeChatMessage[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isNearBottomRef = useRef(true);

  const { data: sessionData } = authClient.useSession();
  const currentUser = sessionData?.user;

  const utils = trpc.useUtils();

  // Fetch message history
  const { data: historyData } = trpc.chat.getMessages.useQuery(
    { projectId, limit: 50 },
    { enabled: !!projectId && isOpen }
  );

  // Read state
  const { data: lastReadMessageId } = trpc.chat.getReadState.useQuery(
    { projectId },
    { enabled: !!projectId }
  );

  // Realtime hooks
  const { liveMessages, markSeen, isMentioned } = useProjectChat(projectId, currentUser?.id || null);

  const { typingUsers, onKeystroke, stopTyping } = useTypingIndicator(
    projectId,
    currentUser ? { id: currentUser.id, name: currentUser.name } : null
  );

  const unreadCount = useUnreadCount(liveMessages, lastReadMessageId ?? null, isOpen);

  // Mutations
  const sendMutation = trpc.chat.sendMessage.useMutation({
    onSuccess: (data) => {
      // Reconcile optimistic message with real ID
      setOptimisticMessages((prev) =>
        prev.map((m) =>
          m.status === "sending" && m.body === data.body
            ? { ...m, id: data.id, status: "sent" as const }
            : m
        )
      );
      markSeen(data.id);
    },
    onError: () => {
      setOptimisticMessages((prev) =>
        prev.map((m) => (m.status === "sending" ? { ...m, status: "failed" as const } : m))
      );
    },
  });

  const markReadMutation = trpc.chat.markRead.useMutation();
  const addReactionMutation = trpc.reactions.addReaction.useMutation({
    onSuccess: () => {
      utils.reactions.getReactions.invalidate();
    },
  });

  // Mark messages as read when panel is open
  useEffect(() => {
    if (!isOpen) return;

    const lastMsg = uniqueMessages[uniqueMessages.length - 1];

    if (lastMsg?.id && (lastMsg as any).status !== "sending") {
      markReadMutation.mutate({ projectId, lastReadMessageId: lastMsg.id });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, liveMessages.length]);

  // Auto-scroll when near bottom
  useEffect(() => {
    if (isNearBottomRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [liveMessages, optimisticMessages]);

  // Mark history messages as seen for dedup
  useEffect(() => {
    if (historyData?.messages) {
      historyData.messages.forEach((m) => markSeen(m.id));
    }
  }, [historyData, markSeen]);

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    isNearBottomRef.current = scrollHeight - scrollTop - clientHeight < 60;
  }, []);

  const handleSend = useCallback(() => {
    const body = message.trim();
    if (!body || !currentUser) return;

    // Optimistic insert (spec section 15)
    const tempId = `temp-${Date.now()}`;
    const optimistic: RealtimeChatMessage = {
      id: tempId,
      projectId,
      authorId: currentUser.id,
      authorName: currentUser.name,
      authorEmail: currentUser.email,
      authorImage: currentUser.image || null,
      authorAvatar:
        currentUser.image ||
        `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(currentUser.name || "U")}`,
      body,
      mentionedUserIds: [],
      createdAt: new Date().toISOString(),
      status: "sending",
    };

    setOptimisticMessages((prev) => [...prev, optimistic]);
    setMessage("");
    stopTyping();

    sendMutation.mutate({ projectId, body });

    // Refocus input
    inputRef.current?.focus();
  }, [message, currentUser, projectId, stopTyping, sendMutation]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleReaction = (messageId: string, emoji: string) => {
    addReactionMutation.mutate({ projectId, messageId, emoji });
    setShowEmojiPicker(null);
  };

  // Combine history + live + optimistic, deduplicate
  const allMessages = [
    ...(historyData?.messages || []).map((m) => ({
      ...m,
      body: m.body,
      authorId: m.authorId,
      authorName: m.authorName,
      authorEmail: m.authorEmail,
      authorImage: m.authorImage,
      authorAvatar: m.authorAvatar,
      mentionedUserIds: (m.mentionedUserIds as string[]) || [],
      createdAt: typeof m.createdAt === "string" ? m.createdAt : m.createdAt?.toISOString?.() || "",
      projectId,
      status: "sent" as const,
    })),
    ...liveMessages,
    ...optimisticMessages,
  ];

  // Deduplicate by ID
  const seen = new Set<string>();
  const uniqueMessages = allMessages.filter((m) => {
    if (seen.has(m.id)) return false;
    seen.add(m.id);
    return true;
  });

  if (!isOpen) return null;

  return (
    <div className="flex flex-col h-full bg-card border-l border-border/60 font-sans">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/40 bg-muted/20">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-indigo-400" />
          <span className="font-bold text-sm text-foreground">Project Chat</span>
          {unreadCount > 0 && (
            <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-indigo-500/20 text-indigo-400 font-mono font-bold">
              {unreadCount}
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="h-7 w-7 rounded-lg hover:bg-muted"
        >
          <X className="w-4 h-4 text-muted-foreground" />
        </Button>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-3 py-3 space-y-3 scroll-smooth"
      >
        {uniqueMessages.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
            <MessageSquare className="w-8 h-8 mb-3 opacity-40" />
            <p className="text-xs font-medium">No messages yet</p>
            <p className="text-[10px] mt-1 opacity-70">Start a conversation with your team</p>
          </div>
        )}

        {uniqueMessages.map((msg) => {
          const isOwnMessage = msg.authorId === currentUser?.id;
          const mentioned = currentUser && msg.mentionedUserIds?.includes(currentUser.id);

          return (
            <div
              key={msg.id}
              className={`group relative px-3 py-2 rounded-xl text-xs transition-colors ${
                mentioned
                  ? "bg-amber-500/10 border border-amber-500/30"
                  : isOwnMessage
                  ? "bg-indigo-500/10 border border-indigo-500/20"
                  : "bg-muted/30 border border-border/30"
              } ${msg.status === "sending" ? "opacity-60" : ""} ${
                msg.status === "failed" ? "border-rose-500/40 bg-rose-500/5" : ""
              }`}
            >
              <div className="flex items-start gap-2">
                <img
                  src={msg.authorAvatar}
                  alt=""
                  className="w-5 h-5 rounded-full border border-border/40 shrink-0 mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="font-bold text-foreground text-[11px] truncate">
                      {msg.authorName || msg.authorEmail}
                    </span>
                    <span className="text-[9px] text-muted-foreground font-mono shrink-0">
                      {formatTime(msg.createdAt)}
                    </span>
                    {msg.status === "sending" && (
                      <span className="text-[9px] text-amber-400 font-mono">sending…</span>
                    )}
                    {msg.status === "failed" && (
                      <span className="text-[9px] text-rose-400 font-mono">failed</span>
                    )}
                  </div>
                  <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap break-words">
                    {msg.body}
                  </p>
                </div>
              </div>

              {/* Reaction bar — show on hover */}
              <div className="absolute -top-2 right-2 hidden group-hover:flex items-center gap-0.5 bg-card border border-border/50 rounded-lg px-1 py-0.5 shadow-lg">
                <button
                  onClick={() => setShowEmojiPicker(showEmojiPicker === msg.id ? null : msg.id)}
                  className="p-0.5 rounded hover:bg-muted/50 transition-colors"
                >
                  <SmilePlus className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              </div>

              {/* Quick emoji picker */}
              {showEmojiPicker === msg.id && (
                <div className="absolute -top-8 right-0 flex items-center gap-0.5 bg-card border border-border/50 rounded-lg px-1.5 py-1 shadow-xl z-50">
                  {EMOJI_QUICK_PICKS.map((emoji) => (
                    <button
                      key={emoji}
                      onClick={() => handleReaction(msg.id, emoji)}
                      className="text-sm hover:scale-125 transition-transform p-0.5"
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Typing indicator */}
      {typingUsers.length > 0 && (
        <div className="px-4 py-1.5 text-[10px] text-muted-foreground font-mono">
          <span className="inline-flex items-center gap-1">
            <span className="flex gap-0.5">
              <span className="w-1 h-1 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1 h-1 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1 h-1 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "300ms" }} />
            </span>
            {typingUsers.map((u) => u.userName).join(", ")}{" "}
            {typingUsers.length === 1 ? "is" : "are"} typing…
          </span>
        </div>
      )}

      {/* Composer */}
      <div className="px-3 py-2.5 border-t border-border/40 bg-muted/10">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={message}
            onChange={(e) => {
              setMessage(e.target.value);
              onKeystroke();
            }}
            onKeyDown={handleKeyDown}
            onBlur={stopTyping}
            placeholder="Type a message… (Shift+Enter for new line)"
            rows={1}
            className="flex-1 resize-none bg-background border border-border/50 rounded-xl px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500/40 min-h-[36px] max-h-24"
            style={{ height: "auto" }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = "auto";
              target.style.height = Math.min(target.scrollHeight, 96) + "px";
            }}
          />
          <Button
            onClick={handleSend}
            disabled={!message.trim() || sendMutation.isPending}
            size="icon"
            className="h-9 w-9 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-500/20 shrink-0"
          >
            <Send className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────

function formatTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}
