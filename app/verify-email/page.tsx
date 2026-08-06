"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Cpu } from "lucide-react";

export default function VerifyEmailPage() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="max-w-md w-full p-8 rounded-2xl border border-border/80 bg-card/70 backdrop-blur-2xl shadow-2xl text-center space-y-6">
        <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mx-auto flex items-center justify-center">
          <CheckCircle2 className="w-8 h-8" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-extrabold text-foreground">Email Verified</h1>
          <p className="text-sm text-muted-foreground">
            Your work email address has been successfully verified for OverBranch Workspace.
          </p>
        </div>
        <Button asChild className="w-full bg-indigo-600 text-white rounded-xl h-11">
          <Link href="/dashboard">Continue to Dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
