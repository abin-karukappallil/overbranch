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
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden text-slate-100">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-tr from-cyan-600/30 to-blue-600/30 border border-cyan-500/30 text-cyan-400">
              <Sparkles className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-white flex items-center gap-2">
                Multimodal AI File Analyzer
                <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-700/50 text-cyan-300 font-mono">
                  Gemini Native
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Direct FILE + PROMPT analysis using Gemini Files API
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* Error Banner */}
          {errorMsg && (
            <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800/80 flex items-start gap-3 text-rose-200 text-sm">
              <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-semibold text-rose-300">Analysis Error</p>
                <p className="text-xs text-rose-200/90 mt-0.5">{errorMsg}</p>
              </div>
              <button
                onClick={() => setErrorMsg(null)}
                className="text-rose-400 hover:text-rose-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Step 1: Upload File Zone */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              1. Upload Document, Log, CSV, Image, Audio, or Video
            </label>

            {!selectedFile ? (
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleFileDrop}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-700 hover:border-cyan-500/60 bg-slate-950/40 hover:bg-slate-950/80 rounded-xl p-8 text-center cursor-pointer transition-all duration-200 flex flex-col items-center justify-center group"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <div className="p-3 rounded-full bg-slate-800 group-hover:bg-cyan-950/80 text-slate-400 group-hover:text-cyan-400 transition-colors mb-3">
                  <UploadCloud className="w-8 h-8" />
                </div>
                <p className="text-sm font-medium text-slate-200">
                  Drag and drop your file here, or <span className="text-cyan-400 underline">browse</span>
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Supports PDF, CSV, JSON, TXT, LOG, Images (PNG/JPG), Audio (MP3/WAV), Video (MP4/WEBM) up to 200MB
                </p>
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-700 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                    {getFileIcon(selectedFile)}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-200 truncate max-w-md">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-slate-400 flex items-center gap-2 font-mono">
                      <span>{selectedFile.type || "application/octet-stream"}</span>
                      <span>•</span>
                      <span>{formatFileSize(selectedFile.size)}</span>
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedFile(null)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors text-xs flex items-center gap-1"
                >
                  <X className="w-4 h-4" /> Change File
                </button>
              </div>
            )}
          </div>

          {/* Step 2: Custom User Prompt & Presets */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                2. User Instructions / Custom Prompt
              </label>

              {/* Model Selector */}
              <div className="flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1 focus:outline-none focus:border-cyan-500 font-mono"
                >
                  <option value="openai/gpt-oss-120b">GPT-120B OSS (Groq API 1)</option>
                  <option value="openai/gpt-oss-120b-fallback-2">GPT-120B OSS (Groq API 2 Fallback)</option>
                  <option value="openai/gpt-oss-120b-fallback-3">GPT-120B OSS (Groq API 3 Fallback)</option>
                </select>
              </div>
            </div>

            {/* Quick Prompt Presets */}
            <div className="flex flex-wrap gap-2 mb-3">
              {PRESET_PROMPTS.map((preset, idx) => (
                <button
                  key={idx}
                  onClick={() => setUserPrompt(preset.prompt)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-cyan-950 border border-slate-700/60 hover:border-cyan-700/60 text-slate-300 hover:text-cyan-300 transition-all flex items-center gap-1.5"
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
              placeholder="Describe what you want Gemini to analyze in this file (e.g. 'Analyze this report and identify suspicious network behavior')..."
              rows={3}
              className="w-full bg-slate-950/90 border border-slate-700/80 focus:border-cyan-500 rounded-xl p-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all font-sans"
            />
          </div>

          {/* Streaming Output / Analysis Result Window */}
          {(isAnalyzing || streamText || analysisResult) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-cyan-400" />
                  AI File Analysis Output
                </span>

                <div className="flex items-center gap-2">
                  {analysisResult?.usage && (
                    <div className="flex items-center gap-2 text-[11px] font-mono bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 text-slate-400">
                      <span>Prompt: {analysisResult.usage.promptTokens ?? 0}</span>
                      <span>•</span>
                      <span>Response: {analysisResult.usage.candidatesTokens ?? 0}</span>
                      <span>•</span>
                      <span className="text-cyan-400 font-semibold">Total: {analysisResult.usage.totalTokens ?? 0}</span>
                    </div>
                  )}

                  <button
                    onClick={handleCopyText}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-white bg-slate-800/80 hover:bg-slate-800 transition-colors text-xs flex items-center gap-1"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
              </div>

              <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 min-h-[160px] max-h-[300px] overflow-y-auto font-sans text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">
                {streamText || analysisResult?.analysis || (
                  <div className="flex items-center gap-2 text-slate-400 py-8 justify-center">
                    <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
                    <span>Uploading file to Gemini Files API & analyzing...</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800/80 rounded-xl transition-colors"
          >
            Close
          </button>

          <div className="flex items-center gap-3">
            {isAnalyzing ? (
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-sm bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-200 rounded-xl transition-all flex items-center gap-2"
              >
                <X className="w-4 h-4" /> Cancel Analysis
              </button>
            ) : (
              <button
                onClick={handleStartAnalysis}
                disabled={!selectedFile || !userPrompt.trim()}
                className="px-6 py-2 text-sm font-semibold bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl shadow-lg shadow-cyan-600/20 transition-all flex items-center gap-2"
              >
                <Send className="w-4 h-4" /> Start File Analysis
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};
