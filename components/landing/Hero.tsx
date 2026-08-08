"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import gsap from "gsap";
import {
  ArrowRight,
  FileCode2,
  CheckCircle2,
  LayoutDashboard,
  FolderGit2,
  Terminal,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge-custom";
import { authClient } from "@/lib/auth-client";

/* Hallmark · macrostructure: Workbench · theme: Garden · HP: HP1 Vertical-rail */
export function LandingHero() {
  const headlineRef = useRef<HTMLHeadingElement>(null);
  const { data: session } = authClient.useSession();
  const isAuthenticated = Boolean(session?.user);

  useEffect(() => {
    if (headlineRef.current) {
      gsap.fromTo(
        headlineRef.current,
        { opacity: 0, y: 24 },
        { opacity: 1, y: 0, duration: 0.8, ease: "power2.out" }
      );
    }
  }, []);

  return (
    <section id="workspace" className="relative pt-10 pb-20 md:pt-16 md:pb-28 px-4 sm:px-6 lg:px-8 overflow-hidden">
      <div className="max-w-5xl mx-auto text-center space-y-7">
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="inline-flex items-center gap-2"
        >
          <StatusBadge variant="outline" dotPulse dotColor="bg-emerald-400">
            <span className="text-xs font-mono tracking-wide uppercase">OverBranch Workbench v1.0</span>
          </StatusBadge>
        </motion.div>

        <h1
          ref={headlineRef}
          className="text-3xl sm:text-5xl md:text-6xl font-extrabold tracking-tight leading-[1.12] text-foreground max-w-4xl mx-auto"
        >
          Collaborative LaTeX & Slides Workspace for Seminars, Reports & Papers.
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="max-w-2xl mx-auto text-base sm:text-lg text-muted-foreground leading-relaxed"
        >
          Co-author seminar reports, lab assignments, final-year project theses, Beamer slide presentations, and journal papers with real-time cursors and sub-10ms PDF compilation.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.25 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-1"
        >
          {isAuthenticated ? (
            <>
              <Button
                size="lg"
                asChild
                className="w-full sm:w-auto h-11 px-7 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold shadow-md rounded-full text-sm"
              >
                <Link href="/dashboard" className="flex items-center gap-2">
                  <LayoutDashboard className="w-4 h-4" />
                  <span>Open Workspace Dashboard</span>
                </Link>
              </Button>
              <Button
                variant="outline"
                size="lg"
                asChild
                className="w-full sm:w-auto h-11 px-6 border-border bg-card hover:bg-accent font-medium rounded-full text-sm"
              >
                <Link href="/projects" className="flex items-center gap-2">
                  <FolderGit2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
                  <span>View All Document Projects</span>
                </Link>
              </Button>
            </>
          ) : (
            <>
              <Button
                size="lg"
                asChild
                className="w-full sm:w-auto h-11 px-7 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold shadow-md rounded-full text-sm"
              >
                <Link href="/register" className="flex items-center gap-2">
                  <span>Start Free Project</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </Button>

              <Button
                variant="outline"
                size="lg"
                asChild
                className="w-full sm:w-auto h-11 px-6 border-border bg-card hover:bg-accent font-medium rounded-full text-sm"
              >
                <Link href="/login" className="flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
                  <span>Sign In to Workspace</span>
                </Link>
              </Button>
            </>
          )}
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.35 }}
          className="flex flex-wrap items-center justify-center gap-6 text-xs text-muted-foreground font-mono pt-1"
        >
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Seminar & Report Templates</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Beamer Slides & PPT</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Journal & Conference Layouts</span>
          </div>
        </motion.div>

        {/* Workbench Macrostructure Feature Window */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.4 }}
          className="mt-10 max-w-5xl mx-auto rounded-2xl border border-border/80 bg-card shadow-2xl overflow-hidden text-left"
        >
          <div className="flex flex-wrap items-center justify-between px-4 py-2.5 border-b border-border bg-muted/40 text-xs font-mono">
            <div className="flex items-center gap-2">
              <FileCode2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
              <span className="font-bold text-foreground">Seminar_Project_Report.tex</span>
              <span className="text-muted-foreground text-[11px] hidden sm:inline">• main.tex</span>
            </div>
            <div className="flex items-center gap-3 text-muted-foreground text-[11px]">
              <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border border-emerald-500/20 font-semibold">
                3 Team Authors Active
              </span>
              <span className="flex items-center gap-1 text-emerald-500 dark:text-emerald-400">
                <Zap className="w-3 h-3" /> Compiled 4ms ago
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-12 min-h-[360px] font-mono text-xs">
            <div className="md:col-span-7 p-5 bg-background/60 border-r border-border space-y-2 leading-relaxed overflow-x-auto">
              <p className="text-purple-400">\documentclass<span className="text-emerald-400">[12pt,report]&#123;report&#125;</span></p>
              <p className="text-purple-400">\usepackage<span className="text-emerald-400">&#123;graphicx, amsmath, hyperref&#125;</span></p>
              <br />
              <p className="text-emerald-500 dark:text-emerald-400">\title<span className="text-foreground">&#123;Seminar Report: Deep Learning Architecture&#125;</span></p>
              <p className="text-muted-foreground flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                <span className="text-emerald-300 dark:text-emerald-300">\author&#123;Student Team: Alex Rivers, Sam Vance&#125;</span>
              </p>
              <br />
              <p className="text-purple-400">\begin<span className="text-emerald-400">&#123;abstract&#125;</span></p>
              <p className="pl-4 text-foreground/90">This seminar report presents an in-depth review of modern neural networks, prepared for academic evaluation and journal publication.</p>
              <p className="text-purple-400">\end<span className="text-emerald-400">&#123;abstract&#125;</span></p>
              <br />
              <p className="text-purple-400">\section<span className="text-emerald-400">&#123;Project Methodology&#125;</span></p>
              <p className="pl-4 text-foreground/80">See Figure 1 for system architecture block diagram.</p>
            </div>

            <div className="md:col-span-5 p-6 bg-card flex flex-col justify-between border-t md:border-t-0 border-border">
              <div className="space-y-4 p-5 rounded-xl border border-border bg-background text-foreground font-serif text-[11px] leading-relaxed shadow-sm">
                <div className="text-center space-y-1 border-b border-border pb-2">
                  <p className="font-bold text-xs">Seminar Report: Deep Learning Architecture</p>
                  <p className="text-[10px] text-muted-foreground italic">Student Team: Alex Rivers, Sam Vance</p>
                </div>
                <div className="space-y-1">
                  <span className="font-sans font-bold text-[9px] uppercase tracking-widest text-emerald-500 dark:text-emerald-400">Abstract</span>
                  <p className="text-muted-foreground leading-normal">This seminar report presents an in-depth review of modern neural networks, prepared for academic evaluation and journal publication.</p>
                </div>
                <div className="py-1.5 text-center bg-muted/50 rounded border border-border/40 font-mono text-[10px] text-emerald-500 dark:text-emerald-400 font-semibold">
                  Section 1 • Project Methodology
                </div>
              </div>

              <div className="pt-4 flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                <span className="flex items-center gap-1.5 text-emerald-500 dark:text-emerald-400">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Live PDF Compiled
                </span>
                <span className="px-2 py-0.5 rounded bg-muted text-foreground">Project Report Format</span>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

