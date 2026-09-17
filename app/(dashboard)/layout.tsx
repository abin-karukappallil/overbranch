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
      <div className="min-h-screen bg-[#F3F4F6] dark:bg-[#0E0F12] flex flex-col items-center justify-center gap-3 text-slate-500 dark:text-[#9E9E9E] font-sans">
        <Loader2 className="w-6 h-6 animate-spin text-emerald-500 dark:text-[#E2E4E9]" />
        <span className="text-xs font-mono font-medium tracking-wider uppercase text-slate-500 dark:text-[#9E9E9E]">Loading workspace...</span>
      </div>
    );
  }

  if (!session?.user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[#F3F4F6] dark:bg-[#0E0F12] text-slate-900 dark:text-[#E2E4E9] relative font-sans selection:bg-emerald-500/20 selection:text-emerald-900 dark:selection:bg-[#22242C] dark:selection:text-[#E2E4E9]">
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
        <main className="flex-1 px-4 py-6 sm:px-8 sm:py-8 max-w-7xl mx-auto w-full min-w-0">
          {children}
        </main>
      </div>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
