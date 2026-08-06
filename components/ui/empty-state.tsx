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
      className={`flex flex-col items-center justify-center p-12 text-center border border-dashed border-border/70 rounded-2xl bg-card/30 backdrop-blur-sm ${className}`}
    >
      <div className="w-14 h-14 rounded-2xl bg-muted/80 flex items-center justify-center mb-4 text-muted-foreground border border-border/40 shadow-inner">
        <Icon className="w-7 h-7 text-indigo-400" />
      </div>
      <h3 className="text-lg font-semibold text-foreground tracking-tight mb-1">
        {title}
      </h3>
      <p className="text-sm text-muted-foreground max-w-md mb-6 leading-relaxed">
        {description}
      </p>
      <div className="flex items-center gap-3">
        {secondaryActionLabel && onSecondaryAction && (
          <Button variant="outline" size="sm" onClick={onSecondaryAction}>
            {secondaryActionLabel}
          </Button>
        )}
        {primaryActionLabel && onPrimaryAction && (
          <Button size="sm" onClick={onPrimaryAction} className="bg-gradient-to-r from-indigo-600 to-cyan-600 text-white hover:opacity-90">
            {primaryActionLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
