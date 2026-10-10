"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { copyText } from "@/lib/clipboard";

interface CopyButtonProps {
  /** The text placed on the clipboard. */
  text: string;
  /** Visible label; omit for an icon-only button. */
  label?: string;
  className?: string;
  title?: string;
}

/**
 * Small "copy this to the clipboard" affordance used on chat messages.
 *
 * Kept deliberately dumb: no toast, no error surface — a failed copy just
 * leaves the icon unchanged, which is the same feedback the browser's own copy
 * affordances give.
 */
export function CopyButton({ text, label, className = "", title }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const ok = await copyText(text);
    if (!ok) return;
    setCopied(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={title ?? (copied ? "Copied" : "Copy message")}
      aria-label={title ?? "Copy message"}
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-mono transition-colors cursor-pointer text-slate-500 hover:text-slate-900 hover:bg-slate-200/70 dark:text-[#8A8F98] dark:hover:text-[#F7F8F8] dark:hover:bg-[#23252A] ${className}`}
    >
      {copied ? (
        <Check className="w-3 h-3 text-emerald-600 dark:text-[#10B981]" />
      ) : (
        <Copy className="w-3 h-3" />
      )}
      {label && <span>{copied ? "Copied" : label}</span>}
    </button>
  );
}
