"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, ChevronRight, Sparkles, Terminal, Menu, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NotificationsPopover } from "@/components/dashboard/NotificationsPopover";
import { UserProfileDropdown } from "@/components/dashboard/UserProfileDropdown";
import { ThemeToggle } from "@/components/ui/theme-toggle";

interface TopNavProps {
  onOpenCommandPalette: () => void;
  collapsed: boolean;
  onToggleMobileSidebar?: () => void;
}

export function DashboardTopNav({ onOpenCommandPalette, collapsed, onToggleMobileSidebar }: TopNavProps) {
  const pathname = usePathname();

  const pathSegments = pathname.split("/").filter(Boolean);

  return (
    <header className="h-16 border-b border-border/40 bg-card/40 backdrop-blur-xl px-4 sm:px-6 flex items-center justify-between sticky top-0 z-20 transition-all">
      <div className="flex items-center gap-2">
        {onToggleMobileSidebar && (
          <Button variant="ghost" size="icon" onClick={onToggleMobileSidebar} className="md:hidden h-9 w-9">
            <Menu className="w-5 h-5 text-muted-foreground" />
          </Button>
        )}
        <div className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
          <Link href="/dashboard" className="hover:text-foreground transition-colors flex items-center gap-1">
            <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            <span>overbranch</span>
          </Link>
          {pathSegments.map((segment, index) => (
            <React.Fragment key={segment}>
              <ChevronRight className="w-3 h-3 text-border" />
              <span
                className={
                  index === pathSegments.length - 1
                    ? "text-foreground font-semibold uppercase tracking-wider"
                    : "hover:text-foreground transition-colors"
                }
              >
                {segment}
              </span>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onOpenCommandPalette}
          className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border/60 bg-muted/40 hover:bg-accent text-xs text-muted-foreground transition-colors"
        >
          <Search className="w-3.5 h-3.5 text-indigo-400" />
          <span>Cmd+K</span>
        </button>

        <NotificationsPopover />
        <ThemeToggle />
        <div className="w-[1px] h-6 bg-border/40 mx-1 hidden sm:block" />
        <UserProfileDropdown />
      </div>
    </header>
  );
}
