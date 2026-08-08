"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Plus,
  FileCode2,
  Search,
  Star,
  Sparkles,
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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/badge-custom";
import { EmptyState } from "@/components/ui/empty-state";
import { ProjectCardSkeleton } from "@/components/ui/skeleton-loader";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";

export default function DashboardPage() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTemplate, setFilterTemplate] = useState("all");
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState("");

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
      description: "Seminar report & academic project workspace",
      template: "Report",
    });
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Header Banner */}
      <div className="relative p-6 sm:p-8 rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="relative z-10 space-y-5">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge variant="outline" dotPulse dotColor="bg-emerald-400">
                  Real-Time Workspace Sync Active
                </StatusBadge>
                <span className="text-xs font-mono text-muted-foreground">TeX Engine: pdfLaTeX</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                Academic Document Workspace
              </h1>
              <p className="text-xs sm:text-sm text-muted-foreground max-w-2xl">
                Co-author seminar reports, assignments, project reports, slides, and papers with real-time compilation and SyncTeX.
              </p>
            </div>

            <Button
              onClick={() => setNewModalOpen(true)}
              size="lg"
              className="h-10 px-5 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold shadow-xs rounded-xl shrink-0 text-xs"
            >
              <Plus className="w-4 h-4 mr-1.5" />
              New Project
            </Button>
          </div>
        </div>
      </div>

      {/* Pending Invitations Section */}
      {pendingInvites && pendingInvites.length > 0 && (
        <div className="p-5 rounded-2xl border border-indigo-500/40 bg-indigo-500/10 backdrop-blur-md space-y-4 shadow-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-indigo-400" />
              <h2 className="font-bold text-base text-foreground tracking-tight">
                Pending Team Invitations
              </h2>
              <span className="px-2 py-0.5 rounded-full bg-indigo-600 text-white text-xs font-mono font-bold">
                {pendingInvites.length}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {pendingInvites.map((invite) => (
              <div
                key={invite.id}
                className="p-4 rounded-xl border border-border/50 bg-card/60 space-y-3 flex flex-col justify-between"
              >
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs font-mono text-indigo-400 font-bold">
                    <span>Role: {invite.role}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {invite.createdAt ? new Date(invite.createdAt).toLocaleDateString() : "Recent"}
                    </span>
                  </div>
                  <h3 className="font-bold text-sm text-foreground">{invite.projectName}</h3>
                  <p className="text-xs text-muted-foreground">
                    Invited by: <span className="text-foreground font-medium">{invite.senderName || invite.senderEmail}</span>
                  </p>
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <Button
                    size="sm"
                    onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={acceptInviteMutation.isPending}
                    className="h-8 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg flex-1 font-medium shadow-md"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                    Accept & Join
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={declineInviteMutation.isPending}
                    className="h-8 text-xs border-border/60 hover:bg-accent rounded-lg flex-1 font-medium"
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
              <div className="flex items-center gap-2 text-xs font-bold text-amber-500 dark:text-amber-400 uppercase tracking-wider font-mono">
                <Crown className="w-4 h-4 text-amber-500 dark:text-amber-400" />
                <span>Owned Projects ({ownedProjects.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {ownedProjects.map((project) => (
                  <motion.div key={project.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                    <Card className="group p-5 rounded-2xl border border-border bg-card hover:border-amber-500/50 hover:bg-card/80 transition-all space-y-4 flex flex-col justify-between h-full shadow-sm">
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <Link href={`/editor/${project.id}`} className="space-y-1 block flex-1">
                            <h3 className="font-bold text-base text-foreground group-hover:text-amber-500 dark:group-hover:text-amber-400 transition-colors flex items-center gap-2 truncate">
                              <FileCode2 className="w-4 h-4 text-amber-500 dark:text-amber-400 shrink-0" />
                              <span className="truncate">{project.name}</span>
                            </h3>
                          </Link>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-500/10 text-amber-500 dark:text-amber-400 border border-amber-500/20">
                            Owner
                          </span>
                        </div>

                        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                          {project.description}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-border flex items-center justify-between text-xs text-muted-foreground font-mono">
                        <span className="px-2.5 py-0.5 rounded-md bg-muted text-foreground font-medium">
                          {project.template}
                        </span>

                        <Link
                          href={`/editor/${project.id}`}
                          className="px-3 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-600 dark:hover:bg-amber-500 text-amber-600 dark:text-amber-400 hover:text-white transition-all flex items-center gap-1.5 font-sans font-medium text-xs"
                        >
                          <span>Open Editor</span>
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
              <div className="flex items-center gap-2 text-xs font-bold text-emerald-500 dark:text-emerald-400 uppercase tracking-wider font-mono">
                <Users className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
                <span>Shared With Me ({sharedProjects.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {sharedProjects.map((project) => (
                  <motion.div key={project.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                    <Card className="group p-5 rounded-2xl border border-border bg-card hover:border-emerald-500/50 hover:bg-card/80 transition-all space-y-4 flex flex-col justify-between h-full shadow-sm">
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <Link href={`/editor/${project.id}`} className="space-y-1 block flex-1">
                            <h3 className="font-bold text-base text-foreground group-hover:text-emerald-500 dark:group-hover:text-emerald-400 transition-colors flex items-center gap-2 truncate">
                              <FileCode2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
                              <span className="truncate">{project.name}</span>
                            </h3>
                          </Link>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border border-emerald-500/20">
                            {project.role}
                          </span>
                        </div>

                        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                          {project.description}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-border flex items-center justify-between text-xs text-muted-foreground font-mono">
                        <span className="px-2.5 py-0.5 rounded-md bg-muted text-foreground font-medium">
                          {project.template}
                        </span>

                        <Link
                          href={`/editor/${project.id}`}
                          className="px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-600 dark:hover:bg-emerald-500 text-emerald-600 dark:text-emerald-400 hover:text-white transition-all flex items-center gap-1.5 font-sans font-medium text-xs"
                        >
                          <span>Open Editor</span>
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

      {/* New Project Modal */}
      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-md w-full p-6 rounded-2xl border border-border/60 bg-card shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-foreground">Create LaTeX Project</h3>
            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Project Name</label>
                <Input
                  autoFocus
                  placeholder="e.g. Quantum_State_Paper_2026"
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  className="h-10 text-sm"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setNewModalOpen(false)}
                  className="h-9 text-xs"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending || !newProjName.trim()}
                  className="h-9 text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
                >
                  {createMutation.isPending ? "Creating..." : "Create Project"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
