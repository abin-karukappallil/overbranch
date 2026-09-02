"use client";

import React, { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  FileText,
  UploadCloud,
  X,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FileCheck2,
  Layers,
  Image as ImageIcon,
  FolderPlus,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { authClient } from "@/lib/auth-client";

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

interface PDFToLatexModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type StepKey = "uploading" | "analyzing" | "extracting_assets" | "generating_latex" | "creating_project" | "done";

interface StepConfig {
  key: StepKey;
  label: string;
  description: string;
  icon: any;
}

const STEPS: StepConfig[] = [
  { key: "uploading", label: "Uploading", description: "Reading and validating PDF document", icon: UploadCloud },
  { key: "analyzing", label: "Analyzing PDF", description: "Detecting layout, text, tables & structure", icon: Layers },
  { key: "extracting_assets", label: "Extracting Assets", description: "Extracting embedded images & graphics", icon: ImageIcon },
  { key: "generating_latex", label: "Generating LaTeX", description: "Synthesizing semantic LaTeX & auto-repair", icon: Sparkles },
  { key: "creating_project", label: "Creating Project", description: "Setting up workspace & saving files", icon: FolderPlus },
];

export function PDFToLatexModal({ isOpen, onClose }: PDFToLatexModalProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { data: session } = authClient.useSession();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const [documentTypeHint, setDocumentTypeHint] = useState<"auto" | "beamer" | "report" | "article">("auto");
  const [isDragging, setIsDragging] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [currentStep, setCurrentStep] = useState<StepKey>("uploading");
  const [statusMessage, setStatusMessage] = useState("");
  const [progressPct, setProgressPct] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [convertedProject, setConvertedProject] = useState<any | null>(null);

  if (!isOpen) return null;

  const handleFileSelect = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
      toast.error("Please select a valid PDF file.");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      toast.error("File size exceeds 50MB limit.");
      return;
    }
    setSelectedFile(file);
    setErrorMessage(null);
    if (!projectName.trim()) {
      // Pre-fill project name based on PDF file name without extension
      const defaultName = file.name.replace(/\.pdf$/i, "").replace(/[^a-zA-Z0-9_\- ]/g, "_").trim();
      setProjectName(defaultName);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleStartConversion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      toast.error("Please upload a PDF document first.");
      return;
    }

    setIsConverting(true);
    setErrorMessage(null);
    setCurrentStep("uploading");
    setProgressPct(10);
    setStatusMessage("Reading PDF data...");

    // Read PDF file as Data URL / Base64
    const reader = new FileReader();
    reader.onerror = () => {
      setIsConverting(false);
      setErrorMessage("Failed to read local PDF file.");
    };

    reader.onload = async () => {
      const pdfBase64 = reader.result as string;

      try {
        // Clean up any stale guest tokens for logged-in users so project ownership is crystal clear
        if (session?.user?.id) {
          try {
            localStorage.removeItem("ob_guest_token");
            document.cookie = "ob_guest_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
          } catch (_) {}
        }

        const response = await fetch(`${BACKEND_URL}/api/pdf/convert`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            pdf_data: pdfBase64,
            project_name: projectName.trim() || undefined,
            user_id: session?.user?.id,
            document_type_hint: documentTypeHint !== "auto" ? documentTypeHint : undefined,
          }),
        });

        if (!response.ok) {
          const errJson = await response.json().catch(() => ({ detail: "Conversion failed" }));
          throw new Error(errJson.detail || `Server responded with status ${response.status}`);
        }

        const sseReader = response.body?.getReader();
        if (!sseReader) throw new Error("No response stream available.");

        const decoder = new TextDecoder();
        let buffer = "";
        let finalResult: any = null;

        const parseLines = (lines: string[]) => {
          let currentEvent = "";
          for (const line of lines) {
            const trimmed = line.replace(/\r$/, "");
            if (trimmed.startsWith("event: ")) {
              currentEvent = trimmed.slice(7).trim();
            } else if (trimmed.startsWith("data: ")) {
              const raw = trimmed.slice(6);
              try {
                const parsed = JSON.parse(raw);
                if (currentEvent === "progress") {
                  if (parsed.step) {
                    if (parsed.step.includes("analyz")) setCurrentStep("analyzing");
                    else if (parsed.step.includes("asset")) setCurrentStep("extracting_assets");
                    else if (parsed.step.includes("latex") || parsed.step.includes("compil") || parsed.step.includes("repair")) setCurrentStep("generating_latex");
                    else if (parsed.step.includes("creat")) setCurrentStep("creating_project");
                    else if (parsed.step === "done") setCurrentStep("done");
                  }
                  if (parsed.message) setStatusMessage(parsed.message);
                  if (parsed.pct) setProgressPct(parsed.pct);
                } else if (currentEvent === "result") {
                  finalResult = parsed;
                } else if (currentEvent === "error") {
                  throw new Error(parsed.message || "PDF conversion failed.");
                }
              } catch (parseErr: any) {
                if (parseErr.message && !parseErr.message.includes("JSON")) {
                  throw parseErr;
                }
              }
              currentEvent = "";
            }
          }
        };

        while (true) {
          const { done, value } = await sseReader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          parseLines(lines);
        }

        if (buffer.trim()) {
          parseLines(buffer.split("\n"));
        }

        if (!finalResult || !finalResult.project_id) {
          throw new Error("Conversion finished but no project ID was received.");
        }

        setCurrentStep("done");
        setProgressPct(100);
        setStatusMessage("Project created successfully!");
        setConvertedProject(finalResult);
        toast.success("PDF converted into editable LaTeX project!");

        // Automatically open the new project
        setTimeout(() => {
          router.push(`/editor/${finalResult.project_id}`);
        }, 1200);

      } catch (err: any) {
        console.error("PDF Conversion Error:", err);
        setErrorMessage(err.message || "An unexpected error occurred during PDF conversion.");
        setIsConverting(false);
      }
    };

    reader.readAsDataURL(selectedFile);
  };

  const getStepStatus = (stepKey: StepKey) => {
    const order: StepKey[] = ["uploading", "analyzing", "extracting_assets", "generating_latex", "creating_project", "done"];
    const curIdx = order.indexOf(currentStep);
    const stepIdx = order.indexOf(stepKey);

    if (curIdx > stepIdx || currentStep === "done") return "completed";
    if (curIdx === stepIdx) return "active";
    return "pending";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/85 backdrop-blur-md animate-fade-in font-mono">
      <div className="max-w-xl w-[calc(100vw-2rem)] rounded-2xl border border-zinc-800 bg-zinc-950 text-white shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-zinc-800/80 flex items-center justify-between bg-zinc-900/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-[#00CC68]/15 border border-[#00CC68]/30 text-[#00CC68]">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-archivo font-black uppercase text-white tracking-wide">
                  PDF to Editable LaTeX
                </h3>
                <span className="text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-zinc-800 text-[#00CC68] border border-zinc-700 tracking-wider">
                  BETA
                </span>
              </div>
              <p className="text-xs text-zinc-400 font-sans">
                Convert any PDF paper, slides, resume, or report into compilable LaTeX with assets.
              </p>
            </div>
          </div>

          {!isConverting && (
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-5 space-y-5">
          {!isConverting && !convertedProject ? (
            <form onSubmit={handleStartConversion} className="space-y-4">
              {/* Dropzone */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                  isDragging
                    ? "border-[#00CC68] bg-[#00CC68]/10"
                    : selectedFile
                    ? "border-[#00CC68]/60 bg-zinc-900/80"
                    : "border-zinc-800 hover:border-zinc-700 bg-zinc-900/40"
                }`}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  accept=".pdf,application/pdf"
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      handleFileSelect(e.target.files[0]);
                    }
                  }}
                  className="hidden"
                />

                {selectedFile ? (
                  <div className="flex items-center justify-center gap-3">
                    <div className="p-2.5 rounded-xl bg-[#00CC68]/15 border border-[#00CC68]/40 text-[#00CC68]">
                      <FileCheck2 className="w-6 h-6" />
                    </div>
                    <div className="text-left truncate max-w-xs sm:max-w-sm">
                      <div className="text-xs font-bold text-white truncate">{selectedFile.name}</div>
                      <div className="text-[11px] text-zinc-400 font-sans">
                        {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • PDF Document
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedFile(null);
                      }}
                      className="ml-auto p-1.5 text-zinc-400 hover:text-rose-400 rounded-lg"
                      title="Remove PDF"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="mx-auto w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400">
                      <UploadCloud className="w-5 h-5 text-[#00CC68]" />
                    </div>
                    <div>
                      <span className="text-xs text-[#00CC68] font-bold">Click to upload</span>
                      <span className="text-xs text-zinc-400"> or drag and drop</span>
                    </div>
                    <p className="text-[11px] text-zinc-500 font-sans">
                      Articles, Research Papers, Beamer Slides, Resumes, or Reports (up to 50 pages)
                    </p>
                  </div>
                )}
              </div>

              {/* Project Name Input */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400 font-bold uppercase tracking-wider flex items-center justify-between">
                  <span>Project Name (Optional)</span>
                  <span className="text-[10px] text-zinc-500 font-normal">Auto-generated if blank</span>
                </label>
                <Input
                  placeholder=""
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="h-10 text-xs font-mono border-zinc-800 bg-zinc-900 text-white focus-visible:ring-2 focus-visible:ring-[#00CC68]"
                />
              </div>

              {/* Target Format / Document Class Selector */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400 font-bold uppercase tracking-wider">
                  Target LaTeX Template
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("auto")}
                    className={`px-3 py-2 rounded-xl text-xs font-mono font-bold border transition-all cursor-pointer ${
                      documentTypeHint === "auto"
                        ? "border-[#00CC68] bg-[#00CC68]/15 text-[#00CC68]"
                        : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-white"
                    }`}
                  >
                    Auto-Detect
                  </button>
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("beamer")}
                    className={`px-3 py-2 rounded-xl text-xs font-mono font-bold border transition-all cursor-pointer ${
                      documentTypeHint === "beamer"
                        ? "border-[#00CC68] bg-[#00CC68]/15 text-[#00CC68]"
                        : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-white"
                    }`}
                  >
                    Slides (Beamer)
                  </button>
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("report")}
                    className={`px-3 py-2 rounded-xl text-xs font-mono font-bold border transition-all cursor-pointer ${
                      documentTypeHint === "report"
                        ? "border-[#00CC68] bg-[#00CC68]/15 text-[#00CC68]"
                        : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-white"
                    }`}
                  >
                    Report / Thesis
                  </button>
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("article")}
                    className={`px-3 py-2 rounded-xl text-xs font-mono font-bold border transition-all cursor-pointer ${
                      documentTypeHint === "article"
                        ? "border-[#00CC68] bg-[#00CC68]/15 text-[#00CC68]"
                        : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-white"
                    }`}
                  >
                    Paper (Article)
                  </button>
                </div>
              </div>

              {/* Error Alert if any */}
              {errorMessage && (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <div className="font-sans leading-relaxed">{errorMessage}</div>
                </div>
              )}

              {/* Beta Notice Banner */}
              <div className="p-3 rounded-xl bg-zinc-900/70 border border-zinc-800 text-[11px] text-zinc-400 font-sans flex items-start gap-2.5">
                <span className="text-[#00CC68] font-mono font-bold text-[9px] px-1.5 py-0.5 rounded bg-[#00CC68]/15 border border-[#00CC68]/30 shrink-0">BETA</span>
                <div className="leading-relaxed">
                  PDF decompilation is currently in Beta. Scanned documents or complex layouts may have formatting differences. Found any issues or bugs? Please{" "}
                  <a
                    href="https://github.com/abin-karukappallil/overbranch/issues"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#00CC68] hover:underline font-bold"
                  >
                    report them on GitHub Issues →
                  </a>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2 pt-2 text-xs font-mono font-bold">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onClose}
                  className="h-9 px-4 text-xs border-zinc-800 text-zinc-300 hover:bg-zinc-900 rounded-xl"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={!selectedFile}
                  className="h-9 px-5 text-xs bg-[#00CC68] hover:bg-[#00E676] text-black font-bold border border-black shadow-[3px_3px_0px_0px_#000000] rounded-xl cursor-pointer disabled:opacity-50 transition-all flex items-center gap-2"
                >
                  <span>Start Conversion</span>
                  <span className="text-[9px] bg-black text-[#00CC68] px-1.5 py-0.5 rounded font-black">BETA</span>
                  <span>→</span>
                </Button>
              </div>
            </form>
          ) : (
            /* Progress Stepper Flow */
            <div className="space-y-6 py-2">
              {/* Progress bar */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-zinc-300 font-bold flex items-center gap-2">
                    {currentStep === "done" ? (
                      <CheckCircle2 className="w-4 h-4 text-[#00CC68]" />
                    ) : (
                      <Loader2 className="w-4 h-4 text-[#00CC68] animate-spin" />
                    )}
                    <span>{statusMessage || "Processing PDF..."}</span>
                  </span>
                  <span className="text-[#00CC68] font-bold">{progressPct}%</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full bg-[#00CC68] transition-all duration-300 rounded-full shadow-[0_0_10px_#00CC68]"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>

              {/* Steps List */}
              <div className="space-y-3 pt-2">
                {STEPS.map((step) => {
                  const st = getStepStatus(step.key);
                  const Icon = step.icon;

                  return (
                    <div
                      key={step.key}
                      className={`flex items-center justify-between p-3 rounded-xl border transition-all ${
                        st === "completed"
                          ? "border-[#00CC68]/30 bg-[#00CC68]/5 text-white"
                          : st === "active"
                          ? "border-[#00CC68] bg-zinc-900 text-white shadow-[0_0_12px_rgba(0,204,104,0.15)]"
                          : "border-zinc-800/60 bg-zinc-900/30 text-zinc-500"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`p-2 rounded-lg ${
                            st === "completed"
                              ? "bg-[#00CC68]/20 text-[#00CC68]"
                              : st === "active"
                              ? "bg-[#00CC68] text-black"
                              : "bg-zinc-800 text-zinc-500"
                          }`}
                        >
                          <Icon className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-xs font-bold font-archivo uppercase tracking-wide">
                            {step.label}
                          </div>
                          <div className="text-[11px] text-zinc-400 font-sans">
                            {step.description}
                          </div>
                        </div>
                      </div>

                      <div>
                        {st === "completed" && (
                          <CheckCircle2 className="w-4 h-4 text-[#00CC68]" />
                        )}
                        {st === "active" && (
                          <Loader2 className="w-4 h-4 text-[#00CC68] animate-spin" />
                        )}
                        {st === "pending" && (
                          <div className="w-2 h-2 rounded-full bg-zinc-700 mr-1" />
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Error during conversion */}
              {errorMessage && (
                <div className="space-y-3 pt-2">
                  <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2.5">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <div className="font-sans leading-relaxed">{errorMessage}</div>
                  </div>
                  <div className="flex justify-end">
                    <Button
                      onClick={() => {
                        setIsConverting(false);
                        setErrorMessage(null);
                      }}
                      className="h-8 text-xs bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg"
                    >
                      Try Again
                    </Button>
                  </div>
                </div>
              )}

              {/* Ready message */}
              {convertedProject && (
                <div className="p-3 rounded-xl bg-[#00CC68]/15 border border-[#00CC68]/40 text-[#00CC68] text-xs flex items-center justify-between font-mono font-bold">
                  <span>Project Created! Launching editor...</span>
                  <Button
                    size="sm"
                    onClick={() => router.push(`/editor/${convertedProject.project_id}`)}
                    className="h-7 text-xs bg-[#00CC68] text-black hover:bg-[#00E676] font-bold rounded-lg cursor-pointer"
                  >
                    <span>Open Now</span>
                    <ArrowRight className="w-3.5 h-3.5 ml-1" />
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
