"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User, Settings, Shield, LogOut, ChevronDown, Sparkles } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";
import { toast } from "sonner";

export function UserProfileDropdown() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { data: session } = authClient.useSession();

  const user = session?.user;
  const userName = user?.name || "Alex Rivers";
  const userEmail = user?.email || "alex@overbranch.dev";
  const userImage = user?.image || "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80";

  const handleSignOut = async () => {
    try {
      await authClient.signOut();
    } catch {
      
    }
    toast.info("Logged out of OverBranch session");
    router.push("/login");
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-accent/60 transition-colors"
      >
        <Avatar className="w-8 h-8 rounded-lg border border-border/60">
          <AvatarImage src={userImage} />
          <AvatarFallback className="bg-gradient-to-br from-indigo-600 to-cyan-600 text-white font-bold text-xs">
            {userName.slice(0, 2).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <div className="hidden sm:flex flex-col text-left">
          <span className="text-xs font-bold text-foreground tracking-tight">{userName}</span>
          <span className="text-[10px] text-muted-foreground font-mono">Owner & Admin</span>
        </div>
        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground hidden sm:block" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 z-50 w-60 rounded-2xl border border-border/70 bg-card/95 backdrop-blur-xl shadow-2xl p-2 space-y-1 text-xs">
            <div className="p-2 border-b border-border/40 space-y-0.5">
              <p className="font-semibold text-foreground">{userName}</p>
              <p className="text-muted-foreground font-mono text-[11px] truncate">{userEmail}</p>
            </div>

            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <User className="w-4 h-4 text-indigo-400" />
              <span>Customize Profile</span>
            </Link>

            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <Settings className="w-4 h-4 text-indigo-400" />
              <span>Workspace Settings</span>
            </Link>

            <button
              onClick={() => {
                setOpen(false);
                toast.info("Account Session Active");
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
