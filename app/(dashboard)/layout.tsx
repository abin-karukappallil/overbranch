"use client";

import React, { useState } from "react";
import { DashboardSidebar } from "@/components/dashboard/Sidebar";
import { DashboardTopNav } from "@/components/dashboard/TopNav";
import { CommandPalette } from "@/components/ui/command-palette";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background relative selection:bg-indigo-500/20 selection:text-indigo-300">
      <div className="fixed inset-0 bg-grid-pattern opacity-30 pointer-events-none -z-20" />
      <div className="fixed inset-0 bg-mesh-dark opacity-50 pointer-events-none -z-10" />

      <DashboardSidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        onCloseMobile={() => setMobileOpen(false)}
        onOpenCommandPalette={() => setCommandOpen(true)}
      />

      <div
        className={`transition-all duration-300 flex flex-col min-h-screen pl-0 ${
          collapsed ? "md:pl-20" : "md:pl-64"
        }`}
      >
        <DashboardTopNav
          collapsed={collapsed}
          onOpenCommandPalette={() => setCommandOpen(true)}
          onToggleMobileSidebar={() => setMobileOpen(!mobileOpen)}
        />
        <main className="flex-1 px-4 py-5 sm:p-6 md:p-8 max-w-7xl mx-auto w-full min-w-0">
          {children}
        </main>
      </div>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
