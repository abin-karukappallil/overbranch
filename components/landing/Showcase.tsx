"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileCode2, Users, BookOpen, Check } from "lucide-react";
import { AnimatedTabs } from "@/components/ui/tabs-animated";

/* Hallmark · component: Showcase · theme: Cobalt */
const tabs = [
  { id: "split", label: "Split TeX & PDF", icon: FileCode2 },
  { id: "coauthors", label: "Multi-Author Cursors", icon: Users },
  { id: "bibtex", label: "BibTeX Manager", icon: BookOpen },
];

export function LandingShowcase() {
  const [activeTab, setActiveTab] = useState("split");

  return (
    <section id="showcase" className="py-20 px-4 sm:px-6 lg:px-8 bg-card/20 border-t border-border">
      <div className="max-w-6xl mx-auto space-y-10">
        <div className="text-center max-w-2xl mx-auto space-y-3">
          <span className="text-xs font-mono text-emerald-500 dark:text-emerald-400 font-bold uppercase tracking-widest">
            WORKFLOW PREVIEW
          </span>
          <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-foreground">
            Engineered for students, project teams & academic authors
          </h2>
          <p className="text-xs sm:text-sm text-muted-foreground">
            From 10-page seminar reports and lab assignments to final year project theses and slide presentations.
          </p>

          <div className="pt-3 flex justify-center overflow-x-auto pb-1 max-w-full">
            <AnimatedTabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card p-6 sm:p-8 shadow-xl overflow-hidden">
          <AnimatePresence mode="wait">
            {activeTab === "split" && (
              <motion.div
                key="split"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.25 }}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center"
              >
                <div className="lg:col-span-6 space-y-4">
                  <div className="inline-flex items-center gap-2 text-xs font-mono text-emerald-500 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20 font-bold">
                    <FileCode2 className="w-3.5 h-3.5" /> Instant PDF Recompile
                  </div>
                  <h3 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
                    Synchronized TeX source code & live PDF document output
                  </h3>
                  <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
                    Type equations, graphics, and figures for seminar reports, assignments, and slides with sub-10ms compiled PDF feedback.
                  </p>
                  <ul className="space-y-2 text-xs text-foreground/90 font-medium font-mono">
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" /> Auto-compile on keystroke with instant error highlighting
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" /> Native support for seminar reports, project reports & Beamer slides
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" /> Bi-directional SyncTeX cursor navigation
                    </li>
                  </ul>
                </div>
                <div className="lg:col-span-6 p-5 rounded-xl bg-background border border-border font-mono text-xs space-y-3">
                  <div className="text-purple-400">\begin&#123;equation&#125;</div>
                  <div className="text-emerald-500 dark:text-emerald-400 pl-4">E = m c^2</div>
                  <div className="text-purple-400">\end&#123;equation&#125;</div>
                  <div className="pt-2 text-emerald-500 dark:text-emerald-400 font-semibold border-t border-border flex items-center justify-between text-[11px]">
                    <span>✓ Compiled in 8ms</span>
                    <span>Report & Slide Layout</span>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "coauthors" && (
              <motion.div
                key="coauthors"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.25 }}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center"
              >
                <div className="lg:col-span-6 space-y-4">
                  <div className="inline-flex items-center gap-2 text-xs font-mono text-emerald-500 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20 font-bold">
                    <Users className="w-3.5 h-3.5" /> Real-Time Presence
                  </div>
                  <h3 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
                    Group project co-authoring with live selection cursors
                  </h3>
                  <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
                    Collaborate seamlessly alongside classmates and project teammates with live selection highlights, cursor tracking, and comment threads.
                  </p>
                </div>
                <div className="lg:col-span-6 p-5 rounded-xl bg-background border border-border font-mono text-xs space-y-3">
                  <div className="flex items-center justify-between text-muted-foreground border-b border-border pb-2 text-[11px]">
                    <span>ACTIVE TEAM MEMBERS</span>
                    <span className="text-emerald-500 dark:text-emerald-400 font-bold">3 Collaborators Active</span>
                  </div>
                  <div className="space-y-2 text-foreground text-[11px]">
                    <div className="flex items-center gap-2 text-emerald-500 dark:text-emerald-400">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                      <span>Alex Rivers → main_report.tex (Ln 14)</span>
                    </div>
                    <div className="flex items-center gap-2 text-emerald-500 dark:text-emerald-400">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                      <span>Sam Vance → references.bib (Ln 28)</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "bibtex" && (
              <motion.div
                key="bibtex"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.25 }}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center"
              >
                <div className="lg:col-span-6 space-y-4">
                  <div className="inline-flex items-center gap-2 text-xs font-mono text-emerald-500 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20 font-bold">
                    <BookOpen className="w-3.5 h-3.5" /> Reference Autocomplete
                  </div>
                  <h3 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
                    BibTeX reference manager & instant citation lookup
                  </h3>
                  <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
                    Type <code className="text-emerald-500 dark:text-emerald-400 font-mono">\cite&#123;...&#125;</code> to inspect BibTeX keys and resolve citations instantly for journal papers and reports.
                  </p>
                </div>
                <div className="lg:col-span-6 p-5 rounded-xl bg-background border border-border font-mono text-xs space-y-2">
                  <div className="text-purple-400">@article&#123;vance2026overbranch,</div>
                  <div className="pl-4 text-emerald-500 dark:text-emerald-400">author = &#123;Vance, Alice and Chen, Bob&#125;,</div>
                  <div className="pl-4 text-emerald-500 dark:text-emerald-400">title = &#123;Real-Time Academic Collaboration Platform&#125;,</div>
                  <div className="pl-4 text-emerald-500 dark:text-emerald-400">journal = &#123;Academic Software Engineering&#125;, year = &#123;2026&#125;</div>
                  <div className="text-purple-400">&#125;</div>
                  <div className="text-emerald-500 dark:text-emerald-400 font-semibold pt-2 text-[11px]">✓ 42 BibTeX References Resolved</div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}

