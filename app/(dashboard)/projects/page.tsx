"use client";

import React, { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Plus,
  Search,
  Star,
  Clock,
  Users,
  MoreVertical,
  Edit2,
  Trash2,
  Copy,
  ExternalLink,
  FolderPlus,
  FileCode2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge-custom";
import { toast } from "sonner";

const mockProjects = [
  {
    id: "proj-1",
    name: "IEEE_Paper_OverBranch_v1",
    description: "Architectural Foundations for Collaborative LaTeX Editors with real-time PDF recompilation.",
    repository: "overbranch/ieee-paper-2026",
    branch: "main.tex",
    template: "IEEEtran",
    status: "active",
    isFavorite: true,
    collaboratorsCount: 3,
    stars: 142,
    updatedAt: "10 mins ago",
  },
  {
    id: "proj-2",
    name: "arXiv_Quantum_Intelligence_2026",
    description: "Multi-file LaTeX project tree for neural symbol parsing and quantum state matrix formulations.",
    repository: "overbranch/arxiv-quantum-draft",
    branch: "sections/abstract.tex",
    template: "arXiv",
    status: "compiling",
    isFavorite: false,
    collaboratorsCount: 2,
    stars: 88,
    updatedAt: "1 hour ago",
  },
  {
    id: "proj-3",
    name: "PhD_Dissertation_Thesis",
    description: "Distributed real-time document synchronization algorithms with BibTeX reference citation manager.",
    repository: "overbranch/phd-dissertation-v2",
    branch: "chapters/ch3_results.tex",
    template: "Book / Thesis",
    status: "active",
    isFavorite: true,
    collaboratorsCount: 4,
    stars: 210,
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
    toast.success("Updated project favorite status");
  };

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName) return;
    const newP = {
      id: `proj-${Date.now()}`,
      name: newProjName,
      description: "Custom LaTeX scientific document",
      repository: `overbranch/${newProjName.toLowerCase().replace(/\s+/g, "-")}`,
      branch: "main.tex",
      template: "IEEEtran",
      status: "active",
      isFavorite: false,
      collaboratorsCount: 1,
      stars: 0,
      updatedAt: "Just now",
    };
    setProjectsList([newP, ...projectsList]);
    setNewModalOpen(false);
    setNewProjName("");
    toast.success("New project created!");
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Workspace Projects
          </h1>
          <p className="text-sm text-muted-foreground">
            Manage, duplicate, and filter your scientific LaTeX manuscripts.
          </p>
        </div>

        <Button
          onClick={() => setNewModalOpen(true)}
          className="bg-gradient-to-r from-indigo-600 to-cyan-600 text-white rounded-xl h-11 px-5"
        >
          <Plus className="w-4 h-4 mr-2" />
          New Project
        </Button>
      </div>

      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl">
        <div className="relative w-full sm:w-80">
          <Input
            placeholder="Search manuscripts..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-10 pl-9"
          />
          <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          <button
            onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            className={`px-3 py-2 rounded-lg border text-xs font-mono transition-colors flex items-center gap-1.5 ${
              showFavoritesOnly ? "bg-amber-500/10 border-amber-500/30 text-amber-400 font-bold" : "border-border/60 text-muted-foreground"
            }`}
          >
            <Star className={`w-3.5 h-3.5 ${showFavoritesOnly ? "fill-amber-400" : ""}`} />
            Favorites Only
          </button>

          <select
            value={templateFilter}
            onChange={(e) => setTemplateFilter(e.target.value)}
            className="h-9 px-3 text-xs rounded-lg border border-border/60 bg-card text-foreground outline-none font-mono"
          >
            <option value="all">All Templates</option>
            <option value="IEEE">IEEEtran</option>
            <option value="arXiv">arXiv</option>
            <option value="Thesis">Thesis</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((proj) => (
          <motion.div key={proj.id} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }}>
            <Link href={`/editor/${proj.id}`}>
              <Card className="group p-6 rounded-2xl border border-border/60 bg-card/40 backdrop-blur-xl hover:border-indigo-500/40 hover:shadow-2xl transition-all duration-300 space-y-4 relative overflow-hidden">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <h3 className="font-bold text-base text-foreground tracking-tight group-hover:text-indigo-400 transition-colors flex items-center gap-1.5">
                      <FileCode2 className="w-4 h-4 text-indigo-400" />
                      {proj.name}
                    </h3>
                    <p className="text-xs text-muted-foreground font-mono">{proj.repository}</p>
                  </div>
                  <button onClick={(e) => toggleFavorite(proj.id, e)} className="p-1 hover:scale-110 transition-transform">
                    <Star className={`w-4 h-4 ${proj.isFavorite ? "text-amber-400 fill-amber-400" : "text-muted-foreground"}`} />
                  </button>
                </div>

                <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                  {proj.description}
                </p>

                <div className="pt-3 border-t border-border/30 flex items-center justify-between text-xs text-muted-foreground font-mono">
                  <span className="px-2 py-0.5 rounded bg-muted/80 text-foreground font-semibold">
                    {proj.template}
                  </span>
                  <div className="flex items-center gap-2">
                    <Users className="w-3 h-3 text-indigo-400" />
                    <span>{proj.collaboratorsCount} authors</span>
                  </div>
                </div>
              </Card>
            </Link>
          </motion.div>
        ))}
      </div>

      {newModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md">
          <div className="max-w-md w-full p-6 rounded-2xl border border-border/80 bg-card shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-foreground">Create New LaTeX Project</h3>
            <form onSubmit={handleCreateProject} className="space-y-4">
              <Input
                placeholder="e.g. ACM_Proceedings_2026"
                value={newProjName}
                onChange={(e) => setNewProjName(e.target.value)}
                required
                className="h-11 font-mono"
              />
              <div className="flex justify-end gap-3">
                <Button variant="ghost" type="button" onClick={() => setNewModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" className="bg-indigo-600 text-white">
                  Create Project
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
