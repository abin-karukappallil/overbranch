"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Plus,
  Search,
  Star,
  UserPlus,
  FileCode2,
  X,
  Users,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";

export default function ProjectsPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [templateFilter, setTemplateFilter] = useState("all");
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [inviteModalProj, setInviteModalProj] = useState<any | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"Editor" | "Viewer">("Editor");
  const [deleteConfirmProj, setDeleteConfirmProj] = useState<any | null>(null);

  const utils = trpc.useUtils();

  const { data: dbProjects, isLoading, refetch } = trpc.projects.listProjects.useQuery({
    search,
    template: templateFilter,
    favoritesOnly: showFavoritesOnly,
  });

  const toggleFavMutation = trpc.projects.toggleFavorite.useMutation({
    onSuccess: () => refetch(),
  });

  const createMutation = trpc.projects.createProject.useMutation({
    onSuccess: (newProj) => {
      refetch();
      setNewModalOpen(false);
      setNewProjName("");
      toast.success("Project created successfully!");
      router.push(`/editor/${newProj.id}`);
    },
    onError: (err) => {
      toast.error(err.message || "Failed to create project");
    },
  });

  const deleteMutation = trpc.projects.deleteProject.useMutation({
    onSuccess: () => {
      toast.success("Project deleted successfully.");
      setDeleteConfirmProj(null);
      refetch();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to delete project");
    },
  });

  const sendInviteMutation = trpc.invitations.sendInvite.useMutation({
    onSuccess: (data) => {
      toast.success(`Invitation sent to ${data.receiverName || data.receiverEmail}`);
      setInviteEmail("");
      setInviteModalProj(null);
    },
    onError: (err) => {
      toast.error(err.message || "Invitation failed");
    },
  });

  const filtered = dbProjects || [];

  const toggleFavorite = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const target = filtered.find((p: any) => p.id === id);
    if (target) {
      toggleFavMutation.mutate({ projectId: id, isFavorite: !target.isFavorite });
    }
  };

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName.trim()) return;
    createMutation.mutate({
      name: newProjName.trim(),
      description: "Custom LaTeX Workspace",
      template: "None",
    });
  };

  const handleDeleteProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!deleteConfirmProj) return;
    deleteMutation.mutate({ projectId: deleteConfirmProj.id });
  };

  const handleSendProjectInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !inviteModalProj) return;
    sendInviteMutation.mutate({
      projectId: inviteModalProj.id,
      email: inviteEmail.trim(),
      role: inviteRole,
    });
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12 font-sans text-zinc-100">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl sm:text-3xl font-archivo font-black uppercase tracking-tight text-white">
            Project Workspaces
          </h1>
          <p className="text-xs sm:text-sm text-zinc-400">
            Manage and co-author your seminar reports, assignments, project reports, slides & research papers.
          </p>
        </div>

        <Button
          onClick={() => setNewModalOpen(true)}
          className="w-full sm:w-auto bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider rounded-xl h-10 px-5 text-xs border border-black shadow-[3px_3px_0px_0px_#000000] shrink-0 justify-center cursor-pointer transition-all"
        >
          <Plus className="w-4 h-4 mr-1.5 text-black stroke-[3]" />
          New Project
        </Button>
      </div>

      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-2xl border border-zinc-800 bg-zinc-900 shadow-lg font-mono">
        <div className="relative flex-1 w-full sm:max-w-sm">
          <Input
            placeholder="Search documents & projects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 text-xs pl-8 bg-zinc-950 border-zinc-800 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
          />
          <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
        </div>

        <div className="flex items-center gap-2 text-xs w-full sm:w-auto justify-between sm:justify-start">
          <button
            onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            className={`px-3 py-2 rounded-xl border text-xs font-mono transition-colors flex items-center gap-1.5 cursor-pointer ${
              showFavoritesOnly
                ? "bg-[#00CC68]/10 border-[#00CC68]/30 text-[#00CC68] font-bold"
                : "border-zinc-800 text-zinc-400 hover:bg-zinc-800"
            }`}
          >
            <Star className={`w-3.5 h-3.5 ${showFavoritesOnly ? "fill-amber-400 text-amber-400" : ""}`} />
            <span>Favorites</span>
          </button>

          <select
            value={templateFilter}
            onChange={(e) => setTemplateFilter(e.target.value)}
            className="h-9 px-3 text-xs rounded-xl border border-zinc-800 bg-zinc-950 text-white outline-none font-mono flex-1 sm:flex-initial cursor-pointer"
          >
            <option value="all">All Templates</option>
            <option value="Report">Seminar / Report</option>
            <option value="Beamer">Beamer Slides (PPT)</option>
            <option value="Thesis">Project Thesis</option>
            <option value="Paper">Journal Paper</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((proj: any) => (
          <motion.div key={proj.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="group p-5 rounded-2xl border border-zinc-800 bg-zinc-900 hover:border-[#00CC68]/60 transition-all space-y-4 flex flex-col justify-between h-full shadow-lg">
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <Link href={`/editor/${proj.id}`} className="space-y-1 block flex-1 min-w-0">
                    <h3 className="font-archivo font-bold text-base text-white group-hover:text-[#00CC68] transition-colors flex items-center gap-2 truncate">
                      <FileCode2 className="w-4 h-4 text-[#00CC68] shrink-0" />
                      <span className="truncate min-w-0">{proj.name}</span>
                    </h3>
                  </Link>

                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={(e) => toggleFavorite(proj.id, e)} className="p-1 text-zinc-500 hover:text-amber-400 transition-colors" title="Toggle Favorite">
                      <Star className={`w-3.5 h-3.5 ${proj.isFavorite ? "text-amber-400 fill-amber-400" : ""}`} />
                    </button>
                    {proj.isOwner && (
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setDeleteConfirmProj(proj);
                        }}
                        className="p-1 text-zinc-500 hover:text-rose-400 transition-colors"
                        title="Delete Project"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed font-sans">
                  {proj.description}
                </p>
              </div>

              <div className="pt-3 border-t border-zinc-800 flex items-center justify-between text-xs text-zinc-400 font-mono gap-2">
                <span className="px-2.5 py-1 rounded-lg bg-zinc-950 text-zinc-300 font-medium border border-zinc-800 w-fit shrink-0 text-[11px]" title={proj.template || "None"}>
                  {proj.template || "None"}
                </span>

                <button
                  onClick={() => setInviteModalProj(proj)}
                  className="px-3 py-1.5 rounded-xl bg-[#00CC68]/10 hover:bg-[#00CC68] text-[#00CC68] hover:text-black border border-[#00CC68]/30 font-mono font-bold text-xs transition-all flex items-center gap-1.5 cursor-pointer shrink-0"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>Invite Co-Author</span>
                </button>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmProj && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-sm w-[calc(100vw-2rem)] p-5 rounded-2xl border border-rose-500/40 bg-zinc-900 text-white shadow-2xl space-y-4">
            <div className="flex items-center gap-2.5 text-rose-500">
              <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-archivo font-bold uppercase text-white">Delete Project</h3>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed font-sans">
              Are you sure you want to delete <strong className="text-white">{deleteConfirmProj.name}</strong>? This will permanently remove all files, documents, comments, and member access. Action cannot be undone.
            </p>

            <form onSubmit={handleDeleteProject} className="flex justify-end gap-2 pt-2 text-xs font-mono font-bold">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setDeleteConfirmProj(null)}
                className="h-8 text-xs rounded-xl border-zinc-800 text-zinc-300"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={deleteMutation.isPending}
                className="h-8 text-xs bg-rose-600 hover:bg-rose-500 text-white font-mono font-bold rounded-xl shadow-md"
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete Permanently"}
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-md w-[calc(100vw-2rem)] p-6 rounded-2xl border border-zinc-800 bg-zinc-900 text-white shadow-2xl space-y-4">
            <h3 className="text-base font-archivo font-black uppercase text-white">Create LaTeX Project</h3>
            <form onSubmit={handleCreateProject} className="space-y-4 font-mono">
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400 font-bold uppercase">Project Name</label>
                <Input
                  autoFocus
                  placeholder="e.g. Quantum_State_Paper_2026"
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  required
                  className="h-10 text-xs font-mono border-zinc-800 bg-zinc-950 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 text-xs font-bold">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setNewModalOpen(false)}
                  className="h-9 text-xs border-zinc-800 text-zinc-300"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending || !newProjName.trim()}
                  className="h-9 text-xs bg-[#00CC68] hover:bg-[#00E676] text-black font-bold border border-black shadow-[3px_3px_0px_0px_#000000] cursor-pointer"
                >
                  {createMutation.isPending ? "Creating..." : "Create Project →"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Invite Collaborator Modal */}
      {inviteModalProj && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-md w-[calc(100vw-2rem)] p-6 rounded-2xl border border-zinc-800 bg-zinc-900 text-white shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3 gap-2">
              <span className="font-archivo font-bold text-sm text-white uppercase truncate min-w-0 flex-1">
                Invite to: {inviteModalProj.name}
              </span>
              <button onClick={() => setInviteModalProj(null)} className="text-zinc-500 hover:text-white shrink-0">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSendProjectInvite} className="space-y-4 font-mono text-xs">
              <div className="space-y-1.5">
                <label className="text-zinc-400 font-bold uppercase text-[11px]">Registered User Email</label>
                <Input
                  type="email"
                  placeholder="coauthor@university.edu"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  className="h-10 text-xs border-zinc-800 bg-zinc-950 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-zinc-400 font-bold uppercase text-[11px]">Permission Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as "Editor" | "Viewer")}
                  className="w-full h-10 px-3 text-xs rounded-xl border border-zinc-800 bg-zinc-950 text-white outline-none font-mono cursor-pointer"
                >
                  <option value="Editor">Editor (Full edit & compile)</option>
                  <option value="Viewer">Viewer (Read-only)</option>
                </select>
              </div>

              <Button
                type="submit"
                size="sm"
                disabled={sendInviteMutation.isPending || !inviteEmail.trim()}
                className="w-full bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider rounded-xl h-10 text-xs border border-black shadow-[3px_3px_0px_0px_#000000] cursor-pointer"
              >
                {sendInviteMutation.isPending ? "Validating & Inviting..." : "Send In-App Invite"}
              </Button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
