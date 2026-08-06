"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User, Settings, Shield, LogOut, ChevronDown, Sparkles } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { toast } from "sonner";

export function UserProfileDropdown() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  const handleSignOut = () => {
    toast.info("Logged out successfully");
    router.push("/login");
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-accent/60 transition-colors"
      >
        <Avatar className="w-8 h-8 rounded-lg border border-border/60">
          <AvatarImage src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80" />
          <AvatarFallback className="bg-gradient-to-br from-indigo-600 to-cyan-600 text-white font-bold text-xs">
            OB
          </AvatarFallback>
        </Avatar>
        <div className="hidden sm:flex flex-col text-left">
          <span className="text-xs font-bold text-foreground tracking-tight">Alex Rivers</span>
          <span className="text-[10px] text-muted-foreground font-mono">Owner & Admin</span>
        </div>
        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground hidden sm:block" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 z-50 w-60 rounded-2xl border border-border/70 bg-card/95 backdrop-blur-xl shadow-2xl p-2 space-y-1 text-xs">
            <div className="p-2 border-b border-border/40 space-y-0.5">
              <p className="font-semibold text-foreground">Alex Rivers</p>
              <p className="text-muted-foreground font-mono text-[11px]">alex@overbranch.dev</p>
            </div>

            <Link
              href="/dashboard/settings"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <Settings className="w-4 h-4 text-indigo-400" />
              <span>Workspace Settings</span>
            </Link>

            <button
              onClick={() => {
                setOpen(false);
                toast.info("Better Auth Session Security Dialog");
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-accent transition-colors text-left"
            >
              <Shield className="w-4 h-4 text-emerald-400" />
              <span>Security & Sessions</span>
            </button>

            <div className="border-t border-border/40 pt-1">
              <button
                onClick={handleSignOut}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-rose-500 hover:bg-rose-500/10 transition-colors text-left font-medium"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
