"use client";

/**
 * RebuildProgress — stage cards for an AI-rebuild import (engine "rebuild"). Pages are generated,
 * compiled and verified in parallel, so those three cards carry live "N of M pages" counts from
 * `stage_counts` rather than a single active step.
 */

import React, { useRef } from "react";
import { CheckCircle2, Layers, Loader2 } from "lucide-react";
import type { ConversionJob, StageCounts } from "./usePdfConversionJob";
import { SectionLabel } from "./shared";

const REBUILD_STAGES: { id: string; title: string; desc: string }[] = [
  { id: "queued", title: "Queued", desc: "Waiting for a free worker" },
  { id: "inspecting", title: "Inspecting", desc: "Fonts, text layer, page sizes" },
  { id: "ocr", title: "OCR", desc: "Adding a text layer to scanned pages" },
  { id: "extracting", title: "Extracting", desc: "Text blocks, columns and reading order" },
  { id: "rasterizing", title: "Rendering pages", desc: "Reference images of every page" },
  { id: "assets", title: "Assets", desc: "Images, figures, tables and math" },
  { id: "generating", title: "Writing LaTeX", desc: "Preamble, then each page" },
  { id: "compiling", title: "Compiling", desc: "Sandboxed build and repair" },
  { id: "verifying", title: "Comparing", desc: "Measuring each page against the original" },
  { id: "packaging", title: "Packaging", desc: "Project files, report and zip" },
];

const ORDER = [...REBUILD_STAGES.map((s) => s.id), "done"];

/** Pages that have got past each parallel step, out of the total. */
function passed(stage: string, c: StageCounts, total: number) {
  const pending = c.pending ?? 0;
  const gen = c.generating ?? 0;
  const comp = c.compiling ?? 0;
  const ver = c.verifying ?? 0;
  if (stage === "generating") return { n: total - pending - gen, active: gen };
  if (stage === "compiling") return { n: total - pending - gen - comp, active: comp };
  return { n: total - pending - gen - comp - ver, active: ver };
}

export function RebuildProgress({ job, isRunning }: { job: ConversionJob; isRunning: boolean }) {
  const stage = job.status === "done" ? "done" : job.stage;
  const sawOcr = useRef(false);
  if (stage === "ocr") sawOcr.current = true;
  const ocrApplied = !!job.report?.rebuild?.ocr?.applied;
  const stages = REBUILD_STAGES.filter((s) => s.id !== "ocr" || ocrApplied || sawOcr.current);
  const currentIdx = ORDER.indexOf(stage);
  const counts = job.stage_counts || null;
  const total = counts
    ? Object.values(counts).reduce<number>((a, b) => a + (typeof b === "number" ? b : 0), 0) || job.page_count
    : job.page_count;

  return (
    <div className="space-y-2">
      <SectionLabel icon={<Layers className="w-3.5 h-3.5" />}>AI rebuild progress</SectionLabel>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {stages.map((st) => {
          const stIdx = ORDER.indexOf(st.id);
          const isDone = stage === "done" || (currentIdx >= 0 && currentIdx > stIdx);
          const isActive = isRunning && stage === st.id;
          const parallel = ["generating", "compiling", "verifying"].includes(st.id);
          const count = parallel && counts && total > 0 && currentIdx >= ORDER.indexOf("generating") ? passed(st.id, counts, total) : null;
          const inFlight = !isActive && !isDone && !!count && count.active > 0;

          let detail = st.desc;
          if (st.id === "queued" && isActive && job.queue_position != null) {
            detail = `Position ${job.queue_position} in queue`;
          } else if (count && !isDone) {
            detail = `${Math.max(0, count.n)} of ${total} pages${count.active ? ` · ${count.active} in progress` : ""}`;
          }

          return (
            <div
              key={st.id}
              data-stage={st.id}
              aria-current={isActive ? "step" : undefined}
              className={`px-3 py-2 rounded-lg border text-xs flex items-center gap-2.5 transition-all ${
                isActive
                  ? "border-[#5E6AD2]/60 bg-[#5E6AD2]/12"
                  : inFlight
                  ? "border-[#5E6AD2]/30 bg-[#5E6AD2]/5"
                  : isDone
                  ? "border-emerald-500/20 bg-emerald-500/5"
                  : "border-[#23252A] bg-[#191A1B]/40"
              }`}
            >
              <div className="shrink-0">
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : isActive || inFlight ? (
                  <Loader2 className={`w-4 h-4 animate-spin ${isActive ? "text-[#5E6AD2]" : "text-[#5E6AD2]/60"}`} />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-[#3B3D45]" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className={`font-semibold truncate ${isActive || inFlight ? "text-[#F7F8F8]" : isDone ? "text-[#E6E8EC]" : "text-[#62666D]"}`}>
                  {st.title}
                </div>
                <div className={`text-[10px] truncate ${count && !isDone ? "font-mono tabular-nums text-[#C7CAD1]" : "text-[#8A8F98]"}`}>
                  {detail}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
