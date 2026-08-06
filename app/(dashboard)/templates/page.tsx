"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Sparkles, FileCode2, BookOpen, Layers, CheckCircle2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";

const mockTemplates = [
  {
    id: "tmpl-ieee",
    name: "IEEE Conference Paper",
    category: "Proceedings",
    description: "Official two-column IEEEtran proceedings layout with equations, figure blocks, and BibTeX integration.",
    fileExtension: "cls",
    isFeatured: true,
    usageCount: 1420,
    color: "from-indigo-500/20 to-purple-500/20",
  },
  {
    id: "tmpl-arxiv",
    name: "arXiv Scientific Preprint",
    category: "Preprint",
    description: "Single-column preprint format optimized for computer science, physics, and mathematics submission.",
    fileExtension: "sty",
    isFeatured: true,
    usageCount: 980,
    color: "from-cyan-500/20 to-blue-500/20",
  },
  {
    id: "tmpl-acm",
    name: "ACM SIGCONF Proceedings",
    category: "ACM",
    description: "Official ACM Master Article Template for primary conferences and symposiums.",
    fileExtension: "cls",
    isFeatured: false,
    usageCount: 650,
    color: "from-emerald-500/20 to-teal-500/20",
  },
  {
    id: "tmpl-thesis",
    name: "University PhD Dissertation",
    category: "Thesis",
    description: "Multi-chapter thesis book class setup with list of figures, tables, and bibliography configuration.",
    fileExtension: "cls",
    isFeatured: true,
    usageCount: 1120,
    color: "from-amber-500/20 to-rose-500/20",
  },
];

export default function TemplatesPage() {
  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="space-y-1">
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          Scientific LaTeX Templates
        </h1>
        <p className="text-sm text-muted-foreground">
          Pre-configured document preambles and proceedings styles ready for instant compilation.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {mockTemplates.map((tmpl) => (
          <Card key={tmpl.id} className="p-6 rounded-2xl border border-border/60 bg-card/40 backdrop-blur-xl space-y-4 relative overflow-hidden">
            <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${tmpl.color}`} />

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-mono text-xs text-indigo-400 font-bold">
                <FileCode2 className="w-4 h-4" />
                {tmpl.fileExtension.toUpperCase()} Class
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">
                {tmpl.usageCount} uses
              </span>
            </div>

            <div className="space-y-1">
              <h3 className="text-lg font-bold text-foreground">{tmpl.name}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{tmpl.description}</p>
            </div>

            <div className="pt-2 flex justify-end">
              <Button asChild size="sm" className="bg-indigo-600 text-white rounded-xl">
                <Link href="/editor">
                  Use Template
                  <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                </Link>
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
