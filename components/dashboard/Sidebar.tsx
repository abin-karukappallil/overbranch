"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderGit2,
  Presentation,
  User,
  Search,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

interface SidebarProps {
  collapsed: boolean;
  mobileOpen?: boolean;
  onToggleCollapse: () => void;
  onCloseMobile?: () => void;
  onOpenCommandPalette: () => void;
}

const navItems = [
  { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { name: "Projects", href: "/projects", icon: FolderGit2 },
  { name: "Templates", href: "/templates", icon: Presentation },
  { name: "Profile", href: "/profile", icon: User },
];

export function DashboardSidebar({
  collapsed,
  mobileOpen = false,
  onToggleCollapse,
  onCloseMobile,
  onOpenCommandPalette,
}: SidebarProps) {
  const pathname = usePathname();

  const renderContent = (isMobile: boolean = false) => {
    const isCompact = !isMobile && collapsed;

    return (
      <div className="flex h-full flex-col bg-ob-deep text-ob-text select-none">
        {/* Logo row lines up with the top bar */}
        <div className={`flex h-14 shrink-0 items-center px-4 ${isCompact ? "justify-center px-0" : "justify-between"}`}>
          {!isCompact && (
            <Link
              href="/dashboard"
              onClick={isMobile ? onCloseMobile : undefined}
              className="flex min-w-0 items-center gap-2 rounded-md"
            >
              <OverBranchLogo
                variant="full"
                size="sm"
                colored={false}
                animated={false}
                iconClassName="[&_svg]:text-ob-accent!"
                textClassName="font-normal! tracking-normal! text-sm!"
              />
              <span className="font-mono text-xs text-ob-muted">Beta</span>
            </Link>
          )}

          {!isMobile && (
            <button
              onClick={onToggleCollapse}
              className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
            </button>
          )}
        </div>

        {/* New project and search */}
        <div className="flex shrink-0 flex-col gap-2 px-3 pt-2">
          <Link
            href="/projects"
            onClick={isMobile ? onCloseMobile : undefined}
            title={isCompact ? "New project" : undefined}
            className={buttonVariants({ variant: "ob-secondary", className: "w-full" })}
          >
            <Plus className="size-4 text-ob-text-2" />
            {!isCompact && <span>New project</span>}
          </Link>

          <button
            onClick={() => {
              if (isMobile && onCloseMobile) onCloseMobile();
              onOpenCommandPalette();
            }}
            className={`flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 text-sm text-ob-text-2 transition-colors hover:bg-ob-raised hover:text-ob-text ${
              isCompact ? "justify-center px-0" : ""
            }`}
            title={isCompact ? "Search" : undefined}
            aria-label="Search"
          >
            <Search className="size-4 shrink-0 text-ob-muted" />
            {!isCompact && (
              <>
                <span className="flex-1 truncate text-left">Search</span>
                <kbd className="rounded-sm border border-ob-line px-1 font-mono text-xs leading-[18px] text-ob-muted">⌘K</kbd>
              </>
            )}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 pt-4">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={isMobile ? onCloseMobile : undefined}
                aria-current={isActive ? "page" : undefined}
                className={`flex h-9 shrink-0 items-center gap-2.5 rounded-lg px-3 text-sm transition-colors ${
                  isActive
                    ? "bg-ob-raised font-medium text-ob-text"
                    : "text-ob-text-2 hover:bg-ob-raised/60 hover:text-ob-text"
                } ${isCompact ? "justify-center px-0" : ""}`}
                title={isCompact ? item.name : undefined}
              >
                <Icon className={`size-4 shrink-0 ${isActive ? "text-ob-accent" : "text-ob-muted"}`} />
                {!isCompact && <span>{item.name}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Sponsor, as quiet text */}
        {!isCompact && (
          <div className="shrink-0 px-6 py-4">
            <a
              href="https://upzare.com"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-sm text-xs text-ob-muted transition-colors hover:text-ob-text-2"
              title="Powered by UPZARE Technologies Private Limited"
            >
              Powered by UPZARE
            </a>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-30 hidden flex-col overflow-hidden border-r border-ob-line bg-ob-deep md:flex ${
          collapsed ? "w-16" : "w-64"
        }`}
      >
        {renderContent(false)}
      </aside>

      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex animate-in fade-in duration-200 md:hidden">
          <div className="fixed inset-0 bg-black/60" onClick={onCloseMobile} />
          <aside className="relative z-50 flex h-full w-72 max-w-[85vw] flex-col overflow-hidden border-r border-ob-line bg-ob-deep text-ob-text animate-in slide-in-from-left duration-300">
            {renderContent(true)}
          </aside>
        </div>
      )}
    </>
  );
}
