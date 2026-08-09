"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { DashboardSidebar } from "@/components/dashboard/Sidebar";
import { DashboardTopNav } from "@/components/dashboard/TopNav";
import { CommandPalette } from "@/components/ui/command-palette";
import { authClient } from "@/lib/auth-client";
import { Loader2 } from "lucide-react";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: session, isPending } = authClient.useSession();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);

  useEffect(() => {
    if (!isPending && !session?.user) {
      router.replace("/login");
    }
  }, [isPending, session, router]);

  if (isPending) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-3 text-muted-foreground">
        <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
        <span className="text-xs font-mono">Verifying workspace session...</span>
      </div>
    );
  }

  if (!session?.user) {
    return null;
  }

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
