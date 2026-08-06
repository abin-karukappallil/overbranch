"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import {
  Plus,
  FileCode2,
  Terminal,
  Search,
  GitBranch,
  Star,
  Clock,
  Sparkles,
  ExternalLink,
  Users,
  CheckCircle2,
  Layers,
  ArrowUpRight,
  Filter,
  RefreshCw,
  FolderPlus,
  BookOpen,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/badge-custom";
import { EmptyState } from "@/components/ui/empty-state";
import { ProjectCardSkeleton } from "@/components/ui/skeleton-loader";
import { toast } from "sonner";

const mockLatexProjects = [
  {
    id: "proj-1",
    name: "IEEE_Paper_OverBranch_v1",
    description: "Architectural Foundations for Collaborative LaTeX Editors with real-time PDF recompilation.",
    repository: "overbranch/ieee-paper-2026",
    branch: "main.tex",
    template: "IEEEtran",
    status: "active",
    collaboratorsCount: 3,
    stars: 142,
    updatedAt: "10 mins ago",
    color: "from-indigo-500/20 to-purple-500/20",
    badgeVariant: "glow" as const,
  },
  {
    id: "proj-2",
    name: "arXiv_Quantum_Intelligence_2026",
    description: "Multi-file LaTeX project tree for neural symbol parsing and quantum state matrix formulations.",
    repository: "overbranch/arxiv-quantum-draft",
    branch: "sections/abstract.tex",
    template: "arXiv",
    status: "compiling",
    collaboratorsCount: 2,
    stars: 88,
    updatedAt: "1 hour ago",
    color: "from-cyan-500/20 to-blue-500/20",
    badgeVariant: "info" as const,
  },
  {
    id: "proj-3",
    name: "PhD_Dissertation_Thesis",
    description: "Distributed real-time document synchronization algorithms with BibTeX reference citation manager.",
    repository: "overbranch/phd-dissertation-v2",
    branch: "chapters/ch3_results.tex",
    template: "Book / Thesis",
    status: "active",
    collaboratorsCount: 4,
    stars: 210,
    updatedAt: "Yesterday",
    color: "from-emerald-500/20 to-teal-500/20",
    badgeVariant: "success" as const,
  },
];

