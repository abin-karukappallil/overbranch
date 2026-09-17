"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User, Settings, LogOut, ChevronDown, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";
import { toast } from "sonner";

export function UserProfileDropdown() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { data: session } = authClient.useSession();
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = mounted && (resolvedTheme === "dark" || theme === "dark");

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
        className="flex items-center gap-2 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-[#141517] transition-colors cursor-pointer"
      >
        <Avatar className="w-7 h-7 rounded-md border border-slate-200 dark:border-[#23252A]">
          <AvatarImage src={userImage} />
          <AvatarFallback className="bg-emerald-600 dark:bg-[#5E6AD2] text-white font-medium text-xs">
            {userName.slice(0, 2).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <div className="hidden sm:flex flex-col text-left">
          <span className="text-xs font-medium text-slate-800 dark:text-[#F7F8F8] tracking-tight">{userName}</span>
          <span className="text-[10px] text-slate-500 dark:text-[#8A8F98] font-mono">Workspace</span>
        </div>
        <ChevronDown className="w-3.5 h-3.5 text-slate-500 dark:text-[#8A8F98] hidden sm:block" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-10 z-50 w-56 rounded-xl border border-slate-200 dark:border-[#23252A] bg-white dark:bg-[#0F1011] text-slate-900 dark:text-[#F7F8F8] shadow-2xl p-1.5 space-y-0.5 text-xs font-sans">
            <div className="p-2 border-b border-slate-100 dark:border-[#23252A] space-y-0.5">
              <p className="font-medium text-slate-900 dark:text-[#F7F8F8]">{userName}</p>
              <p className="text-slate-500 dark:text-[#8A8F98] font-mono text-[11px] truncate">{userEmail}</p>
            </div>

            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-slate-600 dark:text-[#8A8F98] hover:text-slate-900 dark:hover:text-[#F7F8F8] hover:bg-slate-100 dark:hover:bg-[#141517] transition-colors"
            >
              <User className="w-3.5 h-3.5 text-emerald-600 dark:text-[#5E6AD2]" />
              <span>Customize Profile</span>
            </Link>

            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-slate-600 dark:text-[#8A8F98] hover:text-slate-900 dark:hover:text-[#F7F8F8] hover:bg-slate-100 dark:hover:bg-[#141517] transition-colors"
            >
              <Settings className="w-3.5 h-3.5 text-emerald-600 dark:text-[#5E6AD2]" />
              <span>Workspace Settings</span>
            </Link>

            <button
              onClick={() => setTheme(isDark ? "light" : "dark")}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-slate-600 dark:text-[#8A8F98] hover:text-slate-900 dark:hover:text-[#F7F8F8] hover:bg-slate-100 dark:hover:bg-[#141517] transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                {isDark ? <Sun className="w-3.5 h-3.5 text-amber-400" /> : <Moon className="w-3.5 h-3.5 text-slate-700" />}
                <span>Theme</span>
              </div>
              <span className="text-[10px] font-mono capitalize px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#1E2026] text-slate-600 dark:text-[#9E9E9E] border border-slate-200 dark:border-[#282A30]">
                {isDark ? "Dark" : "Light"}
              </span>
            </button>

            <div className="border-t border-slate-100 dark:border-[#23252A] pt-1">
              <button
                onClick={handleSignOut}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[#EB5757] hover:bg-[#EB5757]/10 transition-colors text-left font-medium cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
