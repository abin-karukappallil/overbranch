"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, FileArchive, Loader2, UploadCloud, X } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useZipImport } from "./useZipImport";

export interface ImportZipDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (projectId: string, name: string) => void;
}

const MAX_ZIP_MB = 50;

export function ImportZipDialog({ open, onOpenChange, onSuccess }: ImportZipDialogProps) {
  const { start, reset, progress, error, state, result } = useZipImport();
  const [file, setFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const nameEdited = useRef(false);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const busy = state === "uploading" || state === "extracting";

  // Fresh form every time the dialog opens.
  useEffect(() => {
    if (open) {
      reset();
      setFile(null);
      setProjectName("");
      nameEdited.current = false;
      setLocalError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const pickFile = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".zip")) {
      setLocalError("Please choose a .zip file.");
      return;
    }
    if (f.size > MAX_ZIP_MB * 1024 * 1024) {
      setLocalError(`The file is ${(f.size / 1048576).toFixed(1)} MB; the limit is ${MAX_ZIP_MB} MB.`);
      return;
    }
    setLocalError(null);
    setFile(f);
    if (!nameEdited.current) setProjectName(f.name.replace(/\.zip$/i, ""));
  };

  const close = () => {
    if (busy) return; // an import in flight cannot be cancelled safely mid-extraction
    onOpenChange(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || busy) return;
    const res = await start(file, projectName);
    if (res) {
      onSuccess?.(res.project_id, res.name);
      onOpenChange(false);
    }
  };

  const shownError = localError || error;

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent
        showCloseButton={false}
        className="max-w-lg w-[calc(100vw-2rem)] sm:max-w-lg p-0 gap-0 rounded-xl border border-[#23252A] bg-[#0F1011] text-[#F7F8F8] shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
      >
        <div className="p-5 border-b border-[#23252A] flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-2 rounded-lg bg-[#5E6AD2]/12 border border-[#5E6AD2]/25 text-[#5E6AD2] shrink-0">
              <FileArchive className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <DialogTitle className="text-sm font-semibold">Import from ZIP</DialogTitle>
              <DialogDescription className="text-xs text-[#8A8F98]">
                Upload a .zip of your LaTeX sources to create a new project.
              </DialogDescription>
            </div>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={busy}
            className="p-1.5 text-[#8A8F98] hover:text-[#F7F8F8] rounded-md hover:bg-[#191A1B] transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form className="p-5 space-y-4 overflow-y-auto min-h-0" onSubmit={submit}>
          {/* Dropzone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (!busy && e.dataTransfer.files?.[0]) pickFile(e.dataTransfer.files[0]);
            }}
            onClick={() => !busy && fileInput.current?.click()}
            className={`border-2 border-dashed rounded-lg p-6 text-center transition-all ${
              busy ? "cursor-default" : "cursor-pointer"
            } ${
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
              accept=".zip,application/zip,application/x-zip-compressed"
              className="hidden"
              data-testid="zip-file-input"
              onChange={(e) => {
                if (e.target.files?.[0]) pickFile(e.target.files[0]);
                e.target.value = "";
              }}
            />
            {file ? (
              <div className="flex items-center justify-center gap-3">
                <div className="p-2.5 rounded-lg bg-[#5E6AD2]/15 border border-[#5E6AD2]/30 text-[#5E6AD2]">
                  <FileArchive className="w-5 h-5" />
                </div>
                <div className="text-left min-w-0">
                  <div className="text-xs font-semibold truncate">{file.name}</div>
                  <div className="text-[11px] text-[#8A8F98]">{(file.size / 1048576).toFixed(2)} MB</div>
                </div>
                {!busy && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                    }}
                    className="ml-auto p-1.5 text-[#8A8F98] hover:text-rose-400 rounded-md cursor-pointer"
                    aria-label="Remove file"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="mx-auto w-9 h-9 rounded-lg bg-[#191A1B] border border-[#23252A] flex items-center justify-center">
                  <UploadCloud className="w-4 h-4 text-[#5E6AD2]" />
                </div>
                <div className="text-xs">
                  <span className="text-[#5E6AD2] font-semibold">Click to choose a ZIP</span>
                  <span className="text-[#8A8F98]"> or drag it here</span>
                </div>
                <p className="text-[11px] text-[#62666D]">Up to {MAX_ZIP_MB} MB. Hidden files are skipped.</p>
              </div>
            )}
          </div>

          {/* Project name */}
          <div className="space-y-1.5">
            <label htmlFor="zip-project-name" className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider">
              Project name
            </label>
            <Input
              id="zip-project-name"
              value={projectName}
              disabled={busy}
              maxLength={80}
              placeholder="Defaults to the ZIP file name"
              onChange={(e) => {
                nameEdited.current = true;
                setProjectName(e.target.value);
              }}
              className="h-9 text-xs bg-[#191A1B] border-[#23252A] text-[#F7F8F8] placeholder:text-[#62666D]"
            />
          </div>

          {/* Progress */}
          {busy && (
            <div className="space-y-1.5" role="status" aria-live="polite">
              <div className="flex items-center justify-between text-[11px] text-[#8A8F98]">
                <span className="flex items-center gap-1.5">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {state === "uploading" ? "Uploading…" : "Extracting…"}
                </span>
                {state === "uploading" && <span>{Math.round(progress * 100)}%</span>}
              </div>
              <div className="h-1.5 rounded-full bg-[#191A1B] overflow-hidden">
                {state === "uploading" ? (
                  <div className="h-full bg-[#5E6AD2] transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
                ) : (
                  <div className="h-full w-1/3 bg-[#5E6AD2] animate-pulse rounded-full" />
                )}
              </div>
            </div>
          )}

          {state === "done" && result && (
            <div className="flex items-start gap-2 p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-xs text-emerald-300">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Imported {result.files_count + result.assets_count} files.
                {result.created_main_tex && " No .tex file was found, so an empty main.tex was created."}
              </span>
            </div>
          )}

          {shownError && (
            <div role="alert" className="flex items-start gap-2 p-3 rounded-lg border border-rose-500/30 bg-rose-500/10 text-xs text-rose-300">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{shownError}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={close} disabled={busy} className="h-9 text-xs text-[#8A8F98] hover:text-[#F7F8F8] cursor-pointer">
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!file || busy}
              className="h-9 px-4 text-xs bg-[#5E6AD2] hover:bg-[#6B77DE] text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Importing…" : "Import project"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
