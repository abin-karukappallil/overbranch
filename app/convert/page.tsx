"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  UploadCloud,
  FileText,
  Sparkles,
  Layers,
  Image as ImageIcon,
  FolderPlus,
  ArrowRight,
  ShieldCheck,
  Clock,
  AlertCircle,
  CheckCircle2,
  Lock,
  Zap,
  RotateCw,
  Terminal,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { authClient } from "@/lib/auth-client";
import { toast } from "sonner";

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

type StepKey = "uploading" | "analyzing" | "extracting_assets" | "generating_latex" | "creating_project" | "done";

interface StepConfig {
  key: StepKey;
  label: string;
  description: string;
  icon: any;
}

const STEPS: StepConfig[] = [
  { key: "uploading", label: "Upload & Verify", description: "Verifying document binary & establishing guest session", icon: UploadCloud },
  { key: "analyzing", label: "Layout Analysis", description: "PyMuPDF AST layout, font, math & block parsing", icon: Layers },
  { key: "extracting_assets", label: "Extract Assets", description: "Isolating embedded figures & tables to assets/", icon: ImageIcon },
  { key: "generating_latex", label: "Synthesize LaTeX", description: "Generating modular TeX code with auto-compilation check", icon: Sparkles },
  { key: "creating_project", label: "Workspace Ready", description: "Provisioning ephemeral workspace and SyncTeX map", icon: FolderPlus },
];

