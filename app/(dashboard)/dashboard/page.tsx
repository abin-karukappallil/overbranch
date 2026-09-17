"use client";

import React, { useState, useEffect, Suspense } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Plus,
  FileCode2,
  Search,
  FileText,
  Users,
  CheckCircle2,
  FolderPlus,
  UserPlus,
  XCircle,
  Crown,
  Trash2,
  AlertTriangle,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

  const { data: projectsData, isLoading: isProjectsLoading } = trpc.projects.listProjects.useQuery(
    {
      search: searchQuery,
      template: filterTemplate,
    },
    {
      placeholderData: (previousData) => previousData,
      staleTime: 60 * 1000,
    }
  );

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
    <div className="space-y-8 animate-fade-in pb-16 text-slate-900 dark:text-[#E2E4E9]">
      {/* Header Banner */}
      <div className="relative p-6 sm:p-8 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] shadow-sm dark:shadow-none overflow-hidden">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5">
          <div className="space-y-1.5">
            <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] text-[11px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
              <span>Workspace Hub</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-archivo font-bold tracking-tight text-slate-900 dark:text-[#E2E4E9]">
              Document Projects
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-[#9E9E9E] max-w-2xl leading-relaxed">
              Co-author seminar reports, assignments, project thesis, slides, and research papers with real-time compilation and SyncTeX.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-2.5 w-full sm:w-auto shrink-0">
            <Button
              onClick={() => setPdfModalOpen(true)}
              size="lg"
              className="h-9 sm:h-9 w-full sm:w-auto px-4 bg-slate-100 hover:bg-slate-200 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] text-slate-800 dark:text-[#E2E4E9] font-mono font-medium border border-slate-200 dark:border-[#282A30] rounded-lg shrink-0 text-xs justify-center cursor-pointer transition-all flex items-center gap-2"
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-600 dark:text-[#E2E4E9]" />
              <span>PDF to LaTeX</span>
              <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-white dark:bg-[#141519] text-slate-500 dark:text-[#9E9E9E] border border-slate-200 dark:border-[#282A30] tracking-wider">
                BETA
              </span>
            </Button>

            <Button
              onClick={() => setNewModalOpen(true)}
              size="lg"
              className="h-9 sm:h-9 w-full sm:w-auto px-4 bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold rounded-lg shrink-0 text-xs justify-center cursor-pointer transition-all border border-emerald-600 dark:border-[#282A30] shadow-sm"
            >
              <Plus className="w-4 h-4 mr-1.5 text-white dark:text-[#E2E4E9] stroke-[2.5]" />
              New Project
            </Button>
          </div>
        </div>
      </div>

      {/* Quick Action Creation Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* PDF to LaTeX Card */}
        <div
          onClick={() => setPdfModalOpen(true)}
          className="group relative p-5 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] hover:bg-slate-50 dark:hover:bg-[#1A1C22] hover:border-slate-300 dark:hover:border-[#383B46] transition-all cursor-pointer flex flex-col justify-between overflow-hidden shadow-sm dark:shadow-none"
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="p-2.5 rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-slate-800 dark:text-[#E2E4E9] group-hover:bg-slate-200 dark:group-hover:bg-[#22242C] transition-all">
                <FileText className="w-4 h-4 stroke-[2]" />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-slate-100 dark:bg-[#1A1C22] text-slate-500 dark:text-[#9E9E9E] border border-slate-200 dark:border-[#282A30] uppercase tracking-wider">
                  BETA
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-100 dark:bg-[#1E2026] text-slate-700 dark:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30] uppercase">
                  AI Convert
                </span>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] transition-colors flex items-center gap-2">
                <span>PDF to LaTeX</span>
              </h3>
              <p className="text-xs text-slate-500 dark:text-[#9E9E9E] leading-relaxed mt-1">
                Upload any PDF document to automatically extract text, layout, and equations into an editable LaTeX project.
              </p>
            </div>
          </div>
          <div className="pt-4 mt-3 border-t border-slate-100 dark:border-[#282A30] flex items-center justify-between text-xs font-mono font-medium text-slate-800 dark:text-[#E2E4E9]">
            <span>Import PDF & Convert</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        {/* Blank Project Card */}
        <div
          onClick={() => setNewModalOpen(true)}
          className="group relative p-5 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] hover:bg-slate-50 dark:hover:bg-[#1A1C22] hover:border-slate-300 dark:hover:border-[#383B46] transition-all cursor-pointer flex flex-col justify-between overflow-hidden shadow-sm dark:shadow-none"
        >
          <div className="space-y-3">
            <div className="p-2.5 rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-slate-800 dark:text-[#E2E4E9] group-hover:bg-slate-200 dark:group-hover:bg-[#22242C] transition-all w-fit">
              <Plus className="w-4 h-4 stroke-[2]" />
            </div>
            <div>
              <h3 className="text-sm font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] transition-colors">
                New Blank Document
              </h3>
              <p className="text-xs text-slate-500 dark:text-[#9E9E9E] leading-relaxed mt-1">
                Start from a minimal LaTeX article template with live PDF rendering.
              </p>
            </div>
          </div>
          <div className="pt-4 mt-3 border-t border-slate-100 dark:border-[#282A30] flex items-center justify-between text-xs font-mono font-medium text-slate-800 dark:text-[#E2E4E9]">
            <span>Create Empty Project</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        {/* Browse Templates Card */}
        <Link
          href="/templates"
          className="group relative p-5 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] hover:bg-slate-50 dark:hover:bg-[#1A1C22] hover:border-slate-300 dark:hover:border-[#383B46] transition-all cursor-pointer flex flex-col justify-between overflow-hidden shadow-sm dark:shadow-none"
        >
          <div className="space-y-3">
            <div className="p-2.5 rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-slate-800 dark:text-[#E2E4E9] group-hover:bg-slate-200 dark:group-hover:bg-[#22242C] transition-all w-fit">
              <FileCode2 className="w-4 h-4 stroke-[2]" />
            </div>
            <div>
              <h3 className="text-sm font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] transition-colors">
                Browse Templates
              </h3>
              <p className="text-xs text-slate-500 dark:text-[#9E9E9E] leading-relaxed mt-1">
                Pick from IEEE papers, resumes, slide presentations, and lab reports.
              </p>
            </div>
          </div>
          <div className="pt-4 mt-3 border-t border-slate-100 dark:border-[#282A30] flex items-center justify-between text-xs font-mono font-medium text-slate-500 dark:text-[#9E9E9E] group-hover:text-slate-900 dark:group-hover:text-[#E2E4E9] transition-colors">
            <span>Browse Gallery</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </Link>
      </div>

      {/* Pending Invitations Section */}
      {pendingInvites && pendingInvites.length > 0 && (
        <div className="p-5 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] space-y-4 shadow-sm dark:shadow-none">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <UserPlus className="w-4 h-4 text-slate-900 dark:text-[#E2E4E9]" />
              <h2 className="font-archivo font-bold text-sm text-slate-900 dark:text-[#E2E4E9]">
                Pending Team Invitations
              </h2>
              <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] text-[11px] font-mono font-bold">
                {pendingInvites.length}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {pendingInvites.map((invite) => (
              <div
                key={invite.id}
                className="p-4 rounded-lg border border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] space-y-3 flex flex-col justify-between"
              >
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs font-mono text-slate-500 dark:text-[#9E9E9E] font-semibold">
                    <span>Role: {invite.role}</span>
                    <span className="text-[10px] text-slate-400 dark:text-[#62666D]">
                      {invite.createdAt ? new Date(invite.createdAt).toLocaleDateString() : "Recent"}
                    </span>
                  </div>
                  <h3 className="font-archivo font-bold text-sm text-slate-900 dark:text-[#E2E4E9]">{invite.projectName}</h3>
                  <p className="text-xs text-slate-500 dark:text-[#9E9E9E]">
                    Invited by: <span className="text-slate-900 dark:text-[#E2E4E9] font-medium">{invite.senderName || invite.senderEmail}</span>
                  </p>
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <Button
                    size="sm"
                    onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={acceptInviteMutation.isPending}
                    className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-mono font-semibold rounded-lg flex-1 cursor-pointer border border-emerald-600 dark:border-[#282A30]"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 mr-1.5 text-white dark:text-[#10B981]" />
                    Accept & Join
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={declineInviteMutation.isPending}
                    className="h-8 text-xs border-slate-200 dark:border-[#282A30] bg-white dark:bg-transparent hover:bg-slate-100 dark:hover:bg-[#1E2026] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] rounded-lg flex-1 font-mono font-medium"
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
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-2">
        <div>
          <h2 className="text-base sm:text-lg font-archivo font-bold tracking-tight text-slate-900 dark:text-[#E2E4E9] flex items-center gap-2">
            Your Document Projects
            <span className="text-xs px-2 py-0.5 rounded-md bg-slate-100 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] font-mono">
              {(ownedProjects.length + sharedProjects.length)}
            </span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-[#9E9E9E]">
            Select a project to launch the live collaborative LaTeX workspace
          </p>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="relative w-full sm:w-64">
            <Input
              placeholder="Search reports, slides & projects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 pl-8 pr-3 text-xs font-mono bg-white dark:bg-[#1A1C22] border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46]"
            />
            <Search className="w-3.5 h-3.5 text-slate-400 dark:text-[#62666D] absolute left-2.5 top-1/2 -translate-y-1/2" />
          </div>
        </div>
      </div>

      {isProjectsLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
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
              <div className="flex items-center gap-2 text-xs font-mono font-bold text-slate-500 dark:text-[#9E9E9E] uppercase tracking-wider">
                <Crown className="w-3.5 h-3.5 text-slate-700 dark:text-[#E2E4E9]" />
                <span>Owned Projects ({ownedProjects.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {ownedProjects.map((project) => (
                  <motion.div key={project.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <Card className="group p-5 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] hover:border-slate-300 dark:hover:border-[#383B46] hover:bg-slate-50 dark:hover:bg-[#1A1C22] transition-all space-y-4 flex flex-col justify-between h-full shadow-sm dark:shadow-none">
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2 min-w-0">
                          <Link href={`/editor/${project.id}`} className="space-y-1 block flex-1 min-w-0">
                            <h3 className="font-archivo font-bold text-sm text-slate-900 dark:text-[#E2E4E9] group-hover:text-emerald-600 dark:group-hover:text-white transition-colors flex items-center gap-2 min-w-0">
                              <FileCode2 className="w-4 h-4 text-emerald-600 dark:text-[#E2E4E9] shrink-0" />
                              <span className="truncate min-w-0" title={project.name}>{project.name}</span>
                            </h3>
                          </Link>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className="px-2 py-0.5 rounded text-[10px] font-medium font-mono bg-slate-100 dark:bg-[#1E2026] text-slate-600 dark:text-[#9E9E9E] border border-slate-200 dark:border-[#282A30] uppercase">
                              Owner
                            </span>
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                setDeleteConfirmProj(project);
                              }}
                              className="p-1 text-slate-400 dark:text-[#62666D] hover:text-red-500 dark:hover:text-[#FF8585] transition-colors"
                              title="Delete Project"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>

                        <p className="text-xs text-slate-500 dark:text-[#9E9E9E] line-clamp-2 leading-relaxed font-sans">
                          {project.description}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-slate-100 dark:border-[#282A30] flex items-center justify-between gap-2 text-xs text-slate-500 dark:text-[#9E9E9E] font-mono min-w-0">
                        <span className="px-2.5 py-1 rounded-md bg-slate-100 dark:bg-[#1E2026] text-slate-600 dark:text-[#9E9E9E] font-medium border border-slate-200 dark:border-[#282A30] w-fit shrink-0 text-[11px]" title={project.template || "None"}>
                          {project.template || "None"}
                        </span>

                        <Link
                          href={`/editor/${project.id}`}
                          className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] hover:text-white border border-emerald-600 dark:border-[#282A30] font-mono font-medium text-[11px] transition-all flex items-center gap-1 shrink-0 whitespace-nowrap shadow-xs"
                        >
                          <span>Open Workspace →</span>
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
            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-2 text-xs font-mono font-bold text-slate-500 dark:text-[#9E9E9E] uppercase tracking-wider">
                <Users className="w-3.5 h-3.5 text-slate-700 dark:text-[#E2E4E9]" />
                <span>Shared With Me ({sharedProjects.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {sharedProjects.map((project) => (
                  <motion.div key={project.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <Card className="group p-5 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] hover:border-slate-300 dark:hover:border-[#383B46] hover:bg-slate-50 dark:hover:bg-[#1A1C22] transition-all space-y-4 flex flex-col justify-between h-full shadow-sm dark:shadow-none">
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2 min-w-0">
                          <Link href={`/editor/${project.id}`} className="space-y-1 block flex-1 min-w-0">
                            <h3 className="font-archivo font-bold text-sm text-slate-900 dark:text-[#E2E4E9] group-hover:text-emerald-600 dark:group-hover:text-white transition-colors flex items-center gap-2 min-w-0">
                              <FileCode2 className="w-4 h-4 text-emerald-600 dark:text-[#E2E4E9] shrink-0" />
                              <span className="truncate min-w-0" title={project.name}>{project.name}</span>
                            </h3>
                          </Link>
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium font-mono bg-slate-100 dark:bg-[#1E2026] text-slate-600 dark:text-[#9E9E9E] border border-slate-200 dark:border-[#282A30] uppercase shrink-0">
                            {project.role}
                          </span>
                        </div>

                        <p className="text-xs text-slate-500 dark:text-[#9E9E9E] line-clamp-2 leading-relaxed font-sans">
                          {project.description}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-slate-100 dark:border-[#282A30] flex items-center justify-between gap-2 text-xs text-slate-500 dark:text-[#9E9E9E] font-mono min-w-0">
                        <span className="px-2.5 py-1 rounded-md bg-slate-100 dark:bg-[#1E2026] text-slate-600 dark:text-[#9E9E9E] font-medium border border-slate-200 dark:border-[#282A30] w-fit shrink-0 text-[11px]" title={project.template || "None"}>
                          {project.template || "None"}
                        </span>

                        <Link
                          href={`/editor/${project.id}`}
                          className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] hover:text-white border border-emerald-600 dark:border-[#282A30] font-mono font-medium text-[11px] transition-all flex items-center gap-1 shrink-0 whitespace-nowrap shadow-xs"
                        >
                          <span>Open Workspace →</span>
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/50 dark:bg-black/80 animate-fade-in backdrop-blur-xs">
          <div className="max-w-sm w-[calc(100vw-2rem)] p-5 rounded-xl border border-red-200 dark:border-[#FF8585]/30 bg-white dark:bg-[#141519] text-slate-900 dark:text-[#E2E4E9] shadow-2xl space-y-4">
            <div className="flex items-center gap-2.5 text-red-600 dark:text-[#FF8585]">
              <div className="p-2 rounded-lg bg-red-50 dark:bg-[#FF8585]/10 border border-red-200 dark:border-[#FF8585]/20">
                <AlertTriangle className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-archivo font-bold uppercase text-slate-900 dark:text-[#E2E4E9]">Delete Project</h3>
            </div>

            <p className="text-xs text-slate-600 dark:text-[#9E9E9E] leading-relaxed">
              Are you sure you want to delete <strong className="text-slate-900 dark:text-[#E2E4E9]">{deleteConfirmProj.name}</strong>? This will permanently remove all files, documents, and co-author access.
            </p>

            <form onSubmit={handleDeleteSubmit} className="flex justify-end gap-2 pt-2 text-xs font-mono font-medium">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setDeleteConfirmProj(null)}
                className="h-8 text-xs rounded-lg border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9]"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={deleteMutation.isPending}
                className="h-8 text-xs bg-red-600 hover:bg-red-700 dark:bg-[#EB5757] dark:hover:bg-[#D64545] text-white font-mono font-semibold rounded-lg border border-red-600 dark:border-[#EB5757]/50"
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete Permanently"}
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* New Project Modal */}
      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/50 dark:bg-black/80 animate-fade-in backdrop-blur-xs">
          <div className="max-w-md w-[calc(100vw-2rem)] p-6 rounded-xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] text-slate-900 dark:text-[#E2E4E9] shadow-2xl space-y-4">
            <div className="space-y-1">
              <h3 className="text-base font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">Create LaTeX Project</h3>
              <p className="text-xs text-slate-500 dark:text-[#9E9E9E]">Initialize a new LaTeX document workspace with real-time compilation.</p>
            </div>
            <form onSubmit={handleCreateSubmit} className="space-y-4 font-mono">
              <div className="space-y-1.5">
                <label className="text-xs text-slate-600 dark:text-[#9E9E9E] font-medium uppercase">Project Name</label>
                <Input
                  autoFocus
                  placeholder="e.g. Quantum Computing Seminar"
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  className="h-10 text-xs font-mono border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#383B46]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 text-xs font-medium">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setNewModalOpen(false)}
                  className="h-8 text-xs border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] rounded-lg"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending || !newProjName.trim()}
                  className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold rounded-lg border border-emerald-600 dark:border-[#282A30] cursor-pointer"
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

