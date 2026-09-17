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
        className="h-8 w-8 rounded-lg hover:bg-[#141517] text-[#8A8F98] hover:text-[#F7F8F8] relative cursor-pointer"
        title="Notifications"
      >
        <Bell className="w-4 h-4" />
        {totalBadges > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-3.5 h-3.5 px-0.5 rounded-full bg-[#5E6AD2] text-white text-[9px] font-bold flex items-center justify-center">
            {totalBadges}
          </span>
        )}
      </Button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="fixed top-16 left-3 right-3 sm:absolute sm:top-10 sm:left-auto sm:right-0 z-50 w-auto sm:w-80 max-h-[80vh] overflow-y-auto rounded-xl border border-[#23252A] bg-[#0F1011] text-[#F7F8F8] shadow-2xl p-3.5 space-y-3 font-sans animate-in fade-in duration-150">
            <div className="flex items-center justify-between border-b border-[#23252A] pb-2.5">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-xs text-[#F7F8F8] tracking-tight">Notifications</span>
                {totalBadges > 0 && (
                  <span className="px-1.5 py-0.2 text-[10px] rounded bg-[#5E6AD2]/10 text-[#5E6AD2] font-mono font-medium">
                    {totalBadges} new
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllReadMutation.mutate()}
                  className="text-[11px] text-[#5E6AD2] hover:text-[#4F5BBE] flex items-center gap-1 font-medium cursor-pointer"
                >
                  <Check className="w-3 h-3" /> Mark read
                </button>
              )}
            </div>

            {/* Pending Invitations Section */}
            {pendingInvites && pendingInvites.length > 0 && (
              <div className="space-y-2">
                <span className="text-[10px] font-medium text-[#8A8F98] uppercase tracking-wider block">
                  Pending Invitations ({pendingInvites.length})
                </span>
                {pendingInvites.map((invite) => (
                  <div
                    key={invite.id}
                    className="p-3 rounded-lg border border-[#23252A] bg-[#141517] space-y-2"
                  >
                    <div className="flex items-start gap-2">
                      <UserPlus className="w-3.5 h-3.5 text-[#5E6AD2] shrink-0 mt-0.5" />
                      <div className="text-xs space-y-0.5">
                        <p className="font-medium text-[#F7F8F8]">
                          {invite.senderName || invite.senderEmail} invited you
                        </p>
                        <p className="text-[#8A8F98] text-[11px]">
                          Project: <span className="font-mono text-[#D0D6E0]">{invite.projectName}</span>
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        size="sm"
                        onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={acceptInviteMutation.isPending}
                        className="h-6 text-[11px] bg-[#5E6AD2] hover:bg-[#4F5BBE] text-white rounded-md px-2.5 flex-1 cursor-pointer font-medium"
                      >
                        <CheckCircle2 className="w-3 h-3 mr-1" />
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={declineInviteMutation.isPending}
                        className="h-6 text-[11px] border-[#23252A] bg-[#0F1011] text-[#8A8F98] hover:text-[#F7F8F8] rounded-md px-2.5 flex-1 cursor-pointer"
                      >
                        <XCircle className="w-3 h-3 mr-1" />
                        Decline
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* System Notifications List */}
            <div className="space-y-1.5 max-h-56 overflow-y-auto">
              {!notificationsList || notificationsList.length === 0 ? (
                <div className="py-6 text-center text-xs text-[#62666D]">
                  No notifications yet.
                </div>
              ) : (
                notificationsList.map((item) => (
                  <div
                    key={item.id}
                    className={`p-2.5 rounded-lg border transition-all ${
                      item.isRead
                        ? "border-[#23252A]/50 bg-[#141517]/40 opacity-70"
                        : "border-[#23252A] bg-[#141517]"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <Zap className="w-3.5 h-3.5 text-[#5E6AD2] shrink-0 mt-0.5" />
                      <div className="space-y-0.5 text-xs flex-1">
                        <div className="flex items-center justify-between font-medium text-[#F7F8F8]">
                          <span>{item.title}</span>
                          <span className="text-[10px] text-[#62666D] font-mono">
                            {item.createdAtFormatted}
                          </span>
                        </div>
                        <p className="text-[#8A8F98] leading-relaxed text-[11px]">{item.message}</p>
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
