"use client";

import React from "react";
import { X } from "lucide-react";
import type { MentionRef } from "@/lib/mentions";

interface MentionChipsProps {
  mentions: MentionRef[];
  onRemove: (id: string) => void;
  disabled?: boolean;
}

/** The selections mentioned in the chat message being written: one chip each. */
export function MentionChips({ mentions, onRemove, disabled }: MentionChipsProps) {
  if (mentions.length === 0) return null;

  return (
    <div className="mb-2 flex flex-wrap gap-1">
      {mentions.map((mention) => (
        <div
          key={mention.id}
          title={mention.text.slice(0, 200)}
          className="flex items-center gap-1.5 max-w-full pl-2 pr-1 py-1 rounded-lg border text-[11px] font-mono bg-slate-100 dark:bg-[#141517] border-slate-200 dark:border-[#23252A] text-slate-900 dark:text-[#F7F8F8]"
        >
          <span className="shrink-0 font-semibold text-indigo-600 dark:text-[#5E6AD2]">@</span>
          <span className="truncate font-medium">{mention.label}</span>
          <button
            type="button"
            onClick={() => onRemove(mention.id)}
            disabled={disabled}
            className="p-0.5 shrink-0 text-slate-400 dark:text-[#8A8F98] hover:text-red-500 dark:hover:text-[#EB5757] transition-colors rounded-md cursor-pointer disabled:opacity-40 disabled:cursor-default"
            aria-label={`Remove mention ${mention.label}`}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