export default function ConvertPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [currentStep, setCurrentStep] = useState<StepKey>("uploading");
  const [statusMessage, setStatusMessage] = useState("");
  const [progressPct, setProgressPct] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [convertedResult, setConvertedResult] = useState<any | null>(null);

  // Authenticated user check: logged in users should use the dashboard converter
  const { data: authSession, isPending: isAuthPending } = authClient.useSession();

  useEffect(() => {
    if (!isAuthPending && authSession?.user) {
      router.replace("/dashboard?openPdfModal=true");
    }
  }, [authSession, isAuthPending, router]);

  // Session & Quota Status
  const [sessionLoading, setSessionLoading] = useState(true);
  const [quotaStatus, setQuotaStatus] = useState<any | null>(null);

  const fetchSessionStatus = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/guest/session`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setQuotaStatus(data);
        if (data.token) {
          document.cookie = `ob_guest_token=${data.token}; path=/; max-age=86400; SameSite=Lax`;
          localStorage.setItem("ob_guest_token", data.token);
        }
      }
    } catch (e) {
      console.warn("Could not load guest session:", e);
    } finally {
      setSessionLoading(false);
    }
  };

  useEffect(() => {
    fetchSessionStatus();
  }, []);

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
      const cleanName = file.name.replace(/\.pdf$/i, "").replace(/[^a-zA-Z0-9_\- ]/g, "_").trim();
      setProjectName(cleanName);
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
    setStatusMessage("Reading and validating document bytes...");

    const reader = new FileReader();
    reader.onerror = () => {
      setIsConverting(false);
      setErrorMessage("Failed to read local PDF file.");
    };

    reader.onload = async () => {
      const pdfBase64 = reader.result as string;

      try {
        const response = await fetch(`${BACKEND_URL}/api/guest/pdf/convert`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            pdf_data: pdfBase64,
            project_name: projectName.trim() || undefined,
          }),
        });

        if (!response.ok) {
          const errJson = await response.json().catch(() => ({ detail: "Conversion failed" }));
          throw new Error(errJson.detail || `Server responded with status ${response.status}`);
        }

        const sseReader = response.body?.getReader();
        if (!sseReader) throw new Error("No response stream available from server.");

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

        if (finalResult.guest_token) {
          document.cookie = `ob_guest_token=${finalResult.guest_token}; path=/; max-age=86400; SameSite=Lax`;
          localStorage.setItem("ob_guest_token", finalResult.guest_token);
        }

        setCurrentStep("done");
        setProgressPct(100);
        setStatusMessage("Project created successfully!");
        setConvertedResult(finalResult);
        toast.success("PDF successfully converted into editable LaTeX!");

        // Auto open generated project in guest editor
        setTimeout(() => {
          router.push(`/editor/${finalResult.project_id}`);
        }, 1200);

      } catch (err: any) {
        setIsConverting(false);
        setErrorMessage(err.message || "An unexpected error occurred during conversion.");
        toast.error(err.message || "Conversion failed");
        fetchSessionStatus();
      }
    };

    reader.readAsDataURL(selectedFile);
  };

  const isQuotaReached = quotaStatus && !quotaStatus.allowed;

  if (isAuthPending || authSession?.user) {
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center text-zinc-400 gap-3">
        <RotateCw className="w-6 h-6 animate-spin text-[#00CC68]" />
        <p className="text-xs font-mono">
          {authSession?.user ? "Redirecting to Dashboard PDF Workspace..." : "Verifying session..."}
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col selection:bg-[#00CC68]/30 selection:text-[#00CC68]">
      {/* Top Navigation */}
      <header className="h-16 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md px-4 sm:px-8 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 hover:opacity-90 transition-opacity">
            <OverBranchLogo size="sm" colored />
          </Link>
          <div className="h-4 w-px bg-zinc-800 hidden sm:block" />
          
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-xs font-mono text-zinc-400 hover:text-white transition-colors px-3 py-1.5 rounded-lg"
          >
            Sign In
          </Link>
          <Link
            href="/register"
            className="text-xs font-mono font-bold bg-[#00CC68] hover:bg-[#00E676] text-black px-4 py-2 rounded-xl shadow-[3px_3px_0px_0px_#000000] border border-black transition-all flex items-center gap-1.5"
          >
            <span>Create Account</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 flex flex-col justify-center">
        {/* Header Hero */}
        <div className="text-center space-y-3 mb-8">
         

          <h1 className="text-2xl sm:text-4xl font-archivo font-black uppercase tracking-tight text-white">
            Convert PDF Document to <span className="text-[#00CC68]">Editable LaTeX</span>
          </h1>

          <p className="text-xs sm:text-sm text-zinc-400 max-w-xl mx-auto font-sans leading-relaxed">
            Upload research papers, lecture slides, seminar reports, or resumes. Our neural pipeline analyzes layouts, extracts figures into assets, and generates compilable LaTeX with modular structure.
          </p>
        </div>

        {/* Existing Active Project Banner */}
        {quotaStatus?.active_project && !isConverting && (
          <div className="mb-6 p-4 rounded-2xl bg-zinc-900/90 border border-[#00CC68]/30 shadow-lg flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-left">
              <div className="p-2.5 rounded-xl bg-[#00CC68]/15 border border-[#00CC68]/30 text-[#00CC68]">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs font-mono text-[#00CC68] uppercase font-bold tracking-wider">
                  Active Guest Project Found
                </div>
                <div className="text-sm font-archivo font-bold text-white">
                  {quotaStatus.active_project.name}
                </div>
                <div className="text-[11px] text-zinc-400 font-mono">
                  Expires in ~{Math.ceil(quotaStatus.active_project.seconds_remaining / 3600)}h
                </div>
              </div>
            </div>

            <Link
              href={`/editor/${quotaStatus.active_project.project_id}`}
              className="w-full sm:w-auto px-4 py-2 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold text-xs rounded-xl shadow-[3px_3px_0px_0px_#000000] border border-black transition-all flex items-center justify-center gap-2"
            >
              <span>Resume in Editor</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>
        )}

        {/* Quota Exhausted Card */}
        {isQuotaReached && !isConverting ? (
          <div className="p-6 sm:p-8 rounded-3xl border border-amber-500/30 bg-zinc-900/90 shadow-2xl text-center space-y-5">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Clock className="w-7 h-7" />
            </div>

            <div className="space-y-2 max-w-md mx-auto">
              <h3 className="text-xl font-archivo font-black uppercase text-white">
                Daily Guest Limit Reached
              </h3>
              <p className="text-xs text-zinc-400 leading-relaxed font-sans">
                {quotaStatus?.reason || "Guest conversions are capped at 1 document per 24 hours per device to maintain GPU availability."}
              </p>
            </div>

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                href="/register"
                className="w-full sm:w-auto px-6 py-3 rounded-xl bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold text-xs uppercase tracking-wider shadow-[4px_4px_0px_0px_#000000] border border-black transition-all flex items-center justify-center gap-2"
              >
                <span>Create Free Account for Unlimited Access</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/login"
                className="w-full sm:w-auto px-5 py-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-mono text-xs border border-zinc-700 transition-colors"
              >
                Sign In
              </Link>
            </div>
          </div>
        ) : (
          /* Conversion Card */
          <div className="p-6 sm:p-8 rounded-3xl border border-zinc-800 bg-zinc-900/90 shadow-2xl space-y-6">
            {!isConverting ? (
              <form onSubmit={handleStartConversion} className="space-y-6">
                {/* Drag & Drop Area */}
                <div
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragging(false);
                    if (e.dataTransfer.files?.[0]) handleFileSelect(e.dataTransfer.files[0]);
                  }}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-3 ${
                    isDragging
                      ? "border-[#00CC68] bg-[#00CC68]/5 scale-[0.99]"
                      : selectedFile
                      ? "border-[#00CC68]/60 bg-[#00CC68]/5"
                      : "border-zinc-800 hover:border-zinc-700 bg-zinc-950/40 hover:bg-zinc-950/70"
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,application/pdf"
                    onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
                    className="hidden"
                  />

                  {selectedFile ? (
                    <div className="space-y-2">
                      <div className="w-12 h-12 mx-auto rounded-xl bg-[#00CC68]/20 border border-[#00CC68]/40 flex items-center justify-center text-[#00CC68]">
                        <FileText className="w-6 h-6 stroke-[2.5]" />
                      </div>
                      <div className="font-archivo font-bold text-white text-sm sm:text-base">
                        {selectedFile.name}
                      </div>
                      <div className="text-xs font-mono text-zinc-400">
                        {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB · Ready for conversion
                      </div>
                      <span className="inline-block text-[11px] font-mono text-[#00CC68] hover:underline pt-1">
                        Click to choose a different PDF
                      </span>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="w-12 h-12 mx-auto rounded-xl bg-zinc-800/80 border border-zinc-700 flex items-center justify-center text-zinc-400">
                        <UploadCloud className="w-6 h-6" />
                      </div>
                      <div className="font-archivo font-bold text-white text-sm sm:text-base">
                        Drop your PDF document here
                      </div>
                      <p className="text-xs text-zinc-400 font-sans">
                        Drag and drop or <span className="text-[#00CC68] underline font-medium">browse from your device</span>
                      </p>
                      <p className="text-[11px] font-mono text-zinc-400">
                        Max file size: 50MB · Up to 50 pages supported
                      </p>
                    </div>
                  )}
                </div>

                {/* Optional Project Name */}
                <div className="space-y-2">
                  <label className="text-xs font-mono font-bold text-zinc-300 uppercase tracking-wider block">
                    Workspace Project Name (Optional)
                  </label>
                  <Input
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="Enter a project name"
                    className="bg-zinc-950 border-zinc-800 text-white font-mono text-xs h-11 rounded-xl focus:border-[#00CC68]"
                  />
                </div>

                {errorMessage && (
                  <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2.5">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{errorMessage}</span>
                  </div>
                )}

                {/* Submit Action */}
                <Button
                  type="submit"
                  disabled={!selectedFile || isConverting}
                  size="lg"
                  className="w-full h-12 bg-[#00CC68] hover:bg-[#00E676] disabled:opacity-50 text-black font-mono font-bold uppercase tracking-wider text-xs rounded-xl shadow-[4px_4px_0px_0px_#000000] border border-black transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span>Start Free PDF to LaTeX Conversion</span>
                </Button>
              </form>
            ) : (
              /* Progress View */
              <div className="space-y-6 py-4">
                <div className="text-center space-y-2">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#00CC68]/15 border border-[#00CC68]/30 text-xs font-mono text-[#00CC68]">
                    <RotateCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Pipeline Active</span>
                  </div>
                  <h3 className="text-lg font-archivo font-bold text-white">
                    {STEPS.find((s) => s.key === currentStep)?.label || "Processing PDF"}
                  </h3>
                  <p className="text-xs font-mono text-zinc-400 max-w-md mx-auto">
                    {statusMessage || "Parsing structure, tables, and typography..."}
                  </p>
                </div>

                {/* Progress Bar */}
                <div className="space-y-1.5">
                  <div className="w-full h-2.5 rounded-full bg-zinc-950 border border-zinc-800 overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-[#00CC68] to-[#00E676]"
                      initial={{ width: "10%" }}
                      animate={{ width: `${progressPct}%` }}
                      transition={{ duration: 0.4 }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] font-mono text-zinc-400">
                    <span>PROGRESS</span>
                    <span>{progressPct}%</span>
                  </div>
                </div>

                {/* Step List */}
                <div className="space-y-2.5 pt-2">
                  {STEPS.map((step, idx) => {
                    const stepIdx = STEPS.findIndex((s) => s.key === currentStep);
                    const isPassed = stepIdx > idx || currentStep === "done";
                    const isCurrent = step.key === currentStep && currentStep !== "done";

                    return (
                      <div
                        key={step.key}
                        className={`p-3 rounded-xl border flex items-center justify-between gap-3 text-xs transition-all ${
                          isPassed
                            ? "bg-[#00CC68]/10 border-[#00CC68]/30 text-zinc-200"
                            : isCurrent
                            ? "bg-zinc-800/80 border-[#00CC68] text-white shadow-[0_0_15px_rgba(0,204,104,0.15)]"
                            : "bg-zinc-950/40 border-zinc-800/60 text-zinc-400 opacity-60"
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <step.icon className={`w-4 h-4 ${isPassed || isCurrent ? "text-[#00CC68]" : "text-zinc-400"}`} />
                          <span className="font-mono font-bold">{step.label}</span>
                          <span className="text-[11px] text-zinc-400 hidden sm:inline">— {step.description}</span>
                        </div>
                        <div>
                          {isPassed ? (
                            <CheckCircle2 className="w-4 h-4 text-[#00CC68]" />
                          ) : isCurrent ? (
                            <RotateCw className="w-3.5 h-3.5 text-[#00CC68] animate-spin" />
                          ) : (
                            <span className="text-[10px] font-mono text-zinc-400">WAITING</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Technical Architecture Guarantees */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-8">
          <div className="p-4 rounded-2xl border border-zinc-800/80 bg-zinc-900/50 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white">
              <Zap className="w-3.5 h-3.5 text-[#00CC68]" />
              <span>Native AST Extraction</span>
            </div>
            <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">
              Never rasterizes text into images. Headers, math formulas, and tabular structures are converted into authentic LaTeX environments.
            </p>
          </div>

          <div className="p-4 rounded-2xl border border-zinc-800/80 bg-zinc-900/50 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white">
              <ImageIcon className="w-3.5 h-3.5 text-[#00CC68]" />
              <span>Asset Preservation</span>
            </div>
            <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">
              Embedded figures and charts are cleanly extracted to the project assets folder with automatic resolution deduplication.
            </p>
          </div>

          <div className="p-4 rounded-2xl border border-zinc-800/80 bg-zinc-900/50 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white">
              <ShieldCheck className="w-3.5 h-3.5 text-[#00CC68]" />
              <span>Seamless Migration</span>
            </div>
            <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">
              Sign up at any time to automatically migrate your temporary guest project into your personal account with full edit history preserved.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
