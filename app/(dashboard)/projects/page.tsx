"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Plus,
  FileArchive,
  Search,
  Star,
  UserPlus,
  Trash2,
  Download,
  Crown,
  LogOut,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { PaperSheet } from "@/components/dashboard/PaperSheet";
import { ProjectCardSkeleton } from "@/components/ui/skeleton-loader";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";
import { ImportZipDialog } from "@/components/project-import/ImportZipDialog";
import { downloadAllProjectsZip, downloadProjectZip } from "@/components/project-import/useZipImport";

const PROJECT_GRID = "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";
const DIALOG_OVERLAY = "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4";
const DIALOG_PANEL =
  "flex w-full max-w-md flex-col gap-4 rounded-xl border border-ob-line bg-ob-card p-6 text-ob-text shadow-[0_16px_48px_rgba(0,0,0,0.32)]";
const DIALOG_TITLE = "text-[15px] leading-6 font-medium text-ob-text";
const DIALOG_BODY = "text-[13px] leading-5 text-ob-text-2";
const DIALOG_FOOTER = "flex justify-end gap-2 pt-2";

function IconAction({
  label,
  danger = false,
  active = false,
  onClick,
  children,
}: {
  label: string;
  danger?: boolean;
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      }}
      title={label}
      aria-label={label}
      className={`flex size-8 cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-ob-raised ${
        active
          ? "text-amber-500 hover:text-amber-600"
          : danger
            ? "text-ob-muted hover:text-ob-negative"
            : "text-ob-muted hover:text-ob-text"
      }`}
    >
      {children}
    </button>
  );
}

function ProjectCard({ project, children }: { project: any; children: React.ReactNode }) {
  const hasTemplate = project.template && project.template !== "None";
  return (
    <article className="group relative flex flex-row overflow-hidden rounded-xl border border-ob-line bg-ob-card transition-colors hover:border-ob-text/15 sm:flex-col">
      <div className="flex w-28 shrink-0 items-center justify-center border-r border-ob-line bg-ob-deep py-3 sm:h-48 sm:w-auto sm:border-r-0 sm:border-b sm:py-0">
        <PaperSheet
          template={project.template}
          seed={project.id}
          className="max-sm:hidden transition-transform duration-200 group-hover:-translate-y-0.5"
        />
        <PaperSheet template={project.template} seed={project.id} size="sm" className="sm:hidden" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col p-4">
        <h3 className="line-clamp-2 text-[15px] leading-[22px] font-medium text-ob-text">
          <Link
            href={`/editor/${project.id}`}
            title={project.name}
            className="rounded-sm after:absolute after:inset-0 after:content-['']"
          >
            {project.name}
          </Link>
        </h3>
        {project.description && (
          <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-ob-text-2">{project.description}</p>
        )}
        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          <span className="min-w-0 truncate font-mono text-xs text-ob-muted">
            {hasTemplate ? `${project.template} · ` : ""}
            {project.role}
          </span>
          <div className="relative z-10 -mr-2 flex shrink-0 items-center">{children}</div>
        </div>
      </div>
    </article>
  );
}

