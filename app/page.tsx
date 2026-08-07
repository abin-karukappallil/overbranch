"use client";

import React from "react";
import { LandingHeader } from "@/components/landing/Header";
import { LandingHero } from "@/components/landing/Hero";
import { LandingFeatures } from "@/components/landing/Features";
import { LandingShowcase } from "@/components/landing/Showcase";
import { LandingFooter } from "@/components/landing/Footer";
import { Button } from "@/components/ui/button";
import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background relative selection:bg-indigo-500/20 selection:text-indigo-300 overflow-x-hidden">
      <div className="fixed inset-0 bg-grid-pattern opacity-40 pointer-events-none -z-20" />
      <div className="fixed inset-0 bg-mesh-dark opacity-70 pointer-events-none -z-10" />

      <LandingHeader />

      <main>
        <LandingHero />
        <LandingFeatures />
        <LandingShowcase />

        <section className="py-20 px-4 sm:px-6 lg:px-8 relative border-t border-border/40 bg-gradient-to-b from-transparent to-muted/30">
          <div className="max-w-4xl mx-auto text-center space-y-6 p-10 sm:p-14 rounded-3xl border border-indigo-500/20 bg-card/60 backdrop-blur-2xl shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
            
            <div className="inline-flex items-center gap-2 text-xs font-semibold text-indigo-400 bg-indigo-500/10 px-3 py-1 rounded-full border border-indigo-500/20">
              <Sparkles className="w-3.5 h-3.5" /> Ready for Next-Level Coding?
            </div>

            <h2 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-foreground">
              Build your workspace on OverBranch
            </h2>
            <p className="text-muted-foreground text-base sm:text-lg max-w-xl mx-auto leading-relaxed">
              Start writing scientific documents with real-time co-authoring, instant TeX recompilation, and pixel-perfect responsive layouts.
            </p>

            <div className="pt-4 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Button
                size="lg"
                asChild
                className="w-full sm:w-auto h-12 px-8 bg-gradient-to-r from-indigo-600 via-purple-600 to-cyan-600 hover:opacity-95 text-white font-semibold shadow-xl shadow-indigo-500/20 rounded-xl"
              >
                <Link href="/register">
                  Get Started Free
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Link>
              </Button>
              <Button
                variant="outline"
                size="lg"
                asChild
                className="w-full sm:w-auto h-12 px-6 border-border/80 bg-card/60 backdrop-blur-md rounded-xl"
              >
                <Link href="/login">Sign In to Workspace</Link>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <LandingFooter />
    </div>
  );
}