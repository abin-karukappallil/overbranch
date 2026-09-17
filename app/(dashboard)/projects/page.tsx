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
  Trash2,
  AlertTriangle,
  ArrowRight,
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

  const { data: dbProjects, isLoading, refetch } = trpc.projects.listProjects.useQuery(
    {
      search,
      template: templateFilter,
      favoritesOnly: showFavoritesOnly,
    },
    {
      placeholderData: (previousData) => previousData,
      staleTime: 60 * 1000,
    }
  );

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
    <div className="space-y-6 animate-fade-in pb-16 text-slate-900 dark:text-[#E2E4E9]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] text-[11px] font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
            <span>Repository Index</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-archivo font-bold tracking-tight text-slate-900 dark:text-[#E2E4E9]">
            Project Workspaces
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-[#9E9E9E]">
            Manage and co-author your seminar reports, assignments, project thesis, slides & research papers.
          </p>
        </div>

        <Button
          onClick={() => setNewModalOpen(true)}
          className="w-full sm:w-auto bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold rounded-lg h-9 px-4 text-xs border border-emerald-600 dark:border-[#282A30] shrink-0 justify-center cursor-pointer transition-all flex items-center gap-1.5 shadow-sm"
        >
          <Plus className="w-4 h-4 mr-1 text-white dark:text-[#E2E4E9] stroke-[2.5]" />
          New Project
        </Button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] shadow-sm dark:shadow-none font-mono">
        <div className="relative flex-1 w-full sm:max-w-sm">
          <Input
            placeholder="Search documents & projects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 text-xs pl-8 bg-slate-50 dark:bg-[#1A1C22] border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46]"
          />
          <Search className="w-3.5 h-3.5 text-slate-400 dark:text-[#62666D] absolute left-2.5 top-1/2 -translate-y-1/2" />
        </div>

        <div className="flex items-center gap-2 text-xs w-full sm:w-auto justify-between sm:justify-start">
          <button
            onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            className={`px-3 py-1.5 rounded-lg border text-xs font-mono transition-colors flex items-center gap-1.5 cursor-pointer ${
              showFavoritesOnly
                ? "bg-amber-50 dark:bg-[#22242C] border-amber-200 dark:border-[#383B46] text-amber-800 dark:text-[#E2E4E9] font-semibold"
                : "border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] hover:bg-slate-100 dark:hover:bg-[#1E2026] hover:text-slate-900 dark:hover:text-[#E2E4E9]"
            }`}
          >
            <Star className={`w-3.5 h-3.5 ${showFavoritesOnly ? "fill-amber-400 text-amber-400" : ""}`} />
            <span>Favorites</span>
          </button>

          <select
            value={templateFilter}
            onChange={(e) => setTemplateFilter(e.target.value)}
            className="h-9 px-3 text-xs rounded-lg border border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] outline-none font-mono flex-1 sm:flex-initial cursor-pointer hover:border-slate-300 dark:hover:border-[#383B46] transition-colors"
          >
            <option value="all">All Templates</option>
            <option value="Report">Seminar / Report</option>
            <option value="Beamer">Beamer Slides (PPT)</option>
            <option value="Thesis">Project Thesis</option>
            <option value="Paper">Journal Paper</option>
            <option value="Resume">Resume / CV</option>
          </select>
        </div>
      </div>

      {/* Projects Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {filtered.map((proj: any) => (
          <motion.div key={proj.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="group p-5 rounded-2xl border border-slate-200 dark:border-[#23252A] bg-white dark:bg-[#0F1011] hover:border-slate-300 dark:hover:border-[#343842] hover:bg-slate-50 dark:hover:bg-[#121315] transition-all space-y-4 flex flex-col justify-between h-full shadow-sm dark:shadow-lg">
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <Link href={`/editor/${proj.id}`} className="space-y-1 block flex-1 min-w-0">
                    <h3 className="font-semibold text-sm text-slate-900 dark:text-[#F7F8F8] group-hover:text-emerald-600 dark:group-hover:text-white transition-colors flex items-center gap-2 truncate">
                      <FileCode2 className="w-4 h-4 text-emerald-600 dark:text-[#5E6AD2] shrink-0" />
                      <span className="truncate min-w-0">{proj.name}</span>
                    </h3>
                  </Link>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={(e) => toggleFavorite(proj.id, e)}
                      className="p-1 text-slate-400 dark:text-[#62666D] hover:text-amber-400 transition-colors"
                      title="Toggle Favorite"
                    >
                      <Star className={`w-3.5 h-3.5 ${proj.isFavorite ? "text-amber-400 fill-amber-400" : ""}`} />
                    </button>
                    {proj.isOwner && (
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setDeleteConfirmProj(proj);
                        }}
                        className="p-1 text-slate-400 dark:text-[#62666D] hover:text-red-500 dark:hover:text-[#EB5757] transition-colors"
                        title="Delete Project"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                <p className="text-xs text-slate-500 dark:text-[#8A8F98] line-clamp-2 leading-relaxed">
                  {proj.description}
                </p>
              </div>

              <div className="pt-3 border-t border-slate-100 dark:border-[#23252A] flex items-center justify-between text-xs text-slate-500 dark:text-[#8A8F98] font-mono gap-2">
                <span className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-[#08090A] text-slate-600 dark:text-[#8A8F98] font-medium border border-slate-200 dark:border-[#23252A] w-fit shrink-0 text-[11px]" title={proj.template || "None"}>
                  {proj.template || "None"}
                </span>

                <button
                  onClick={() => setInviteModalProj(proj)}
                  className="px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-emerald-600 dark:bg-[#18191B] dark:hover:bg-[#5E6AD2] text-slate-800 hover:text-white dark:text-[#F7F8F8] dark:hover:text-white border border-slate-200 hover:border-emerald-600 dark:border-[#23252A] dark:hover:border-[#5E6AD2] font-mono font-medium text-xs transition-all flex items-center gap-1.5 cursor-pointer shrink-0"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/50 dark:bg-black/80 backdrop-blur-xs animate-fade-in">
          <div className="max-w-sm w-[calc(100vw-2rem)] p-5 rounded-2xl border border-red-200 dark:border-[#EB5757]/30 bg-white dark:bg-[#0F1011] text-slate-900 dark:text-[#F7F8F8] shadow-2xl space-y-4">
            <div className="flex items-center gap-2.5 text-red-600 dark:text-[#EB5757]">
              <div className="p-2 rounded-xl bg-red-50 dark:bg-[#EB5757]/10 border border-red-200 dark:border-[#EB5757]/20">
                <AlertTriangle className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-semibold uppercase text-slate-900 dark:text-[#F7F8F8]">Delete Project</h3>
            </div>

            <p className="text-xs text-slate-600 dark:text-[#8A8F98] leading-relaxed">
              Are you sure you want to delete <strong className="text-slate-900 dark:text-[#F7F8F8]">{deleteConfirmProj.name}</strong>? This will permanently remove all files, documents, and co-author access.
            </p>

            <form onSubmit={handleDeleteProject} className="flex justify-end gap-2 pt-2 text-xs font-mono font-medium">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setDeleteConfirmProj(null)}
                className="h-8 text-xs rounded-xl border-slate-200 dark:border-[#23252A] bg-slate-50 dark:bg-[#141517] hover:bg-slate-100 dark:hover:bg-[#1C1E22] text-slate-600 dark:text-[#8A8F98] hover:text-slate-900 dark:hover:text-[#F7F8F8]"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={deleteMutation.isPending}
                className="h-8 text-xs bg-red-600 hover:bg-red-700 dark:bg-[#EB5757] dark:hover:bg-[#D64545] text-white font-mono font-semibold rounded-xl shadow-md border border-red-600 dark:border-[#EB5757]/50"
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete Permanently"}
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/50 dark:bg-black/80 backdrop-blur-xs animate-fade-in">
          <div className="max-w-md w-[calc(100vw-2rem)] p-6 rounded-2xl border border-slate-200 dark:border-[#23252A] bg-white dark:bg-[#0F1011] text-slate-900 dark:text-[#F7F8F8] shadow-2xl space-y-4">
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-slate-900 dark:text-[#F7F8F8]">Create LaTeX Project</h3>
              <p className="text-xs text-slate-500 dark:text-[#8A8F98]">Initialize a new LaTeX document workspace with real-time compilation.</p>
            </div>
            <form onSubmit={handleCreateProject} className="space-y-4 font-mono">
              <div className="space-y-1.5">
                <label className="text-xs text-slate-600 dark:text-[#8A8F98] font-medium uppercase">Project Name</label>
                <Input
                  autoFocus
                  placeholder="e.g. Quantum Computing Seminar"
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  required
                  className="h-10 text-xs font-mono border-slate-200 dark:border-[#23252A] bg-slate-50 dark:bg-[#141517] text-slate-900 dark:text-[#F7F8F8] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-xl focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#5E6AD2]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 text-xs font-medium">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setNewModalOpen(false)}
                  className="h-9 text-xs border-slate-200 dark:border-[#23252A] bg-slate-50 dark:bg-[#141517] hover:bg-slate-100 dark:hover:bg-[#1C1E22] text-slate-600 dark:text-[#8A8F98] hover:text-slate-900 dark:hover:text-[#F7F8F8] rounded-xl"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending || !newProjName.trim()}
                  className="h-9 text-xs bg-emerald-600 hover:bg-emerald-700 dark:bg-[#5E6AD2] dark:hover:bg-[#4F5BBE] text-white font-semibold rounded-xl border border-emerald-600 dark:border-[#6875E5]/30 shadow-sm cursor-pointer"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/50 dark:bg-black/80 backdrop-blur-xs animate-fade-in">
          <div className="max-w-md w-[calc(100vw-2rem)] p-6 rounded-2xl border border-slate-200 dark:border-[#23252A] bg-white dark:bg-[#0F1011] text-slate-900 dark:text-[#F7F8F8] shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-[#23252A] pb-3 gap-2">
              <span className="font-semibold text-sm text-slate-900 dark:text-[#F7F8F8] truncate min-w-0 flex-1">
                Invite Co-Author to: {inviteModalProj.name}
              </span>
              <button onClick={() => setInviteModalProj(null)} className="text-slate-400 dark:text-[#8A8F98] hover:text-slate-900 dark:hover:text-[#F7F8F8] shrink-0">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSendProjectInvite} className="space-y-4 font-mono text-xs">
              <div className="space-y-1.5">
                <label className="text-slate-600 dark:text-[#8A8F98] font-medium uppercase text-[11px]">Registered User Email</label>
                <Input
                  type="email"
                  placeholder="collaborator@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  className="h-10 text-xs border-slate-200 dark:border-[#23252A] bg-slate-50 dark:bg-[#141517] text-slate-900 dark:text-[#F7F8F8] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-xl focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#5E6AD2]"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-slate-600 dark:text-[#8A8F98] font-medium uppercase text-[11px]">Permission Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as "Editor" | "Viewer")}
                  className="w-full h-10 px-3 text-xs rounded-xl border border-slate-200 dark:border-[#23252A] bg-slate-50 dark:bg-[#141517] text-slate-900 dark:text-[#F7F8F8] outline-none font-mono cursor-pointer hover:border-slate-300 dark:hover:border-[#343842] transition-colors"
                >
                  <option value="Editor">Editor (Full edit & compile)</option>
                  <option value="Viewer">Viewer (Read-only)</option>
                </select>
              </div>

              <Button
                type="submit"
                size="sm"
                disabled={sendInviteMutation.isPending || !inviteEmail.trim()}
                className="w-full bg-emerald-600 hover:bg-emerald-700 dark:bg-[#5E6AD2] dark:hover:bg-[#4F5BBE] text-white font-mono font-semibold rounded-xl h-10 text-xs border border-emerald-600 dark:border-[#6875E5]/30 shadow-sm cursor-pointer"
              >
                {sendInviteMutation.isPending ? "Validating & Inviting..." : "Send Workspace Invite"}
              </Button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
