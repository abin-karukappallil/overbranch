"use client";

import React, { useState, useEffect, Suspense } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Plus,
  FileCode2,
  Search,
  Star,
  FileText,
  Users,
  CheckCircle2,
  FolderPlus,
  UserPlus,
  XCircle,
  FolderGit2,
  ShieldCheck,
  Crown,
  Edit3,
  Eye,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/badge-custom";
import { EmptyState } from "@/components/ui/empty-state";
import { ProjectCardSkeleton } from "@/components/ui/skeleton-loader";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";
import { PDFToLatexModal } from "@/components/dashboard/PDFToLatexModal";

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTemplate, setFilterTemplate] = useState("all");
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [pdfModalOpen, setPdfModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [deleteConfirmProj, setDeleteConfirmProj] = useState<any | null>(null);

  useEffect(() => {
    if (searchParams.get("openPdfModal") === "true") {
      setPdfModalOpen(true);
    }
  }, [searchParams]);

  const utils = trpc.useUtils();

  const { data: projectsData, isLoading: isProjectsLoading } = trpc.projects.listProjects.useQuery({
    search: searchQuery,
    template: filterTemplate,
  });

  const { data: pendingInvites } = trpc.invitations.listPending.useQuery(undefined, {
    refetchInterval: 5000,
  });

  const createMutation = trpc.projects.createProject.useMutation({
    onSuccess: (newProj) => {
      toast.success("LaTeX Project initialized!");
      utils.projects.invalidate();
      setNewModalOpen(false);
      setNewProjName("");
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
      utils.projects.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to delete project");
    },
  });

  const acceptInviteMutation = trpc.invitations.acceptInvite.useMutation({
    onSuccess: () => {
      toast.success("Invitation accepted! Project added to Shared With Me.");
      utils.invitations.invalidate();
      utils.projects.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to accept invitation");
    },
  });

  const declineInviteMutation = trpc.invitations.declineInvite.useMutation({
    onSuccess: () => {
      toast.success("Invitation declined.");
      utils.invitations.invalidate();
    },
  });

  const ownedProjects = (projectsData || []).filter((p: any) => p.isOwner);
  const sharedProjects = (projectsData || []).filter((p: any) => !p.isOwner);

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName.trim()) return;
    createMutation.mutate({
      name: newProjName.trim(),
      description: "Custom LaTeX Workspace",
      template: "None",
    });
  };

  const handleDeleteSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!deleteConfirmProj) return;
    deleteMutation.mutate({ projectId: deleteConfirmProj.id });
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Header Banner */}
      <div className="relative p-6 sm:p-8 rounded-2xl border border-zinc-800 bg-zinc-900 shadow-xl overflow-hidden">
        <div className="relative z-10 space-y-4 sm:space-y-5">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-1.5">
              
              <h1 className="text-xl sm:text-3xl font-archivo font-black uppercase tracking-tight text-white">
                LaTeX Projects Workspace
              </h1>
              <p className="text-xs sm:text-sm text-zinc-400 max-w-2xl leading-relaxed">
                Co-author seminar reports, assignments, project reports, slides, and research papers with real-time compilation and SyncTeX.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-2.5 w-full sm:w-auto shrink-0">
              <Button
                onClick={() => setPdfModalOpen(true)}
                size="lg"
                className="h-10 sm:h-11 w-full sm:w-auto px-5 bg-zinc-800 hover:bg-zinc-700 text-white font-mono font-bold uppercase tracking-wider border border-zinc-700 hover:border-[#00CC68] rounded-xl shrink-0 text-xs justify-center cursor-pointer transition-all shadow-md flex items-center gap-2"
              >
                
                <span>PDF to LaTeX</span>
              </Button>

              <Button
                onClick={() => setNewModalOpen(true)}
                size="lg"
                className="h-10 sm:h-11 w-full sm:w-auto px-6 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider shadow-[4px_4px_0px_0px_#000000] border border-black rounded-xl shrink-0 text-xs justify-center cursor-pointer transition-all"
              >
                <Plus className="w-4 h-4 mr-1.5 text-black stroke-[3]" />
                New Project
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Action Creation Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* PDF to LaTeX Card */}
        <div
          onClick={() => setPdfModalOpen(true)}
          className="group relative p-5 rounded-2xl border border-zinc-800 bg-zinc-900 hover:border-[#00CC68] transition-all cursor-pointer shadow-lg flex flex-col justify-between overflow-hidden hover:shadow-[0_0_24px_rgba(0,204,104,0.15)]"
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="p-2.5 rounded-xl bg-[#00CC68]/15 border border-[#00CC68]/30 text-[#00CC68] group-hover:bg-[#00CC68] group-hover:text-black transition-all">
                <FileText className="w-5 h-5 stroke-[2.5]" />
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#00CC68]/20 text-[#00CC68] border border-[#00CC68]/30 uppercase">
                AI Powered
              </span>
            </div>
            <div>
              <h3 className="text-base font-archivo font-bold text-white group-hover:text-[#00CC68] transition-colors">
                PDF to LaTeX
              </h3>
              <p className="text-xs text-zinc-400 font-sans leading-relaxed mt-1">
                Upload any PDF document to automatically extract text, layout, and images into an editable LaTeX project.
              </p>
            </div>
          </div>
          <div className="pt-4 mt-3 border-t border-zinc-800/80 flex items-center justify-between text-xs font-mono font-bold text-[#00CC68]">
            <span>Import PDF & Convert</span>
            <span className="group-hover:translate-x-1 transition-transform">→</span>
          </div>
        </div>

        {/* Blank Project Card */}
        <div
          onClick={() => setNewModalOpen(true)}
          className="group p-5 rounded-2xl border border-zinc-800 bg-zinc-900 hover:border-zinc-700 transition-all cursor-pointer shadow-lg flex flex-col justify-between"
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="p-2.5 rounded-xl bg-zinc-800 border border-zinc-700 text-zinc-300 group-hover:bg-zinc-700 transition-all">
                <Plus className="w-5 h-5" />
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-zinc-800 text-zinc-400 border border-zinc-700 uppercase">
                Quick Start
              </span>
            </div>
            <div>
              <h3 className="text-base font-archivo font-bold text-white group-hover:text-white transition-colors">
                Blank Project
              </h3>
              <p className="text-xs text-zinc-400 font-sans leading-relaxed mt-1">
                Start from a clean LaTeX canvas with full SyncTeX forward/inverse sync and real-time compilation.
              </p>
            </div>
          </div>
          <div className="pt-4 mt-3 border-t border-zinc-800/80 flex items-center justify-between text-xs font-mono font-bold text-zinc-400 group-hover:text-white transition-colors">
            <span>Create Blank</span>
            <span className="group-hover:translate-x-1 transition-transform">→</span>
          </div>
        </div>

        {/* Templates Card */}
        <Link
          href="/templates"
          className="group p-5 rounded-2xl border border-zinc-800 bg-zinc-900 hover:border-zinc-700 transition-all cursor-pointer shadow-lg flex flex-col justify-between whitespace-normal min-w-0"
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="p-2.5 rounded-xl bg-zinc-800 border border-zinc-700 text-zinc-300 group-hover:bg-zinc-700 transition-all">
                <FolderPlus className="w-5 h-5" />
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-zinc-800 text-zinc-400 border border-zinc-700 uppercase">
                Catalog
              </span>
            </div>
            <div>
              <h3 className="text-base font-archivo font-bold text-white group-hover:text-white transition-colors">
                Templates Library
              </h3>
              <p className="text-xs text-zinc-400 font-sans leading-relaxed mt-1">
                Explore pre-styled templates for research papers, seminar slides, thesis chapters, and resumes.
              </p>
            </div>
          </div>
          <div className="pt-4 mt-3 border-t border-zinc-800/80 flex items-center justify-between text-xs font-mono font-bold text-zinc-400 group-hover:text-white transition-colors">
            <span>Browse Templates</span>
            <span className="group-hover:translate-x-1 transition-transform">→</span>
          </div>
        </Link>
      </div>

      {/* Pending Invitations Section */}
      {pendingInvites && pendingInvites.length > 0 && (
        <div className="p-5 rounded-2xl border border-[#00CC68]/40 bg-zinc-900 space-y-4 shadow-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-[#00CC68]" />
              <h2 className="font-archivo font-black uppercase text-base text-white tracking-tight">
                Pending Team Invitations
              </h2>
              <span className="px-2 py-0.5 rounded-full bg-[#00CC68] text-black text-xs font-mono font-bold">
                {pendingInvites.length}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {pendingInvites.map((invite) => (
              <div
                key={invite.id}
                className="p-4 rounded-xl border border-zinc-800 bg-zinc-950 space-y-3 flex flex-col justify-between"
              >
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs font-mono text-[#00CC68] font-bold">
                    <span>Role: {invite.role}</span>
                    <span className="text-[10px] text-zinc-500">
                      {invite.createdAt ? new Date(invite.createdAt).toLocaleDateString() : "Recent"}
                    </span>
                  </div>
                  <h3 className="font-archivo font-bold text-sm text-white">{invite.projectName}</h3>
                  <p className="text-xs text-zinc-400">
                    Invited by: <span className="text-white font-medium">{invite.senderName || invite.senderEmail}</span>
                  </p>
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <Button
                    size="sm"
                    onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={acceptInviteMutation.isPending}
                    className="h-8 text-xs bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold rounded-lg flex-1 shadow-md cursor-pointer"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                    Accept & Join
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={declineInviteMutation.isPending}
                    className="h-8 text-xs border-zinc-800 hover:bg-zinc-900 text-zinc-300 rounded-lg flex-1 font-mono font-bold"
                  >
                    <XCircle className="w-3.5 h-3.5 mr-1.5" />
                    Decline
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
            Your Document Projects
            <span className="text-xs px-2 py-0.5 rounded-md bg-muted text-muted-foreground font-mono">
              {(ownedProjects.length + sharedProjects.length)}
            </span>
          </h2>
          <p className="text-xs text-muted-foreground">
            Select a project to launch live collaborative LaTeX editor
          </p>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="relative w-full sm:w-64">
            <Input
              placeholder="Search reports, slides & projects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 pl-9 text-xs"
            />
            <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          </div>
        </div>
      </div>

      {isProjectsLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <ProjectCardSkeleton />
          <ProjectCardSkeleton />
          <ProjectCardSkeleton />
        </div>
      ) : ownedProjects.length === 0 && sharedProjects.length === 0 ? (
        <EmptyState
          icon={FolderPlus}
          title="No LaTeX Projects Found"
          description="Create your first LaTeX document or accept pending invitations to start co-authoring."
          primaryActionLabel="Create New LaTeX Project"
          onPrimaryAction={() => setNewModalOpen(true)}
        />
      ) : (
        <div className="space-y-8">
          {/* Owned Projects */}
          {ownedProjects.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-[#00CC68] uppercase tracking-wider font-mono">
                <Crown className="w-4 h-4 text-[#00CC68]" />
                <span>Owned Projects ({ownedProjects.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {ownedProjects.map((project) => (
                  <motion.div key={project.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                    <Card className="group p-5 rounded-2xl border border-zinc-800 bg-zinc-900 hover:border-[#00CC68]/60 transition-all space-y-4 flex flex-col justify-between h-full shadow-lg">
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2 min-w-0">
                          <Link href={`/editor/${project.id}`} className="space-y-1 block flex-1 min-w-0">
                            <h3 className="font-archivo font-bold text-base text-white group-hover:text-[#00CC68] transition-colors flex items-center gap-2 min-w-0">
                              <FileCode2 className="w-4 h-4 text-[#00CC68] shrink-0" />
                              <span className="truncate min-w-0" title={project.name}>{project.name}</span>
                            </h3>
                          </Link>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-[#00CC68]/10 text-[#00CC68] border border-[#00CC68]/20 uppercase">
                              Owner
                            </span>
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                setDeleteConfirmProj(project);
                              }}
                              className="p-1 text-zinc-500 hover:text-rose-400 transition-colors"
                              title="Delete Project"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>

                        <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed font-sans">
                          {project.description}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-zinc-800 flex items-center justify-between gap-2 text-xs text-zinc-400 font-mono min-w-0">
                        <span className="px-2.5 py-1 rounded-lg bg-zinc-950 text-zinc-300 font-medium border border-zinc-800 w-fit shrink-0 text-[11px]" title={project.template || "None"}>
                          {project.template || "None"}
                        </span>

                        <Link
                          href={`/editor/${project.id}`}
                          className="px-3 py-1.5 rounded-xl bg-[#00CC68]/10 hover:bg-[#00CC68] text-[#00CC68] hover:text-black border border-[#00CC68]/30 font-mono font-bold text-[11px] transition-all flex items-center gap-1 shrink-0 whitespace-nowrap"
                        >
                          <span>Open Editor →</span>
                        </Link>
                      </div>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {/* Shared With Me Projects */}
          {sharedProjects.length > 0 && (
            <div className="space-y-3 pt-4">
              <div className="flex items-center gap-2 text-xs font-bold text-[#00CC68] uppercase tracking-wider font-mono">
                <Users className="w-4 h-4 text-[#00CC68]" />
                <span>Shared With Me ({sharedProjects.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {sharedProjects.map((project) => (
                  <motion.div key={project.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                    <Card className="group p-5 rounded-2xl border border-zinc-800 bg-zinc-900 hover:border-[#00CC68]/60 transition-all space-y-4 flex flex-col justify-between h-full shadow-lg">
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2 min-w-0">
                          <Link href={`/editor/${project.id}`} className="space-y-1 block flex-1 min-w-0">
                            <h3 className="font-archivo font-bold text-base text-white group-hover:text-[#00CC68] transition-colors flex items-center gap-2 min-w-0">
                              <FileCode2 className="w-4 h-4 text-[#00CC68] shrink-0" />
                              <span className="truncate min-w-0" title={project.name}>{project.name}</span>
                            </h3>
                          </Link>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-[#00CC68]/10 text-[#00CC68] border border-[#00CC68]/20 uppercase shrink-0">
                            {project.role}
                          </span>
                        </div>

                        <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed font-sans">
                          {project.description}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-zinc-800 flex items-center justify-between gap-2 text-xs text-zinc-400 font-mono min-w-0">
                        <span className="px-2.5 py-1 rounded-lg bg-zinc-950 text-zinc-300 font-medium border border-zinc-800 w-fit shrink-0 text-[11px]" title={project.template || "None"}>
                          {project.template || "None"}
                        </span>

                        <Link
                          href={`/editor/${project.id}`}
                          className="px-3 py-1.5 rounded-xl bg-[#00CC68]/10 hover:bg-[#00CC68] text-[#00CC68] hover:text-black border border-[#00CC68]/30 font-mono font-bold text-[11px] transition-all flex items-center gap-1 shrink-0 whitespace-nowrap"
                        >
                          <span>Open Editor →</span>
                        </Link>
                      </div>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

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
              Are you sure you want to delete <strong className="text-white">{deleteConfirmProj.name}</strong>? This will permanently remove all files, documents, comments, and member access.
            </p>

            <form onSubmit={handleDeleteSubmit} className="flex justify-end gap-2 pt-2 text-xs font-mono font-bold">
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

      {/* New Project Modal */}
      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-md w-[calc(100vw-2rem)] p-6 rounded-2xl border border-zinc-800 bg-zinc-900 text-white shadow-2xl space-y-4">
            <h3 className="text-base font-archivo font-black uppercase text-white">Create LaTeX Project</h3>
            <form onSubmit={handleCreateSubmit} className="space-y-4 font-mono">
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400 font-bold uppercase">Project Name</label>
                <Input
                  autoFocus
                  placeholder="Enter a project name"
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
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

      {/* PDF to LaTeX Conversion Modal */}
      <PDFToLatexModal
        isOpen={pdfModalOpen}
        onClose={() => setPdfModalOpen(false)}
      />
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={null}>
      <DashboardContent />
    </Suspense>
  );
}
