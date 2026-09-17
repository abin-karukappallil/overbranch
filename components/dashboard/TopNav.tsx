"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, ChevronRight, Menu, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { NotificationsPopover } from "@/components/dashboard/NotificationsPopover";
import { UserProfileDropdown } from "@/components/dashboard/UserProfileDropdown";

interface TopNavProps {
  onOpenCommandPalette: () => void;
  collapsed: boolean;
  onToggleMobileSidebar?: () => void;
}

export function DashboardTopNav({ onOpenCommandPalette, collapsed, onToggleMobileSidebar }: TopNavProps) {
  const pathname = usePathname();
  const pathSegments = pathname.split("/").filter(Boolean);
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = mounted && (resolvedTheme === "dark" || theme === "dark");

  return (
    <header className="h-14 border-b border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] px-4 sm:px-8 flex items-center justify-between sticky top-0 z-20 min-w-0 transition-colors">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        {onToggleMobileSidebar && (
          <Button variant="ghost" size="icon" onClick={onToggleMobileSidebar} className="md:hidden h-8 w-8 shrink-0 text-slate-500 hover:text-slate-900 dark:text-[#9E9E9E] dark:hover:text-[#E2E4E9] hover:bg-slate-100 dark:hover:bg-[#1E2026]">
            <Menu className="w-4 h-4" />
          </Button>
        )}
        <div className="flex items-center gap-1.5 text-xs font-mono text-slate-500 dark:text-[#9E9E9E] min-w-0 truncate">
          <Link href="/dashboard" className="hover:text-slate-900 dark:hover:text-[#E2E4E9] transition-colors font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] shrink-0 flex items-center gap-1.5">
            <span>OverBranch</span>
            <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#1E2026] text-slate-700 dark:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30] tracking-wider">
              BETA
            </span>
          </Link>
          {pathSegments.map((segment, index) => (
            <React.Fragment key={segment}>
              <ChevronRight className="w-3 h-3 text-slate-400 dark:text-[#62666D] shrink-0" />
              <span className={`capitalize truncate min-w-0 font-sans ${index === pathSegments.length - 1 ? "text-slate-900 dark:text-[#E2E4E9] font-semibold" : "hover:text-slate-900 dark:hover:text-[#E2E4E9]"}`}>
                {segment}
              </span>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-2.5">
        <a
          href="https://github.com/abin-karukappallil/overbranch/issues"
          target="_blank"
          rel="noopener noreferrer"
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] hover:bg-slate-200 dark:hover:bg-[#22242C] text-[11px] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] font-mono transition-colors"
          title="Report any bugs on GitHub Issues"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#FF8849]" />
          <span>Feedback</span>
        </a>

        <button
          onClick={onOpenCommandPalette}
          className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] hover:bg-slate-200 dark:hover:bg-[#22242C] text-[11px] text-slate-600 dark:text-[#9E9E9E] font-mono transition-colors cursor-pointer"
        >
          <Search className="w-3 h-3 text-slate-400 dark:text-[#9E9E9E]" />
          <span>⌘K</span>
        </button>

        {/* Theme Switcher Button */}
        <button
          onClick={() => setTheme(isDark ? "light" : "dark")}
          className="p-1.5 rounded-md border border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] hover:bg-slate-200 dark:hover:bg-[#22242C] text-slate-700 dark:text-[#E2E4E9] transition-colors cursor-pointer flex items-center justify-center h-8 w-8 shrink-0"
          title={isDark ? "Switch to Light Theme" : "Switch to Dark Theme"}
          aria-label="Toggle Theme"
        >
          {mounted ? (
            isDark ? (
              <Sun className="w-3.5 h-3.5 text-amber-400 transition-transform duration-200 hover:rotate-45" />
            ) : (
              <Moon className="w-3.5 h-3.5 text-slate-700 transition-transform duration-200 hover:-rotate-12" />
            )
          ) : (
            <div className="w-3.5 h-3.5 rounded-full border border-current opacity-30" />
          )}
        </button>

        <NotificationsPopover />
        <div className="w-[1px] h-4 bg-slate-200 dark:bg-[#282A30] mx-0.5 hidden sm:block" />
        <UserProfileDropdown />
      </div>
    </header>
  );
}
