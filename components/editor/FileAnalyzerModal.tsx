"use me";
"use client";

import React, { useState, useRef } from "react";
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  FileCode,
  Image as ImageIcon,
  Music,
  Video,
  Sparkles,
  X,
  Send,
  Loader2,
  Check,
  Copy,
  Cpu,
  AlertTriangle,
  RefreshCw,
  Zap,
  ShieldAlert,
  FileCheck
} from "lucide-react";
import { analyzeFile, FileAnalysisResponse, FileAnalysisUsage } from "@/lib/ai-file-analysis";

interface FileAnalyzerModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialFile?: File | null;
}

const PRESET_PROMPTS = [
  { label: "Summarize Document", prompt: "Summarize this document and highlight key takeaways.", icon: "📄" },
  { label: "Find Anomalies", prompt: "Find anomalies, outliers, and suspicious data points in this dataset.", icon: "🔍" },
  { label: "Security Audit", prompt: "Perform a security analysis on this file and identify any suspicious network or system behavior.", icon: "🛡️" },
  { label: "Explain Suspicious Log Events", prompt: "Explain the suspicious events, error patterns, and root causes found in this log file.", icon: "⚠️" },
  { label: "Identify Objects & Details", prompt: "Identify objects, visual patterns, and security-relevant details in this file.", icon: "👁️" },
  { label: "Audio/Video Analysis", prompt: "Analyze this recording and identify important events, spoken context, and key timestamps.", icon: "🎥" },
];

