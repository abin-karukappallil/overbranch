"use client";

import React, { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Plus,
  Search,
  Star,
  UserPlus,
  FileCode2,
  X,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";

const mockProjects = [
  {
    id: "proj-1",
    name: "IEEE_Paper_OverBranch_v1",
    description: "Architectural Foundations for Collaborative LaTeX Editors with real-time PDF recompilation.",
    template: "IEEEtran",
    isFavorite: true,
    collaboratorsCount: 3,
    updatedAt: "10m ago",
  },
  {
    id: "proj-2",
    name: "arXiv_Quantum_Intelligence_2026",
    description: "Multi-file LaTeX project tree for neural symbol parsing and quantum state matrix formulations.",
    template: "arXiv",
    isFavorite: false,
    collaboratorsCount: 2,
    updatedAt: "1h ago",
  },
  {
    id: "proj-3",
    name: "PhD_Dissertation_Thesis",
    description: "Distributed real-time document synchronization algorithms with BibTeX reference citation manager.",
    template: "Thesis",
    isFavorite: true,
    collaboratorsCount: 4,
    updatedAt: "Yesterday",
  },
];

export default function ProjectsPage() {
  const [search, setSearch] = useState("");
  const [templateFilter, setTemplateFilter] = useState("all");
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [projectsList, setProjectsList] = useState(mockProjects);
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [inviteModalProj, setInviteModalProj] = useState<typeof mockProjects[0] | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("Editor");

  const filtered = projectsList.filter((p) => {
    const matchesSearch = p.name.toLowerCase().includes(search.toLowerCase()) || p.description.toLowerCase().includes(search.toLowerCase());
    const matchesTemplate = templateFilter === "all" || p.template.toLowerCase().includes(templateFilter.toLowerCase());
    const matchesFav = !showFavoritesOnly || p.isFavorite;
    return matchesSearch && matchesTemplate && matchesFav;
  });

  const toggleFavorite = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setProjectsList((prev) =>
      prev.map((p) => (p.id === id ? { ...p, isFavorite: !p.isFavorite } : p))
    );
    toast.success("Updated favorite");
  };

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName) return;
    const newP = {
      id: `proj-${Date.now()}`,
      name: newProjName,
      description: "Custom scientific LaTeX paper",
      template: "IEEEtran",
      isFavorite: false,
      collaboratorsCount: 1,
      updatedAt: "Just now",
    };
    setProjectsList([newP, ...projectsList]);
    setNewModalOpen(false);
    setNewProjName("");
    toast.success("Project created");
  };

  const handleSendProjectInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail || !inviteModalProj) return;
    toast.success(`Invite sent to ${inviteEmail}`);
    setInviteEmail("");
    setInviteModalProj(null);
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Projects</h1>
          <p className="text-xs text-muted-foreground">Manage and co-author your LaTeX manuscripts.</p>
        </div>

        <Button
          onClick={() => setNewModalOpen(true)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg h-9 px-3.5 text-xs font-medium"
        >
          <Plus className="w-3.5 h-3.5 mr-1.5" />
          New Project
        </Button>
      </div>

      <div className="flex items-center justify-between gap-3 p-2 rounded-xl border border-border/40 bg-card/40">
        <div className="relative flex-1 max-w-xs">
          <Input
            placeholder="Filter projects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 text-xs pl-8 bg-background/50 border-border/40"
          />
          <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
        </div>

        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            className={`px-2.5 py-1.5 rounded-md border text-[11px] transition-colors flex items-center gap-1 ${
              showFavoritesOnly ? "bg-amber-500/10 border-amber-500/30 text-amber-400 font-bold" : "border-border/40 text-muted-foreground"
            }`}
          >
            <Star className={`w-3 h-3 ${showFavoritesOnly ? "fill-amber-400" : ""}`} />
            Favorites
          </button>

          <select
            value={templateFilter}
            onChange={(e) => setTemplateFilter(e.target.value)}
            className="h-8 px-2 text-[11px] rounded-md border border-border/40 bg-background text-foreground outline-none font-mono"
          >
            <option value="all">All Templates</option>
            <option value="IEEE">IEEEtran</option>
            <option value="arXiv">arXiv</option>
            <option value="Thesis">Thesis</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((proj) => (
          <motion.div key={proj.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="group p-4 rounded-xl border border-border/40 bg-card/30 hover:border-indigo-500/30 hover:bg-card/60 transition-all space-y-3 flex flex-col justify-between h-full">
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <Link href={`/editor/${proj.id}`} className="space-y-0.5 block flex-1">
                    <h3 className="font-bold text-sm text-foreground group-hover:text-indigo-400 transition-colors flex items-center gap-1.5 truncate">
                      <FileCode2 className="w-4 h-4 text-indigo-400 shrink-0" />
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

              <div className="pt-2 border-t border-border/30 flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                <span className="px-2 py-0.5 rounded bg-muted/60 text-foreground font-medium">
                  {proj.template}
                </span>

                <button
                  onClick={() => setInviteModalProj(proj)}
                  className="px-2 py-1 rounded-md border border-border/40 hover:bg-indigo-500/10 hover:text-indigo-400 transition-colors flex items-center gap-1 text-[10px]"
                >
                  <UserPlus className="w-3 h-3 text-indigo-400" />
                  <span>{proj.collaboratorsCount} authors</span>
                </button>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="max-w-sm w-full p-5 rounded-xl border border-border/60 bg-card shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-foreground">Create LaTeX Project</h3>
            <form onSubmit={handleCreateProject} className="space-y-3">
              <Input
                placeholder="e.g. ACM_Proceedings_2026"
                value={newProjName}
                onChange={(e) => setNewProjName(e.target.value)}
                required
                className="h-9 text-xs font-mono"
              />
              <div className="flex justify-end gap-2 text-xs">
                <Button variant="ghost" type="button" size="sm" onClick={() => setNewModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" className="bg-indigo-600 text-white">
                  Create
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {inviteModalProj && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="max-w-sm w-full p-5 rounded-xl border border-border/60 bg-card shadow-2xl space-y-3">
            <div className="flex items-center justify-between border-b border-border/30 pb-2">
              <span className="font-bold text-xs text-foreground truncate">{inviteModalProj.name}</span>
              <button onClick={() => setInviteModalProj(null)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSendProjectInvite} className="space-y-2.5 text-xs">
              <Input
                type="email"
                placeholder="coauthor@university.edu"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="h-8 text-xs"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="w-full h-8 px-2 text-xs rounded-md border border-border/40 bg-background text-foreground outline-none font-mono"
              >
                <option value="Editor">Editor</option>
                <option value="Viewer">Viewer</option>
              </select>
              <Button type="submit" size="sm" className="w-full bg-indigo-600 text-white rounded-md h-8 text-xs">
                Send Invite
              </Button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
