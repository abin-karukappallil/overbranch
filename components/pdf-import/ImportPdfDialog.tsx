"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileCheck2,
  FileText,
  Info,
  Layers,
  Loader2,
  UploadCloud,
  X,
} from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isResumeMessage } from "@/lib/pdf-import-poll";
import {
  ConversionJob,
  ConversionMode,
  TemplateRules,
  useConversionConfig,
  usePagePreview,
  usePdfConversionJob,
} from "./usePdfConversionJob";

export interface ImportPdfDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Import into this project (editor). When omitted the backend creates a new project. */
  projectId?: string;
  /** Show an already-started job (e.g. one launched by the AI copilot). */
  attachJobId?: string | null;
  onCompleted?: (info: { projectId: string; texPath: string }) => void;
  /** Render as a panel without the modal wrapper (used by the /convert page). */
  inline?: boolean;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Waiting",
  generating: "Generating",
  compiling: "Compiling",
  repairing: "Repairing",
  verifying: "Verifying",
  rerunning: "Refining",
  done: "Done",
  below_threshold: "Needs a look",
  failed: "Failed",
};

function pct(v: number | null | undefined, digits = 1) {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

export function ImportPdfDialog(props: ImportPdfDialogProps) {
  const { open, onOpenChange, inline, attachJobId, onCompleted } = props;
  // Job state lives here (always mounted) so a running conversion keeps polling and
  // still reports completion while the dialog is hidden.
  const conversion = usePdfConversionJob();
  const { job, attach } = conversion;
  const completedFor = useRef<string | null>(null);

  useEffect(() => {
    if (attachJobId) attach(attachJobId);
  }, [attachJobId, attach]);

  useEffect(() => {
    if (job?.status === "done" && job.result && completedFor.current !== job.job_id) {
      completedFor.current = job.job_id;
      onCompleted?.({ projectId: job.project_id, texPath: job.result.tex_path });
    }
  }, [job, onCompleted]);

  if (inline) return <ImportPdfPanel {...props} conversion={conversion} />;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="max-w-3xl w-[calc(100vw-2rem)] sm:max-w-3xl p-0 gap-0 rounded-xl border border-[#23252A] bg-[#0F1011] text-[#F7F8F8] shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
      >
        <ImportPdfPanel {...props} conversion={conversion} />
      </DialogContent>
    </Dialog>
  );
}

