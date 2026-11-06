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
      <div className="ob-app fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-ob-bg px-4 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
        <Loader2 className="size-4 animate-spin text-ob-muted" />
        <span className="text-[13px] leading-5 text-ob-text-2">Loading workspace</span>
      </div>
    );
  }

  if (!session?.user) {
    return null;
  }

  return (
    <div className="ob-app relative min-h-dvh bg-ob-bg text-ob-text">
      <DashboardSidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        onCloseMobile={() => setMobileOpen(false)}
        onOpenCommandPalette={() => setCommandOpen(true)}
      />

      <div className={`flex min-h-dvh flex-col pl-0 ${collapsed ? "md:pl-16" : "md:pl-64"}`}>
        <DashboardTopNav onToggleMobileSidebar={() => setMobileOpen(!mobileOpen)} />
        <main className="mx-auto w-full max-w-[1440px] min-w-0 flex-1 px-4 py-8 md:px-8">
          {children}
        </main>
      </div>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
