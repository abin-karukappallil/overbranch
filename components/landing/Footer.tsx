"use client";

import React from "react";
import Link from "next/link";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

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
            Built for scientific authors who demand precision, continuous co-authoring, and zero compilation friction.
          </h3>
        </div>

        <div className="pt-8 border-t border-border flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <Link href="/" className="flex items-center gap-2">
              <OverBranchLogo size="md" variant="full" colored />
            </Link>
            <div className="flex items-center gap-2 text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded border border-emerald-500/20 w-fit">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
              <span>pdfLaTeX Engine Operational</span>
            </div>
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
            <Link href="/login" className="hover:text-foreground transition-colors">
              Sign In
            </Link>
            <Link href="/register" className="hover:text-foreground transition-colors">
              Register
            </Link>
          </nav>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs font-mono text-muted-foreground pt-4 border-t border-border/40">
          <p>© {new Date().getFullYear()} OverBranch</p>
        </div>
      </div>
    </footer>
  );
}

