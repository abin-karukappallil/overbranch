"use client";

import React from "react";
import Link from "next/link";
import { Code2 } from "lucide-react";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { GithubIcon } from "@/components/ui/github-icon";

/* Hallmark · archetype: Ft5 Statement · footer: Ft5 · theme: Cobalt */
export function LandingFooter() {
  return (
    <footer className="border-t border-border bg-card py-16 px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto space-y-12">
        <div className="space-y-4 max-w-3xl">
          <span className="text-xs font-mono text-indigo-400 font-bold uppercase tracking-widest">
            OVERBRANCH COLLABORATIVE PLATFORM
          </span>
          <h3 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-foreground leading-tight">
            Built for students, researchers and scientific authors who demand precision, continuous co-authoring, and zero compilation friction.
          </h3>
        </div>

        <div className="pt-8 border-t border-border flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <Link href="/" className="flex items-center gap-2">
              <OverBranchLogo size="md" variant="full" colored />
            </Link>
            <a
              href="https://github.com/abin-karukappallil/overbranch"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-xs font-mono text-foreground/80 hover:text-foreground bg-muted/60 hover:bg-accent px-3 py-1.5 rounded-xl border border-border/60 transition-all group shrink-0 w-fit"
              title="View OverBranch Source Code on GitHub"
            >
              <GithubIcon className="w-4 h-4 text-foreground group-hover:scale-110 transition-transform" />
              <span className="font-semibold">Star on GitHub</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
                Open Source
              </span>
            </a>
          </div>

          <nav className="flex flex-wrap items-center gap-6 text-xs font-mono text-muted-foreground">
            <a href="#workspace" className="hover:text-foreground transition-colors">
              Workspace
            </a>
            <a href="#specs" className="hover:text-foreground transition-colors">
              Specs
            </a>
            <a href="#showcase" className="hover:text-foreground transition-colors">
              Engine
            </a>
            <a
              href="https://github.com/abin-karukappallil/overbranch"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground transition-colors flex items-center gap-1.5 text-emerald-400 font-semibold"
            >
              <GithubIcon className="w-3.5 h-3.5" />
              <span>GitHub</span>
            </a>
            <Link href="/login" className="hover:text-foreground transition-colors">
              Sign In
            </Link>
            <Link href="/register" className="hover:text-foreground transition-colors">
              Register
            </Link>
          </nav>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs font-mono text-muted-foreground pt-4 border-t border-border/40">
          <p>© {new Date().getFullYear()} OverBranch — Free & Open Source LaTeX Platform</p>
          <a
            href="https://github.com/abin-karukappallil/overbranch"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-indigo-400 transition-colors flex items-center gap-1"
          >
            <Code2 className="w-3.5 h-3.5 text-indigo-400" />
            <span>github.com/abin-karukappallil/overbranch</span>
          </a>
        </div>
      </div>
    </footer>
  );
}

