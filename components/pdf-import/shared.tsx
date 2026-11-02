"use client";

/** Small presentational pieces shared by the PDF import views. */

import React from "react";

export function pct(v: number | null | undefined, digits = 1) {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

export function Stat({ label, value, tone, title }: { label: string; value: string; tone: "good" | "warn" | "neutral"; title?: string }) {
  const colour = tone === "good" ? "text-emerald-400" : tone === "warn" ? "text-amber-400" : "text-[#C7CAD1]";
  return (
    <div className="p-2.5 rounded-lg border border-[#23252A] bg-[#191A1B]/60 min-w-0" title={title}>
      <div className={`text-base font-semibold font-mono tabular-nums truncate ${colour}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-[#8A8F98] truncate">{label}</div>
    </div>
  );
}

export function SectionLabel({ icon, children }: { icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider flex items-center gap-1.5">
      {icon}
      {children}
    </div>
  );
}
