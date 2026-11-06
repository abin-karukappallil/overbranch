"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { UserPlus, Share2, X, Trash2, Crown, LogOut } from "lucide-react";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";
import { initialsOf } from "@/lib/initials";

interface CollaboratorAvatarsProps {
  projectId?: string;
}

const DIALOG_PANEL =
  "flex w-full max-w-md flex-col gap-4 rounded-xl border border-ob-line bg-ob-card p-6 text-ob-text shadow-[0_16px_48px_rgba(0,0,0,0.32)]";
const DIALOG_TITLE = "text-[15px] leading-6 font-medium text-ob-text";
const DIALOG_BODY = "text-[13px] leading-5 text-ob-text-2";
const DIALOG_FOOTER = "flex justify-end gap-2 pt-2";

export function CollaboratorAvatars({ projectId }: CollaboratorAvatarsProps) {
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"Editor" | "Viewer" | "Transfer">("Editor");
  const [copied, setCopied] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [leaveConfirmOpen, setLeaveConfirmOpen] = useState(false);
  const [transferConfirmMember, setTransferConfirmMember] = useState<any | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const utils = trpc.useUtils();

  const { data: membersList = [] } = trpc.projects.getMembers.useQuery(
    { projectId: projectId! },
    { enabled: !!projectId, refetchInterval: 5000 }
  );

  const { data: projectInfo } = trpc.projects.getById.useQuery(
    { projectId: projectId! },
    { enabled: !!projectId }
  );

  const sendInviteMutation = trpc.invitations.sendInvite.useMutation({
    onSuccess: (data) => {
      toast.success(`Invitation sent to ${data.receiverName || data.receiverEmail}`);
      setInviteEmail("");
      utils.invitations.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to send invitation");
    },
  });

  const removeMemberMutation = trpc.projects.removeMember.useMutation({
    onSuccess: () => {
      toast.success("Collaborator removed");
      utils.projects.getMembers.invalidate({ projectId: projectId! });
    },
    onError: (err) => {
      toast.error(err.message || "Failed to remove member");
    },
  });

  const transferOwnershipMutation = trpc.projects.transferOwnership.useMutation({
    onSuccess: (data) => {
      toast.success(
        data?.newOwnerName
          ? `Ownership transferred to ${data.newOwnerName}`
          : "Ownership transferred successfully"
      );
      setTransferConfirmMember(null);
      utils.projects.getMembers.invalidate({ projectId: projectId! });
      utils.projects.getById.invalidate({ projectId: projectId! });
    },
    onError: (err) => {
      toast.error(err.message || "Failed to transfer ownership");
    },
  });

  const deleteProjectMutation = trpc.projects.deleteProject.useMutation({
    onSuccess: () => {
      toast.success("Project deleted");
      router.push("/dashboard");
    },
    onError: (err) => {
      toast.error(err.message || "Failed to delete project");
    },
  });

  const leaveProjectMutation = trpc.projects.leaveProject.useMutation({
    onSuccess: () => {
      toast.success("You left the project");
      router.push("/dashboard");
    },
    onError: (err) => {
      toast.error(err.message || "Failed to leave project");
    },
  });

  const isOwner = projectInfo?.isOwner;

  const handleShare = () => {
    if (typeof window !== "undefined") {
      navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      toast.success("Project link copied");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSendInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !projectId) return;

    if (inviteRole === "Transfer") {
      transferOwnershipMutation.mutate({
        projectId,
        newOwnerEmail: inviteEmail.trim(),
      });
      return;
    }

    sendInviteMutation.mutate({
      projectId,
      email: inviteEmail.trim(),
      role: inviteRole,
    });
  };

  const modalContent = modalOpen && (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) setModalOpen(false);
      }}
    >
      <div className={DIALOG_PANEL}>
        <div className="flex items-center justify-between border-b border-ob-line pb-3">
          <h3 className={DIALOG_TITLE}>Co-authors and permissions</h3>
          <button
            onClick={() => setModalOpen(false)}
            className="text-ob-muted hover:text-ob-text"
          >
            <X className="size-4" />
          </button>
        </div>

        <form onSubmit={handleSendInvite} className="flex flex-col gap-3 font-mono text-xs">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-ob-text-2">Account email</label>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="collaborator@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="h-9 rounded-lg border-ob-line bg-ob-raised px-3 font-mono text-xs text-ob-text shadow-none placeholder:text-ob-muted"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as "Editor" | "Viewer" | "Transfer")}
                className="h-9 cursor-pointer rounded-lg border border-ob-line bg-ob-raised px-3 text-xs text-ob-text transition-colors hover:border-ob-text/15"
              >
                <option value="Editor">Editor</option>
                <option value="Viewer">Viewer</option>
                {isOwner && <option value="Transfer">Make Owner</option>}
              </select>
            </div>
          </div>

          {inviteRole === "Transfer" ? (
            <Button
              type="submit"
              variant="ob-secondary"
              size="sm"
              disabled={transferOwnershipMutation.isPending || !inviteEmail.trim()}
              className="w-full text-xs"
            >
              <Crown className="size-3.5" />
              <span>{transferOwnershipMutation.isPending ? "Transferring\u2026" : "Transfer ownership"}</span>
            </Button>
          ) : (
            <Button
              type="submit"
              variant="ob-primary"
              size="sm"
              disabled={sendInviteMutation.isPending || !inviteEmail.trim()}
              className="w-full text-xs"
            >
              {sendInviteMutation.isPending ? "Sending\u2026" : "Send invitation"}
            </Button>
          )}
        </form>

        {/* Transfer Confirmation */}
        {transferConfirmMember && (
          <div className="flex flex-col gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs">
            <span className="font-medium text-amber-500">Confirm transfer</span>
            <p className="text-[11px] text-ob-text-2">
              Transfer ownership to <strong className="text-ob-text">{transferConfirmMember.name || transferConfirmMember.email}</strong>? You will remain an editor.
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <Button
                size="sm"
                variant="ob-quiet"
                onClick={() => setTransferConfirmMember(null)}
                disabled={transferOwnershipMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                variant="ob-secondary"
                onClick={() =>
                  transferOwnershipMutation.mutate({
                    projectId: projectId!,
                    newOwnerUserId: transferConfirmMember.id,
                  })
                }
                disabled={transferOwnershipMutation.isPending}
              >
                Confirm transfer
              </Button>
            </div>
          </div>
        )}

        {/* Members List */}
        <div className="flex flex-col gap-2 border-t border-ob-line pt-3 font-mono text-xs">
          <div className="flex items-center justify-between text-xs text-ob-text-2">
            <span>Members</span>
            <span className="text-ob-muted tabular-nums">{membersList.length}</span>
          </div>

          <div className="flex max-h-40 flex-col gap-1 overflow-y-auto pr-1">
            {membersList.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between rounded-lg border border-ob-line bg-ob-raised p-2 text-xs"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <Avatar className="size-6 rounded-md">
                    <AvatarImage src={m.avatar} referrerPolicy="no-referrer" />
                    <AvatarFallback className="rounded-md bg-ob-card text-[10px] text-ob-text-2 font-medium">
                      {initialsOf(m.name || m.email || "U")}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 truncate">
                    <p className="truncate text-xs font-medium text-ob-text flex items-center gap-1">
                      {m.isOwner && <Crown className="size-3 text-amber-500 shrink-0" />}
                      <span className="truncate">{m.name || m.email}</span>
                    </p>
                    <p className="text-[10px] text-ob-muted">{m.role}</p>
                  </div>
                </div>

                {isOwner && !m.isOwner && (
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setTransferConfirmMember(m)}
                      title="Transfer ownership"
                      className="p-1 text-ob-muted hover:text-amber-500 transition-colors"
                    >
                      <Crown className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => removeMemberMutation.mutate({ projectId: projectId!, memberUserId: m.id })}
                      title="Remove member"
                      className="p-1 text-ob-muted hover:text-ob-negative transition-colors"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <Button
          onClick={handleShare}
          variant="ob-quiet"
          size="sm"
          className="w-full text-xs"
        >
          <Share2 className="size-3.5" />
          <span>{copied ? "Link copied" : "Copy project link"}</span>
        </Button>

        {isOwner && (
          <div className="flex flex-col gap-2 border-t border-ob-line pt-3">
            {!deleteConfirmOpen ? (
              <Button
                onClick={() => setDeleteConfirmOpen(true)}
                variant="ob-quiet"
                size="sm"
                className="w-full text-xs text-ob-negative hover:text-ob-negative"
              >
                <Trash2 className="size-3.5" />
                <span>Delete project</span>
              </Button>
            ) : (
              <div className="flex flex-col gap-2 rounded-lg border border-ob-negative/20 bg-ob-raised p-3 text-xs">
                <p className={DIALOG_BODY}>
                  Permanently delete this project and all files for all members?
                </p>
                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="ob-quiet"
                    onClick={() => setDeleteConfirmOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    variant="ob-danger"
                    onClick={() => deleteProjectMutation.mutate({ projectId: projectId! })}
                    disabled={deleteProjectMutation.isPending}
                  >
                    Delete permanently
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {!isOwner && (
          <div className="flex flex-col gap-2 border-t border-ob-line pt-3">
            {!leaveConfirmOpen ? (
              <Button
                onClick={() => setLeaveConfirmOpen(true)}
                variant="ob-quiet"
                size="sm"
                className="w-full text-xs text-ob-negative hover:text-ob-negative"
              >
                <LogOut className="size-3.5" />
                <span>Leave project</span>
              </Button>
            ) : (
              <div className="flex flex-col gap-2 rounded-lg border border-ob-negative/20 bg-ob-raised p-3 text-xs">
                <p className={DIALOG_BODY}>
                  Leave this project? You will lose access to its files.
                </p>
                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="ob-quiet"
                    onClick={() => setLeaveConfirmOpen(false)}
                    disabled={leaveProjectMutation.isPending}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    variant="ob-danger"
                    onClick={() => leaveProjectMutation.mutate({ projectId: projectId! })}
                    disabled={leaveProjectMutation.isPending}
                  >
                    Leave project
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex shrink-0 select-none items-center gap-1.5 min-w-0">
      <div
        onClick={() => setModalOpen(true)}
        className="flex shrink-0 cursor-pointer items-center -space-x-1.5 overflow-hidden"
        title="Manage project co-authors"
      >
        {membersList.map((m) => (
          <Avatar key={m.id} className="size-6 rounded-md border border-ob-line bg-ob-card">
            <AvatarImage src={m.avatar} alt={m.name || "Member"} />
            <AvatarFallback className="rounded-md bg-ob-raised text-[10px] font-medium text-ob-text-2">
              {initialsOf(m.name || m.email || "U")}
            </AvatarFallback>
          </Avatar>
        ))}
      </div>

      <Button
        variant="ob-quiet"
        size="sm"
        onClick={() => setModalOpen(true)}
        className="h-8 cursor-pointer px-2 text-xs"
        title="Invite co-author"
      >
        <UserPlus className="size-3.5" />
        <span className="hidden xl:inline">Invite</span>
      </Button>

      {mounted && modalContent && createPortal(modalContent, document.body)}
    </div>
  );
}
