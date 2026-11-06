"use client";

import { Button } from "@/components/ui/button";
import { PaperSheet } from "@/components/dashboard/PaperSheet";

interface EmptyStateProps {
  title: string;
  description: string;
  primaryActionLabel?: string;
  onPrimaryAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  className?: string;
}

export function EmptyState({
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
      className={`flex flex-col items-center justify-center rounded-xl border border-ob-line bg-ob-card p-8 text-center sm:p-12 ${className}`}
    >
      <PaperSheet variant="blank" size="sm" className="mb-4" />
      <h3 className="text-[15px] leading-6 font-medium text-ob-text">{title}</h3>
      <p className="mt-1 max-w-sm text-[13px] leading-5 text-ob-text-2">{description}</p>
      {(primaryActionLabel || secondaryActionLabel) && (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {secondaryActionLabel && onSecondaryAction && (
            <Button variant="ob-quiet" size="sm" onClick={onSecondaryAction}>
              {secondaryActionLabel}
            </Button>
          )}
          {primaryActionLabel && onPrimaryAction && (
            <Button variant="ob-primary" size="sm" onClick={onPrimaryAction}>
              {primaryActionLabel}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
