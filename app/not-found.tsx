"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { FileQuestion, ArrowLeft, Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4 text-center">
      <div className="max-w-md w-full p-8 rounded-3xl border border-border/80 bg-card/70 backdrop-blur-2xl shadow-2xl space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mx-auto flex items-center justify-center">
          <FileQuestion className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <span className="font-mono text-xs text-indigo-400 font-bold uppercase tracking-widest">
            Error 404 — Page Not Found
          </span>
          <h1 className="text-3xl font-extrabold text-foreground">Out of Bounds</h1>
          <p className="text-sm text-muted-foreground">
            The requested document or workspace page could not be located in OverBranch.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <Button variant="outline" asChild className="w-full sm:w-1/2 rounded-xl h-11">
            <Link href="/">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Home
            </Link>
          </Button>
          <Button asChild className="w-full sm:w-1/2 bg-indigo-600 text-white rounded-xl h-11">
            <Link href="/dashboard">
              <Home className="w-4 h-4 mr-2" />
              Dashboard
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