function ImportPdfPanel({
  onOpenChange,
  projectId,
  inline,
  conversion,
}: ImportPdfDialogProps & { conversion: ReturnType<typeof usePdfConversionJob> }) {
  const config = useConversionConfig();
  const maxMb = config?.max_file_mb ?? 50;
  const maxPages = config?.max_pages ?? 50;
  const { job, error, starting, start, cancel, commit, reset } = conversion;

  const [file, setFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [mode, setMode] = useState<ConversionMode>("editable");
  const fileInput = useRef<HTMLInputElement>(null);

  const busy = starting || (!!job && !["done", "error", "needs_confirmation", "cancelled"].includes(job.status));

  const pickFile = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".pdf") && f.type !== "application/pdf") {
      setLocalError("Please choose a PDF file.");
      return;
    }
    if (f.size > maxMb * 1024 * 1024) {
      setLocalError(`The file is ${(f.size / 1048576).toFixed(1)} MB; the limit is ${maxMb} MB.`);
      return;
    }
    setLocalError(null);
    setFile(f);
    if (!projectName) setProjectName(f.name.replace(/\.pdf$/i, ""));
  };

  const close = () => {
    if (!busy) {
      reset();
      setFile(null);
    }
    onOpenChange(false);
  };

  const shownError = localError || error;

  return (
    <div className={`flex flex-col min-h-0 ${inline ? "rounded-xl border border-[#23252A] bg-[#0F1011] text-[#F7F8F8]" : ""}`}>
      {/* Header */}
      <div className="p-5 border-b border-[#23252A] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-lg bg-[#5E6AD2]/12 border border-[#5E6AD2]/25 text-[#5E6AD2] shrink-0">
            <FileText className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <DialogTitleOrHeading inline={inline}>Import PDF</DialogTitleOrHeading>
            <DialogDescriptionOrText inline={inline}>
              {projectId
                ? "Convert a PDF into LaTeX inside this project."
                : "Convert a PDF into a new LaTeX project with its fonts, images and layout."}
            </DialogDescriptionOrText>
          </div>
        </div>
        {!inline && (
          <button
            onClick={close}
            className="p-1.5 text-[#8A8F98] hover:text-[#F7F8F8] rounded-md hover:bg-[#191A1B] transition-colors cursor-pointer"
            aria-label={busy ? "Hide (conversion keeps running)" : "Close"}
            title={busy ? "Hide — the conversion keeps running" : "Close"}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="p-5 space-y-5 overflow-y-auto min-h-0">
        {!job ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (file) start(file, { projectId, projectName: projectId ? undefined : projectName.trim() || undefined, mode });
            }}
          >
            {/* Dropzone */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                if (e.dataTransfer.files?.[0]) pickFile(e.dataTransfer.files[0]);
              }}
              onClick={() => fileInput.current?.click()}
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                dragging
                  ? "border-[#5E6AD2] bg-[#5E6AD2]/10"
                  : file
                  ? "border-[#5E6AD2]/50 bg-[#191A1B]"
                  : "border-[#23252A] hover:border-[#3B3D45] bg-[#191A1B]/40"
              }`}
            >
              <input
                ref={fileInput}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && pickFile(e.target.files[0])}
              />
              {file ? (
                <div className="flex items-center justify-center gap-3">
                  <div className="p-2.5 rounded-lg bg-[#5E6AD2]/15 border border-[#5E6AD2]/30 text-[#5E6AD2]">
                    <FileCheck2 className="w-5 h-5" />
                  </div>
                  <div className="text-left min-w-0">
                    <div className="text-xs font-semibold truncate">{file.name}</div>
                    <div className="text-[11px] text-[#8A8F98]">{(file.size / 1048576).toFixed(2)} MB</div>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                    }}
                    className="ml-auto p-1.5 text-[#8A8F98] hover:text-rose-400 rounded-md"
                    aria-label="Remove file"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="mx-auto w-9 h-9 rounded-lg bg-[#191A1B] border border-[#23252A] flex items-center justify-center">
                    <UploadCloud className="w-4 h-4 text-[#5E6AD2]" />
                  </div>
                  <div className="text-xs">
                    <span className="text-[#5E6AD2] font-semibold">Click to choose a PDF</span>
                    <span className="text-[#8A8F98]"> or drag it here</span>
                  </div>
                  <p className="text-[11px] text-[#62666D]">
                    Up to {maxMb} MB and {maxPages} pages
                  </p>
                </div>
              )}
            </div>

            {/* Conversion mode */}
            <div className="space-y-1.5">
              <span className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider">Output</span>
              <div className="grid grid-cols-2 gap-2">
                {([
                  { id: "editable", title: "Editable", desc: "Normal LaTeX you can edit — sections, lists, tables. Same fonts, colours and sizes." },
                  { id: "exact", title: "Exact layout", desc: "Pixel-faithful placement. Hard to edit (coordinate-positioned)." },
                ] as { id: ConversionMode; title: string; desc: string }[]).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setMode(opt.id)}
                    className={`text-left p-3 rounded-lg border transition-all ${
                      mode === opt.id
                        ? "border-[#5E6AD2] bg-[#5E6AD2]/10"
                        : "border-[#23252A] bg-[#191A1B]/40 hover:border-[#3B3D45]"
                    }`}
                  >
                    <div className="text-xs font-semibold flex items-center gap-1.5">
                      {opt.title}
                      {opt.id === "editable" && (
                        <span className="text-[9px] uppercase tracking-wide text-[#5E6AD2] bg-[#5E6AD2]/15 px-1 py-0.5 rounded">
                          Recommended
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-[#8A8F98] mt-1 leading-snug">{opt.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {config && !config.llm_available && (
              <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/10 text-[11px] text-amber-300 flex items-start gap-2">
                <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span>
                  {mode === "editable"
                    ? "The AI copilot's LLM is not configured on this server, so the optional polish step is skipped. The editable LaTeX is still built from the PDF's structure, fonts and colours."
                    : "The AI copilot's LLM is not configured on this server, so pages are reproduced with the positioned-layout fallback (accurate placement, less editable LaTeX)."}
                </span>
              </div>
            )}

            {!projectId && (
              <div className="space-y-1.5">
                <label htmlFor="pdf-import-name" className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider">
                  Project name
                </label>
                <Input
                  id="pdf-import-name"
                  placeholder="Defaults to the file name"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="h-9 text-xs border-[#23252A] bg-[#191A1B] text-[#F7F8F8] placeholder:text-[#62666D] rounded-md"
                />
              </div>
            )}

            <p className="text-[11px] text-[#62666D] leading-relaxed">
              {mode === "editable"
                ? "The PDF is rebuilt as an ordinary, editable LaTeX document — headings, paragraphs, lists, tables and images in reading order — keeping the fonts, colours, sizes and assets. It is compiled and checked for text coverage and style fidelity. Best-effort, not a guaranteed identical copy."
                : `Every page is reproduced as coordinate-placed LaTeX by the same model as the AI copilot${config?.model ? ` (${config.model})` : ""}, compiled and compared with the original. Pixel-faithful but hard to edit. Best-effort, not a guaranteed identical copy.`}
            </p>

            {shownError && (
              <div className="space-y-2">
                <ErrorBox message={shownError} />
                {shownError.toLowerCase().includes("already running") && (
                  <div className="flex items-center justify-between p-2.5 rounded bg-[#191A1B] border border-[#23252A] text-xs">
                    <span className="text-[#8A8F98]">A conversion is already recorded for your account.</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs border-rose-500/30 text-rose-400 hover:bg-rose-500/10"
                      onClick={() => {
                        if (file) {
                          start(file, { projectId, projectName: projectName || undefined, cancelPrevious: true, mode });
                        }
                      }}
                    >
                      Cancel Previous &amp; Retry
                    </Button>
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center justify-end gap-2">
              {!inline && (
                <Button type="button" variant="outline" onClick={close}
                  className="h-8 px-3 text-xs border-[#23252A] bg-[#191A1B] text-[#8A8F98] hover:text-[#F7F8F8] hover:bg-[#23252A]">
                  Cancel
                </Button>
              )}
              <Button type="submit" disabled={!file || starting}
                className="h-8 px-4 text-xs bg-[#5E6AD2] hover:bg-[#4F5BBE] text-white flex items-center gap-1.5">
                {starting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                <span>{starting ? "Uploading…" : "Convert"}</span>
                {!starting && <ArrowRight className="w-3.5 h-3.5" />}
              </Button>
            </div>
          </form>
        ) : (
          <JobView
            job={job}
            error={error}
            onCommit={commit}
            onRetry={() => {
              reset();
            }}
            onCancel={cancel}
            onClose={close}
            doneLabel={projectId ? "Done" : "Open in editor"}
          />
        )}
      </div>
    </div>
  );
}


function DialogTitleOrHeading({ inline, children }: { inline?: boolean; children: React.ReactNode }) {
  const cls = "text-sm font-semibold uppercase tracking-wide";
  return inline ? <h2 className={cls}>{children}</h2> : <DialogTitle className={cls}>{children}</DialogTitle>;
}

function DialogDescriptionOrText({ inline, children }: { inline?: boolean; children: React.ReactNode }) {
  const cls = "text-xs text-[#8A8F98]";
  return inline ? <p className={cls}>{children}</p> : <DialogDescription className={cls}>{children}</DialogDescription>;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="p-3 rounded-md bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2.5">
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
      <div className="leading-relaxed break-words min-w-0">{message}</div>
    </div>
  );
}

function JobView({
  job,
  error,
  onCommit,
  onRetry,
  onCancel,
  onClose,
  doneLabel,
}: {
  job: ConversionJob;
  error: string | null;
  onCommit: (o: { overwrite?: boolean; targetPath?: string }) => Promise<boolean>;
  onRetry: () => void;
  onCancel?: () => void;
  onClose: () => void;
  doneLabel: string;
}) {
  const threshold = job.report?.threshold ?? 0.85;
  const running = !["done", "error", "needs_confirmation", "cancelled"].includes(job.status);
  const progress = Math.round((job.progress || 0) * 100);

  return (
    <div className="space-y-5">
      {/* Overall progress */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="font-semibold flex items-center gap-2 min-w-0">
            {running ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-[#5E6AD2] shrink-0" />
            ) : job.status === "error" ? (
              <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            )}
            <span className={`truncate ${running && isResumeMessage(job.message) ? "text-amber-300" : ""}`}>
              {job.message || "Working…"}
            </span>
          </span>
          <span className="font-mono text-[#8A8F98] tabular-nums">{progress}%</span>
        </div>
        <div className="h-1.5 w-full bg-[#191A1B] rounded-full overflow-hidden border border-[#23252A]" role="progressbar"
          aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-[#5E6AD2] transition-all duration-300 rounded-full" style={{ width: `${progress}%` }} />
        </div>
        <div className="text-[11px] text-[#62666D]">
          {job.filename} · {job.page_count} page{job.page_count === 1 ? "" : "s"}
          {job.report?.model ? ` · ${job.report.model}` : ""}
        </div>
      </div>

      {/* Progress view: pipeline steps for editable mode, per-page grid for exact mode */}
      {job.mode === "editable" ? (
        <EditablePipelineProgress currentStage={job.stage} isRunning={running} />
      ) : (
        job.pages.length > 0 && (
          <div>
            <div className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" /> Pages
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 max-h-40 overflow-y-auto pr-1">
              {job.pages.map((p) => {
                const ok = p.status === "done";
                const active = ["generating", "compiling", "repairing", "verifying", "rerunning"].includes(p.status);
                return (
                  <div key={p.number}
                    className={`px-2.5 py-1.5 rounded-md border text-[11px] flex items-center justify-between gap-2 ${
                      active ? "border-[#5E6AD2]/40 bg-[#5E6AD2]/8" : "border-[#23252A] bg-[#191A1B]/60"
                    }`}
                    title={(p.warnings || []).join("\n")}
                  >
                    <span className="text-[#8A8F98]">p.{p.number}{p.fallback ? " ·" : ""}</span>
                    <span className={`font-mono tabular-nums ${p.similarity == null ? "text-[#62666D]" : ok ? "text-emerald-400" : "text-amber-400"}`}>
                      {p.similarity != null ? pct(p.text_coverage ?? p.similarity) : STATUS_LABEL[p.status] || p.status}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )
      )}

      {job.status === "needs_confirmation" && (
        <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/10 text-xs space-y-3">
          <div className="flex items-start gap-2 text-amber-300">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              <b>{job.conflict_path || "main.tex"}</b> already has content. Choose how to save the converted document.
            </span>
          </div>
          <div className="flex flex-wrap gap-2 justify-end">
            <Button variant="outline" onClick={() => onCommit({ targetPath: "converted.tex" })}
              className="h-8 px-3 text-xs border-[#23252A] bg-[#191A1B] text-[#F7F8F8] hover:bg-[#23252A]">
              Save as converted.tex
            </Button>
            <Button onClick={() => onCommit({ overwrite: true, targetPath: job.conflict_path || "main.tex" })}
              className="h-8 px-3 text-xs bg-rose-600 hover:bg-rose-500 text-white">
              Replace {job.conflict_path || "main.tex"}
            </Button>
          </div>
        </div>
      )}

      {(job.status === "error" || error) && (
        <div className="space-y-3">
          <ErrorBox message={job.error || error || "Conversion failed."} />
          <div className="flex justify-end">
            <Button onClick={onRetry} className="h-8 text-xs bg-[#191A1B] border border-[#23252A] hover:bg-[#23252A] text-white">
              Try again
            </Button>
          </div>
        </div>
      )}

      {job.report && !running && <ReportView job={job} threshold={threshold} />}

      {job.status === "done" && (
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} className="h-8 px-4 text-xs bg-[#5E6AD2] hover:bg-[#4F5BBE] text-white flex items-center gap-1.5">
            {doneLabel} <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      )}

      {running && onCancel && (
        <div className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={() => onCancel()}
            className="h-8 px-3 text-xs border-[#23252A] bg-[#191A1B] text-[#8A8F98] hover:text-rose-400 hover:bg-[#23252A]"
          >
            Cancel conversion
          </Button>
        </div>
      )}
    </div>
  );
}

const EDITABLE_STAGES = [
  { id: "extracting", title: "Extracting Assets", desc: "Text, vector graphics & images" },
  { id: "analysing", title: "Document Structure", desc: "Headings, paragraphs, lists & tables" },
  { id: "compiling", title: "Compiling LaTeX", desc: "pdfLaTeX compilation & auto-repair" },
  { id: "verifying", title: "Quality Gates", desc: "Checking coverage & style fidelity" },
  { id: "laying_out", title: "Figure & Table Layout", desc: "Vision-corrected size, alignment & floats" },
  { id: "polishing", title: "Math & Table Polish", desc: "Equations & semantic formatting" },
  { id: "writing", title: "Saving Project", desc: "Writing output files to workspace" },
];

const STAGE_ORDER = ["queued", "extracting", "analysing", "compiling", "verifying", "laying_out", "polishing", "writing", "done"];

function EditablePipelineProgress({ currentStage, isRunning }: { currentStage: string; isRunning: boolean }) {
  const currentIdx = STAGE_ORDER.indexOf(currentStage);

  return (
    <div className="space-y-2">
      <div className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider flex items-center gap-1.5">
        <Layers className="w-3.5 h-3.5" /> Pipeline Progress
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {EDITABLE_STAGES.map((st) => {
          const stIdx = STAGE_ORDER.indexOf(st.id);
          const isDone = currentIdx > stIdx || currentStage === "done";
          const isActive = isRunning && currentStage === st.id;

          return (
            <div
              key={st.id}
              className={`px-3 py-2 rounded-lg border text-xs flex items-center gap-2.5 transition-all ${
                isActive
                  ? "border-[#5E6AD2]/50 bg-[#5E6AD2]/10"
                  : isDone
                  ? "border-emerald-500/20 bg-emerald-500/5 text-[#F7F8F8]"
                  : "border-[#23252A] bg-[#191A1B]/40 text-[#62666D]"
              }`}
            >
              <div className="shrink-0">
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : isActive ? (
                  <Loader2 className="w-4 h-4 text-[#5E6AD2] animate-spin" />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-[#3B3D45] flex items-center justify-center text-[10px] text-[#62666D]" />
                )}
              </div>
              <div className="min-w-0">
                <div className={`font-semibold truncate ${isActive ? "text-[#F7F8F8]" : isDone ? "text-[#E6E8EC]" : "text-[#62666D]"}`}>
                  {st.title}
                </div>
                <div className="text-[10px] text-[#8A8F98] truncate">{st.desc}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EditableReportView({ job }: { job: ConversionJob }) {
  const report = job.report!;
  const ed = report.editable || {};
  const g = ed.gates || {};
  const failed = new Set(ed.failed || []);
  const tone = (ok: boolean) => (ok ? "good" : "warn");
  const assetsOk = ed.assets?.ok !== false && (ed.assets?.extra?.length ?? 0) === 0;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-2 text-center">
        <Stat label="Text kept" value={pct(g.coverage ?? null)} tone={tone(!failed.has("coverage"))} />
        <Stat label="Style match" value={pct(g.style ?? null)} tone={tone(!failed.has("style"))} />
        <Stat label="Pages"
          value={`${g.pages_out ?? report.compiled_page_count ?? "—"} / ${g.pages_source ?? report.page_count}`}
          tone={tone(!failed.has("pages"))} />
        <Stat label="Images"
          value={`${(ed.assets?.referenced?.length ?? 0)}`}
          tone={tone(assetsOk)} />
      </div>
      <p className="text-[11px] text-[#62666D] leading-relaxed">
        Editable LaTeX · {report.compiled ? "compiled" : "not compiled"} · pdfLaTeX ·{" "}
        {report.llm_used ? `polished with ${report.model}` : "deterministic (no LLM polish)"}
        {report.disclaimer ? ` · ${report.disclaimer}` : ""}
      </p>
      {failed.size > 0 && (
        <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/10 text-[11px] text-amber-300">
          Some quality checks did not fully pass: {[...failed].join(", ")}. The document is still editable
          and carries all of its text; review the flagged areas.
        </div>
      )}
      {ed.lint && (
        <div className="text-[11px] text-[#62666D]">
          Editability: {ed.lint.sections ?? 0} headings · {ed.lint.fontsize ?? 0} inline font-size ·{" "}
          {ed.lint.nodes ?? 0} positioned nodes
          {typeof ed.polish?.accepted === "number" ? ` · ${ed.polish.accepted}/${ed.polish.tried ?? 0} polish edits kept` : ""}
        </div>
      )}
    </div>
  );
}

function ReportView({ job, threshold }: { job: ConversionJob; threshold: number }) {
  const report = job.report!;
  const [page, setPage] = useState(1);
  const [showDiff, setShowDiff] = useState(false);
  const canPreview = report.compiled;
  if (job.mode === "editable" || report.mode === "editable") {
    return <EditableReportView job={job} />;
  }
  const below = useMemo(() => report.pages.filter((p) => p.status === "below_threshold").length, [report]);
  const fallbacks = report.pages.filter((p) => p.fallback).length;
  const coverageTarget = report.coverage_target ?? 0.995;
  const maxShift = report.max_displacement ?? 25;
  const meanCoverage = useMemo(() => {
    const vals = report.pages.map((p) => p.text_coverage).filter((v): v is number => v != null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  }, [report]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-2 text-center">
        <Stat label="Text found" value={pct(meanCoverage)} tone={meanCoverage != null && meanCoverage >= coverageTarget ? "good" : "warn"} />
        <Stat label="Mean similarity" value={pct(report.mean_similarity)} tone="neutral" />
        <Stat label="Needs a look" value={`${below} / ${report.page_count}`} tone={below ? "warn" : "good"} />
        <Stat label="Fallback pages" value={`${fallbacks} / ${report.page_count}`} tone={fallbacks ? "warn" : "good"} />
      </div>
      <p className="text-[11px] text-[#62666D] leading-relaxed">
        Text target {pct(coverageTarget, 1)} · max text movement {maxShift}pt · similarity reference {pct(threshold, 0)} · pdfLaTeX · {report.llm_used ? report.model : "no LLM (positioned layout)"}
        {report.compiled_page_count != null && report.compiled_page_count !== report.page_count
          ? ` · compiled ${report.compiled_page_count} of ${report.page_count} pages`
          : ""}{" "}
        · {report.disclaimer}
      </p>

      <TemplateRulesPanel rules={report.template_rules} />

      {canPreview && (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider">Original vs converted</div>
            <div className="flex items-center gap-1.5">
              <label className="flex items-center gap-1.5 text-[11px] text-[#8A8F98] mr-2 cursor-pointer">
                <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
                Highlight differences
              </label>
              <Button variant="outline" size="icon" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
                className="h-7 w-7 border-[#23252A] bg-[#191A1B]"><ChevronLeft className="w-3.5 h-3.5" /></Button>
              <span className="text-[11px] font-mono tabular-nums w-14 text-center">{page} / {report.page_count}</span>
              <Button variant="outline" size="icon" aria-label="Next page" disabled={page >= report.page_count} onClick={() => setPage((p) => p + 1)}
                className="h-7 w-7 border-[#23252A] bg-[#191A1B]"><ChevronRight className="w-3.5 h-3.5" /></Button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <PreviewPane jobId={job.job_id} page={page} which="original" label="Original" />
            <PreviewPane jobId={job.job_id} page={page} which={showDiff ? "diff" : "converted"}
              label={`Converted · ${pct(report.pages[page - 1]?.similarity)}`} />
          </div>
        </div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-[#8A8F98] font-medium uppercase tracking-wider">Per-page detail</summary>
        <table className="mt-2 w-full text-[11px]">
          <thead className="text-[#62666D]">
            <tr><th className="text-left font-normal py-1">Page</th><th className="text-right font-normal">Similarity</th><th className="text-right font-normal">SSIM</th><th className="text-right font-normal">Text found</th><th className="text-right font-normal" title="Median distance a word moved from where it sits in the PDF">Text moved</th><th className="text-right font-normal">LLM calls</th><th className="text-right font-normal">Source</th></tr>
          </thead>
          <tbody>
            {report.pages.map((p) => (
              <tr key={p.number} className="border-t border-[#23252A]" title={p.warnings.join("\n")}>
                <td className="py-1">{p.number}{p.warnings.length ? " ⚠" : ""}</td>
                <td className="text-right font-mono tabular-nums text-[#8A8F98]">{pct(p.similarity)}</td>
                <td className="text-right font-mono tabular-nums">{p.ssim?.toFixed(3) ?? "—"}</td>
                <td className={`text-right font-mono tabular-nums ${p.text_coverage != null && p.text_coverage >= coverageTarget ? "text-emerald-400" : "text-amber-400"}`}>{pct(p.text_coverage, 0)}</td>
                <td className={`text-right font-mono tabular-nums ${p.displacement == null ? "text-[#62666D]" : p.displacement <= maxShift ? "text-emerald-400" : "text-amber-400"}`}>
                  {p.displacement == null ? "—" : `${p.displacement.toFixed(0)}pt`}
                </td>
                <td className="text-right font-mono tabular-nums">{p.attempts + p.compile_repairs}</td>
                <td className="text-right">{p.fallback === "layout" ? "positioned layout" : p.fallback === "image" ? "page image" : "LLM"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      {(report.warnings.length > 0 || report.pages.some((p) => p.warnings.length)) && (
        <details className="text-xs">
          <summary className="cursor-pointer text-[#8A8F98] font-medium uppercase tracking-wider">Warnings</summary>
          <ul className="mt-2 space-y-1 text-[11px] text-amber-300/90 list-disc pl-4">
            {report.warnings.map((w, i) => <li key={`d${i}`}>{w}</li>)}
            {report.pages.flatMap((p) => p.warnings.map((w, i) => <li key={`p${p.number}-${i}`}>Page {p.number}: {w}</li>))}
          </ul>
        </details>
      )}
    </div>
  );
}

const RULE_LABELS: [string, string][] = [
  ["body_font", "Font"],
  ["body_size_pt", "Size"],
  ["line_spacing", "Line spacing"],
  ["margins_mm", "Margins"],
  ["heading_levels", "Headings"],
];

/** One short human-readable value for a rule; rules come from an LLM, so anything may be missing or odd. */
function ruleText(key: string, value: unknown): string | null {
  if (value == null || value === "") return null;
  if (key === "body_size_pt" && typeof value === "number") return `${value} pt`;
  if (key === "margins_mm" && typeof value === "object" && !Array.isArray(value)) {
    const m = value as Record<string, unknown>;
    const parts = ["top", "bottom", "left", "right"]
      .filter((side) => m[side] != null && m[side] !== "")
      .map((side) => `${side} ${String(m[side])} mm`);
    return parts.length ? parts.join(", ") : null;
  }
  if (key === "heading_levels" && Array.isArray(value)) {
    const parts = value
      .map((h) => {
        if (!h || typeof h !== "object") return typeof h === "string" ? h : "";
        const o = h as Record<string, unknown>;
        const bits = [o.font, o.size_pt != null ? `${o.size_pt} pt` : "", o.bold ? "bold" : "", o.italic ? "italic" : ""]
          .filter((b) => b != null && b !== "" && b !== false)
          .map(String);
        return [o.name != null ? String(o.name) : "", bits.join(" ")].filter(Boolean).join(": ");
      })
      .filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  if (typeof value === "object") return null;
  return String(value);
}

function TemplateRulesPanel({ rules }: { rules?: TemplateRules | null }) {
  if (!rules || rules.is_template !== true) return null;
  const stated =
    rules.rules && typeof rules.rules === "object" && !Array.isArray(rules.rules)
      ? RULE_LABELS.map(([key, label]) => [label, ruleText(key, (rules.rules as Record<string, unknown>)[key])] as const).filter(
          (row): row is readonly [string, string] => row[1] != null
        )
      : [];
  const evidence = Array.isArray(rules.evidence)
    ? rules.evidence.filter((e): e is string => typeof e === "string" && e.trim() !== "")
    : [];
  if (!stated.length && !evidence.length) return null;
  return (
    <div className="p-3 rounded-lg border border-[#5E6AD2]/30 bg-[#5E6AD2]/8 text-xs space-y-2">
      <div className="flex items-center gap-2 font-semibold text-[#C7CAD1]">
        <Info className="w-3.5 h-3.5 text-[#5E6AD2] shrink-0" />
        Template rules detected
      </div>
      {stated.length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px]">
          {stated.map(([label, text]) => (
            <React.Fragment key={label}>
              <dt className="text-[#8A8F98]">{label}</dt>
              <dd className="text-[#F7F8F8] break-words min-w-0">{text}</dd>
            </React.Fragment>
          ))}
        </dl>
      )}
      {evidence.length > 0 && (
        <ul className="space-y-1 text-[11px] text-[#8A8F98] list-disc pl-4">
          {evidence.map((e, i) => (
            <li key={i} className="break-words">
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: "good" | "warn" | "neutral" }) {
  const colour = tone === "good" ? "text-emerald-400" : tone === "warn" ? "text-amber-400" : "text-[#C7CAD1]";
  return (
    <div className="p-2.5 rounded-lg border border-[#23252A] bg-[#191A1B]/60">
      <div className={`text-base font-semibold font-mono tabular-nums ${colour}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-[#8A8F98]">{label}</div>
    </div>
  );
}

function PreviewPane({ jobId, page, which, label }: { jobId: string; page: number; which: "original" | "converted" | "diff"; label: string }) {
  const { url, failed } = usePagePreview(jobId, page, which);
  return (
    <figure className="rounded-lg border border-[#23252A] bg-white/95 overflow-hidden">
      <figcaption className="px-2 py-1 text-[10px] uppercase tracking-wider bg-[#191A1B] text-[#8A8F98]">{label}</figcaption>
      <div className="aspect-[1/1.3] flex items-center justify-center">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={`${label} page ${page}`} className="w-full h-full object-contain" />
        ) : failed ? (
          <span className="text-[11px] text-[#62666D]">Preview unavailable</span>
        ) : (
          <Loader2 className="w-4 h-4 animate-spin text-[#8A8F98]" />
        )}
      </div>
    </figure>
  );
}
