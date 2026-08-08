"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, ChevronRight, Menu, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NotificationsPopover } from "@/components/dashboard/NotificationsPopover";
import { UserProfileDropdown } from "@/components/dashboard/UserProfileDropdown";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

interface TopNavProps {
  onOpenCommandPalette: () => void;
  collapsed: boolean;
  onToggleMobileSidebar?: () => void;
}

export function DashboardTopNav({ onOpenCommandPalette, collapsed, onToggleMobileSidebar }: TopNavProps) {
  const pathname = usePathname();
  const pathSegments = pathname.split("/").filter(Boolean);

  return (
    <header className="h-14 border-b border-border/40 bg-card/30 backdrop-blur-md px-4 sm:px-6 md:px-8 flex items-center justify-between sticky top-0 z-20 min-w-0">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        {onToggleMobileSidebar && (
          <Button variant="ghost" size="icon" onClick={onToggleMobileSidebar} className="md:hidden h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground">
            <Menu className="w-4.5 h-4.5" />
          </Button>
        )}
        <div className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground min-w-0 truncate">
          <Link href="/dashboard" className="hover:text-foreground transition-colors font-bold text-foreground shrink-0">
            OverBranch
          </Link>
          {pathSegments.map((segment, index) => (
            <React.Fragment key={segment}>
              <ChevronRight className="w-3 h-3 text-border shrink-0" />
              <span className={`capitalize truncate min-w-0 ${index === pathSegments.length - 1 ? "text-foreground font-medium" : "hover:text-foreground"}`}>
                {segment}
              </span>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onOpenCommandPalette}
          className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border/40 bg-background/50 hover:bg-accent text-[11px] text-muted-foreground transition-colors"
        >
          <Search className="w-3 h-3 text-indigo-400" />
          <span>⌘K</span>
        </button>

        <NotificationsPopover />
        <ThemeToggle />
        <div className="w-[1px] h-5 bg-border/40 mx-1 hidden sm:block" />
        <UserProfileDropdown />
      </div>
    </header>
  );
}
