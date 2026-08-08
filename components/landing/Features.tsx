"use client";

import React from "react";
import { motion } from "framer-motion";
import {
  Zap,
  ShieldCheck,
  GitPullRequest,
  Terminal,
  Cpu,
  Layers,
} from "lucide-react";

/* Hallmark · archetype: F3 Tabular spec sheet · feature: F3 · theme: Cobalt */
const specRows = [
  {
    code: "01",
    label: "TeX Recompilation Engine",
    spec: "pdfLaTeX, XeLaTeX & LuaLaTeX",
    detail: "Incremental compilation pipelines with sub-10ms UI sync and live PDF preview.",
    icon: Zap,
  },
  {
    code: "02",
    label: "Multi-Author Co-Authoring",
    spec: "Real-time presence & live cursors",
    detail: "Conflict-free document state synchronization with role-based invitation control.",
    icon: Layers,
  },
  {
    code: "03",
    label: "Document Tree & BibTeX",
    spec: "Multi-file .tex & .bib resolution",
    detail: "Instant citation key autocompletion and package dependency tracking.",
    icon: GitPullRequest,
  },
  {
    code: "04",
    label: "Command Palette & Shortcuts",
    spec: "Global Cmd+K spotlight matrix",
    detail: "Keyboard-driven project search, dark/light theme switching, and quick actions.",
    icon: Terminal,
  },
  {
    code: "05",
    label: "Enterprise Session Protection",
    spec: "Encrypted session & API security",
    detail: "Strict session management, secure cookies, and type-safe server queries.",
    icon: ShieldCheck,
  },
  {
    code: "06",
    label: "Universal Responsiveness",
    spec: "320px to 4K display adaptation",
    detail: "Mobile-tested layout collapse, no horizontal scroll, and touch-optimized hit targets.",
    icon: Cpu,
  },
];

export function LandingFeatures() {
  return (
    <section id="specs" className="py-20 px-4 sm:px-6 lg:px-8 border-t border-border bg-card/40">
      <div className="max-w-6xl mx-auto space-y-12">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-border pb-6">
          <div className="space-y-2">
            <span className="text-xs font-mono text-indigo-400 font-bold uppercase tracking-widest">
              SYSTEM ARCHITECTURE
            </span>
            <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-foreground">
              Technical Specifications & Engine Capabilities
            </h2>
          </div>
          <p className="text-xs font-mono text-muted-foreground max-w-xs">
            Built for student seminars, project reports, assignments, slides, and journal publications.
          </p>
        </div>

        <div className="divide-y divide-border border-y border-border">
          {specRows.map((row, idx) => (
            <motion.div
              key={row.code}
              initial={{ opacity: 0, y: 15 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: idx * 0.05 }}
              className="py-5 grid grid-cols-1 md:grid-cols-12 gap-4 items-start hover:bg-accent/40 transition-colors px-3 rounded-lg"
            >
              <div className="md:col-span-1 text-xs font-mono text-indigo-400 font-bold">
                {row.code}
              </div>

              <div className="md:col-span-4 space-y-1">
                <div className="flex items-center gap-2">
                  <row.icon className="w-4 h-4 text-indigo-400 shrink-0" />
                  <h3 className="text-sm font-bold text-foreground">
                    {row.label}
                  </h3>
                </div>
                <p className="text-xs font-mono text-muted-foreground">
                  {row.spec}
                </p>
              </div>

              <div className="md:col-span-7 text-xs text-muted-foreground leading-relaxed font-sans">
                {row.detail}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

