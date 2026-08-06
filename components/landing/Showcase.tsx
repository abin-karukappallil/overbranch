"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileCode2, Users, BookOpen, Check, Eye, Play, Sparkles } from "lucide-react";
import { AnimatedTabs } from "@/components/ui/tabs-animated";
import { Button } from "@/components/ui/button";
import Link from "next/link";

const tabs = [
  { id: "split", label: "Split TeX & PDF View", icon: FileCode2 },
  { id: "coauthors", label: "Multi-Author Cursors", icon: Users },
  { id: "bibtex", label: "BibTeX Manager", icon: BookOpen },
];

export function LandingShowcase() {
  const [activeTab, setActiveTab] = useState("split");

  return (
    <section id="showcase" className="py-24 px-4 sm:px-6 lg:px-8 relative bg-muted/20 border-t border-border/40">
      <div className="max-w-6xl mx-auto space-y-12">
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">
            Built for scientific authors & research teams
          </h2>
          <p className="text-base text-muted-foreground">
            Inspect the live features of the OverBranch LaTeX workspace.
          </p>

          <div className="pt-4 flex justify-center">
            <AnimatedTabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
          </div>
        </div>

        <div className="relative rounded-2xl border border-border/70 bg-card/70 backdrop-blur-xl p-6 sm:p-10 shadow-2xl overflow-hidden">
          <AnimatePresence mode="wait">
            {activeTab === "split" && (
              <motion.div
                key="split"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                transition={{ duration: 0.3 }}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center"
              >
                <div className="lg:col-span-6 space-y-5">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold text-indigo-400 bg-indigo-500/10 px-3 py-1 rounded-full border border-indigo-500/20">
                    <FileCode2 className="w-3.5 h-3.5" /> Instant PDF Recompile
                  </div>
                  <h3 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
                    Side-by-side TeX code & live paper rendering
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Type equations, references, and graphics with instantaneous compiled PDF paper feedback.
                  </p>
                  <ul className="space-y-2 text-sm text-foreground/90 font-medium">
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-400" /> Auto-compile on keystroke toggle
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-400" /> Support for pdfLaTeX, XeLaTeX, and LuaLaTeX
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-400" /> Synchronized editor & PDF cursor navigation
                    </li>
                  </ul>
                </div>
                <div className="lg:col-span-6 p-6 rounded-xl bg-background/80 border border-border/50 font-mono text-xs space-y-3 shadow-inner">
                  <div className="text-purple-400">\begin&#123;equation&#125;</div>
                  <div className="text-indigo-300 pl-4">E = m c^2</div>
                  <div className="text-purple-400">\end&#123;equation&#125;</div>
                  <div className="pt-2 text-emerald-400 font-semibold border-t border-border/40 flex items-center justify-between">
                    <span>✓ PDF Rendered in 8ms</span>
                    <span>IEEEtran.cls</span>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "coauthors" && (
              <motion.div
                key="coauthors"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                transition={{ duration: 0.3 }}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center"
              >
                <div className="lg:col-span-6 space-y-5">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold text-cyan-400 bg-cyan-500/10 px-3 py-1 rounded-full border border-cyan-500/20">
                    <Users className="w-3.5 h-3.5" /> Real-Time Presence
                  </div>
                  <h3 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
                    Co-authoring with multi-user cursors
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Work alongside co-authors with color-coded cursors, live selection badges, and comment threads.
                  </p>
                </div>
                <div className="lg:col-span-6 p-6 rounded-xl bg-background/80 border border-border/50 font-mono text-xs space-y-3">
                  <div className="flex items-center justify-between text-muted-foreground border-b border-border/30 pb-2">
                    <span>ACTIVE CO-AUTHORS</span>
                    <span className="text-cyan-400 font-bold">3 Collaborators</span>
                  </div>
                  <div className="space-y-2 text-foreground">
                    <div className="flex items-center gap-2 text-indigo-400">
                      <span className="w-2 h-2 rounded-full bg-indigo-400" />
                      <span>Dr. Alice Vance → main.tex (Ln 14)</span>
                    </div>
                    <div className="flex items-center gap-2 text-cyan-400">
                      <span className="w-2 h-2 rounded-full bg-cyan-400" />
                      <span>Prof. Bob Chen → references.bib (Ln 28)</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "bibtex" && (
              <motion.div
                key="bibtex"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                transition={{ duration: 0.3 }}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center"
              >
                <div className="lg:col-span-6 space-y-5">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold text-purple-400 bg-purple-500/10 px-3 py-1 rounded-full border border-purple-500/20">
                    <BookOpen className="w-3.5 h-3.5" /> Reference Autocomplete
                  </div>
                  <h3 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
                    BibTeX reference manager & instant citation
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Type <code className="text-indigo-300 font-mono">\cite&#123;...&#125;</code> to inspect BibTeX keys and insert citations effortlessly.
                  </p>
                </div>
                <div className="lg:col-span-6 p-6 rounded-xl bg-background/80 border border-border/50 font-mono text-xs space-y-2">
                  <div className="text-purple-400">@article&#123;vance2026overbranch,</div>
                  <div className="pl-4 text-cyan-300">author = &#123;Vance, Alice and Chen, Bob&#125;,</div>
                  <div className="pl-4 text-cyan-300">title = &#123;OverBranch Collaborative LaTeX Workspace&#125;,</div>
                  <div className="pl-4 text-cyan-300">journal = &#123;IEEE TSE&#125;, year = &#123;2026&#125;</div>
                  <div className="text-purple-400">&#125;</div>
                  <div className="text-emerald-400 font-semibold pt-2">✓ 42 Citations Resolved</div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}
