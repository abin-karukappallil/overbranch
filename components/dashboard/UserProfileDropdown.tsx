"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User, Settings, LogOut, ChevronDown } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";
import { toast } from "sonner";

export function UserProfileDropdown() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { data: session } = authClient.useSession();

  const user = session?.user;
  const userName = user?.name || user?.email?.split("@")[0] || "User";
  const userEmail = user?.email || "";
  const userImage = user?.image || "";

  const handleSignOut = async () => {
    try {
      await authClient.signOut();
    } catch {}
    router.push("/login");
  };

  return (
    <div className="relative font-sans">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-zinc-900 transition-colors cursor-pointer"
      >
        <Avatar className="w-8 h-8 rounded-lg border border-zinc-700">
          <AvatarImage src={userImage} />
          <AvatarFallback className="bg-[#00CC68] text-black font-archivo font-bold text-xs">
            {userName.slice(0, 2).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <div className="hidden sm:flex flex-col text-left">
          <span className="text-xs font-bold text-white tracking-tight">{userName}</span>
          <span className="text-[10px] text-[#00CC68] font-mono">Owner & Admin</span>
        </div>
        <ChevronDown className="w-3.5 h-3.5 text-zinc-400 hidden sm:block" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 z-50 w-60 rounded-2xl border border-zinc-800 bg-zinc-900 text-white shadow-2xl p-2 space-y-1 text-xs font-mono">
            <div className="p-2 border-b border-zinc-800 space-y-0.5 font-sans">
              <p className="font-bold text-white">{userName}</p>
              <p className="text-zinc-400 font-mono text-[11px] truncate">{userEmail}</p>
            </div>

            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors font-mono"
            >
              <User className="w-4 h-4 text-[#00CC68]" />
              <span>Customize Profile</span>
            </Link>

            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors font-mono"
            >
              <Settings className="w-4 h-4 text-[#00CC68]" />
              <span>Workspace Settings</span>
            </Link>

            <div className="border-t border-zinc-800 pt-1">
              <button
                onClick={handleSignOut}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-rose-400 hover:bg-rose-500/10 transition-colors text-left font-bold cursor-pointer font-mono"
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
