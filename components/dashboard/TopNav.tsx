"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { ChevronRight, Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { NotificationsPopover } from "@/components/dashboard/NotificationsPopover";
import { UserProfileDropdown } from "@/components/dashboard/UserProfileDropdown";

interface TopNavProps {
  onToggleMobileSidebar?: () => void;
}

// The sidebar calls /dashboard "Overview"; the breadcrumb says the same thing.
const SEGMENT_LABELS: Record<string, string> = { dashboard: "Overview" };

export function DashboardTopNav({ onToggleMobileSidebar }: TopNavProps) {
  const pathname = usePathname();
  const pathSegments = pathname.split("/").filter(Boolean);

  return (
    <header className="sticky top-0 z-20 flex h-14 min-w-0 items-center justify-between border-b border-ob-line bg-ob-bg px-4 md:px-8">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {onToggleMobileSidebar && (
          <Button
            variant="ob-quiet"
            size="icon-sm"
            onClick={onToggleMobileSidebar}
            aria-label="Open navigation"
            className="-ml-2 md:hidden"
          >
            <Menu className="size-4" />
          </Button>
        )}
        <span className="md:hidden">
          <OverBranchLogo
            variant="text"
            size="sm"
            animated={false}
            textClassName="font-normal! tracking-normal! text-sm!"
          />
        </span>
        <div className="hidden min-w-0 items-center gap-1.5 text-[13px] leading-5 text-ob-text-2 md:flex">
          {pathSegments.map((segment, index) => (
            <React.Fragment key={segment}>
              {index > 0 && <ChevronRight className="size-4 shrink-0 text-ob-muted" />}
              <span className="min-w-0 truncate capitalize">{SEGMENT_LABELS[segment] ?? segment}</span>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <a
          href="https://github.com/abin-karukappallil/overbranch/issues"
          target="_blank"
          rel="noopener noreferrer"
          className="hidden h-8 items-center rounded-lg px-2 text-[13px] text-ob-text-2 transition-colors hover:bg-ob-raised hover:text-ob-text md:flex"
          title="Report a bug on GitHub Issues"
        >
          Feedback
        </a>
        <NotificationsPopover />
        <UserProfileDropdown />
      </div>
    </header>
  );
}
