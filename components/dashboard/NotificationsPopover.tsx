"use client";

import React, { useState } from "react";
import { Bell, Check, Zap, UserPlus, CheckCircle2, XCircle } from "lucide-react";
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
        className="h-9 w-9 rounded-xl hover:bg-zinc-800 text-zinc-400 hover:text-white relative cursor-pointer"
        title="Notifications"
      >
        <Bell className="w-4 h-4" />
        {totalBadges > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-[#00CC68] text-black text-[10px] font-bold flex items-center justify-center animate-pulse">
            {totalBadges}
          </span>
        )}
      </Button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="fixed top-16 left-3 right-3 sm:absolute sm:top-11 sm:left-auto sm:right-0 z-50 w-auto sm:w-96 max-h-[80vh] overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 text-white shadow-2xl p-3.5 sm:p-4 space-y-4 font-sans animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <span className="font-archivo font-bold text-sm text-white uppercase tracking-wider">Notifications</span>
                {totalBadges > 0 && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-[#00CC68]/20 text-[#00CC68] font-mono font-bold">
                    {totalBadges} new
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllReadMutation.mutate()}
                  className="text-xs text-[#00CC68] hover:underline flex items-center gap-1 font-mono font-bold cursor-pointer"
                >
                  <Check className="w-3.5 h-3.5" /> Mark all read
                </button>
              )}
            </div>

            {/* Pending Invitations Section */}
            {pendingInvites && pendingInvites.length > 0 && (
              <div className="space-y-2 font-mono">
                <span className="text-[11px] font-bold text-[#00CC68] uppercase tracking-wider block">
                  Pending Co-Author Invitations ({pendingInvites.length})
                </span>
                {pendingInvites.map((invite) => (
                  <div
                    key={invite.id}
                    className="p-3 rounded-xl border border-[#00CC68]/40 bg-zinc-950 space-y-2"
                  >
                    <div className="flex items-start gap-2.5">
                      <UserPlus className="w-4 h-4 text-[#00CC68] shrink-0 mt-0.5" />
                      <div className="text-xs space-y-0.5">
                        <p className="font-bold text-white">
                          {invite.senderName || invite.senderEmail} invited you
                        </p>
                        <p className="text-zinc-400">
                          Project: <span className="font-mono text-[#00CC68] font-bold">{invite.projectName}</span>
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 pt-1 font-bold">
                      <Button
                        size="sm"
                        onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={acceptInviteMutation.isPending}
                        className="h-7 text-xs bg-[#00CC68] hover:bg-[#00E676] text-black rounded-lg px-3 flex-1 font-mono cursor-pointer"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={declineInviteMutation.isPending}
                        className="h-7 text-xs border-zinc-800 text-zinc-300 hover:text-white rounded-lg px-3 flex-1 font-mono cursor-pointer"
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
            <div className="space-y-2 max-h-64 overflow-y-auto font-mono">
              {!notificationsList || notificationsList.length === 0 ? (
                <div className="py-6 text-center text-xs text-zinc-500 font-mono">
                  No notifications yet.
                </div>
              ) : (
                notificationsList.map((item) => (
                  <div
                    key={item.id}
                    className={`p-3 rounded-xl border transition-all ${
                      item.isRead
                        ? "border-zinc-800/60 bg-zinc-950/40 opacity-70"
                        : "border-[#00CC68]/30 bg-zinc-950 shadow-xs"
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <Zap className="w-4 h-4 text-[#00CC68] shrink-0 mt-0.5" />
                      <div className="space-y-1 text-xs flex-1">
                        <div className="flex items-center justify-between font-bold text-white">
                          <span>{item.title}</span>
                          <span className="text-[10px] text-zinc-500 font-mono">
                            {item.createdAtFormatted}
                          </span>
                        </div>
                        <p className="text-zinc-400 leading-relaxed font-sans">{item.message}</p>
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
