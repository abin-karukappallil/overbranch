"use client";

import React, { useState } from "react";
import { MessageCircle, Check, RotateCcw, Trash2, Reply, X, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { trpc } from "@/trpc/client";
import { authClient } from "@/lib/auth-client";

interface CommentsPanelProps {
  projectId: string;
  documentId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function CommentsPanel({ projectId, documentId, isOpen, onClose }: CommentsPanelProps) {
  const [newComment, setNewComment] = useState("");
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [showResolved, setShowResolved] = useState(false);

  const { data: sessionData } = authClient.useSession();
  const currentUser = sessionData?.user;

  const utils = trpc.useUtils();

  const { data: commentsList = [], isLoading } = trpc.realtimeComments.list.useQuery(
    { projectId, documentId },
    { enabled: !!projectId && !!documentId && isOpen }
  );

  const createMutation = trpc.realtimeComments.create.useMutation({
    onSuccess: () => {
      setNewComment("");
      utils.realtimeComments.list.invalidate({ projectId, documentId });
    },
  });

  const replyMutation = trpc.realtimeComments.reply.useMutation({
    onSuccess: () => {
      setReplyText("");
      setReplyingTo(null);
      utils.realtimeComments.list.invalidate({ projectId, documentId });
    },
  });

  const resolveMutation = trpc.realtimeComments.resolve.useMutation({
    onSuccess: () => {
      utils.realtimeComments.list.invalidate({ projectId, documentId });
    },
  });

  const reopenMutation = trpc.realtimeComments.reopen.useMutation({
    onSuccess: () => {
      utils.realtimeComments.list.invalidate({ projectId, documentId });
    },
  });

  const deleteMutation = trpc.realtimeComments.delete.useMutation({
    onSuccess: () => {
      utils.realtimeComments.list.invalidate({ projectId, documentId });
    },
  });

  const handleCreateComment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim()) return;
    createMutation.mutate({ projectId, documentId, content: newComment.trim() });
  };

  const handleReply = (parentId: string) => {
    if (!replyText.trim()) return;
    replyMutation.mutate({
      projectId,
      documentId,
      parentId,
      content: replyText.trim(),
    });
  };

  // Organize comments into threads (top-level + replies)
  const topLevelComments = commentsList.filter((c: any) => !c.parentId);
  const getReplies = (parentId: string) =>
    commentsList.filter((c: any) => c.parentId === parentId);

  const openComments = topLevelComments.filter((c: any) => c.status === "open");
  const resolvedComments = topLevelComments.filter((c: any) => c.status === "resolved");

  if (!isOpen) return null;

  return (
    <div className="flex flex-col h-full bg-card border-l border-border/60 font-sans">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/40 bg-muted/20">
        <div className="flex items-center gap-2">
          <MessageCircle className="w-4 h-4 text-indigo-400" />
          <span className="font-bold text-sm text-foreground">Comments</span>
          <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-muted text-muted-foreground font-mono">
            {openComments.length} open
          </span>
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

      {/* New comment composer */}
      <form onSubmit={handleCreateComment} className="px-3 py-2.5 border-b border-border/40">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment…"
          rows={2}
          className="w-full resize-none bg-background border border-border/50 rounded-xl px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500/40"
        />
        <div className="flex justify-end mt-1.5">
          <Button
            type="submit"
            disabled={!newComment.trim() || createMutation.isPending}
            size="sm"
            className="h-7 text-[11px] bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-3 font-medium"
          >
            {createMutation.isPending ? "Posting…" : "Post Comment"}
          </Button>
        </div>
      </form>

      {/* Comment list */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {isLoading && (
          <div className="py-8 text-center text-xs text-muted-foreground">Loading comments…</div>
        )}

        {!isLoading && openComments.length === 0 && resolvedComments.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
            <MessageCircle className="w-8 h-8 mb-3 opacity-40" />
            <p className="text-xs font-medium">No comments yet</p>
            <p className="text-[10px] mt-1 opacity-70">Add a comment to start a discussion</p>
          </div>
        )}

        {/* Open comments */}
        {openComments.map((comment: any) => (
          <CommentThread
            key={comment.id}
            comment={comment}
            replies={getReplies(comment.id)}
            currentUserId={currentUser?.id}
            replyingTo={replyingTo}
            replyText={replyText}
            onSetReplyingTo={setReplyingTo}
            onSetReplyText={setReplyText}
            onReply={handleReply}
            onResolve={() =>
              resolveMutation.mutate({ projectId, documentId, commentId: comment.id })
            }
            onDelete={() =>
              deleteMutation.mutate({ projectId, documentId, commentId: comment.id })
            }
            isReplyPending={replyMutation.isPending}
          />
        ))}

        {/* Resolved comments (collapsible) */}
        {resolvedComments.length > 0 && (
          <div className="pt-2 border-t border-border/30">
            <button
              onClick={() => setShowResolved(!showResolved)}
              className="flex items-center gap-1.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors w-full py-1"
            >
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform ${showResolved ? "rotate-0" : "-rotate-90"}`}
              />
              Resolved ({resolvedComments.length})
            </button>

            {showResolved &&
              resolvedComments.map((comment: any) => (
                <CommentThread
                  key={comment.id}
                  comment={comment}
                  replies={getReplies(comment.id)}
                  currentUserId={currentUser?.id}
                  replyingTo={replyingTo}
                  replyText={replyText}
                  onSetReplyingTo={setReplyingTo}
                  onSetReplyText={setReplyText}
                  onReply={handleReply}
                  onReopen={() =>
                    reopenMutation.mutate({ projectId, documentId, commentId: comment.id })
                  }
                  onDelete={() =>
                    deleteMutation.mutate({ projectId, documentId, commentId: comment.id })
                  }
                  isResolved
                  isReplyPending={replyMutation.isPending}
                />
              ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Comment Thread ─────────────────────────────────────────────────

interface CommentThreadProps {
  comment: any;
  replies: any[];
  currentUserId?: string;
  replyingTo: string | null;
  replyText: string;
  onSetReplyingTo: (id: string | null) => void;
  onSetReplyText: (text: string) => void;
  onReply: (parentId: string) => void;
  onResolve?: () => void;
  onReopen?: () => void;
  onDelete: () => void;
  isResolved?: boolean;
  isReplyPending: boolean;
}

function CommentThread({
  comment,
  replies,
  currentUserId,
  replyingTo,
  replyText,
  onSetReplyingTo,
  onSetReplyText,
  onReply,
  onResolve,
  onReopen,
  onDelete,
  isResolved,
  isReplyPending,
}: CommentThreadProps) {
  const isOwn = comment.authorId === currentUserId;

  return (
    <div
      className={`rounded-xl border transition-colors ${
        isResolved
          ? "border-border/20 bg-muted/10 opacity-70"
          : "border-border/40 bg-muted/20"
      }`}
    >
      {/* Main comment */}
      <div className="px-3 py-2.5">
        <div className="flex items-start gap-2">
          <img
            src={comment.authorAvatar}
            alt=""
            className="w-5 h-5 rounded-full border border-border/40 shrink-0 mt-0.5"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="font-bold text-[11px] text-foreground truncate">
                {comment.authorName || comment.authorEmail}
              </span>
              <span className="text-[9px] text-muted-foreground font-mono shrink-0">
                {formatTime(comment.createdAt)}
              </span>
              {isResolved && (
                <span className="text-[9px] text-emerald-400 font-mono flex items-center gap-0.5">
                  <Check className="w-2.5 h-2.5" /> resolved
                </span>
              )}
            </div>
            <p className="text-xs text-foreground/90 leading-relaxed whitespace-pre-wrap">
              {comment.content}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 mt-2 ml-7">
          <button
            onClick={() => onSetReplyingTo(replyingTo === comment.id ? null : comment.id)}
            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded-md hover:bg-muted/50 transition-colors"
          >
            <Reply className="w-3 h-3" /> Reply
          </button>

          {onResolve && !isResolved && (
            <button
              onClick={onResolve}
              className="flex items-center gap-1 text-[10px] text-emerald-400 hover:text-emerald-300 px-1.5 py-0.5 rounded-md hover:bg-emerald-500/10 transition-colors"
            >
              <Check className="w-3 h-3" /> Resolve
            </button>
          )}

          {onReopen && isResolved && (
            <button
              onClick={onReopen}
              className="flex items-center gap-1 text-[10px] text-amber-400 hover:text-amber-300 px-1.5 py-0.5 rounded-md hover:bg-amber-500/10 transition-colors"
            >
              <RotateCcw className="w-3 h-3" /> Reopen
            </button>
          )}

          {isOwn && (
            <button
              onClick={onDelete}
              className="flex items-center gap-1 text-[10px] text-rose-400 hover:text-rose-300 px-1.5 py-0.5 rounded-md hover:bg-rose-500/10 transition-colors"
            >
              <Trash2 className="w-3 h-3" /> Delete
            </button>
          )}
        </div>
      </div>

      {/* Replies */}
      {replies.length > 0 && (
        <div className="border-t border-border/20 ml-5 pl-3 space-y-1 py-1.5">
          {replies.map((reply: any) => (
            <div key={reply.id} className="flex items-start gap-2 px-2 py-1.5">
              <img
                src={reply.authorAvatar}
                alt=""
                className="w-4 h-4 rounded-full border border-border/40 shrink-0 mt-0.5"
              />
              <div>
                <div className="flex items-center gap-1 mb-0.5">
                  <span className="font-bold text-[10px] text-foreground">
                    {reply.authorName || reply.authorEmail}
                  </span>
                  <span className="text-[8px] text-muted-foreground font-mono">
                    {formatTime(reply.createdAt)}
                  </span>
                </div>
                <p className="text-[11px] text-foreground/85 leading-relaxed">{reply.content}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Reply composer */}
      {replyingTo === comment.id && (
        <div className="border-t border-border/20 px-3 py-2 ml-5">
          <textarea
            value={replyText}
            onChange={(e) => onSetReplyText(e.target.value)}
            placeholder="Write a reply…"
            rows={2}
            className="w-full resize-none bg-background border border-border/50 rounded-lg px-2.5 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500/40"
            autoFocus
          />
          <div className="flex items-center gap-1.5 mt-1 justify-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                onSetReplyingTo(null);
                onSetReplyText("");
              }}
              className="h-6 text-[10px] px-2 rounded-md"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => onReply(comment.id)}
              disabled={!replyText.trim() || isReplyPending}
              className="h-6 text-[10px] bg-indigo-600 hover:bg-indigo-500 text-white rounded-md px-2.5"
            >
              {isReplyPending ? "Sending…" : "Reply"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────

function formatTime(dateStr: string | Date): string {
  try {
    const date = typeof dateStr === "string" ? new Date(dateStr) : dateStr;
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}
