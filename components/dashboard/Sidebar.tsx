"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  FolderGit2,
  Presentation,
  User,
  Search,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { toast } from "sonner";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { authClient } from "@/lib/auth-client";

interface SidebarProps {
  collapsed: boolean;
  mobileOpen?: boolean;
  onToggleCollapse: () => void;
  onCloseMobile?: () => void;
  onOpenCommandPalette: () => void;
}

export function DashboardSidebar({
  collapsed,
  mobileOpen = false,
  onToggleCollapse,
  onCloseMobile,
  onOpenCommandPalette,
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: session } = authClient.useSession();

  const navItems = [
    { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { name: "Projects", href: "/projects", icon: FolderGit2 },
    { name: "Templates", href: "/templates", icon: Presentation },
    { name: "Profile", href: "/profile", icon: User },
  ];

  const renderContent = (isMobile: boolean = false) => {
    const isCompact = !isMobile && collapsed;

    return (
      <div className="flex flex-col h-full font-sans select-none relative bg-zinc-900 text-zinc-100">
        {/* Sidebar Interior Container */}
        <div className="flex flex-col h-full p-3 sm:p-4">
          {/* Classic Header Bar with OverBranch Logo */}
          <div
            className={`h-14 pb-3 mb-2 border-b border-zinc-800 flex items-center shrink-0 ${
              isCompact ? "justify-center px-1" : "justify-between px-2"
            }`}
          >
            <Link
              href="/dashboard"
              onClick={isMobile ? onCloseMobile : undefined}
              className="flex items-center gap-2 shrink-0"
            >
              <OverBranchLogo
                variant={isCompact ? "icon" : "full"}
                size={isCompact ? "sm" : "md"}
                colored
              />
              {!isCompact && (
                <span className="text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-zinc-800 text-[#00CC68] border border-zinc-700 tracking-wider">
                  BETA
                </span>
              )}
            </Link>

            {!isMobile && (
              <button
                onClick={onToggleCollapse}
                className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/40 transition-all opacity-60 hover:opacity-100 shrink-0 cursor-pointer"
                title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
              >
                {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
              </button>
            )}
          </div>

          {/* Quick Action & Search Button */}
          <div className="space-y-2 my-2 shrink-0">
            <Link
              href="/projects"
              onClick={isMobile ? onCloseMobile : undefined}
              className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-2xl bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold text-xs uppercase tracking-wider border border-black shadow-[3px_3px_0px_0px_#000000] transition-all cursor-pointer ${
                isCompact ? "justify-center" : "justify-center"
              }`}
            >
              <Plus className="w-4 h-4 text-black stroke-[3] shrink-0" />
              {!isCompact && <span>New Project</span>}
            </Link>

            <button
              onClick={() => {
                if (isMobile && onCloseMobile) onCloseMobile();
                onOpenCommandPalette();
              }}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-2xl bg-zinc-950 border border-zinc-800 hover:border-zinc-700 text-xs text-zinc-400 hover:text-white font-mono transition-colors cursor-pointer ${
                isCompact ? "justify-center" : "justify-between"
              }`}
            >
              <div className="flex items-center gap-2 truncate">
                <Search className="w-3.5 h-3.5 text-[#00CC68] shrink-0" />
                {!isCompact && <span className="text-[11px] truncate">Search or ⌘K</span>}
              </div>
              {!isCompact && (
                <kbd className="px-1.5 py-0.5 text-[10px] bg-zinc-900 border border-zinc-800 rounded-md text-zinc-400">
                  ⌘K
                </kbd>
              )}
            </button>
          </div>

          {/* Navigation Links with Window-Blending Tab Style */}
          <div className="flex-1 my-3 space-y-1.5 overflow-y-auto font-sans">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={isMobile ? onCloseMobile : undefined}
                  className={`flex items-center gap-3.5 px-4 py-3 rounded-2xl text-xs font-semibold transition-all duration-200 ${
                    isActive
                      ? "bg-zinc-950 dark:bg-zinc-950 text-white font-archivo font-black border border-zinc-800 border-r-0 shadow-lg text-[#00CC68]"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
                  } ${isCompact ? "justify-center px-0" : ""}`}
                  title={isCompact ? item.name : undefined}
                >
                  <Icon className={`w-4.5 h-4.5 shrink-0 ${isActive ? "text-[#00CC68]" : "text-zinc-400"}`} />
                  {!isCompact && <span className="tracking-wide uppercase text-[12px]">{item.name}</span>}
                </Link>
              );
            })}
          </div>

          {/* User Footer */}
          <div className="space-y-3 pt-3 border-t border-zinc-800 shrink-0 font-mono">
            {!isCompact && session?.user && (
              <div className="p-2.5 rounded-2xl bg-zinc-950 border border-zinc-800 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5 min-w-0">
                  <Avatar className="w-8 h-8 rounded-full border border-zinc-700 shrink-0">
                    <AvatarImage src={session.user.image || ""} />
                    <AvatarFallback className="bg-[#00CC68] text-black text-[10px] font-bold">
                      {(session.user.name || "U").slice(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 truncate">
                    <p className="text-xs font-bold text-white truncate">{session.user.name || "User"}</p>
                    <p className="text-[10px] text-zinc-400 font-mono truncate">{session.user.email}</p>
                  </div>
                </div>
              </div>
            )}

            <div className={`flex items-center ${isCompact ? "justify-center" : "justify-[#00CC68]"}`}>
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  if (isMobile && onCloseMobile) onCloseMobile();
                  try {
                    await authClient.signOut();
                  } catch {}
                  router.push("/login");
                }}
                className={`text-xs font-mono font-bold text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 cursor-pointer rounded-xl ${
                  isCompact ? "w-9 h-9 p-0 justify-center" : "w-full justify-start"
                }`}
                title="Sign Out"
              >
                <LogOut className="w-3.5 h-3.5 shrink-0" />
                {(!isCompact || isMobile) && <span className="ml-1.5">Sign Out</span>}
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Floating Sidebar Capsule Structure */}
      <aside
        className={`hidden md:flex fixed left-3 top-3 bottom-3 z-30 flex-col rounded-3xl border border-zinc-800 bg-zinc-900 shadow-2xl transition-all duration-300 overflow-hidden ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        {renderContent(false)}
      </aside>

      {/* Mobile Sidebar Capsule */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex animate-in fade-in duration-200">
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" onClick={onCloseMobile} />
          <aside className="relative z-50 my-3 ml-3 w-72 max-w-[85vw] h-[calc(100vh-1.5rem)] rounded-3xl border border-zinc-800 bg-zinc-900 shadow-2xl flex flex-col animate-in slide-in-from-left duration-300 text-zinc-100 overflow-hidden">
            {renderContent(true)}
          </aside>
        </div>
      )}
    </>
  );
}
