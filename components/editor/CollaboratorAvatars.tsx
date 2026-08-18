"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Users, UserPlus, Share2, X, Trash2, Crown, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";

interface CollaboratorAvatarsProps {
  projectId?: string;
}

export function CollaboratorAvatars({ projectId }: CollaboratorAvatarsProps) {
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"Editor" | "Viewer">("Editor");
  const [copied, setCopied] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

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

  const deleteProjectMutation = trpc.projects.deleteProject.useMutation({
    onSuccess: () => {
      toast.success("Project deleted successfully.");
      setModalOpen(false);
      setDeleteConfirmOpen(false);
      router.push("/dashboard");
    },
    onError: (err) => {
      toast.error(err.message || "Failed to delete project");
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
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) setModalOpen(false);
      }}
    >
      <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 text-white rounded-2xl shadow-2xl overflow-hidden font-sans space-y-0 animate-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 bg-zinc-950">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-[#00CC68]" />
            <h3 className="font-archivo font-black uppercase text-sm text-white tracking-tight">Invite Co-Authors</h3>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setModalOpen(false)}
            className="h-7 w-7 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="p-5 space-y-4 font-mono">
          <form onSubmit={handleSendInvite} className="space-y-2.5">
            <label className="text-xs font-bold text-zinc-400 uppercase block">
              Registered Account Email
            </label>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="collaborator@domain.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="h-9 text-xs rounded-xl bg-zinc-950 border-zinc-800 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as "Editor" | "Viewer")}
                className="h-9 px-2.5 text-xs rounded-xl border border-zinc-800 bg-zinc-950 text-white outline-none font-mono cursor-pointer"
              >
                <option value="Editor">Editor</option>
                <option value="Viewer">Viewer</option>
              </select>
            </div>
            <Button
              type="submit"
              disabled={sendInviteMutation.isPending || !inviteEmail.trim()}
              className="w-full bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider rounded-xl h-9 text-xs border border-black shadow-[3px_3px_0px_0px_#000000] cursor-pointer"
            >
              {sendInviteMutation.isPending ? "Sending Invite..." : "Send In-App Invite"}
            </Button>
          </form>

          <div className="space-y-2 pt-2 border-t border-zinc-800">
            <span className="text-xs font-bold text-white uppercase block">
              Active Members ({membersList.length})
            </span>
            <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
              {membersList.map((m) => (
                <div
                  key={m.id}
                  className="p-2 rounded-xl border border-zinc-800 bg-zinc-950 flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <Avatar className="w-6 h-6 rounded-full border border-zinc-700">
                      <AvatarImage src={m.avatar} />
                      <AvatarFallback className="bg-[#00CC68] text-black text-[9px] font-bold">
                        {(m.name || 'U').slice(0, 2).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <div className="truncate max-w-[180px]">
                      <p className="font-semibold text-white text-[11px] truncate flex items-center gap-1">
                        {m.isOwner && <Crown className="w-3 h-3 text-amber-400 shrink-0" />}
                        <span className="truncate">{m.name || m.email}</span>
                      </p>
                      <p className="text-[9px] text-[#00CC68] font-mono leading-none">{m.role}</p>
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
            className="w-full rounded-xl h-9 text-xs border-zinc-800 bg-zinc-950 hover:bg-zinc-800 text-white font-mono font-bold"
          >
            <Share2 className="w-3.5 h-3.5 mr-2 text-[#00CC68]" />
            {copied ? "Project Link Copied!" : "Copy Direct Project Link"}
          </Button>

          {isOwner && (
            <div className="pt-3 border-t border-rose-500/20 space-y-2">
              <span className="text-[11px] font-bold text-rose-500 uppercase tracking-wider block font-mono">
                Danger Zone
              </span>
              {!deleteConfirmOpen ? (
                <Button
                  onClick={() => setDeleteConfirmOpen(true)}
                  variant="outline"
                  className="w-full rounded-xl h-9 text-xs border-rose-500/40 text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 transition-colors flex items-center justify-center gap-1.5 font-mono font-bold"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Delete Project</span>
                </Button>
              ) : (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 space-y-2 font-sans animate-in fade-in">
                  <div className="flex items-center gap-2 text-rose-400 font-bold text-xs">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>Confirm Project Deletion</span>
                  </div>
                  <p className="text-[11px] text-zinc-400 leading-relaxed">
                    This action is permanent and will delete all files and member permissions.
                  </p>
                  <div className="flex items-center gap-2 pt-1 font-mono font-bold">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleteConfirmOpen(false)}
                      className="h-8 text-xs rounded-lg flex-1 text-zinc-300"
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => deleteProjectMutation.mutate({ projectId: projectId! })}
                      disabled={deleteProjectMutation.isPending}
                      className="h-8 text-xs bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-lg flex-1 shadow-md"
                    >
                      {deleteProjectMutation.isPending ? "Deleting..." : "Confirm Delete"}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex items-center gap-2 select-none">
      <div
        onClick={() => setModalOpen(true)}
        className="flex items-center -space-x-2 overflow-hidden cursor-pointer"
        title="Manage Project Co-Authors"
      >
        {membersList.map((m) => (
          <div key={m.id} className="relative group">
            <Avatar className="w-7 h-7 sm:w-8 sm:h-8 rounded-full border-2 border-zinc-950 shadow-md">
              <AvatarImage src={m.avatar} alt={m.name || 'Member'} />
              <AvatarFallback className="bg-[#00CC68] text-black text-[10px] font-bold">
                {(m.name || 'U').slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>

            <span className="absolute bottom-0 right-0 w-2 h-2 rounded-full bg-[#00CC68] border border-zinc-950" />

            <div className="absolute right-0 top-10 hidden group-hover:block z-50 p-2.5 rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl text-xs whitespace-nowrap space-y-1">
              <p className="font-bold text-white flex items-center gap-1">
                {m.isOwner && <Crown className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                <span>{m.name || m.email}</span>
              </p>
              <p className="text-[10px] text-[#00CC68] font-mono">Role: {m.role}</p>
            </div>
          </div>
        ))}
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={() => setModalOpen(true)}
        className="h-8 px-3 border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-white font-mono font-bold text-xs rounded-xl"
      >
        <UserPlus className="w-3.5 h-3.5 text-[#00CC68] sm:mr-1.5" />
        <span className="hidden sm:inline">Invite Co-Author</span>
      </Button>

      {mounted && modalContent && createPortal(modalContent, document.body)}
    </div>
  );
}
