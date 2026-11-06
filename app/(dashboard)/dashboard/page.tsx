"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Plus,
  FileArchive,
  FileCode2,
  Search,
  Trash2,
  Download,
  ArrowRight,
  LogOut,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { PaperSheet } from "@/components/dashboard/PaperSheet";
import { ProjectCardSkeleton } from "@/components/ui/skeleton-loader";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";
import { ImportPdfDialog } from "@/components/pdf-import/ImportPdfDialog";
import { ImportZipDialog } from "@/components/project-import/ImportZipDialog";
import { downloadAllProjectsZip, downloadProjectZip } from "@/components/project-import/useZipImport";

const ACTION_ROW =
  "group flex flex-1 cursor-pointer items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-ob-raised/60";
const ACTION_ARROW =
  "size-4 shrink-0 text-ob-muted transition-[color,transform] group-hover:translate-x-0.5 group-hover:text-ob-text";
const PROJECT_GRID = "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";
const DIALOG_OVERLAY = "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4";
const DIALOG_PANEL =
  "flex w-full flex-col gap-4 rounded-xl border border-ob-line bg-ob-card p-6 text-ob-text shadow-[0_16px_48px_rgba(0,0,0,0.32)]";
const DIALOG_TITLE = "text-[15px] leading-6 font-medium text-ob-text";
const DIALOG_BODY = "text-[13px] leading-5 text-ob-text-2";
const DIALOG_FOOTER = "flex justify-end gap-2";

function SectionLabel({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-baseline gap-2">
      <h2 className="text-[15px] leading-6 font-medium text-ob-text">{title}</h2>
      {count !== undefined && <span className="font-mono text-xs text-ob-muted tabular-nums">{count}</span>}
    </div>
  );
}

function IconAction({
  label,
  danger = false,
  onClick,
  children,
}: {
  label: string;
  danger?: boolean;
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
      className={`flex size-8 cursor-pointer items-center justify-center rounded-lg text-ob-muted transition-colors hover:bg-ob-raised ${
        danger ? "hover:text-ob-negative" : "hover:text-ob-text"
      }`}
    >
      {children}
    </button>
  );
}

