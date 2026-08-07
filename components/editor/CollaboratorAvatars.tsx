"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Users, UserPlus, Share2, X, Trash2, Crown } from "lucide-react";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";

interface CollaboratorAvatarsProps {
  projectId?: string;
}

export function CollaboratorAvatars({ projectId }: CollaboratorAvatarsProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"Editor" | "Viewer">("Editor");
  const [copied, setCopied] = useState(false);
  const [mounted, setMounted] = useState(false);

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
      toast.success("Collaborator removed.");
      utils.projects.getMembers.invalidate({ projectId: projectId! });
    },
    onError: (err) => {
      toast.error(err.message || "Failed to remove member");
    },
  });

  const transferOwnershipMutation = trpc.projects.transferOwnership.useMutation({
    onSuccess: () => {
      toast.success("Project ownership transferred.");
      utils.projects.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to transfer ownership");
    },
  });

  const isOwner = projectInfo?.isOwner;

  const handleShare = () => {
    if (!projectId) return;
    const shareUrl = `${window.location.origin}/editor/${projectId}`;
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    toast.success("Project URL copied to clipboard!");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !projectId) return;
    sendInviteMutation.mutate({
      projectId,
      email: inviteEmail.trim(),
      role: inviteRole,
    });
  };

  const modalContent = modalOpen && (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) setModalOpen(false);
      }}
    >
      <div className="w-full max-w-md bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden font-sans space-y-0 text-foreground animate-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/40 bg-muted/20">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-indigo-400" />
            <h3 className="font-bold text-sm text-foreground tracking-tight">Invite Co-Authors</h3>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setModalOpen(false)}
            className="h-7 w-7 rounded-lg hover:bg-muted"
          >
            <X className="w-4 h-4 text-muted-foreground" />
          </Button>
        </div>

        <div className="p-5 space-y-4">
          <form onSubmit={handleSendInvite} className="space-y-2.5">
            <label className="text-xs font-semibold text-muted-foreground block">
              Registered Account Email
            </label>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="collaborator@domain.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="h-9 text-xs rounded-xl bg-background border-border/60"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as "Editor" | "Viewer")}
                className="h-9 px-2.5 text-xs rounded-xl border border-border/60 bg-background text-foreground outline-none font-mono cursor-pointer"
              >
                <option value="Editor">Editor</option>
                <option value="Viewer">Viewer</option>
              </select>
            </div>
            <Button
              type="submit"
              disabled={sendInviteMutation.isPending || !inviteEmail.trim()}
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl h-9 text-xs font-medium shadow-md shadow-indigo-500/20"
            >
              {sendInviteMutation.isPending ? "Sending Invite..." : "Send In-App Invite"}
            </Button>
          </form>

          <div className="space-y-2 pt-2 border-t border-border/40">
            <span className="text-xs font-bold text-foreground block">
              Active Members ({membersList.length})
            </span>
            <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
              {membersList.map((m) => (
                <div
                  key={m.id}
                  className="p-2 rounded-xl border border-border/40 bg-muted/20 flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <Avatar className="w-6 h-6 rounded-full border border-border/60">
                      <AvatarImage src={m.avatar} />
                      <AvatarFallback className="bg-indigo-600 text-white text-[9px] font-bold">
                        {(m.name || 'U').slice(0, 2).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <div className="truncate max-w-[180px]">
                      <p className="font-semibold text-foreground text-[11px] truncate flex items-center gap-1">
                        {m.isOwner && <Crown className="w-3 h-3 text-amber-400 shrink-0" />}
                        <span className="truncate">{m.name || m.email}</span>
                      </p>
                      <p className="text-[9px] text-muted-foreground font-mono leading-none">{m.role}</p>
                    </div>
                  </div>

                  {isOwner && !m.isOwner && (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => transferOwnershipMutation.mutate({ projectId: projectId!, newOwnerUserId: m.id })}
                        title="Transfer Ownership"
                        className="p-1 rounded-lg hover:bg-amber-500/20 text-amber-400 transition-colors"
                      >
                        <Crown className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeMemberMutation.mutate({ projectId: projectId!, memberUserId: m.id })}
                        title="Remove Member"
                        className="p-1 rounded-lg hover:bg-rose-500/20 text-rose-400 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <Button
            onClick={handleShare}
            variant="outline"
            className="w-full rounded-xl h-9 text-xs border-border/60 bg-muted/20 hover:bg-muted/40"
          >
            <Share2 className="w-3.5 h-3.5 mr-2 text-indigo-400" />
            {copied ? "Project Link Copied!" : "Copy Direct Project Link"}
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex items-center gap-2">
      <div
        onClick={() => setModalOpen(true)}
        className="flex items-center -space-x-2 overflow-hidden cursor-pointer"
        title="Manage Project Co-Authors"
      >
        {membersList.map((m) => (
          <div key={m.id} className="relative group">
            <Avatar className="w-7 h-7 sm:w-8 sm:h-8 rounded-full border-2 border-background shadow-md">
              <AvatarImage src={m.avatar} alt={m.name || 'Member'} />
              <AvatarFallback className="bg-indigo-600 text-white text-[10px] font-bold">
                {(m.name || 'U').slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>

            <span className="absolute bottom-0 right-0 w-2 h-2 rounded-full bg-emerald-400 border border-background" />

            <div className="absolute right-0 top-10 hidden group-hover:block z-50 p-2.5 rounded-xl border border-border/60 bg-card/95 backdrop-blur-xl shadow-2xl text-xs whitespace-nowrap space-y-1">
              <p className="font-bold text-foreground flex items-center gap-1">
                {m.isOwner && <Crown className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                <span>{m.name || m.email}</span>
              </p>
              <p className="text-[10px] text-indigo-400 font-mono">Role: {m.role}</p>
            </div>
          </div>
        ))}
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={() => setModalOpen(true)}
        className="h-8 px-2.5 border-border/60 bg-card/60 backdrop-blur-md text-xs font-medium"
      >
        <UserPlus className="w-3.5 h-3.5 text-indigo-400 sm:mr-1.5" />
        <span className="hidden sm:inline">Invite Co-Author</span>
      </Button>

      {mounted && modalContent && createPortal(modalContent, document.body)}
    </div>
  );
}
