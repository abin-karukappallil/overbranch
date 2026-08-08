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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";

/* Hallmark · theme: Studio */
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
      description: "Seminar report & academic project workspace",
      template: "Report",
    });
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
    <div className="space-y-6 animate-fade-in pb-12">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-extrabold text-foreground tracking-tight">Project Workspaces</h1>
          <p className="text-xs text-muted-foreground">Manage and co-author your seminar reports, assignments, project reports, slides & papers.</p>
        </div>

        <Button
          onClick={() => setNewModalOpen(true)}
          className="bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold rounded-xl h-9 px-4 text-xs shadow-sm shrink-0"
        >
          <Plus className="w-4 h-4 mr-1.5" />
          New Project
        </Button>
      </div>

      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl border border-border bg-card">
        <div className="relative flex-1 max-w-sm">
          <Input
            placeholder="Filter reports, slides & projects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 text-xs pl-8 bg-background border-border"
          />
          <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
        </div>

        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            className={`px-3 py-1.5 rounded-lg border text-[11px] font-mono transition-colors flex items-center gap-1.5 ${
              showFavoritesOnly ? "bg-amber-500/10 border-amber-500/30 text-amber-500 dark:text-amber-400 font-bold" : "border-border text-muted-foreground"
            }`}
          >
            <Star className={`w-3.5 h-3.5 ${showFavoritesOnly ? "fill-amber-400 text-amber-400" : ""}`} />
            Favorites
          </button>

          <select
            value={templateFilter}
            onChange={(e) => setTemplateFilter(e.target.value)}
            className="h-8 px-2 text-[11px] rounded-lg border border-border bg-background text-foreground outline-none font-mono"
          >
            <option value="all">All Templates</option>
            <option value="Report">Seminar / Report</option>
            <option value="Beamer">Beamer Slides (PPT)</option>
            <option value="Thesis">Project Thesis</option>
            <option value="Paper">Journal Paper</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((proj: any) => (
          <motion.div key={proj.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="group p-4 rounded-2xl border border-border bg-card hover:border-amber-500/40 hover:bg-card/80 transition-all space-y-3 flex flex-col justify-between h-full shadow-sm">
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <Link href={`/editor/${proj.id}`} className="space-y-0.5 block flex-1">
                    <h3 className="font-bold text-sm text-foreground group-hover:text-amber-500 dark:group-hover:text-amber-400 transition-colors flex items-center gap-1.5 truncate">
                      <FileCode2 className="w-4 h-4 text-amber-500 dark:text-amber-400 shrink-0" />
                      <span className="truncate">{proj.name}</span>
                    </h3>
                  </Link>

                  <button onClick={(e) => toggleFavorite(proj.id, e)} className="p-1">
                    <Star className={`w-3.5 h-3.5 ${proj.isFavorite ? "text-amber-400 fill-amber-400" : "text-muted-foreground/40"}`} />
                  </button>
                </div>

                <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                  {proj.description}
                </p>
              </div>

              <div className="pt-2 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                <span className="px-2 py-0.5 rounded bg-muted text-foreground font-medium">
                  {proj.template}
                </span>

                <button
                  onClick={() => setInviteModalProj(proj)}
                  className="px-2.5 py-1 rounded-md border border-border hover:bg-amber-500/10 hover:text-amber-500 dark:hover:text-amber-400 transition-colors flex items-center gap-1 text-[10px]"
                >
                  <UserPlus className="w-3 h-3 text-amber-500 dark:text-amber-400" />
                  <span>Invite Co-Author</span>
                </button>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Create Project Modal */}
      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="max-w-sm w-full p-5 rounded-2xl border border-border bg-card shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-foreground">Create LaTeX Project</h3>
            <form onSubmit={handleCreateProject} className="space-y-3">
              <Input
                placeholder="e.g. Quantum_State_Paper_2026"
                value={newProjName}
                onChange={(e) => setNewProjName(e.target.value)}
                required
                className="h-9 text-xs font-mono"
              />
              <div className="flex justify-end gap-2 text-xs">
                <Button variant="ghost" type="button" size="sm" onClick={() => setNewModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" disabled={createMutation.isPending} className="bg-amber-600 dark:bg-amber-500 text-white dark:text-zinc-950 font-bold">
                  {createMutation.isPending ? "Creating..." : "Create"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Invite Collaborator Modal */}
      {inviteModalProj && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="max-w-sm w-full p-5 rounded-2xl border border-border bg-card shadow-2xl space-y-3">
            <div className="flex items-center justify-between border-b border-border pb-2">
              <span className="font-bold text-xs text-foreground truncate">
                Invite to: {inviteModalProj.name}
              </span>
              <button onClick={() => setInviteModalProj(null)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSendProjectInvite} className="space-y-3 text-xs">
              <div className="space-y-1">
                <label className="text-muted-foreground font-mono text-[11px]">Registered User Email</label>
                <Input
                  type="email"
                  placeholder="coauthor@university.edu"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  className="h-8 text-xs"
                />
              </div>

              <div className="space-y-1">
                <label className="text-muted-foreground font-mono text-[11px]">Permission Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as "Editor" | "Viewer")}
                  className="w-full h-8 px-2 text-xs rounded-md border border-border bg-background text-foreground outline-none font-mono"
                >
                  <option value="Editor">Editor (Full edit & compile)</option>
                  <option value="Viewer">Viewer (Read-only)</option>
                </select>
              </div>

              <Button
                type="submit"
                size="sm"
                disabled={sendInviteMutation.isPending || !inviteEmail.trim()}
                className="w-full bg-amber-600 dark:bg-amber-500 text-white dark:text-zinc-950 rounded-lg h-8 text-xs font-semibold"
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

