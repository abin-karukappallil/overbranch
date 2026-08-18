"use client";

import { LucideIcon, FolderPlus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  primaryActionLabel?: string;
  onPrimaryAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  className?: string;
}

export function EmptyState({
  icon: Icon = FolderPlus,
  title,
  description,
  primaryActionLabel,
  onPrimaryAction,
  secondaryActionLabel,
  onSecondaryAction,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-10 sm:p-14 text-center border border-dashed border-zinc-800 rounded-3xl bg-zinc-950/60 font-sans ${className}`}
    >
      <div className="w-14 h-14 rounded-2xl bg-zinc-900 flex items-center justify-center mb-4 text-[#00CC68] border border-zinc-800 shadow-xl">
        <Icon className="w-7 h-7 text-[#00CC68]" />
      </div>
      <h3 className="text-lg sm:text-xl font-archivo font-bold text-white tracking-tight uppercase mb-2">
        {title}
      </h3>
      <p className="text-xs sm:text-sm text-zinc-400 max-w-md mb-6 leading-relaxed font-sans">
        {description}
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        {secondaryActionLabel && onSecondaryAction && (
          <Button
            variant="outline"
            size="sm"
            onClick={onSecondaryAction}
            className="h-10 px-5 border-zinc-800 bg-zinc-900 text-zinc-300 hover:text-white font-mono font-bold rounded-xl cursor-pointer"
          >
            {secondaryActionLabel}
          </Button>
        )}
        {primaryActionLabel && onPrimaryAction && (
          <Button
            size="sm"
            onClick={onPrimaryAction}
            className="h-10 px-6 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider border border-black shadow-[3px_3px_0px_0px_#000000] rounded-xl cursor-pointer transition-all"
          >
            {primaryActionLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
