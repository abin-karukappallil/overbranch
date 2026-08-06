"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Cpu, ArrowRight, Menu, X, Sparkles, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { motion, AnimatePresence } from "framer-motion";

export function LandingHeader() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-background/70 backdrop-blur-xl transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-cyan-500 p-[1px] shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform duration-300">
            <div className="w-full h-full bg-background rounded-[11px] flex items-center justify-center">
              <Cpu className="w-5 h-5 text-indigo-400 group-hover:text-cyan-400 transition-colors" />
            </div>
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-lg tracking-tight gradient-text">
              OverBranch
            </span>
            <span className="text-[10px] text-muted-foreground font-mono -mt-1 tracking-widest uppercase">
              Collaborative Stack
            </span>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-muted-foreground">
          <a href="#features" className="hover:text-foreground transition-colors">
            Architecture
          </a>
          <a href="#speed" className="hover:text-foreground transition-colors">
            Engine & Speed
          </a>
          <a href="#showcase" className="hover:text-foreground transition-colors">
            Workspace Preview
          </a>
          <a href="#pricing" className="hover:text-foreground transition-colors">
            Enterprise
          </a>
        </nav>

        <div className="hidden md:flex items-center gap-3">
          <ThemeToggle />
          <Button variant="ghost" size="sm" asChild className="text-sm font-medium">
            <Link href="/login">Sign In</Link>
          </Button>
          <Button
            size="sm"
            asChild
            className="h-9 px-4 bg-gradient-to-r from-indigo-600 via-purple-600 to-cyan-600 text-white font-medium hover:opacity-90 shadow-md shadow-indigo-500/20 rounded-lg"
          >
            <Link href="/register">
              Get Started
              <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Link>
          </Button>
        </div>

        <div className="flex items-center gap-2 md:hidden">
          <ThemeToggle />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="h-9 w-9 text-muted-foreground"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </Button>
        </div>
      </div>

      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="md:hidden border-b border-border/40 bg-background/95 backdrop-blur-2xl px-6 py-6 space-y-4"
          >
            <nav className="flex flex-col space-y-3 font-medium text-base">
              <a
                href="#features"
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              >
                Architecture
              </a>
              <a
                href="#speed"
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              >
                Engine & Speed
              </a>
              <a
                href="#showcase"
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              >
                Workspace Preview
              </a>
            </nav>
            <div className="pt-4 border-t border-border/40 flex flex-col gap-3">
              <Button variant="outline" asChild className="w-full justify-center">
                <Link href="/login">Sign In</Link>
              </Button>
              <Button asChild className="w-full justify-center bg-gradient-to-r from-indigo-600 to-cyan-600 text-white">
                <Link href="/register">
                  Get Started Free
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Link>
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
