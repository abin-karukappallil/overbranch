"use client";

/**
 * RebuildReportView — summary of an AI-rebuild import: engine, document type, whether the model
 * could see page images, OCR, mean match / coverage, page count, and the pages that need a look.
 */

import React from "react";
import { AlertTriangle, Eye, EyeOff, Info } from "lucide-react";
import type { ConversionJob } from "./usePdfConversionJob";
import { Stat, pct } from "./shared";

const VISION_OFF_TEXT = "The model could not see page images; layout was corrected from measurements only.";

export function RebuildReportView({ job, onFocusPage }: { job: ConversionJob; onFocusPage: (page: number) => void }) {
  const report = job.report!;
  const rb = report.rebuild || {};
  const sourcePages = report.page_count || job.page_count;
  const outPages = rb.output_pages ?? report.compiled_page_count ?? null;
  const lowConf = rb.low_confidence || [];
  const imagePages = job.pages.filter((p) => p.fallback === true || p.fallback === "image").length;
  const engineLabel = rb.engine === "deterministic" ? "Deterministic (fallback)" : "AI rebuild";
  const ocr = rb.ocr;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        <Stat label="Mean match" value={pct(rb.score_mean ?? report.mean_similarity)} tone="neutral"
          title="Average visual match of the compiled pages against the original" />
        <Stat label="Text coverage" value={pct(rb.coverage_mean)} tone={rb.coverage_mean != null && rb.coverage_mean >= 0.98 ? "good" : "warn"}
          title="Share of the original's words found in the compiled output" />
        <Stat label="Pages out / in" value={`${outPages ?? "—"} / ${sourcePages}`} tone={rb.page_count_match === false ? "warn" : "good"}
          title={rb.page_count_match === false ? "The output has a different number of pages than the source" : "Same number of pages as the source"} />
        <Stat label="Low confidence" value={`${lowConf.length}`} tone={lowConf.length ? "warn" : "good"} />
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[11px]">
        <dt className="text-[#8A8F98]">Engine</dt>
        <dd className="text-[#F7F8F8] min-w-0 break-words">
          {engineLabel}
          {report.model ? ` · ${report.model}` : ""}
          {rb.rounds_used != null ? ` · ${rb.rounds_used} correction round${rb.rounds_used === 1 ? "" : "s"}` : ""}
          {rb.seconds != null ? ` · ${Math.round(rb.seconds)}s` : ""}
        </dd>
        {rb.fallback_reason && (
          <>
            <dt className="text-[#8A8F98]">Fallback</dt>
            <dd className="text-amber-300 min-w-0 break-words">{rb.fallback_reason}</dd>
          </>
        )}
        {rb.doc_type && (
          <>
            <dt className="text-[#8A8F98]">Document type</dt>
            <dd className="text-[#F7F8F8] min-w-0 break-words">{rb.doc_type}</dd>
          </>
        )}
        <dt className="text-[#8A8F98]">Visual review</dt>
        <dd className="min-w-0 break-words" title={rb.vision_detail || undefined}>
          {rb.vision ? (
            <span className="inline-flex items-center gap-1 text-emerald-300">
              <Eye className="w-3 h-3" /> On
              {rb.vision_detail ? <span className="text-[#8A8F98]"> · {rb.vision_detail}</span> : null}
            </span>
          ) : (
            <span className="inline-flex items-start gap-1 text-amber-300">
              <EyeOff className="w-3 h-3 mt-0.5 shrink-0" />
              <span>Off. {VISION_OFF_TEXT}</span>
            </span>
          )}
        </dd>
        <dt className="text-[#8A8F98]">OCR</dt>
        <dd className="text-[#F7F8F8] min-w-0 break-words">
          {ocr?.applied
            ? `Applied${ocr.engine ? ` (${ocr.engine})` : ""}${ocr.pages?.length ? ` on page${ocr.pages.length === 1 ? "" : "s"} ${ocr.pages.join(", ")}` : ""}`
            : "Not needed (the PDF has a text layer)"}
        </dd>
        {imagePages > 0 && (
          <>
            <dt className="text-[#8A8F98]">Page images</dt>
            <dd className="text-amber-300 min-w-0 break-words">
              {imagePages} page{imagePages === 1 ? " was" : "s were"} kept as an image of the original (not editable text)
            </dd>
          </>
        )}
      </dl>

      {lowConf.length > 0 && (
        <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/10 text-[11px] space-y-2">
          <div className="flex items-center gap-1.5 text-amber-300 font-semibold">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> Pages to check
          </div>
          <ul className="space-y-1">
            {lowConf.map((lc) => (
              <li key={lc.page} className="flex items-start gap-2 min-w-0">
                <button
                  type="button"
                  onClick={() => onFocusPage(lc.page)}
                  className="shrink-0 px-1.5 py-px rounded border border-amber-500/40 text-amber-200 hover:bg-amber-500/20 font-mono"
                >
                  p.{lc.page}
                </button>
                <span className="text-amber-200/90 break-words min-w-0">{(lc.reasons || []).join("; ") || "Low match score"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11px] text-[#62666D] leading-relaxed flex items-start gap-1.5">
        <Info className="w-3 h-3 mt-0.5 shrink-0" />
        <span>{report.disclaimer || "Closest match, not pixel-exact."}</span>
      </p>
    </div>
  );
}
