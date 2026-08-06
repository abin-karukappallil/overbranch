"use client";

import React, { useState } from "react";
import { DashboardSidebar } from "@/components/dashboard/Sidebar";
import { DashboardTopNav } from "@/components/dashboard/TopNav";
import { CommandPalette } from "@/components/ui/command-palette";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background relative selection:bg-indigo-500/20 selection:text-indigo-300">
      <div className="fixed inset-0 bg-grid-pattern opacity-30 pointer-events-none -z-20" />
      <div className="fixed inset-0 bg-mesh-dark opacity-50 pointer-events-none -z-10" />

      <DashboardSidebar
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        onOpenCommandPalette={() => setCommandOpen(true)}
      />

      <div
        className={`transition-all duration-300 flex flex-col min-h-screen ${
          collapsed ? "pl-20" : "pl-64"
        }`}
      >
        <DashboardTopNav
          collapsed={collapsed}
          onOpenCommandPalette={() => setCommandOpen(true)}
        />
        <main className="flex-1 p-4 sm:p-8 max-w-7xl mx-auto w-full">
          {children}
        </main>
      </div>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
