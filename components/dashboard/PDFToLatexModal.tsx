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
import { authFetch } from "@/lib/api-client";

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
        // Resolve authenticated user ID reliably
        let userId = session?.user?.id;
        if (!userId) {
          try {
            const currentSession = await authClient.getSession();
            userId = currentSession?.data?.user?.id;
          } catch (_) {}
        }

        // Clean up any stale guest tokens for logged-in users so project ownership is crystal clear
        if (userId) {
          try {
            localStorage.removeItem("ob_guest_token");
            document.cookie = "ob_guest_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
          } catch (_) {}
        }

        const endpoint = userId ? `${BACKEND_URL}/api/pdf/convert` : `${BACKEND_URL}/api/guest/pdf/convert`;
        const response = await authFetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(userId ? { "X-User-Id": userId } : {}),
          },
          body: JSON.stringify({
            pdf_data: pdfBase64,
            project_name: projectName.trim() || undefined,
            user_id: userId,
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
        let currentEvent = "";

        const parseLines = (lines: string[]) => {
          for (const line of lines) {
            const trimmed = line.replace(/\r$/, "");
            if (trimmed.startsWith("event: ")) {
              currentEvent = trimmed.slice(7).trim();
            } else if (trimmed.startsWith("data: ")) {
              const raw = trimmed.slice(6);
              try {
                const parsed = JSON.parse(raw);
                const projId = parsed.project_id || parsed.data?.project_id || parsed.result?.project_id;
                if (projId) {
                  finalResult = { ...(finalResult || {}), ...parsed, project_id: projId };
                }

                if (currentEvent === "progress" || parsed.step) {
                  if (parsed.step) {
                    if (parsed.step.includes("analyz")) setCurrentStep("analyzing");
                    else if (parsed.step.includes("asset")) setCurrentStep("extracting_assets");
                    else if (parsed.step.includes("latex") || parsed.step.includes("compil") || parsed.step.includes("repair")) setCurrentStep("generating_latex");
                    else if (parsed.step.includes("creat")) setCurrentStep("creating_project");
                    else if (parsed.step === "done") setCurrentStep("done");
                  }
                  if (parsed.message) setStatusMessage(parsed.message);
                  if (parsed.pct) setProgressPct(parsed.pct);
                }
                
                if (currentEvent === "result" || (parsed.success && projId)) {
                  finalResult = { ...(finalResult || {}), ...parsed, ...(projId ? { project_id: projId } : {}) };
                } else if (currentEvent === "error" || parsed.type === "error" || (parsed.error && !parsed.step)) {
                  throw new Error(parsed.message || parsed.error || (typeof parsed === "string" ? parsed : "PDF conversion failed."));
                }
              } catch (parseErr: any) {
                if (parseErr.message && !parseErr.message.includes("JSON")) {
                  throw parseErr;
                }
              }
            } else if (trimmed === "") {
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

        if (finalResult.guest_token) {
          document.cookie = `ob_guest_token=${finalResult.guest_token}; path=/; max-age=86400; SameSite=Lax`;
          localStorage.setItem("ob_guest_token", finalResult.guest_token);
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/85 backdrop-blur-md animate-fade-in font-sans">
      <div className="max-w-xl w-[calc(100vw-2rem)] rounded-xl border border-[#23252A] bg-[#0F1011] text-[#F7F8F8] shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-[#23252A] flex items-center justify-between bg-[#0F1011]">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#5E6AD2]/12 border border-[#5E6AD2]/25 text-[#5E6AD2]">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold uppercase text-[#F7F8F8] tracking-wide">
                  PDF to Editable LaTeX
                </h3>
                <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-[#191A1B] text-[#5E6AD2] border border-[#23252A] tracking-wider">
                  BETA
                </span>
              </div>
              <p className="text-xs text-[#8A8F98]">
                Convert any PDF paper, slides, resume, or report into compilable LaTeX with assets.
              </p>
            </div>
          </div>

          {!isConverting && (
            <button
              onClick={onClose}
              className="p-1.5 text-[#8A8F98] hover:text-[#F7F8F8] rounded-md hover:bg-[#191A1B] transition-colors cursor-pointer"
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
                className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                  isDragging
                    ? "border-[#5E6AD2] bg-[#5E6AD2]/10"
                    : selectedFile
                    ? "border-[#5E6AD2]/50 bg-[#191A1B]"
                    : "border-[#23252A] hover:border-[#3B3D45] bg-[#191A1B]/40"
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
                    <div className="p-2.5 rounded-lg bg-[#5E6AD2]/15 border border-[#5E6AD2]/30 text-[#5E6AD2]">
                      <FileCheck2 className="w-5 h-5" />
                    </div>
                    <div className="text-left truncate max-w-xs sm:max-w-sm">
                      <div className="text-xs font-semibold text-[#F7F8F8] truncate">{selectedFile.name}</div>
                      <div className="text-[11px] text-[#8A8F98]">
                        {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • PDF Document
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedFile(null);
                      }}
                      className="ml-auto p-1.5 text-[#8A8F98] hover:text-rose-400 rounded-md"
                      title="Remove PDF"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="mx-auto w-9 h-9 rounded-lg bg-[#191A1B] border border-[#23252A] flex items-center justify-center text-[#8A8F98]">
                      <UploadCloud className="w-4 h-4 text-[#5E6AD2]" />
                    </div>
                    <div>
                      <span className="text-xs text-[#5E6AD2] font-semibold">Click to upload</span>
                      <span className="text-xs text-[#8A8F98]"> or drag and drop</span>
                    </div>
                    <p className="text-[11px] text-[#62666D]">
                      Articles, Research Papers, Beamer Slides, Resumes, or Reports (up to 50 pages)
                    </p>
                  </div>
                )}
              </div>

              {/* Project Name Input */}
              <div className="space-y-1.5">
                <label className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider flex items-center justify-between">
                  <span>Project Name (Optional)</span>
                  <span className="text-[10px] text-[#62666D] font-normal font-sans">Auto-generated if blank</span>
                </label>
                <Input
                  placeholder="e.g. My Converted Paper"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="h-9 text-xs border-[#23252A] bg-[#191A1B] text-[#F7F8F8] placeholder:text-[#62666D] focus-visible:ring-1 focus-visible:ring-[#5E6AD2] rounded-md"
                />
              </div>

              {/* Target Format / Document Class Selector */}
              <div className="space-y-1.5">
                <label className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider">
                  Target LaTeX Template
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("auto")}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors cursor-pointer ${
                      documentTypeHint === "auto"
                        ? "border-[#5E6AD2]/50 bg-[#5E6AD2]/12 text-[#F7F8F8]"
                        : "border-[#23252A] bg-[#191A1B] text-[#8A8F98] hover:text-[#F7F8F8]"
                    }`}
                  >
                    Auto-Detect
                  </button>
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("beamer")}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors cursor-pointer ${
                      documentTypeHint === "beamer"
                        ? "border-[#5E6AD2]/50 bg-[#5E6AD2]/12 text-[#F7F8F8]"
                        : "border-[#23252A] bg-[#191A1B] text-[#8A8F98] hover:text-[#F7F8F8]"
                    }`}
                  >
                    Slides (Beamer)
                  </button>
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("report")}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors cursor-pointer ${
                      documentTypeHint === "report"
                        ? "border-[#5E6AD2]/50 bg-[#5E6AD2]/12 text-[#F7F8F8]"
                        : "border-[#23252A] bg-[#191A1B] text-[#8A8F98] hover:text-[#F7F8F8]"
                    }`}
                  >
                    Report / Thesis
                  </button>
                  <button
                    type="button"
                    onClick={() => setDocumentTypeHint("article")}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors cursor-pointer ${
                      documentTypeHint === "article"
                        ? "border-[#5E6AD2]/50 bg-[#5E6AD2]/12 text-[#F7F8F8]"
                        : "border-[#23252A] bg-[#191A1B] text-[#8A8F98] hover:text-[#F7F8F8]"
                    }`}
                  >
                    Paper (Article)
                  </button>
                </div>
              </div>

              {/* Error Alert if any */}
              {errorMessage && (
                <div className="p-3 rounded-md bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <div className="leading-relaxed">{errorMessage}</div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2 pt-2 text-xs">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onClose}
                  className="h-8 px-3 text-xs border-[#23252A] bg-[#191A1B] text-[#8A8F98] hover:text-[#F7F8F8] hover:bg-[#23252A] rounded-md"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={!selectedFile}
                  className="h-8 px-4 text-xs bg-[#5E6AD2] hover:bg-[#4F5BBE] text-white font-medium rounded-md cursor-pointer disabled:opacity-50 transition-colors flex items-center gap-1.5"
                >
                  <span>Decompile PDF</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </form>
          ) : (
            /* Conversion in progress / Finished state */
            <div className="space-y-5 py-2">
              {/* Progress bar */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-[#F7F8F8] flex items-center gap-2">
                    {isConverting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-[#5E6AD2]" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#00FF05]" />
                    )}
                    <span>{statusMessage || "Processing document..."}</span>
                  </span>
                  <span className="font-mono text-xs text-[#8A8F98]">{progressPct}%</span>
                </div>
                <div className="h-1.5 w-full bg-[#191A1B] rounded-full overflow-hidden border border-[#23252A]">
                  <div
                    className="h-full bg-[#5E6AD2] transition-all duration-300 rounded-full"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>

              {/* Steps timeline */}
              <div className="space-y-2">
                {STEPS.map((step) => {
                  const status = getStepStatus(step.key);
                  const Icon = step.icon;
                  return (
                    <div
                      key={step.key}
                      className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                        status === "active"
                          ? "bg-[#5E6AD2]/10 border-[#5E6AD2]/30 text-[#F7F8F8]"
                          : status === "completed"
                          ? "bg-[#191A1B]/60 border-[#23252A] text-[#F7F8F8]"
                          : "bg-transparent border-[#23252A]/50 text-[#62666D]"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`p-1.5 rounded-md ${
                            status === "completed"
                              ? "bg-[#00FF05]/15 text-[#00FF05]"
                              : status === "active"
                              ? "bg-[#5E6AD2] text-white"
                              : "bg-[#191A1B] text-[#62666D]"
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <div className="text-xs font-medium text-[#F7F8F8]">
                            {step.label}
                          </div>
                          <div className="text-[11px] text-[#8A8F98]">
                            {step.description}
                          </div>
                        </div>
                      </div>

                      <div>
                        {status === "completed" && (
                          <CheckCircle2 className="w-4 h-4 text-[#00FF05]" />
                        )}
                        {status === "active" && (
                          <Loader2 className="w-4 h-4 text-[#5E6AD2] animate-spin" />
                        )}
                        {status === "pending" && (
                          <div className="w-1.5 h-1.5 rounded-full bg-[#23252A] mr-1" />
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
                <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/40 text-emerald-500 text-xs flex items-center justify-between font-mono font-bold">
                  <span>Project Created! Launching editor...</span>
                  <Button
                    size="sm"
                    onClick={() => router.push(`/editor/${convertedProject.project_id}`)}
                    className="h-7 text-xs bg-emerald-600 text-white hover:bg-emerald-500 font-bold rounded-lg cursor-pointer"
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
