"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { trpc } from "@/trpc/client";
import { authClient } from "@/lib/auth-client";

interface Project {
    id: string;
    userId: string;
    name: string;
    description: string | null;
    createdAt: Date;
    updatedAt: Date;
}

interface DashboardClientProps {
    initialProjects: Project[];
    userName: string;
    userEmail: string;
}

export default function DashboardClient({ initialProjects, userName, userEmail }: DashboardClientProps) {
    const router = useRouter();
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newProjectName, setNewProjectName] = useState("");
    const [newProjectDesc, setNewProjectDesc] = useState("");
    const [creating, setCreating] = useState(false);

    const { data: projects, refetch } = trpc.project.list.useQuery(undefined, {
        initialData: initialProjects,
    });

    const createMutation = trpc.project.create.useMutation({
        onSuccess: (project) => {
            setShowCreateModal(false);
            setNewProjectName("");
            setNewProjectDesc("");
            setCreating(false);
            router.push(`/editor/${project.id}`);
        },
        onError: () => {
            setCreating(false);
        },
    });

    const deleteMutation = trpc.project.delete.useMutation({
        onSuccess: () => {
            refetch();
        },
    });

    const handleCreate = () => {
        if (!newProjectName.trim()) return;
        setCreating(true);
        createMutation.mutate({
            name: newProjectName.trim(),
            description: newProjectDesc.trim() || undefined,
        });
    };

    const handleDelete = (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        if (confirm("Are you sure you want to delete this project? This cannot be undone.")) {
            deleteMutation.mutate({ id });
        }
    };

    const handleLogout = async () => {
        await authClient.signOut();
        router.push("/login");
        router.refresh();
    };

    const formatDate = (date: Date) => {
        return new Date(date).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    };

    return (
        <div className="dashboard-page">
            {/* Header */}
            <header className="dashboard-header">
                <div className="dashboard-brand">
                    <div className="dashboard-brand-icon">
                        <svg className="h-5 w-5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                            <polyline points="14,2 14,8 20,8" />
                            <line x1="9" y1="13" x2="15" y2="13" />
                            <line x1="9" y1="17" x2="15" y2="17" />
                        </svg>
                    </div>
                    <h1>OverBranch</h1>
                </div>

                <div className="dashboard-user">
                    <span className="dashboard-user-name">{userName || userEmail}</span>
                    <button onClick={handleLogout} className="dashboard-logout">
                        Sign out
                    </button>
                </div>
            </header>

            {/* Content */}
            <div className="dashboard-content">
                <div className="dashboard-toolbar">
                    <h2>Your Projects</h2>
                    <button onClick={() => setShowCreateModal(true)} className="create-project-btn">
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="12" y1="5" x2="12" y2="19" />
                            <line x1="5" y1="12" x2="19" y2="12" />
                        </svg>
                        New Project
                    </button>
                </div>

                {projects && projects.length > 0 ? (
                    <div className="project-grid">
                        {projects.map((project) => (
                            <div
                                key={project.id}
                                className="project-card fade-in"
                                onClick={() => router.push(`/editor/${project.id}`)}
                            >
                                <h3 className="project-card-name">{project.name}</h3>
                                <p className="project-card-desc">
                                    {project.description || "No description"}
                                </p>
                                <div className="project-card-meta">
                                    <span className="project-card-date">
                                        {formatDate(project.updatedAt)}
                                    </span>
                                    <div className="project-card-actions">
                                        <button
                                            className="project-delete-btn"
                                            onClick={(e) => handleDelete(e, project.id)}
                                        >
                                            Delete
                                        </button>
                                        <button
                                            className="project-card-open"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                router.push(`/editor/${project.id}`);
                                            }}
                                        >
                                            Open →
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="empty-state fade-in">
                        <div className="empty-state-icon">
                            <svg className="h-10 w-10 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                                <polyline points="14,2 14,8 20,8" />
                            </svg>
                        </div>
                        <h3>No projects yet</h3>
                        <p>Create your first project to get started with OverBranch</p>
                    </div>
                )}
            </div>

            {/* Create Project Modal */}
            {showCreateModal && (
                <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
                    <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                        <h2 className="modal-title">Create New Project</h2>

                        <div className="auth-form">
                            <div className="auth-field">
                                <label htmlFor="project-name">Project Name</label>
                                <input
                                    id="project-name"
                                    type="text"
                                    value={newProjectName}
                                    onChange={(e) => setNewProjectName(e.target.value)}
                                    placeholder="My LaTeX Project"
                                    autoFocus
                                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                                />
                            </div>

                            <div className="auth-field">
                                <label htmlFor="project-desc">Description (optional)</label>
                                <input
                                    id="project-desc"
                                    type="text"
                                    value={newProjectDesc}
                                    onChange={(e) => setNewProjectDesc(e.target.value)}
                                    placeholder="A brief description of your project"
                                />
                            </div>

                            <div className="modal-actions">
                                <button className="modal-cancel" onClick={() => setShowCreateModal(false)}>
                                    Cancel
                                </button>
                                <button
                                    className="auth-submit"
                                    style={{ width: "auto" }}
                                    onClick={handleCreate}
                                    disabled={creating || !newProjectName.trim()}
                                >
                                    {creating ? "Creating..." : "Create Project"}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