export default function ProjectsPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [templateFilter, setTemplateFilter] = useState("all");
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [zipModalOpen, setZipModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [inviteModalProj, setInviteModalProj] = useState<any | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"Editor" | "Viewer" | "Transfer">("Editor");
  const [deleteConfirmProj, setDeleteConfirmProj] = useState<any | null>(null);
  const [leaveConfirmProj, setLeaveConfirmProj] = useState<any | null>(null);

  useEffect(() => {
    document.title = "OverBranch | Projects";
  }, []);

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
      toast.success("Project created");
      router.push(`/editor/${newProj.id}`);
    },
    onError: (err) => {
      toast.error(err.message || "Failed to create project");
    },
  });

  const deleteMutation = trpc.projects.deleteProject.useMutation({
    onSuccess: () => {
      toast.success("Project deleted");
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

  const transferOwnershipMutation = trpc.projects.transferOwnership.useMutation({
    onSuccess: (data) => {
      toast.success(
        data?.newOwnerName
          ? `Ownership transferred to ${data.newOwnerName}`
          : "Ownership transferred successfully"
      );
      setInviteModalProj(null);
      setInviteEmail("");
      setInviteRole("Editor");
      refetch();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to transfer ownership");
    },
  });

  const leaveMutation = trpc.projects.leaveProject.useMutation({
    onSuccess: () => {
      toast.success("You left the project");
      setLeaveConfirmProj(null);
      refetch();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to leave project");
    },
  });

  const filtered = dbProjects || [];
  const projectCount = filtered.length;

  const toggleFavorite = (id: string) => {
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

  const handleLeaveProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!leaveConfirmProj) return;
    leaveMutation.mutate({ projectId: leaveConfirmProj.id });
  };

  const handleSendProjectInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !inviteModalProj) return;

    if (inviteRole === "Transfer") {
      transferOwnershipMutation.mutate({
        projectId: inviteModalProj.id,
        newOwnerEmail: inviteEmail.trim(),
      });
      return;
    }

    sendInviteMutation.mutate({
      projectId: inviteModalProj.id,
      email: inviteEmail.trim(),
      role: inviteRole,
    });
  };

  return (
    <div className="ob-enter flex flex-col gap-8 pb-16">
      {/* Header */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-baseline gap-3">
            <h1 className="font-ob-title text-[32px] leading-[1.15] font-normal text-ob-text">Projects</h1>
            {!isLoading && (
              <span className="font-mono text-[13px] text-ob-muted tabular-nums">
                {search || templateFilter !== "all" || showFavoritesOnly
                  ? `${projectCount} matching`
                  : `${projectCount} ${projectCount === 1 ? "project" : "projects"}`}
              </span>
            )}
          </div>
          <p className="max-w-2xl text-sm leading-[22px] text-ob-text-2">
            Manage, export and co-author your seminar reports, assignments, theses, slides and papers
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ob-quiet"
            size="sm"
            onClick={() => setZipModalOpen(true)}
            className="cursor-pointer text-[13px]"
          >
            <FileArchive className="size-4" />
            Import ZIP
          </Button>

          <Button
            variant="ob-quiet"
            size="sm"
            onClick={() => downloadAllProjectsZip()}
            disabled={!dbProjects || dbProjects.length === 0}
            className="cursor-pointer text-[13px]"
          >
            <Download className="size-4" />
            Export all
          </Button>

          <Button
            variant="ob-primary"
            size="sm"
            onClick={() => setNewModalOpen(true)}
            className="cursor-pointer text-[13px]"
          >
            <Plus className="size-4" />
            New project
          </Button>
        </div>
      </header>

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-3 rounded-xl border border-ob-line bg-ob-card p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ob-muted" />
          <Input
            placeholder="Search projects"
            aria-label="Search projects"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 rounded-lg border-ob-line bg-ob-raised pr-3 pl-9 text-sm text-ob-text shadow-none placeholder:text-ob-muted md:text-sm dark:bg-ob-raised"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            className={`flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border px-3 text-xs transition-colors ${
              showFavoritesOnly
                ? "border-amber-500/30 bg-amber-500/10 text-amber-500"
                : "border-ob-line bg-ob-raised text-ob-text-2 hover:text-ob-text"
            }`}
          >
            <Star className={`size-3.5 ${showFavoritesOnly ? "fill-amber-500 text-amber-500" : ""}`} />
            <span>Favorites</span>
          </button>

          <select
            value={templateFilter}
            onChange={(e) => setTemplateFilter(e.target.value)}
            className="h-9 cursor-pointer rounded-lg border border-ob-line bg-ob-raised px-3 text-xs text-ob-text transition-colors hover:border-ob-text/15"
          >
            <option value="all">All templates</option>
            <option value="Report">Seminar / Report</option>
            <option value="Beamer">Beamer Slides</option>
            <option value="Thesis">Project Thesis</option>
            <option value="Paper">Journal Paper</option>
            <option value="Resume">Resume / CV</option>
          </select>
        </div>
      </div>

      {/* Projects Grid */}
      {isLoading ? (
        <div className={PROJECT_GRID}>
          {Array.from({ length: 8 }).map((_, i) => (
            <ProjectCardSkeleton key={i} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No projects found"
          description={
            search || templateFilter !== "all" || showFavoritesOnly
              ? "No projects match your current filters"
              : "Create your first LaTeX document or import an existing archive"
          }
          primaryActionLabel={
            search || templateFilter !== "all" || showFavoritesOnly ? "Clear filters" : "New project"
          }
          onPrimaryAction={
            search || templateFilter !== "all" || showFavoritesOnly
              ? () => {
                  setSearch("");
                  setTemplateFilter("all");
                  setShowFavoritesOnly(false);
                }
              : () => setNewModalOpen(true)
          }
        />
      ) : (
        <div className={PROJECT_GRID}>
          {filtered.map((proj: any) => (
            <ProjectCard key={proj.id} project={proj}>
              <IconAction
                label={proj.isFavorite ? "Remove favorite" : "Add favorite"}
                active={proj.isFavorite}
                onClick={() => toggleFavorite(proj.id)}
              >
                <Star className={`size-4 ${proj.isFavorite ? "fill-amber-500 text-amber-500" : ""}`} />
              </IconAction>

              <IconAction
                label="Export zip"
                onClick={() => downloadProjectZip(proj.id, proj.name)}
              >
                <Download className="size-4" />
              </IconAction>

              {proj.role !== "Viewer" && (
                <IconAction
                  label="Invite co-author"
                  onClick={() => {
                    setInviteModalProj(proj);
                    setInviteRole("Editor");
                  }}
                >
                  <UserPlus className="size-4" />
                </IconAction>
              )}

              {proj.isOwner ? (
                <>
                  <IconAction
                    label="Transfer ownership"
                    onClick={() => {
                      setInviteModalProj(proj);
                      setInviteRole("Transfer");
                    }}
                  >
                    <Crown className="size-4" />
                  </IconAction>
                  <IconAction
                    label="Delete project"
                    danger
                    onClick={() => setDeleteConfirmProj(proj)}
                  >
                    <Trash2 className="size-4" />
                  </IconAction>
                </>
              ) : (
                <IconAction
                  label="Leave project"
                  danger
                  onClick={() => setLeaveConfirmProj(proj)}
                >
                  <LogOut className="size-4" />
                </IconAction>
              )}
            </ProjectCard>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmProj && (
        <div className={DIALOG_OVERLAY} onClick={() => setDeleteConfirmProj(null)}>
          <div className={DIALOG_PANEL} onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-col gap-1">
              <h3 className={DIALOG_TITLE}>Delete project</h3>
              <p className={DIALOG_BODY}>
                Permanently delete <strong className="text-ob-text">{deleteConfirmProj.name}</strong>? All files and document history will be removed. This cannot be undone.
              </p>
            </div>
            <form onSubmit={handleDeleteProject} className={DIALOG_FOOTER}>
              <Button
                type="button"
                variant="ob-quiet"
                size="sm"
                onClick={() => setDeleteConfirmProj(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="ob-danger"
                size="sm"
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? "Deleting\u2026" : "Delete project"}
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* Leave Confirmation Modal */}
      {leaveConfirmProj && (
        <div className={DIALOG_OVERLAY} onClick={() => setLeaveConfirmProj(null)}>
          <div className={DIALOG_PANEL} onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-col gap-1">
              <h3 className={DIALOG_TITLE}>Leave project</h3>
              <p className={DIALOG_BODY}>
                Leave <strong className="text-ob-text">{leaveConfirmProj.name}</strong>? You will lose access to its files and shared workspace.
              </p>
            </div>
            <form onSubmit={handleLeaveProject} className={DIALOG_FOOTER}>
              <Button
                type="button"
                variant="ob-quiet"
                size="sm"
                onClick={() => setLeaveConfirmProj(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="ob-danger"
                size="sm"
                disabled={leaveMutation.isPending}
              >
                {leaveMutation.isPending ? "Leaving\u2026" : "Leave project"}
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      {newModalOpen && (
        <div className={DIALOG_OVERLAY} onClick={() => setNewModalOpen(false)}>
          <div className={DIALOG_PANEL} onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-col gap-1">
              <h3 className={DIALOG_TITLE}>New blank document</h3>
              <p className={DIALOG_BODY}>Create an empty LaTeX article workspace with live compilation</p>
            </div>
            <form onSubmit={handleCreateProject} className="flex flex-col gap-4">
              <Input
                autoFocus
                placeholder="Document title"
                value={newProjName}
                onChange={(e) => setNewProjName(e.target.value)}
                required
                className="h-9 rounded-lg border-ob-line bg-ob-raised px-3 text-sm text-ob-text shadow-none placeholder:text-ob-muted"
              />
              <div className={DIALOG_FOOTER}>
                <Button
                  type="button"
                  variant="ob-quiet"
                  size="sm"
                  onClick={() => setNewModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="ob-primary"
                  size="sm"
                  disabled={createMutation.isPending || !newProjName.trim()}
                >
                  {createMutation.isPending ? "Creating\u2026" : "Create document"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Invite Collaborator / Transfer Modal */}
      {inviteModalProj && (
        <div className={DIALOG_OVERLAY} onClick={() => setInviteModalProj(null)}>
          <div className={DIALOG_PANEL} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className={DIALOG_TITLE}>
                {inviteRole === "Transfer" ? "Transfer ownership" : "Invite co-author"}
              </h3>
              <button
                onClick={() => setInviteModalProj(null)}
                className="text-ob-muted hover:text-ob-text"
              >
                <X className="size-4" />
              </button>
            </div>

            <form onSubmit={handleSendProjectInvite} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-ob-text-2">User email</label>
                <Input
                  type="email"
                  placeholder="collaborator@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  className="h-9 rounded-lg border-ob-line bg-ob-raised px-3 text-sm text-ob-text shadow-none placeholder:text-ob-muted"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-ob-text-2">Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as "Editor" | "Viewer" | "Transfer")}
                  className="h-9 cursor-pointer rounded-lg border border-ob-line bg-ob-raised px-3 text-xs text-ob-text transition-colors hover:border-ob-text/15"
                >
                  <option value="Editor">Editor (full edit and compile)</option>
                  <option value="Viewer">Viewer (read only)</option>
                  {inviteModalProj.isOwner && <option value="Transfer">Transfer ownership</option>}
                </select>
              </div>

              {inviteRole === "Transfer" && (
                <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-5 text-amber-500">
                  You are transferring complete ownership of this project. You will remain an editor.
                </p>
              )}

              <div className={DIALOG_FOOTER}>
                <Button
                  type="button"
                  variant="ob-quiet"
                  size="sm"
                  onClick={() => setInviteModalProj(null)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant={inviteRole === "Transfer" ? "ob-secondary" : "ob-primary"}
                  size="sm"
                  disabled={
                    inviteRole === "Transfer"
                      ? transferOwnershipMutation.isPending || !inviteEmail.trim()
                      : sendInviteMutation.isPending || !inviteEmail.trim()
                  }
                >
                  {inviteRole === "Transfer"
                    ? transferOwnershipMutation.isPending
                      ? "Transferring\u2026"
                      : "Transfer ownership"
                    : sendInviteMutation.isPending
                      ? "Sending\u2026"
                      : "Send invitation"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ImportZipDialog
        open={zipModalOpen}
        onOpenChange={setZipModalOpen}
        onSuccess={(id) => router.push(`/editor/${id}`)}
        onMultipleImported={() => refetch()}
      />
    </div>
  );
}