/** A proof sheet on the desk, with the name under it. The whole card opens the editor. */
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

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTemplate, setFilterTemplate] = useState("all");
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [pdfModalOpen, setPdfModalOpen] = useState(false);
  const [zipModalOpen, setZipModalOpen] = useState(false);
  const importedProjectId = useRef<string | null>(null);
  const [newProjName, setNewProjName] = useState("");
  const [deleteConfirmProj, setDeleteConfirmProj] = useState<any | null>(null);
  const [leaveConfirmProj, setLeaveConfirmProj] = useState<any | null>(null);

  useEffect(() => {
    document.title = "OverBranch | Dashboard";
  }, []);

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
      toast.success("Project created");
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
      toast.success("Project deleted");
      setDeleteConfirmProj(null);
      utils.projects.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to delete project");
    },
  });

  const acceptInviteMutation = trpc.invitations.acceptInvite.useMutation({
    onSuccess: () => {
      toast.success("Invitation accepted, project added to Shared with me");
      utils.invitations.invalidate();
      utils.projects.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to accept invitation");
    },
  });

  const declineInviteMutation = trpc.invitations.declineInvite.useMutation({
    onSuccess: () => {
      toast.success("Invitation declined");
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

  const leaveMutation = trpc.projects.leaveProject.useMutation({
    onSuccess: () => {
      toast.success("You left the project");
      setLeaveConfirmProj(null);
      utils.projects.invalidate();
    },
    onError: (err) => {
      toast.error(err.message || "Failed to leave project");
    },
  });

  const handleLeaveSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!leaveConfirmProj) return;
    leaveMutation.mutate({ projectId: leaveConfirmProj.id });
  };

  const projectCount = ownedProjects.length + sharedProjects.length;

  return (
    <div className="ob-enter flex flex-col gap-10 pb-16">
      {/* Header */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-baseline gap-3">
            <h1 className="font-ob-title text-[32px] leading-[1.15] font-normal text-ob-text">Overview</h1>
            {!isProjectsLoading && (
              <span className="font-mono text-[13px] text-ob-muted tabular-nums">
                {searchQuery
                  ? `${projectCount} matching`
                  : `${projectCount} ${projectCount === 1 ? "project" : "projects"}`}
              </span>
            )}
          </div>
          <p className="max-w-2xl text-sm leading-[22px] text-ob-text-2">
            Co-author seminar reports, assignments, theses, slides and research papers with live compilation and SyncTeX
          </p>
        </div>
        <Button
          variant="ob-quiet"
          size="sm"
          onClick={() => downloadAllProjectsZip()}
          disabled={projectCount === 0}
          className="-ml-3 w-fit cursor-pointer text-[13px] sm:ml-0"
        >
          <Download className="size-4" />
          Export all projects
        </Button>
      </header>

      {/* Import and create. PDF to LaTeX leads, the other three share a column. */}
      <section aria-label="Import or create a project" className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <button
          onClick={() => setPdfModalOpen(true)}
          className="group flex cursor-pointer flex-row overflow-hidden rounded-xl border border-ob-line bg-ob-card text-left transition-colors hover:border-ob-text/15"
        >
          <span className="flex min-w-0 flex-1 flex-col p-6">
            <span className="flex items-baseline gap-2">
              <span className="text-xl leading-7 font-medium text-ob-text">PDF to LaTeX</span>
              <span className="font-mono text-xs text-ob-muted">Beta</span>
            </span>
            <span className="mt-2 max-w-md text-sm leading-[22px] text-ob-text-2">
              Upload a PDF and get an editable LaTeX project that follows its layout, text and equations as closely as possible. Closest match, not pixel-exact.
            </span>
            <span className={buttonVariants({ variant: "ob-primary", size: "sm", className: "mt-6 w-fit" })}>
              Import PDF and convert
              <ArrowRight className="size-4" />
            </span>
          </span>
          <span className="relative hidden w-56 shrink-0 items-start justify-center overflow-hidden border-l border-ob-line bg-ob-deep pt-5 sm:flex xl:w-64">
            <PaperSheet variant="report" size="lg" seed="pdf" className="absolute top-5" />
          </span>
        </button>

        <div className="flex flex-col divide-y divide-ob-line overflow-hidden rounded-xl border border-ob-line bg-ob-card">
          <button onClick={() => setZipModalOpen(true)} className={ACTION_ROW}>
            <FileArchive className="size-4 shrink-0 text-ob-muted" />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-sm font-medium text-ob-text">Import from ZIP</span>
              <span className="text-[13px] leading-5 text-ob-text-2">
                Upload a .zip of your LaTeX sources and images to continue as a new project
              </span>
            </span>
            <ArrowRight className={ACTION_ARROW} />
          </button>
          <button onClick={() => setNewModalOpen(true)} className={ACTION_ROW}>
            <Plus className="size-4 shrink-0 text-ob-muted" />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-sm font-medium text-ob-text">New blank document</span>
              <span className="text-[13px] leading-5 text-ob-text-2">
                Start from a minimal LaTeX article with live PDF rendering
              </span>
            </span>
            <ArrowRight className={ACTION_ARROW} />
          </button>
          <Link href="/templates" className={ACTION_ROW}>
            <FileCode2 className="size-4 shrink-0 text-ob-muted" />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-sm font-medium text-ob-text">Browse templates</span>
              <span className="text-[13px] leading-5 text-ob-text-2">
                IEEE papers, resumes, slide presentations and lab reports
              </span>
            </span>
            <ArrowRight className={ACTION_ARROW} />
          </Link>
        </div>
      </section>

      {/* Pending invitations */}
      {pendingInvites && pendingInvites.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionLabel title="Pending invitations" count={pendingInvites.length} />
          <div className="flex flex-col divide-y divide-ob-line rounded-xl border border-ob-line bg-ob-card">
            {pendingInvites.map((invite) => (
              <div key={invite.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <h3 className="truncate text-sm font-medium text-ob-text">{invite.projectName}</h3>
                  <p className="text-[13px] leading-5 text-ob-text-2">
                    {invite.senderName || invite.senderEmail} invited you as {String(invite.role).toLowerCase()}
                    {invite.createdAt && (
                      <span className="ml-2 font-mono text-xs text-ob-muted tabular-nums">
                        {new Date(invite.createdAt).toLocaleDateString()}
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    variant="ob-quiet"
                    size="sm"
                    onClick={() => declineInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={declineInviteMutation.isPending}
                    className="cursor-pointer text-[13px]"
                  >
                    Decline
                  </Button>
                  <Button
                    variant="ob-secondary"
                    size="sm"
                    onClick={() => acceptInviteMutation.mutate({ invitationId: invite.id })}
                    disabled={acceptInviteMutation.isPending}
                    className="cursor-pointer text-[13px]"
                  >
                    Accept and join
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Your projects, with the search that covers both lists */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SectionLabel title="Your projects" count={isProjectsLoading ? undefined : ownedProjects.length} />
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ob-muted" />
            <Input
              placeholder="Search projects"
              aria-label="Search projects"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 rounded-lg border-ob-line bg-ob-raised pr-3 pl-9 text-sm text-ob-text shadow-none placeholder:text-ob-muted md:text-sm dark:bg-ob-raised"
            />
          </div>
        </div>

        {isProjectsLoading ? (
          <div className={PROJECT_GRID}>
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
          </div>
        ) : projectCount === 0 ? (
          <EmptyState
            title={searchQuery ? "No matching projects" : "No projects yet"}
            description={
              searchQuery
                ? "Try another name, or create a new LaTeX document"
                : "Create your first LaTeX document, or accept an invitation to start co-authoring"
            }
            primaryActionLabel="New project"
            onPrimaryAction={() => setNewModalOpen(true)}
          />
        ) : ownedProjects.length > 0 ? (
          <div className={PROJECT_GRID}>
            {ownedProjects.map((project: any) => (
              <ProjectCard key={project.id} project={project}>
                <IconAction label={`Export ${project.name} (.zip)`} onClick={() => downloadProjectZip(project.id, project.name)}>
                  <Download className="size-4" />
                </IconAction>
                <IconAction label={`Delete ${project.name}`} danger onClick={() => setDeleteConfirmProj(project)}>
                  <Trash2 className="size-4" />
                </IconAction>
              </ProjectCard>
            ))}
          </div>
        ) : (
          <p className="text-[13px] leading-5 text-ob-text-2">
            {searchQuery ? "None of yours match" : "You have no projects of your own yet"}
          </p>
        )}
      </section>

      {/* Shared with me */}
      {sharedProjects.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionLabel title="Shared with me" count={sharedProjects.length} />
          <div className={PROJECT_GRID}>
            {sharedProjects.map((project: any) => (
              <ProjectCard key={project.id} project={project}>
                <IconAction label={`Export ${project.name} (.zip)`} onClick={() => downloadProjectZip(project.id, project.name)}>
                  <Download className="size-4" />
                </IconAction>
                <IconAction label={`Leave ${project.name}`} danger onClick={() => setLeaveConfirmProj(project)}>
                  <LogOut className="size-4" />
                </IconAction>
              </ProjectCard>
            ))}
          </div>
        </section>
      )}

      {/* Delete confirmation */}
      {deleteConfirmProj && (
        <div className={DIALOG_OVERLAY}>
          <div role="alertdialog" aria-modal="true" aria-labelledby="delete-project-title" className={`${DIALOG_PANEL} max-w-sm`}>
            <h3 id="delete-project-title" className={DIALOG_TITLE}>Delete project</h3>
            <p className={DIALOG_BODY}>
              Delete <span className="font-medium text-ob-text">{deleteConfirmProj.name}</span>? This permanently removes its files, documents and co-author access.
            </p>
            <form onSubmit={handleDeleteSubmit} className={DIALOG_FOOTER}>
              <Button type="button" variant="ob-quiet" size="sm" onClick={() => setDeleteConfirmProj(null)} className="cursor-pointer">
                Cancel
              </Button>
              <Button type="submit" variant="ob-danger" size="sm" disabled={deleteMutation.isPending} className="cursor-pointer">
                {deleteMutation.isPending ? "Deleting" : "Delete permanently"}
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* Leave confirmation */}
      {leaveConfirmProj && (
        <div className={DIALOG_OVERLAY}>
          <div role="alertdialog" aria-modal="true" aria-labelledby="leave-project-title" className={`${DIALOG_PANEL} max-w-sm`}>
            <h3 id="leave-project-title" className={DIALOG_TITLE}>Leave project</h3>
            <p className={DIALOG_BODY}>
              Leave <span className="font-medium text-ob-text">{leaveConfirmProj.name}</span>? You will lose access to its files, real-time collaboration and documents.
            </p>
            <form onSubmit={handleLeaveSubmit} className={DIALOG_FOOTER}>
              <Button type="button" variant="ob-quiet" size="sm" onClick={() => setLeaveConfirmProj(null)} className="cursor-pointer">
                Cancel
              </Button>
              <Button type="submit" variant="ob-danger" size="sm" disabled={leaveMutation.isPending} className="cursor-pointer">
                {leaveMutation.isPending ? "Leaving" : "Leave project"}
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* New project */}
      {newModalOpen && (
        <div className={DIALOG_OVERLAY}>
          <div role="dialog" aria-modal="true" aria-labelledby="new-project-title" className={`${DIALOG_PANEL} max-w-md`}>
            <div className="flex flex-col gap-1">
              <h3 id="new-project-title" className={DIALOG_TITLE}>New LaTeX project</h3>
              <p className={DIALOG_BODY}>A new document workspace with real-time compilation</p>
            </div>
            <form onSubmit={handleCreateSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label htmlFor="new-project-name" className="text-[13px] leading-5 text-ob-text-2">Project name</label>
                <Input
                  id="new-project-name"
                  autoFocus
                  placeholder="Quantum Computing Seminar"
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  className="h-9 rounded-lg border-ob-line bg-ob-raised text-sm text-ob-text shadow-none placeholder:text-ob-muted md:text-sm dark:bg-ob-raised"
                />
              </div>
              <div className={DIALOG_FOOTER}>
                <Button type="button" variant="ob-quiet" size="sm" onClick={() => setNewModalOpen(false)} className="cursor-pointer">
                  Cancel
                </Button>
                <Button type="submit" variant="ob-primary" size="sm" disabled={createMutation.isPending || !newProjName.trim()} className="cursor-pointer">
                  {createMutation.isPending ? "Creating" : "Create project"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ZIP import (creates a new project) */}
      <ImportZipDialog
        open={zipModalOpen}
        onOpenChange={setZipModalOpen}
        onSuccess={(id) => {
          utils.projects.invalidate();
          router.push(`/editor/${id}`);
        }}
        // An archive with one folder per project: the dialog lists them; just refresh the grid.
        onMultipleImported={() => utils.projects.invalidate()}
      />

      {/* PDF → LaTeX import (creates a new project) */}
      <ImportPdfDialog
        open={pdfModalOpen}
        onOpenChange={(open) => {
          setPdfModalOpen(open);
          if (!open && importedProjectId.current) {
            const id = importedProjectId.current;
            importedProjectId.current = null;
            router.push(`/editor/${id}`);
          }
        }}
        onCompleted={({ projectId }) => {
          utils.projects.invalidate();
          if (pdfModalOpen) {
            importedProjectId.current = projectId;
          } else {
            // Finished while the dialog was hidden
            toast.success("PDF import finished", {
              action: { label: "Open project", onClick: () => router.push(`/editor/${projectId}`) },
            });
          }
        }}
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

