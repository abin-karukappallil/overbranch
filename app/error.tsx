"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AlertOctagon, RotateCw, Home } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4 text-center">
      <div className="max-w-md w-full p-8 rounded-3xl border border-rose-500/30 bg-rose-500/5 backdrop-blur-2xl shadow-2xl space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/20 mx-auto flex items-center justify-center">
          <AlertOctagon className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <span className="font-mono text-xs text-rose-400 font-bold uppercase tracking-widest">
            Error 500 — Application Failure
          </span>
          <h1 className="text-3xl font-extrabold text-foreground">Workspace Error</h1>
          <p className="text-sm text-muted-foreground">
            An unexpected error occurred during rendering. Try reloading the active workspace session.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <Button onClick={() => reset()} variant="outline" className="w-full sm:w-1/2 rounded-xl h-11">
            <RotateCw className="w-4 h-4 mr-2" />
            Retry Session
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
