"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { User, Settings, LogOut, ChevronDown, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";
import { initialsOf } from "@/lib/initials";

const ROW =
  "flex h-8 w-full cursor-pointer items-center gap-2.5 rounded-md px-2 text-left text-[13px] text-ob-text-2 transition-colors hover:bg-ob-raised hover:text-ob-text";

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
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-label="Account menu"
        className="flex h-8 cursor-pointer items-center gap-2 rounded-lg pr-2 pl-1 transition-colors hover:bg-ob-raised"
      >
        <Avatar className="size-6 rounded-md">
          <AvatarImage src={userImage} />
          <AvatarFallback className="rounded-md bg-ob-raised text-[11px] font-medium text-ob-text-2">
            {initialsOf(userName)}
          </AvatarFallback>
        </Avatar>
        <span className="hidden max-w-[120px] truncate text-[13px] text-ob-text sm:block">{userName}</span>
        <ChevronDown className="hidden size-4 text-ob-muted sm:block" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute top-10 right-0 z-50 w-60 rounded-xl border border-ob-line bg-ob-card p-1 text-ob-text shadow-[0_8px_24px_rgba(0,0,0,0.16)]">
            <div className="flex flex-col gap-0.5 px-2 py-2">
              <p className="truncate text-[13px] font-medium text-ob-text">{userName}</p>
              <p className="truncate font-mono text-xs text-ob-muted">{userEmail}</p>
            </div>
            <div className="my-1 h-px bg-ob-line" />

            <Link href="/profile" onClick={() => setOpen(false)} className={ROW}>
              <User className="size-4 text-ob-muted" />
              <span>User profile</span>
            </Link>

            <Link href="/profile" onClick={() => setOpen(false)} className={ROW}>
              <Settings className="size-4 text-ob-muted" />
              <span>Workspace settings</span>
            </Link>

            <button onClick={() => setTheme(isDark ? "light" : "dark")} className={ROW}>
              {isDark ? <Sun className="size-4 text-ob-muted" /> : <Moon className="size-4 text-ob-muted" />}
              <span className="flex-1">Theme</span>
              <span className="font-mono text-xs text-ob-muted">{isDark ? "Dark" : "Light"}</span>
            </button>

            <div className="my-1 h-px bg-ob-line" />
            <button
              onClick={handleSignOut}
              className="flex h-8 w-full cursor-pointer items-center gap-2.5 rounded-md px-2 text-left text-[13px] text-ob-text-2 transition-colors hover:bg-ob-negative/10 hover:text-ob-negative"
            >
              <LogOut className="size-4" />
              <span>Sign out</span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}
