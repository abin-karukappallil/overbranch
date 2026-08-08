"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Cpu,
  LayoutDashboard,
  Settings,
  Users,
  Search,
  LogOut,
  PanelLeftClose,
  PanelLeft,
  FileCode2,
  BookOpen,
  User,
  CreditCard,
  FolderGit2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
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

export function DashboardSidebar({ collapsed, mobileOpen = false, onToggleCollapse, onCloseMobile, onOpenCommandPalette }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const navItems = [
    { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { name: "Projects", href: "/projects", icon: FolderGit2 },
    { name: "Profile", href: "/profile", icon: User },
  ];

  const renderContent = (isMobile: boolean = false) => (
    <div className="flex flex-col h-full">
      <div className={`h-16 border-b border-border/40 flex items-center ${!isMobile && collapsed ? "justify-center px-2 gap-1.5" : "justify-between px-4"}`}>
        <Link href="/dashboard" onClick={isMobile ? onCloseMobile : undefined} className="flex items-center gap-2 shrink-0">
          <OverBranchLogo
            variant={!isMobile && collapsed ? "icon" : "full"}
            size={!isMobile && collapsed ? "sm" : "md"}
            colored
          />
        </Link>

        {isMobile ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={onCloseMobile}
            className="h-8 w-8 text-muted-foreground hover:text-foreground shrink-0"
          >
            <PanelLeftClose className="w-4 h-4" />
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleCollapse}
            className={`${collapsed ? "h-7 w-7" : "h-8 w-8"} text-muted-foreground hover:text-foreground shrink-0`}
            title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
          >
            {collapsed ? <PanelLeft className="w-3.5 h-3.5" /> : <PanelLeftClose className="w-4 h-4" />}
          </Button>
        )}
      </div>

      <div className="p-3">
        <button
          onClick={() => {
            if (isMobile && onCloseMobile) onCloseMobile();
            onOpenCommandPalette();
          }}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-accent text-xs text-muted-foreground transition-all ${
            !isMobile && collapsed ? "justify-center" : "justify-between"
          }`}
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-indigo-400" />
            {(isMobile || !collapsed) && <span>Search or Cmd+K</span>}
          </div>
          {(isMobile || !collapsed) && (
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-background border border-border/40 rounded">
              ⌘K
            </kbd>
          )}
        </button>
      </div>

      <div className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {(isMobile || !collapsed) && (
          <div className="px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
            Workspace Nav
          </div>
        )}
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={isMobile ? onCloseMobile : undefined}
              className={`flex items-center gap-3 px-3 py-2.5 sm:py-2 rounded-xl text-xs sm:text-sm font-medium transition-all ${
                isActive
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-semibold"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              } ${!isMobile && collapsed ? "justify-center" : ""}`}
              title={!isMobile && collapsed ? item.name : undefined}
            >
              <Icon className={`w-4 h-4 ${isActive ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`} />
              {(isMobile || !collapsed) && <span>{item.name}</span>}
            </Link>
          );
        })}
      </div>

      <div className="p-3 border-t border-border/40 space-y-2">
        <div className={`flex items-center gap-2 ${!isMobile && collapsed ? "justify-center" : "justify-between px-2"}`}>
          <ThemeToggle />
          {(isMobile || !collapsed) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                if (isMobile && onCloseMobile) onCloseMobile();
                try {
                  await authClient.signOut();
                } catch {}
                toast.info("Signed out of session");
                router.push("/login");
              }}
              className="text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
            >
              <LogOut className="w-3.5 h-3.5 mr-1.5" />
              Sign Out
            </Button>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar (Hidden on mobile) */}
      <aside
        className={`hidden md:flex fixed left-0 top-0 bottom-0 z-30 flex-col border-r border-border/40 bg-card/60 backdrop-blur-xl transition-all duration-300 ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        {renderContent(false)}
      </aside>

      {/* Mobile Drawer (Visible on mobile when open) */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex animate-in fade-in duration-200">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm"
            onClick={onCloseMobile}
          />
          <aside className="relative z-50 w-72 max-w-[85vw] h-full bg-card border-r border-border shadow-2xl flex flex-col animate-in slide-in-from-left duration-300">
            {renderContent(true)}
          </aside>
        </div>
      )}
    </>
  );
}
