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
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
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
      <div className="flex flex-col h-full font-sans select-none bg-white dark:bg-[#141519] text-slate-900 dark:text-[#E2E4E9] transition-colors">
        {/* Sidebar Header with Classic OverBranch Logo */}
        <div
          className={`h-16 px-4 border-b border-slate-200 dark:border-[#282A30] flex items-center shrink-0 ${
            isCompact ? "justify-center" : "justify-between"
          }`}
        >
          <Link
            href="/dashboard"
            onClick={isMobile ? onCloseMobile : undefined}
            className="flex items-center gap-2 shrink-0 group"
          >
            <OverBranchLogo
              variant={isCompact ? "icon" : "full"}
              size={isCompact ? "sm" : "md"}
              colored
            />
            {!isCompact && (
              <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#1E2026] text-slate-700 dark:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30] tracking-wider">
                BETA
              </span>
            )}
          </Link>

          {!isMobile && (
            <button
              onClick={onToggleCollapse}
              className="p-1.5 rounded-md text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] hover:bg-slate-100 dark:hover:bg-[#1E2026] transition-colors shrink-0 cursor-pointer"
              title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
            >
              {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>

        {/* Action Button & Search */}
        <div className="p-3 space-y-2 shrink-0">
          <Link
            href="/projects"
            onClick={isMobile ? onCloseMobile : undefined}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] border border-emerald-600 dark:border-[#282A30] text-white dark:text-[#E2E4E9] font-archivo font-bold text-xs tracking-wide transition-colors cursor-pointer shadow-sm ${
              isCompact ? "justify-center" : "justify-center"
            }`}
          >
            <Plus className="w-4 h-4 text-white dark:text-[#E2E4E9] stroke-[2.5] shrink-0" />
            {!isCompact && <span>New Project</span>}
          </Link>

          <button
            onClick={() => {
              if (isMobile && onCloseMobile) onCloseMobile();
              onOpenCommandPalette();
            }}
            className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] hover:border-slate-300 dark:hover:border-[#383B46] text-xs text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] transition-colors cursor-pointer ${
              isCompact ? "justify-center" : "justify-between"
            }`}
            title="Search or ⌘K"
          >
            <div className="flex items-center gap-2 truncate">
              <Search className="w-3.5 h-3.5 text-slate-400 dark:text-[#9E9E9E] shrink-0" />
              {!isCompact && <span className="text-[11px] truncate font-mono">Search...</span>}
            </div>
            {!isCompact && (
              <kbd className="px-1.5 py-0.5 text-[9px] font-mono bg-white dark:bg-[#141519] border border-slate-200 dark:border-[#282A30] rounded text-slate-500 dark:text-[#9E9E9E]">
                ⌘K
              </kbd>
            )}
          </button>
        </div>

        {/* Navigation Items */}
        <div className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={isMobile ? onCloseMobile : undefined}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-slate-100 dark:bg-[#22242C] text-emerald-700 dark:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30] font-archivo font-bold"
                    : "text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] hover:bg-slate-100 dark:hover:bg-[#1E2026]"
                } ${isCompact ? "justify-center px-0" : ""}`}
                title={isCompact ? item.name : undefined}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-emerald-600 dark:text-[#E2E4E9]" : "text-slate-400 dark:text-[#9E9E9E]"}`} />
                {!isCompact && <span>{item.name}</span>}
              </Link>
            );
          })}
        </div>

        {/* User Profile Footer & Sponsor */}
        <div className="p-3 pb-4 border-t border-slate-200 dark:border-[#282A30] shrink-0 space-y-2">
          {/* UPZARE Sponsor Badge */}
          <a
            href="https://upzare.com"
            target="_blank"
            rel="noopener noreferrer"
            className={`flex items-center gap-2 p-2 rounded-lg bg-slate-50 hover:bg-slate-100 dark:bg-[#1E2026] dark:hover:bg-[#282A30] border border-slate-200 dark:border-[#282A30] transition-colors group ${
              isCompact ? "justify-center" : ""
            }`}
            title="Powered By UPZARE Technologies Private Limited"
          >
            <img
              src="https://cdn.upzare.com/assets/logo.png"
              alt="UPZARE Technologies Private Limited"
              className="h-4 w-auto object-contain shrink-0"
            />
            {(!isCompact || isMobile) && (
              <div className="min-w-0 truncate">
                <span className="text-[9px] font-mono text-slate-500 dark:text-[#9E9E9E] block leading-none uppercase">
                  Powered By
                </span>
                <span className="text-[11px] font-mono font-bold text-slate-800 dark:text-[#E2E4E9] group-hover:text-emerald-600 dark:group-hover:text-emerald-400 truncate block">
                  UPZARE Technologies
                </span>
              </div>
            )}
          </a>

          {!isCompact && session?.user && (
            <div className="p-2 rounded-lg bg-slate-50 dark:bg-[#1E2026] border border-slate-200 dark:border-[#282A30] flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Avatar className="w-7 h-7 rounded-md border border-slate-200 dark:border-[#282A30] shrink-0">
                  <AvatarImage src={session.user.image || ""} />
                  <AvatarFallback className="bg-emerald-600 dark:bg-[#22242C] text-white text-[10px] font-bold">
                    {(session.user.name || "U").slice(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 truncate">
                  <p className="text-xs font-semibold text-slate-800 dark:text-[#E2E4E9] truncate font-sans">{session.user.name || "User"}</p>
                  <p className="text-[10px] text-slate-500 dark:text-[#9E9E9E] font-mono truncate">{session.user.email}</p>
                </div>
              </div>
            </div>
          )}

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
            className={`text-xs text-slate-600 dark:text-[#9E9E9E] hover:text-red-600 dark:hover:text-[#FF8585] hover:bg-red-50 dark:hover:bg-[#FF8585]/10 cursor-pointer rounded-lg h-8 transition-colors ${
              isCompact ? "w-9 p-0 justify-center mx-auto flex" : "w-full justify-start"
            }`}
            title="Sign Out"
          >
            <LogOut className="w-3.5 h-3.5 shrink-0" />
            {(!isCompact || isMobile) && <span className="ml-2 text-xs font-mono font-medium">Sign Out</span>}
          </Button>
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        className={`hidden md:flex fixed left-0 top-0 bottom-0 z-30 flex-col border-r border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] transition-all duration-300 overflow-hidden ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        {renderContent(false)}
      </aside>

      {/* Mobile Sidebar */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex animate-in fade-in duration-200">
          <div className="fixed inset-0 bg-black/60 dark:bg-black/80" onClick={onCloseMobile} />
          <aside className="relative z-50 w-72 max-w-[85vw] h-full border-r border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] shadow-2xl flex flex-col animate-in slide-in-from-left duration-300 text-slate-900 dark:text-[#E2E4E9] overflow-hidden">
            {renderContent(true)}
          </aside>
        </div>
      )}
    </>
  );
}
