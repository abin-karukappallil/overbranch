"use client";

import React, { useState } from "react";
import { Bell, Check } from "lucide-react";
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
      toast.success("Invitation accepted");
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
      toast.success("Invitation declined");
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
        variant="ob-quiet"
        size="icon-sm"
        onClick={() => setOpen(!open)}
        className="relative cursor-pointer"
        title="Notifications"
        aria-label={totalBadges > 0 ? `Notifications, ${totalBadges} new` : "Notifications"}
      >
        <Bell className="size-4" />
        {totalBadges > 0 && (
          <span className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-ob-accent" />
        )}
      </Button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="fixed top-16 right-3 left-3 z-50 flex max-h-[80vh] w-auto animate-in flex-col gap-3 overflow-y-auto rounded-xl border border-ob-line bg-ob-card p-4 text-ob-text shadow-[0_8px_24px_rgba(0,0,0,0.16)] duration-150 fade-in sm:absolute sm:top-10 sm:right-0 sm:left-auto sm:w-80">
            <div className="flex items-center justify-between">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-medium text-ob-text">Notifications</span>
                {totalBadges > 0 && (
                  <span className="font-mono text-xs text-ob-muted tabular-nums">{totalBadges} new</span>
                )}
              </div>
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllReadMutation.mutate()}
                  className="flex cursor-pointer items-center gap-1 rounded-sm text-xs text-ob-text-2 transition-colors hover:text-ob-text"
                >
                  <Check className="size-4" /> Mark read
                </button>
              )}
            </div>

            {/* Pending invitations */}
            {pendingInvites && pendingInvites.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="text-xs text-ob-muted">Pending invitations</span>
                {pendingInvites.map((invite) => (
                  <div key={invite.id} className="flex flex-col gap-3 rounded-lg border border-ob-line p-3">
                    <div className="flex flex-col gap-0.5">
                      <p className="text-[13px] leading-5 text-ob-text">
                        {invite.senderName || invite.senderEmail} invited you
                      </p>
                      <p className="truncate font-mono text-xs text-ob-text-2">{invite.projectName}</p>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="ob-primary"
                        size="xs"
                        onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={acceptInviteMutation.isPending}
                        className="h-7 flex-1 cursor-pointer text-[13px]"
                      >
                        Accept
                      </Button>
                      <Button
                        variant="ob-quiet"
                        size="xs"
                        onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                        disabled={declineInviteMutation.isPending}
                        className="h-7 flex-1 cursor-pointer text-[13px]"
                      >
                        Decline
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* System notifications */}
            <div className="flex max-h-56 flex-col gap-0.5 overflow-y-auto">
              {!notificationsList || notificationsList.length === 0 ? (
                <div className="py-6 text-center text-[13px] text-ob-muted">No notifications yet</div>
              ) : (
                notificationsList.map((item) => (
                  <div
                    key={item.id}
                    className={`flex flex-col gap-0.5 rounded-sm px-2 py-2 ${item.isRead ? "" : "bg-ob-raised"}`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className={`min-w-0 truncate text-[13px] ${item.isRead ? "text-ob-text-2" : "text-ob-text"}`}>
                        {item.title}
                      </span>
                      <span className="shrink-0 font-mono text-xs text-ob-muted">{item.createdAtFormatted}</span>
                    </div>
                    <p className="text-xs leading-4 text-ob-text-2">{item.message}</p>
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
