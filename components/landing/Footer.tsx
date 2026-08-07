"use client";

import React from "react";
import Link from "next/link";
import { Shield, Sparkles, Globe } from "lucide-react";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

export function LandingFooter() {
  return (
    <footer className="border-t border-border/40 bg-background/60 backdrop-blur-xl py-16 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-5 gap-10">
        <div className="md:col-span-2 space-y-4">
          <Link href="/" className="flex items-center gap-3">
            <OverBranchLogo size="lg" variant="full" colored />
          </Link>
          <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
            The modern collaborative LaTeX platform for scientists, researchers, and engineers. Built with Next.js 15, tRPC, and high-performance cloud engines.
          </p>
          <div className="flex items-center gap-2 text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1.5 rounded-lg border border-emerald-500/20 w-fit">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>All Systems Operational</span>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-foreground uppercase tracking-wider">Product</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><a href="#features" className="hover:text-foreground transition-colors">Architecture</a></li>
            <li><a href="#speed" className="hover:text-foreground transition-colors">Engine & Speed</a></li>
            <li><a href="#showcase" className="hover:text-foreground transition-colors">Workspace Preview</a></li>
            <li><Link href="/login" className="hover:text-foreground transition-colors">Sign In Portal</Link></li>
          </ul>
        </div>

        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-foreground uppercase tracking-wider">Resources</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><a href="https://github.com" target="_blank" rel="noreferrer" className="hover:text-foreground transition-colors">GitHub Repository</a></li>
            <li><a href="https://ctan.org" target="_blank" rel="noreferrer" className="hover:text-foreground transition-colors">LaTeX CTAN Packages</a></li>
            <li><a href="https://trpc.io" target="_blank" rel="noreferrer" className="hover:text-foreground transition-colors">tRPC Framework</a></li>
            <li><a href="#features" className="hover:text-foreground transition-colors">Platform Features</a></li>
          </ul>
        </div>

        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-foreground uppercase tracking-wider">Connect</h4>
          <div className="flex items-center gap-3 text-muted-foreground">
            <a href="https://github.com" target="_blank" rel="noreferrer" className="p-2 rounded-lg bg-muted/60 hover:text-foreground hover:bg-accent transition-colors" title="GitHub">
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            </a>
            <a href="https://twitter.com" target="_blank" rel="noreferrer" className="p-2 rounded-lg bg-muted/60 hover:text-foreground hover:bg-accent transition-colors" title="Twitter / X">
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
            </a>
            <a href="https://discord.com" target="_blank" rel="noreferrer" className="p-2 rounded-lg bg-muted/60 hover:text-foreground hover:bg-accent transition-colors" title="Discord">
              <Globe className="w-4 h-4" />
            </a>
          </div>
          <p className="text-xs text-muted-foreground pt-2">
            © {new Date().getFullYear()} OverBranch Inc. MIT License.
          </p>
        </div>
      </div>
    </footer>
  );
}
