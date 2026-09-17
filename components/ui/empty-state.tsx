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
      className={`flex flex-col items-center justify-center p-8 sm:p-12 text-center border border-dashed border-[#23252A] rounded-xl bg-[#0F1011] font-sans ${className}`}
    >
      <div className="w-12 h-12 rounded-xl bg-[#141517] flex items-center justify-center mb-3 text-[#5E6AD2] border border-[#23252A]">
        <Icon className="w-5 h-5 text-[#5E6AD2]" />
      </div>
      <h3 className="text-sm sm:text-base font-semibold text-[#F7F8F8] tracking-tight mb-1.5">
        {title}
      </h3>
      <p className="text-xs text-[#8A8F98] max-w-sm mb-5 leading-relaxed font-sans">
        {description}
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2.5">
        {secondaryActionLabel && onSecondaryAction && (
          <Button
            variant="outline"
            size="sm"
            onClick={onSecondaryAction}
            className="h-8 px-3.5 border-[#23252A] bg-[#141517] text-[#8A8F98] hover:text-[#F7F8F8] hover:bg-[#18191B] font-medium rounded-lg text-xs cursor-pointer"
          >
            {secondaryActionLabel}
          </Button>
        )}
        {primaryActionLabel && onPrimaryAction && (
          <Button
            size="sm"
            onClick={onPrimaryAction}
            className="h-8 px-4 bg-[#5E6AD2] hover:bg-[#4F5BBE] text-white font-medium rounded-lg text-xs cursor-pointer shadow-sm"
          >
            {primaryActionLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
