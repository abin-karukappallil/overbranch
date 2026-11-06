"use client";

import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-md bg-ob-raised", className)} {...props} />;
}

/** Same frame as a project card on /dashboard, with an unprinted sheet where the sketch goes. */
export function ProjectCardSkeleton() {
  return (
    <div className="flex flex-row overflow-hidden rounded-xl border border-ob-line bg-ob-card sm:flex-col">
      <div className="flex w-28 shrink-0 items-center justify-center border-r border-ob-line bg-ob-deep sm:h-48 sm:w-auto sm:border-r-0 sm:border-b">
        <div className="h-20 w-14 rounded-[1px] bg-ob-raised sm:h-[136px] sm:w-24" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2 p-4">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="mt-4 h-3 w-1/3" />
      </div>
    </div>
  );
}

export function DashboardStatsSkeleton() {
  return (
    <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex flex-col gap-3 rounded-xl border border-ob-line bg-ob-card p-5">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-20" />
          <Skeleton className="h-3 w-32" />
        </div>
      ))}
    </div>
  );
}

/** Full editor workbench skeleton: header, files panel, code editor, PDF sheet and chat panel. */
export function EditorSkeleton({ label = "Verifying project access" }: { label?: string }) {
  return (
    <div className="ob-app fixed inset-0 flex h-dvh w-full max-w-full flex-col overflow-hidden bg-ob-bg text-ob-text select-none">
      {/* Header */}
      <header className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-ob-line bg-ob-deep px-3 sm:px-4">
        {/* Left: return + title */}
        <div className="flex items-center gap-2 sm:gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div className="hidden h-4 w-px bg-ob-line sm:block" />
          <div className="flex flex-col gap-1">
            <Skeleton className="h-3.5 w-28 rounded" />
            <Skeleton className="h-2.5 w-16 rounded opacity-60" />
          </div>
        </div>

        {/* Center: view toggle + compile */}
        <div className="hidden items-center gap-2 xl:flex">
          <Skeleton className="h-7 w-24 rounded-lg" />
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>

        {/* Right: status & actions */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          <Skeleton className="hidden h-8 w-16 rounded-lg xl:block" />
          <Skeleton className="hidden h-8 w-16 rounded-lg xl:block" />
          <Skeleton className="size-8 rounded-lg" />
          <Skeleton className="size-8 rounded-lg" />
        </div>
      </header>

      {/* Main workspace */}
      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Files panel */}
        <aside className="hidden w-52 flex-col gap-2 border-r border-ob-line bg-ob-deep p-3 lg:flex xl:w-60">
          <div className="flex items-center justify-between pb-2 border-b border-ob-line">
            <Skeleton className="h-3 w-16 rounded" />
            <Skeleton className="h-3 w-6 rounded" />
          </div>
          <Skeleton className="h-7 w-full rounded-md" />
          <div className="flex flex-col gap-1.5 pt-2">
            {[80, 60, 75, 45, 90, 55, 70].map((width, idx) => (
              <div key={idx} className="flex items-center gap-2 py-1 px-1.5">
                <Skeleton className="size-3.5 rounded shrink-0 opacity-70" />
                <Skeleton className="h-3 rounded" style={{ width: `${width}%` }} />
              </div>
            ))}
          </div>
        </aside>

        {/* Monaco code editor area */}
        <section className="flex flex-1 flex-col border-r border-ob-line bg-ob-bg min-w-0">
          {/* Tab bar */}
          <div className="flex h-9 shrink-0 items-center justify-between border-b border-ob-line bg-ob-deep px-3">
            <Skeleton className="h-3.5 w-24 rounded" />
            <div className="flex items-center gap-1">
              <Skeleton className="size-5 rounded" />
              <Skeleton className="size-5 rounded" />
            </div>
          </div>
          {/* Editor lines */}
          <div className="flex flex-1 overflow-hidden p-4 font-mono">
            <div className="flex flex-col gap-2.5 pr-4 border-r border-ob-line/40 shrink-0 select-none">
              {Array.from({ length: 18 }).map((_, i) => (
                <span key={i} className="text-[11px] text-ob-muted/30 tabular-nums">
                  {i + 1}
                </span>
              ))}
            </div>
            <div className="flex flex-1 flex-col gap-2.5 pl-4">
              {[35, 60, 48, 20, 75, 52, 40, 65, 30, 85, 45, 25, 70, 50, 40, 60, 30, 20].map(
                (w, i) => (
                  <Skeleton
                    key={i}
                    className="h-3 rounded"
                    style={{ width: `${w}%`, opacity: 0.35 + (w % 40) / 100 }}
                  />
                )
              )}
            </div>
          </div>
        </section>

        {/* PDF preview pane */}
        <section className="hidden flex-1 items-center justify-center bg-ob-deep p-6 sm:flex relative min-w-0">
          <div className="flex h-[82%] max-h-[640px] aspect-[1/1.414] flex-col rounded-[2px] border border-ob-line bg-ob-card p-8 shadow-sm">
            <Skeleton className="mx-auto mb-4 h-4 w-1/2 rounded" />
            <Skeleton className="mx-auto mb-8 h-2.5 w-1/4 rounded opacity-60" />
            <div className="space-y-2">
              <Skeleton className="h-2.5 w-full rounded opacity-70" />
              <Skeleton className="h-2.5 w-full rounded opacity-70" />
              <Skeleton className="h-2.5 w-5/6 rounded opacity-70" />
            </div>
            <div className="mt-6 space-y-2">
              <Skeleton className="h-3 w-1/3 rounded" />
              <Skeleton className="h-2.5 w-full rounded opacity-70" />
              <Skeleton className="h-2.5 w-full rounded opacity-70" />
              <Skeleton className="h-2.5 w-4/5 rounded opacity-70" />
            </div>
            <div className="mt-auto flex justify-center">
              <Skeleton className="h-2.5 w-6 rounded opacity-50" />
            </div>
          </div>
        </section>

        {/* AI Agent sidebar */}
        <aside className="hidden w-[300px] flex-col justify-between border-l border-ob-line bg-ob-deep p-3 xl:flex">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2.5 border-b border-ob-line">
              <Skeleton className="h-3.5 w-20 rounded" />
              <Skeleton className="h-7 w-28 rounded-lg" />
            </div>
            <div className="space-y-3 pt-2">
              <div className="mr-4 rounded-xl border border-ob-line bg-ob-raised p-3 space-y-2">
                <Skeleton className="h-3 w-24 rounded" />
                <Skeleton className="h-2.5 w-full rounded opacity-70" />
                <Skeleton className="h-2.5 w-3/4 rounded opacity-70" />
              </div>
            </div>
          </div>
          <Skeleton className="h-9 w-full rounded-lg" />
        </aside>
      </div>

      {/* Quiet bottom status tag */}
      <div className="fixed bottom-3 left-3 z-50 flex items-center gap-2 rounded-lg border border-ob-line bg-ob-card/90 px-2.5 py-1 text-xs text-ob-muted shadow-sm backdrop-blur-sm">
        <span className="size-1.5 rounded-full bg-ob-accent animate-pulse" />
        <span className="font-mono text-[11px] text-ob-text-2">{label}</span>
      </div>
    </div>
  );
}