export const FileAnalyzerModal: React.FC<FileAnalyzerModalProps> = ({
  isOpen,
  onClose,
  initialFile = null,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(initialFile);
  const [userPrompt, setUserPrompt] = useState<string>("");
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [streamText, setStreamText] = useState<string>("");
  const [analysisResult, setAnalysisResult] = useState<FileAnalysisResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [selectedModel, setSelectedModel] = useState<string>("openai/gpt-oss-120b");

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  if (!isOpen) return null;

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setSelectedFile(e.dataTransfer.files[0]);
      setErrorMsg(null);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setErrorMsg(null);
    }
  };

  const handleStartAnalysis = async () => {
    if (!selectedFile) {
      setErrorMsg("Please select or upload a file first.");
      return;
    }
    if (!userPrompt.trim()) {
      setErrorMsg("Please enter a custom prompt for analyzing the file.");
      return;
    }

    setIsAnalyzing(true);
    setErrorMsg(null);
    setStreamText("");
    setAnalysisResult(null);

    abortControllerRef.current = new AbortController();

    try {
      const result = await analyzeFile({
        file: selectedFile,
        prompt: userPrompt.trim(),
        model: selectedModel,
        stream: true,
        onChunk: (chunkText) => {
          setStreamText((prev) => prev + chunkText);
        },
        signal: abortControllerRef.current.signal,
      });

      setAnalysisResult(result);
    } catch (err: any) {
      if (err.name !== "AbortError") {
        setErrorMsg(err.message || "An error occurred during file analysis.");
      }
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsAnalyzing(false);
  };

  const handleCopyText = () => {
    const textToCopy = analysisResult?.analysis || streamText;
    if (textToCopy) {
      navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const getFileIcon = (file: File) => {
    const type = file.type.toLowerCase();
    const name = file.name.toLowerCase();
    if (type.includes("pdf") || name.endsWith(".pdf")) return <FileText className="w-8 h-8 text-red-400" />;
    if (type.includes("csv") || name.endsWith(".csv")) return <FileSpreadsheet className="w-8 h-8 text-emerald-400" />;
    if (type.includes("image")) return <ImageIcon className="w-8 h-8 text-blue-400" />;
    if (type.includes("audio")) return <Music className="w-8 h-8 text-purple-400" />;
    if (type.includes("video")) return <Video className="w-8 h-8 text-amber-400" />;
    return <FileCode className="w-8 h-8 text-cyan-400" />;
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4 animate-in fade-in duration-200 font-sans">
      <div className="bg-[#141519] border border-[#282A30] rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden text-[#E2E4E9]">
        
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-[#282A30] flex items-center justify-between bg-[#1A1C22]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#22242C] border border-[#282A30] flex items-center justify-center text-[#10B981]">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-archivo font-bold tracking-tight text-[#E2E4E9] flex items-center gap-2">
                Multimodal AI File Analyzer
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#22242C] border border-[#282A30] text-[#9E9E9E] font-mono">
                  Gemini Native
                </span>
              </h2>
              <p className="text-[11px] text-[#9E9E9E]">
                Direct file & context analysis via Gemini Files API
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded text-[#9E9E9E] hover:text-[#E2E4E9] hover:bg-[#22242C] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">

          {/* Error Banner */}
          {errorMsg && (
            <div className="p-3.5 rounded-lg bg-[#EB5757]/10 border border-[#EB5757]/30 flex items-start gap-3 text-[#FF8585] text-xs font-mono">
              <ShieldAlert className="w-4 h-4 text-[#EB5757] shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-semibold text-[#FF8585]">Analysis Error</p>
                <p className="text-[11px] text-[#FF8585]/90 mt-0.5">{errorMsg}</p>
              </div>
              <button
                onClick={() => setErrorMsg(null)}
                className="text-[#FF8585] hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Step 1: Upload File Zone */}
          <div>
            <label className="block text-[11px] font-archivo font-bold uppercase tracking-wider text-[#9E9E9E] mb-2">
              1. Upload Document, Log, CSV, Image, Audio, or Video
            </label>

            {!selectedFile ? (
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleFileDrop}
                onClick={() => fileInputRef.current?.click()}
                className="border border-dashed border-[#282A30] hover:border-[#282A30] bg-[#1A1C22] hover:bg-[#22242C] rounded-xl p-8 text-center cursor-pointer transition-all duration-200 flex flex-col items-center justify-center group"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <div className="p-3 rounded-lg bg-[#141519] group-hover:bg-[#22242C] text-[#9E9E9E] group-hover:text-[#10B981] border border-[#282A30] transition-colors mb-2.5">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <p className="text-xs font-medium text-[#E2E4E9]">
                  Drag and drop your file here, or <span className="text-[#10B981] underline">browse</span>
                </p>
                <p className="text-[10px] text-[#62666D] mt-1 font-mono">
                  Supports PDF, CSV, JSON, TXT, LOG, Images, Audio, Video up to 200MB
                </p>
              </div>
            ) : (
              <div className="p-3.5 rounded-xl bg-[#1A1C22] border border-[#282A30] flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-[#141519] border border-[#282A30]">
                    {getFileIcon(selectedFile)}
                  </div>
                  <div>
                    <p className="text-xs font-medium text-[#E2E4E9] truncate max-w-md">
                      {selectedFile.name}
                    </p>
                    <p className="text-[10px] text-[#9E9E9E] flex items-center gap-2 font-mono mt-0.5">
                      <span>{selectedFile.type || "application/octet-stream"}</span>
                      <span>•</span>
                      <span>{formatFileSize(selectedFile.size)}</span>
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedFile(null)}
                  className="p-1.5 rounded-lg text-[#9E9E9E] hover:text-[#EB5757] hover:bg-[#22242C] transition-colors text-xs flex items-center gap-1 font-mono"
                >
                  <X className="w-3.5 h-3.5" /> Change File
                </button>
              </div>
            )}
          </div>

          {/* Step 2: Custom User Prompt & Presets */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[11px] font-archivo font-bold uppercase tracking-wider text-[#9E9E9E]">
                2. User Instructions / Custom Prompt
              </label>

              {/* Model Selector */}
              <div className="flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-[#10B981]" />
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="bg-[#1A1C22] border border-[#282A30] text-[#E2E4E9] text-[11px] rounded-lg px-2 py-1 focus:outline-none focus:border-[#282A30] font-mono"
                >
                  <option value="openai/gpt-oss-120b">GPT-120B OSS (Groq API 1)</option>
                  <option value="openai/gpt-oss-120b-fallback-2">GPT-120B OSS (Groq API 2 Fallback)</option>
                  <option value="openai/gpt-oss-120b-fallback-3">GPT-120B OSS (Groq API 3 Fallback)</option>
                </select>
              </div>
            </div>

            {/* Quick Prompt Presets */}
            <div className="flex flex-wrap gap-1.5 mb-2.5">
              {PRESET_PROMPTS.map((preset, idx) => (
                <button
                  key={idx}
                  onClick={() => setUserPrompt(preset.prompt)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-[#1A1C22] hover:bg-[#22242C] border border-[#282A30] text-[#9E9E9E] hover:text-[#E2E4E9] transition-all flex items-center gap-1.5 cursor-pointer font-mono"
                >
                  <span>{preset.icon}</span>
                  <span>{preset.label}</span>
                </button>
              ))}
            </div>

            {/* Custom Textarea Prompt */}
            <textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="Describe what you want to analyze in this file (e.g. 'Analyze this report and identify key structural takeaways')..."
              rows={3}
              className="w-full bg-[#1A1C22] border border-[#282A30] focus:border-[#282A30] rounded-xl p-3 text-xs text-[#E2E4E9] placeholder-[#62666D] focus:outline-none focus:ring-1 focus:ring-[#282A30] transition-all font-sans resize-none"
            />
          </div>

          {/* Streaming Output / Analysis Result Window */}
          {(isAnalyzing || streamText || analysisResult) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-archivo font-bold uppercase tracking-wider text-[#9E9E9E] flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-[#10B981]" />
                  AI File Analysis Output
                </span>

                <div className="flex items-center gap-2">
                  {analysisResult?.usage && (
                    <div className="flex items-center gap-2 text-[10px] font-mono bg-[#1A1C22] px-2 py-0.5 rounded border border-[#282A30] text-[#9E9E9E]">
                      <span>Prompt: {analysisResult.usage.promptTokens ?? 0}</span>
                      <span>•</span>
                      <span>Response: {analysisResult.usage.candidatesTokens ?? 0}</span>
                      <span>•</span>
                      <span className="text-[#10B981] font-semibold">Total: {analysisResult.usage.totalTokens ?? 0}</span>
                    </div>
                  )}

                  <button
                    onClick={handleCopyText}
                    className="p-1 rounded text-[#9E9E9E] hover:text-white bg-[#1A1C22] hover:bg-[#22242C] border border-[#282A30] transition-colors text-xs flex items-center gap-1 font-mono"
                  >
                    {copied ? <Check className="w-3 h-3 text-[#10B981]" /> : <Copy className="w-3 h-3" />}
                    <span>{copied ? "Copied" : "Copy"}</span>
                  </button>
                </div>
              </div>

              <div className="bg-[#0E0F12] border border-[#282A30] rounded-xl p-4 min-h-[140px] max-h-[280px] overflow-y-auto font-sans text-xs text-[#E2E4E9] leading-relaxed whitespace-pre-wrap">
                {streamText || analysisResult?.analysis || (
                  <div className="flex items-center gap-2 text-[#9E9E9E] py-6 justify-center font-mono">
                    <Loader2 className="w-4 h-4 animate-spin text-[#10B981]" />
                    <span>Uploading file to Gemini Files API & analyzing...</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-5 py-3 border-t border-[#282A30] bg-[#0E0F12] flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-[#9E9E9E] hover:text-white hover:bg-[#1A1C22] rounded-lg transition-colors cursor-pointer font-mono"
          >
            Close
          </button>

          <div className="flex items-center gap-2 font-mono">
            {isAnalyzing ? (
              <button
                onClick={handleCancel}
                className="px-3 py-1.5 text-xs bg-[#1A1C22] hover:bg-[#22242C] border border-[#282A30] text-[#EB5757] rounded-lg transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" /> Cancel Analysis
              </button>
            ) : (
              <button
                onClick={handleStartAnalysis}
                disabled={!selectedFile || !userPrompt.trim()}
                className="px-4 py-1.5 text-xs font-archivo font-bold bg-[#22242C] hover:bg-[#2A2C36] disabled:opacity-40 disabled:cursor-not-allowed text-[#E2E4E9] border border-[#282A30] rounded-lg transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Send className="w-3.5 h-3.5 text-[#10B981]" /> Start File Analysis
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};
