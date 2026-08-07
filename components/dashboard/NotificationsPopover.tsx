"use client";

import React, { useState } from "react";
import { Bell, Check, Sparkles, UserPlus, ShieldAlert, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { trpc } from "@/trpc/client";
import { toast } from "sonner";

export function NotificationsPopover() {
  const [open, setOpen] = useState(false);

  const utils = trpc.useUtils();
  const { data: notificationsList } = trpc.notifications.listNotifications.useQuery(undefined, {
    refetchInterval: 5000,
  });
  const { data: pendingInvites } = trpc.invitations.listPending.useQuery(undefined, {
    refetchInterval: 5000,
  });
  const { data: unreadCount = 0 } = trpc.notifications.unreadCount.useQuery(undefined, {
    refetchInterval: 5000,
  });

  const markAllReadMutation = trpc.notifications.markAllAsRead.useMutation({
    onSuccess: () => {
      utils.notifications.invalidate();
    },
  });

  const acceptInviteMutation = trpc.invitations.acceptInvite.useMutation({
    onSuccess: () => {
      toast.success("Project invitation accepted!");
      utils.invitations.invalidate();
      utils.projects.invalidate();
      utils.notifications.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to accept invitation");
    },
  });

  const declineInviteMutation = trpc.invitations.declineInvite.useMutation({
    onSuccess: () => {
      toast.success("Project invitation declined.");
      utils.invitations.invalidate();
      utils.notifications.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to decline invitation");
    },
  });

  const totalBadges = (unreadCount || 0) + (pendingInvites?.length || 0);

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen(!open)}
        className="h-9 w-9 rounded-xl hover:bg-accent relative"
        title="Notifications"
      >
        <Bell className="w-4 h-4 text-muted-foreground" />
        {totalBadges > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center animate-pulse">
            {totalBadges}
          </span>
        )}
      </Button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 z-50 w-80 sm:w-96 max-h-[80vh] overflow-y-auto rounded-2xl border border-border/70 bg-card/95 backdrop-blur-xl shadow-2xl p-4 space-y-4 font-sans">
            <div className="flex items-center justify-between border-b border-border/40 pb-3">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-foreground">Notification Center</span>
                {totalBadges > 0 && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-indigo-500/20 text-indigo-400 font-mono font-bold">
                    {totalBadges} new
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllReadMutation.mutate()}
                  className="text-xs text-indigo-400 hover:underline flex items-center gap-1"
                >
                  <Check className="w-3.5 h-3.5" /> Mark all read
                </button>
              )}
            </div>

            {/* Pending Invitations Section */}
            {pendingInvites && pendingInvites.length > 0 && (
              <div className="space-y-2">
                <span className="text-[11px] font-bold text-indigo-400 uppercase tracking-wider block font-mono">
                  Pending Co-Author Invitations ({pendingInvites.length})
                </span>
                {pendingInvites.map((invite) => (
                  <div
                    key={invite.id}
                    className="p-3 rounded-xl border border-indigo-500/40 bg-indigo-500/10 space-y-2"
                  >
                    <div className="flex items-start gap-2.5">
                      <UserPlus className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                      <div className="text-xs space-y-0.5">
                        <p className="font-bold text-foreground">
                          {invite.senderName || invite.senderEmail} invited you
                        </p>
                        <p className="text-muted-foreground">
                          Project: <span className="font-mono text-indigo-300 font-semibold">{invite.projectName}</span>
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        size="sm"
                        onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={acceptInviteMutation.isPending}
                        className="h-7 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-3 flex-1 font-medium"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={declineInviteMutation.isPending}
                        className="h-7 text-xs border-border/50 text-muted-foreground hover:text-foreground rounded-lg px-3 flex-1 font-medium"
                      >
                        <XCircle className="w-3.5 h-3.5 mr-1" />
                        Decline
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* System Notifications List */}
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {!notificationsList || notificationsList.length === 0 ? (
                <div className="py-6 text-center text-xs text-muted-foreground">
                  No notifications yet.
                </div>
              ) : (
                notificationsList.map((item) => (
                  <div
                    key={item.id}
                    className={`p-3 rounded-xl border transition-all ${
                      item.isRead
                        ? "border-border/30 bg-muted/20 opacity-80"
                        : "border-indigo-500/30 bg-indigo-500/5 shadow-xs"
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <Sparkles className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                      <div className="space-y-1 text-xs flex-1">
                        <div className="flex items-center justify-between font-semibold text-foreground">
                          <span>{item.title}</span>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {item.createdAtFormatted}
                          </span>
                        </div>
                        <p className="text-muted-foreground leading-relaxed">{item.message}</p>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
