"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ArrowRight, Menu, X, LayoutDashboard, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { motion, AnimatePresence } from "framer-motion";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { authClient } from "@/lib/auth-client";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

/* Hallmark · archetype: N5 Floating pill · nav: N5 · theme: Garden */
export function LandingHeader() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { data: session, isPending } = authClient.useSession();
  const isAuthenticated = Boolean(session?.user);

  const userName = session?.user?.name || "User";
  const userImage = session?.user?.image || undefined;

  return (
    <header className="sticky top-3 z-40 w-full px-4 sm:px-6 lg:px-8 max-w-6xl mx-auto pointer-events-none">
      <div className="pointer-events-auto rounded-full border border-border bg-card/80 backdrop-blur-2xl px-5 h-14 flex items-center justify-between shadow-lg shadow-black/5 transition-all">
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <OverBranchLogo size="md" variant="full" colored />
        </Link>

        <nav className="hidden md:flex items-center gap-6 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          <a href="#workspace" className="hover:text-foreground transition-colors">
            Workspace
          </a>
          <a href="#specs" className="hover:text-foreground transition-colors">
            Technical Specs
          </a>
          <a href="#showcase" className="hover:text-foreground transition-colors">
            Document Engine
          </a>
        </nav>

        <div className="hidden md:flex items-center gap-2.5">
          <ThemeToggle />
          
          {isPending ? (
            <div className="h-8 w-20 bg-muted rounded-full animate-pulse" />
          ) : isAuthenticated ? (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                asChild
                className="h-8 px-4 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold rounded-full text-xs shadow-xs"
              >
                <Link href="/dashboard" className="flex items-center gap-1.5">
                  <LayoutDashboard className="w-3.5 h-3.5" />
                  <span>Go to Workspace</span>
                </Link>
              </Button>
              <Link href="/profile" title={userName} className="hover:opacity-90 transition-opacity">
                <Avatar className="w-8 h-8 rounded-full border border-border">
                  <AvatarImage src={userImage} />
                  <AvatarFallback className="bg-emerald-600 text-white font-bold text-xs">
                    {userName.slice(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
              </Link>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" asChild className="h-8 px-3 text-xs font-medium rounded-full">
                <Link href="/login">Sign In</Link>
              </Button>
              <Button
                size="sm"
                asChild
                className="h-8 px-4 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold rounded-full text-xs shadow-xs"
              >
                <Link href="/register" className="flex items-center gap-1">
                  <span>Start Free</span>
                  <ArrowRight className="w-3 h-3" />
                </Link>
              </Button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 md:hidden">
          <ThemeToggle />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="h-8 w-8 text-muted-foreground rounded-full"
          >
            {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </Button>
        </div>
      </div>

      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 8 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.15 }}
            className="pointer-events-auto md:hidden rounded-2xl border border-border/80 bg-card/95 backdrop-blur-2xl p-5 shadow-2xl space-y-4"
          >
            <nav className="flex flex-col space-y-2 font-medium text-sm">
              <a
                href="#workspace"
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-xl hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              >
                Workspace
              </a>
              <a
                href="#specs"
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-xl hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              >
                Technical Specs
              </a>
              <a
                href="#showcase"
                onClick={() => setMobileMenuOpen(false)}
                className="px-3 py-2 rounded-xl hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              >
                Document Engine
              </a>
            </nav>
            <div className="pt-3 border-t border-border/40 flex flex-col gap-2">
              {isAuthenticated ? (
                <>
                  <Button asChild className="w-full justify-center bg-indigo-600 text-white rounded-xl">
                    <Link href="/dashboard" onClick={() => setMobileMenuOpen(false)}>
                      <LayoutDashboard className="w-4 h-4 mr-2" />
                      Go to Workspace
                    </Link>
                  </Button>
                  <Button variant="outline" asChild className="w-full justify-center rounded-xl">
                    <Link href="/profile" onClick={() => setMobileMenuOpen(false)}>
                      <User className="w-4 h-4 mr-2" />
                      Profile ({userName})
                    </Link>
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" asChild className="w-full justify-center rounded-xl">
                    <Link href="/login" onClick={() => setMobileMenuOpen(false)}>
                      Sign In
                    </Link>
                  </Button>
                  <Button asChild className="w-full justify-center bg-indigo-600 text-white rounded-xl">
                    <Link href="/register" onClick={() => setMobileMenuOpen(false)}>
                      Start Free Project
                      <ArrowRight className="w-4 h-4 ml-1.5" />
                    </Link>
                  </Button>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}

