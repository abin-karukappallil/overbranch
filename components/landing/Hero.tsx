"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import gsap from "gsap";
import {
  ArrowRight,
  Sparkles,
  FileCode2,
  Users,
  CheckCircle2,
  Eye,
  FileText,
  Play,
  RotateCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge-custom";

export function LandingHero() {
  const heroRef = useRef<HTMLDivElement>(null);
  const headlineRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (headlineRef.current) {
      gsap.fromTo(
        headlineRef.current,
        { opacity: 0, y: 30 },
        { opacity: 1, y: 0, duration: 1, ease: "power3.out" }
      );
    }
  }, []);

  return (
    <section ref={heroRef} className="relative pt-12 pb-24 md:pt-20 md:pb-32 px-4 sm:px-6 lg:px-8 overflow-hidden">
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[350px] bg-gradient-to-tr from-indigo-500/20 via-purple-500/20 to-cyan-500/20 rounded-full blur-[120px] pointer-events-none -z-10" />

      <div className="max-w-5xl mx-auto text-center space-y-8">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2"
        >
          <StatusBadge variant="glow" dotPulse dotColor="bg-cyan-400">
            <span className="text-xs font-semibold tracking-wide">OverBranch Collaborative LaTeX Platform</span>
          </StatusBadge>
        </motion.div>

        <h1
          ref={headlineRef}
          className="text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight leading-[1.1] text-foreground"
        >
          Write scientific papers with <br className="hidden sm:inline" />
          <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
            real-time co-authoring
          </span>
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="max-w-2xl mx-auto text-lg sm:text-xl text-muted-foreground leading-relaxed"
        >
          OverBranch unites multi-file TeX document trees, live collaborator cursors, instant pdfLaTeX recompilation, and BibTeX citations into a sleek cloud LaTeX editor.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-2"
        >
          <Button
            size="lg"
            asChild
            className="w-full sm:w-auto h-12 px-8 bg-gradient-to-r from-indigo-600 via-purple-600 to-cyan-600 hover:opacity-95 text-white font-semibold shadow-xl shadow-indigo-500/25 rounded-xl text-base"
          >
            <Link href="/register">
              Start Free LaTeX Project
              <ArrowRight className="w-4 h-4 ml-2" />
            </Link>
          </Button>

          <Button
            variant="outline"
            size="lg"
            asChild
            className="w-full sm:w-auto h-12 px-6 border-border/80 bg-card/60 backdrop-blur-md hover:bg-accent/80 font-medium rounded-xl text-base"
          >
            <Link href="/login" className="flex items-center gap-3">
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              <span>Sign in with Google</span>
            </Link>
          </Button>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="flex flex-wrap items-center justify-center gap-6 text-xs text-muted-foreground font-medium pt-2"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Instant pdfLaTeX PDF Preview</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Multi-Author Cursors & Presence</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>BibTeX Reference Auto-Sync</span>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.5 }}
          className="mt-12 max-w-5xl mx-auto rounded-2xl border border-border/80 bg-card/80 backdrop-blur-2xl shadow-2xl overflow-hidden text-left"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/40 bg-muted/30">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-rose-500/80" />
              <div className="w-3 h-3 rounded-full bg-amber-500/80" />
              <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
              <span className="ml-2 text-xs font-mono text-muted-foreground flex items-center gap-1.5">
                <FileCode2 className="w-3.5 h-3.5 text-indigo-400" />
                IEEE_Paper_OverBranch_v1 — main.tex
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono">
              <span className="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">3 Co-Authors Active</span>
              <span className="hidden sm:inline px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400">pdfLaTeX Compiled</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-12 min-h-[380px] font-mono text-xs">
            <div className="md:col-span-7 p-5 bg-background/50 border-r border-border/30 space-y-2 leading-relaxed overflow-x-auto">
              <p className="text-purple-400">\documentclass<span className="text-cyan-300">[conference]&#123;IEEEtran&#125;</span></p>
              <p className="text-purple-400">\usepackage<span className="text-emerald-300">&#123;amsmath, amssymb, graphicx&#125;</span></p>
              <br />
              <p className="text-indigo-300">\title<span className="text-foreground">&#123;OverBranch: Collaborative LaTeX Editor&#125;</span></p>
              <p className="text-muted-foreground flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
                <span className="text-indigo-300">\author&#123;Alice Vance, Bob Chen, Carol Zhang&#125;</span>
              </p>
              <br />
              <p className="text-purple-400">\begin<span className="text-cyan-300">&#123;abstract&#125;</span></p>
              <p className="pl-4 text-foreground/90">We present OverBranch, a collaborative LaTeX platform featuring sub-10ms UI latency and live PDF preview.</p>
              <p className="text-purple-400">\end<span className="text-cyan-300">&#123;abstract&#125;</span></p>
              <br />
              <p className="text-purple-400">\begin<span className="text-cyan-300">&#123;equation&#125;</span></p>
              <p className="pl-4 text-indigo-300">\mathcal&#123;L&#125;_&#123;latency&#125; = \min_&#123;\theta&#125; \sum_&#123;i=1&#125;^&#123;N&#125; \| T_&#123;compile&#125; - T_&#123;editor&#125; \|^2</p>
              <p className="text-purple-400">\end<span className="text-cyan-300">&#123;equation&#125;</span></p>
            </div>

            <div className="md:col-span-5 p-6 bg-zinc-950/60 flex flex-col justify-between">
              <div className="space-y-4 bg-card p-5 rounded-xl border border-border/80 text-foreground font-serif text-[11px] leading-relaxed shadow-xl">
                <div className="text-center space-y-1 border-b border-border/40 pb-2">
                  <p className="font-bold text-xs">OverBranch: Collaborative LaTeX Editor</p>
                  <p className="text-[10px] text-muted-foreground italic">Alice Vance, Bob Chen, Carol Zhang</p>
                </div>
                <div className="space-y-1">
                  <span className="font-sans font-bold text-[9px] uppercase tracking-widest text-indigo-400">Abstract</span>
                  <p className="text-muted-foreground">We present OverBranch, a collaborative LaTeX platform featuring sub-10ms UI latency and live PDF preview.</p>
                </div>
                <div className="py-1.5 text-center bg-background/80 rounded border border-border/30 font-mono text-[10px] text-indigo-300">
                  L_latency = min_θ ∑ ‖ T_compile - T_editor ‖²
                </div>
              </div>

              <div className="pt-4 flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <CheckCircle2 className="w-3.5 h-3.5" /> PDF Updated Just Now
                </span>
                <span className="px-2 py-0.5 rounded bg-muted/80 text-foreground">Page 1 of 2</span>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
