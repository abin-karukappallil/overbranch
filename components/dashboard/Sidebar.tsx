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

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenCommandPalette: () => void;
}

export function DashboardSidebar({ collapsed, onToggleCollapse, onOpenCommandPalette }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const navItems = [
    { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { name: "Projects", href: "/projects", icon: FolderGit2 },
    { name: "Profile", href: "/profile", icon: User },
  ];

  return (
    <aside
      className={`fixed left-0 top-0 bottom-0 z-30 flex flex-col border-r border-border/40 bg-card/60 backdrop-blur-xl transition-all duration-300 ${
        collapsed ? "w-20" : "w-64"
      }`}
    >
      <div className="h-16 px-4 border-b border-border/40 flex items-center justify-between">
        <div className="flex items-center gap-3 overflow-hidden">
          <Link href="/dashboard" className="flex items-center gap-2">
            <OverBranchLogo
              variant={collapsed ? "icon" : "full"}
              size="md"
              colored
            />
          </Link>
        </div>

        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          className="h-8 w-8 text-muted-foreground hover:text-foreground shrink-0"
          title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {collapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        </Button>
      </div>

      <div className="p-3">
        <button
          onClick={onOpenCommandPalette}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-accent text-xs text-muted-foreground transition-all ${
            collapsed ? "justify-center" : "justify-between"
          }`}
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-indigo-400" />
            {!collapsed && <span>Search or Cmd+K</span>}
          </div>
          {!collapsed && (
            <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-background border border-border/40 rounded">
              ⌘K
            </kbd>
          )}
        </button>
      </div>

      <div className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {!collapsed && (
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
              className={`flex items-center gap-3 px-3 py-2 rounded-xl text-xs sm:text-sm font-medium transition-all ${
                isActive
                  ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-semibold"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              } ${collapsed ? "justify-center" : ""}`}
              title={collapsed ? item.name : undefined}
            >
              <Icon className={`w-4 h-4 ${isActive ? "text-indigo-400" : "text-muted-foreground"}`} />
              {!collapsed && <span>{item.name}</span>}
            </Link>
          );
        })}
      </div>

      <div className="p-3 border-t border-border/40 space-y-2">
        <div className={`flex items-center gap-2 ${collapsed ? "justify-center" : "justify-between px-2"}`}>
          <ThemeToggle />
          {!collapsed && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
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
    </aside>
  );
}
