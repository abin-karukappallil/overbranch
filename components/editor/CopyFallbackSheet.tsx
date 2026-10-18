"use client";

import React, { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

interface CopyFallbackSheetProps {
  /** The text to copy by hand. The sheet renders nothing while this is null. */
  text: string | null;
  onClose: () => void;
  /** Accessible name for the textarea. */
  label?: string;
}

/**
 * Manual copy sheet: shown when every programmatic copy path failed, so the
 * user can still finish the copy with the browser's own selection UI.
 *
 * The textarea is read-only, focused and fully selected on mount. It is
 * portalled to `document.body` so it is not clipped or re-anchored by the
 * transformed / overflow-hidden chat bubbles that host `CopyButton`; clicks are
 * stopped here because React events still bubble through portals to those
 * bubbles' own handlers.
 */
export function CopyFallbackSheet({ text, onClose, label }: CopyFallbackSheetProps) {
  const targetRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (text === null) return;
    const el = targetRef.current;
    if (!el) return;
    el.focus();
    el.select();
    el.setSelectionRange(0, el.value.length);
  }, [text]);

  if (text === null || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/30 p-3"
      onClick={(e) => {
        e.stopPropagation();
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-label="Copy manually"
        className="w-full max-w-sm rounded-xl border border-slate-300 dark:border-[#383B46] bg-white dark:bg-[#141519] shadow-2xl p-3 space-y-2"
      >
        <div className="flex items-start justify-between gap-2">
          <span className="text-[11px] font-mono font-semibold text-slate-900 dark:text-[#E2E4E9]">
            Your browser blocked the copy. Select and copy this text:
          </span>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-slate-500 dark:text-[#9E9E9E] hover:bg-slate-200 dark:hover:bg-[#22242C]"
            aria-label="Close copy sheet"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        <textarea
          ref={targetRef}
          rows={5}
          readOnly
          value={text}
          spellCheck={false}
          aria-label={label ?? "Text to copy"}
          onFocus={(e) => e.currentTarget.select()}
          className="w-full rounded-lg border border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] p-2 text-[11px] font-mono text-slate-900 dark:text-[#E2E4E9] outline-none focus:ring-1 focus:ring-emerald-500"
        />
      </div>
    </div>,
    document.body,
  );
}