export default function DashboardPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTemplate, setFilterTemplate] = useState("all");
  const [showEmptyState, setShowEmptyState] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const filteredProjects = mockLatexProjects.filter((p) => {
    const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) || p.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTemplate = filterTemplate === "all" || p.template.toLowerCase().includes(filterTemplate.toLowerCase());
    return matchesSearch && matchesTemplate;
  });

  const handleSimulateLoading = () => {
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast.success("Workspace synced with Supabase & Better Auth");
    }, 1000);
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="relative p-6 sm:p-8 rounded-3xl border border-indigo-500/30 bg-card/70 backdrop-blur-2xl shadow-2xl overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-bl from-indigo-500/15 via-purple-500/10 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 space-y-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <StatusBadge variant="glow" dotPulse dotColor="bg-cyan-400">
                  New Document Setup
                </StatusBadge>
                <span className="text-xs font-mono text-muted-foreground">LaTeX Engine: pdfLaTeX</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                Create New Project
              </h1>
              <p className="text-sm text-muted-foreground">
                Initialize a LaTeX manuscript from scientific templates or start with a blank canvas.
              </p>
            </div>

            <Button
              asChild
              size="lg"
              className="h-11 px-6 bg-gradient-to-r from-indigo-600 via-purple-600 to-cyan-600 hover:opacity-95 text-white font-semibold shadow-xl shadow-indigo-500/25 rounded-xl shrink-0"
            >
              <Link href="/editor">
                <Plus className="w-5 h-5 mr-2" />
                Create & Launch Editor
              </Link>
            </Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            <Link
              href="/editor"
              className="p-4 rounded-2xl border border-border/60 bg-background/50 hover:border-indigo-500/50 hover:bg-accent/40 transition-all text-left space-y-2 group"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-indigo-400 font-mono">IEEEtran.cls</span>
                <Sparkles className="w-4 h-4 text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <h3 className="font-bold text-sm text-foreground group-hover:text-indigo-300 transition-colors">
                IEEE Conference Paper
              </h3>
              <p className="text-xs text-muted-foreground line-clamp-2">
                Standard two-column IEEE proceedings layout with equations & author block.
              </p>
            </Link>

            <Link
              href="/editor"
              className="p-4 rounded-2xl border border-border/60 bg-background/50 hover:border-cyan-500/50 hover:bg-accent/40 transition-all text-left space-y-2 group"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-cyan-400 font-mono">arXiv.sty</span>
                <Sparkles className="w-4 h-4 text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <h3 className="font-bold text-sm text-foreground group-hover:text-cyan-300 transition-colors">
                arXiv Scientific Preprint
              </h3>
              <p className="text-xs text-muted-foreground line-clamp-2">
                Single-column manuscript template optimized for physics & computer science preprints.
              </p>
            </Link>

            <Link
              href="/editor"
              className="p-4 rounded-2xl border border-border/60 bg-background/50 hover:border-emerald-500/50 hover:bg-accent/40 transition-all text-left space-y-2 group"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-emerald-400 font-mono">blank.tex</span>
                <Sparkles className="w-4 h-4 text-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <h3 className="font-bold text-sm text-foreground group-hover:text-emerald-300 transition-colors">
                Blank Document
              </h3>
              <p className="text-xs text-muted-foreground line-clamp-2">
                Clean TeX document setup for custom packages, homework, and custom styles.
              </p>
            </Link>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Link
          href="/editor"
          className="p-4 rounded-2xl border border-border/50 bg-card/40 hover:bg-accent/60 backdrop-blur-sm text-left transition-all hover:scale-[1.02] flex items-center gap-3 group"
        >
          <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 group-hover:scale-110 transition-transform">
            <FileCode2 className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-sm block text-foreground">New LaTeX Paper</span>
            <span className="text-[11px] text-muted-foreground">IEEE / ACM Template</span>
          </div>
        </Link>

        <button
          onClick={() => toast.info("BibTeX Reference Importer launched")}
          className="p-4 rounded-2xl border border-border/50 bg-card/40 hover:bg-accent/60 backdrop-blur-sm text-left transition-all hover:scale-[1.02] flex items-center gap-3 group"
        >
          <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 group-hover:scale-110 transition-transform">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-sm block text-foreground">Import BibTeX</span>
            <span className="text-[11px] text-muted-foreground">DOI / Zotero Sync</span>
          </div>
        </button>

        <button
          onClick={() => toast.info("Terminal PDF compiler status")}
          className="p-4 rounded-2xl border border-border/50 bg-card/40 hover:bg-accent/60 backdrop-blur-sm text-left transition-all hover:scale-[1.02] flex items-center gap-3 group"
        >
          <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 group-hover:scale-110 transition-transform">
            <Terminal className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-sm block text-foreground">TeX Logs</span>
            <span className="text-[11px] text-muted-foreground">Compiler Output</span>
          </div>
        </button>

        <button
          onClick={() => setShowEmptyState(!showEmptyState)}
          className="p-4 rounded-2xl border border-border/50 bg-card/40 hover:bg-accent/60 backdrop-blur-sm text-left transition-all hover:scale-[1.02] flex items-center gap-3 group"
        >
          <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 group-hover:scale-110 transition-transform">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-sm block text-foreground">Toggle Empty UI</span>
            <span className="text-[11px] text-muted-foreground">Test Empty State</span>
          </div>
        </button>
      </div>

      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
              Active LaTeX Papers & Manuscripts
              <span className="text-xs px-2 py-0.5 rounded-md bg-muted text-muted-foreground font-mono">
                {filteredProjects.length}
              </span>
            </h2>
            <p className="text-xs text-muted-foreground">
              Select a paper to launch split-pane TeX editor and compiled PDF preview
            </p>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <div className="relative w-full sm:w-64">
              <Input
                placeholder="Search paper or topic..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-9 pl-9 text-xs"
              />
              <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            </div>
            <select
              value={filterTemplate}
              onChange={(e) => setFilterTemplate(e.target.value)}
              className="h-9 px-3 text-xs rounded-lg border border-border/60 bg-card text-foreground outline-none font-mono"
            >
              <option value="all">All Templates</option>
              <option value="IEEE">IEEEtran</option>
              <option value="arXiv">arXiv</option>
              <option value="Thesis">Thesis</option>
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
          </div>
        ) : showEmptyState || filteredProjects.length === 0 ? (
          <EmptyState
            icon={FolderPlus}
            title="No LaTeX papers found"
            description="Create your first LaTeX document or import BibTeX references to start writing."
            primaryActionLabel="Create New LaTeX Paper"
            onPrimaryAction={() => toast.info("New LaTeX Document Dialog")}
            secondaryActionLabel="Reset Filters"
            onSecondaryAction={() => {
              setSearchQuery("");
              setFilterTemplate("all");
              setShowEmptyState(false);
            }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredProjects.map((project) => (
              <motion.div
                key={project.id}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <Link href="/editor">
                  <Card className="group p-6 rounded-2xl border border-border/60 bg-card/40 backdrop-blur-xl hover:border-indigo-500/40 hover:shadow-2xl transition-all duration-300 space-y-4 relative overflow-hidden">
                    <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${project.color}`} />

                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <h3 className="font-bold text-base text-foreground tracking-tight group-hover:text-indigo-400 transition-colors flex items-center gap-1.5">
                          {project.name}
                          <ArrowUpRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </h3>
                        <p className="text-xs text-muted-foreground font-mono">{project.repository}</p>
                      </div>
                      <StatusBadge variant={project.badgeVariant} dot={project.status === "active"}>
                        {project.status}
                      </StatusBadge>
                    </div>

                    <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                      {project.description}
                    </p>

                    <div className="pt-3 border-t border-border/30 flex items-center justify-between text-xs text-muted-foreground font-mono">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded bg-muted/80 text-foreground font-semibold">
                          {project.template}
                        </span>
                        <span className="flex items-center gap-1">
                          <Users className="w-3 h-3 text-indigo-400" />
                          {project.collaboratorsCount} authors
                        </span>
                      </div>

                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1">
                          <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400/20" />
                          {project.stars}
                        </span>
                        <span className="flex items-center gap-1 text-[11px]">
                          <Clock className="w-3 h-3" />
                          {project.updatedAt}
                        </span>
                      </div>
                    </div>
                  </Card>
                </Link>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
