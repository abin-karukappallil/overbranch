"use client";

/**
 * PageGrid — one tile per source page with its status and match score. Exact-mode jobs keep the
 * compact tiles they always had; editable jobs add the "page image" and "low confidence" badges.
 * Clicking a tile focuses that page in the side-by-side preview.
 */

import React from "react";
import { Layers } from "lucide-react";
import type { PageStatus } from "./usePdfConversionJob";
import { SectionLabel, pct } from "./shared";

const STATUS_LABEL: Record<string, string> = {
  pending: "Waiting",
  generating: "Writing",
  compiling: "Compiling",
  repairing: "Repairing",
  verifying: "Comparing",
  rerunning: "Refining",
  done: "Done",
  fallback: "Fallback",
  below_threshold: "Needs a look",
  failed: "Failed",
};

const ACTIVE = new Set(["generating", "compiling", "repairing", "verifying", "rerunning"]);

function statusTone(status: string) {
  if (status === "done") return "text-emerald-300 bg-emerald-500/10 border-emerald-500/25";
  if (status === "failed") return "text-rose-300 bg-rose-500/10 border-rose-500/25";
  if (status === "fallback" || status === "below_threshold") return "text-amber-300 bg-amber-500/10 border-amber-500/25";
  if (ACTIVE.has(status)) return "text-[#C7CAD1] bg-[#5E6AD2]/15 border-[#5E6AD2]/30";
  return "text-[#8A8F98] bg-[#191A1B] border-[#23252A]";
}

export function PageGrid({
  pages,
  variant,
  focused,
  onFocus,
}: {
  pages: PageStatus[];
  variant: "exact" | "editable";
  focused?: number | null;
  onFocus?: (page: number) => void;
}) {
  if (!pages.length) return null;

  if (variant === "exact") {
    return (
      <div>
        <div className="mb-2">
          <SectionLabel icon={<Layers className="w-3.5 h-3.5" />}>Pages</SectionLabel>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 max-h-40 overflow-y-auto pr-1">
          {pages.map((p) => {
            const ok = p.status === "done";
            const active = ACTIVE.has(p.status);
            return (
              <button
                type="button"
                key={p.number}
                disabled={!onFocus}
                onClick={() => onFocus?.(p.number)}
                className={`px-2.5 py-1.5 rounded-md border text-[11px] flex items-center justify-between gap-2 text-left ${
                  focused === p.number
                    ? "border-[#5E6AD2] bg-[#5E6AD2]/10"
                    : active
                    ? "border-[#5E6AD2]/40 bg-[#5E6AD2]/8"
                    : "border-[#23252A] bg-[#191A1B]/60"
                }`}
                title={(p.warnings || []).join("\n")}
              >
                <span className="text-[#8A8F98]">p.{p.number}{p.fallback ? " ·" : ""}</span>
                <span className={`font-mono tabular-nums ${p.similarity == null ? "text-[#62666D]" : ok ? "text-emerald-400" : "text-amber-400"}`}>
                  {p.similarity != null ? pct(p.text_coverage ?? p.similarity) : STATUS_LABEL[p.status] || p.status}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <SectionLabel icon={<Layers className="w-3.5 h-3.5" />}>Pages</SectionLabel>
        <span className="text-[10px] text-[#62666D]">{onFocus ? "Match % · click a page to compare" : "Match %"}</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 max-h-56 overflow-y-auto pr-1">
        {pages.map((p) => {
          const imageFallback = p.fallback === true || p.fallback === "image";
          const lowConf = p.low_confidence || [];
          const tip = [
            ...(lowConf.length ? ["Low confidence:", ...lowConf.map((r) => `• ${r}`)] : []),
            ...(p.warnings || []),
          ].join("\n");
          return (
            <button
              type="button"
              key={p.number}
              data-page={p.number}
              disabled={!onFocus}
              onClick={() => onFocus?.(p.number)}
              title={tip || undefined}
              aria-pressed={focused === p.number}
              className={`px-2.5 py-2 rounded-md border text-[11px] text-left space-y-1 transition-colors min-w-0 ${
                focused === p.number
                  ? "border-[#5E6AD2] bg-[#5E6AD2]/10"
                  : ACTIVE.has(p.status)
                  ? "border-[#5E6AD2]/40 bg-[#5E6AD2]/5 hover:border-[#5E6AD2]/70"
                  : "border-[#23252A] bg-[#191A1B]/60 hover:border-[#3B3D45]"
              }`}
            >
              <div className="flex items-center justify-between gap-1.5">
                <span className="text-[#C7CAD1] font-medium">p.{p.number}</span>
                <span className={`font-mono tabular-nums ${p.similarity == null ? "text-[#62666D]" : p.similarity >= 0.85 ? "text-emerald-400" : "text-amber-400"}`}>
                  {pct(p.similarity, 0)}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <span className={`px-1.5 py-px rounded border text-[9px] uppercase tracking-wide ${statusTone(p.status)}`}>
                  {STATUS_LABEL[p.status] || p.status}
                </span>
                {imageFallback && (
                  <span className="px-1.5 py-px rounded border text-[9px] uppercase tracking-wide text-amber-300 bg-amber-500/10 border-amber-500/25">
                    page image
                  </span>
                )}
                {p.fallback === "layout" && (
                  <span className="px-1.5 py-px rounded border text-[9px] uppercase tracking-wide text-amber-300 bg-amber-500/10 border-amber-500/25">
                    positioned
                  </span>
                )}
                {lowConf.length > 0 && (
                  <span className="px-1.5 py-px rounded border text-[9px] uppercase tracking-wide text-rose-300 bg-rose-500/10 border-rose-500/25">
                    low confidence
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
