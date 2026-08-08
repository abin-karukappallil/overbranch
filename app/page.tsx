"use client";

import React from "react";
import { LandingHeader } from "@/components/landing/Header";
import { LandingHero } from "@/components/landing/Hero";
import { LandingFeatures } from "@/components/landing/Features";
import { LandingShowcase } from "@/components/landing/Showcase";
import { LandingFooter } from "@/components/landing/Footer";
import { Button } from "@/components/ui/button";
import { ArrowRight, LayoutDashboard, Terminal } from "lucide-react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";

/* Hallmark · macrostructure: Workbench · theme: Garden */
export default function HomePage() {
  const { data: session } = authClient.useSession();
  const isAuthenticated = Boolean(session?.user);

  return (
    <div className="min-h-screen bg-background relative selection:bg-emerald-500/20 selection:text-emerald-300 dark:selection:text-emerald-200 overflow-x-clip max-w-full">
      <div className="fixed inset-0 bg-grid-pattern opacity-30 pointer-events-none -z-20" />

      <LandingHeader />

      <main>
        <LandingHero />
        <LandingFeatures />
        <LandingShowcase />

        <section className="py-16 px-4 sm:px-6 lg:px-8 border-t border-border bg-card/30">
          <div className="max-w-4xl mx-auto text-center space-y-6 p-8 sm:p-12 rounded-2xl border border-border bg-card shadow-xl">
            <span className="text-xs font-mono text-emerald-500 dark:text-emerald-400 font-bold uppercase tracking-widest">
              NEXT-LEVEL LATEX ENVIRONMENT
            </span>

            <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-foreground">
              {isAuthenticated ? "Ready to continue your document projects?" : "Build your academic workspace on OverBranch"}
            </h2>
            <p className="text-muted-foreground text-xs sm:text-sm max-w-xl mx-auto leading-relaxed">
              Start writing seminar reports, assignments, project reports, slides, and journal papers with real-time co-authoring and instant PDF compilation.
            </p>

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
              {isAuthenticated ? (
                <Button
                  size="lg"
                  asChild
                  className="w-full sm:w-auto h-11 px-7 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold shadow-md rounded-full text-sm"
                >
                  <Link href="/dashboard" className="flex items-center gap-2">
                    <LayoutDashboard className="w-4 h-4" />
                    <span>Go to Workspace Dashboard</span>
                  </Link>
                </Button>
              ) : (
                <>
                  <Button
                    size="lg"
                    asChild
                    className="w-full sm:w-auto h-11 px-7 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold shadow-md rounded-full text-sm"
                  >
                    <Link href="/register" className="flex items-center gap-2">
                      <span>Get Started Free</span>
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
            </div>
          </div>
        </section>
      </main>

      <LandingFooter />
    </div>
  );
}