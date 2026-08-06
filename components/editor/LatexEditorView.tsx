"use client";

import React, { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCode2,
  Folder,
  ChevronRight,
  ChevronDown,
  Plus,
  FilePlus,
  FolderPlus,
  Play,
  FileText,
  Search,
  ZoomIn,
  ZoomOut,
  Download,
  RotateCw,
  Sparkles,
  Users,
  Eye,
  Lock,
  Smartphone,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CompileToolbar } from "@/components/editor/CompileToolbar";
import { CollaboratorAvatars } from "@/components/editor/CollaboratorAvatars";
import { toast } from "sonner";

interface FileNode {
  id: string;
  name: string;
  type: "file" | "folder";
  children?: FileNode[];
  content?: string;
}

const initialFileTree: FileNode[] = [
  {
    id: "main.tex",
    name: "main.tex",
    type: "file",
    content: `\\documentclass[conference]{IEEEtran}
\\usepackage{cite}
\\usepackage{amsmath,amssymb,amsfonts}
\\usepackage{graphicx}

\\title{OverBranch: Mobile Collaborative LaTeX Platforms}

\\author{
  \\IEEEauthorblockN{Alice Vance\\mathbb{1}, Bob Chen\\mathbb{2}, Carol Zhang\\mathbb{1}}
  \\IEEEauthorblockA{\\mathbb{1}OverBranch Research, \\mathbb{2}Stanford Computer Science}
}

\\begin{document}
\\maketitle

\\begin{abstract}
We present OverBranch, a collaborative LaTeX platform designed for mobile phone co-editing, sub-10ms UI latency, and touch-optimized PDF recompilation.
\\end{abstract}

\\section{Introduction}
Scientific collaboration on mobile devices requires fast TeX symbol insertion and side-by-side paper rendering \\cite{vance2026overbranch}.

\\begin{equation}
\\mathcal{L}_{mobile} = \\min_{\\theta} \\sum_{i=1}^{N} \\| T_{compile} - T_{touch} \\|^2
\\end{equation}

\\section{Results}
Mobile co-authors can edit documents anywhere with full syntax support.

\\bibliographystyle{IEEEtran}
\\bibliography{references}
\\end{document}`,
  },
  {
    id: "sections",
    name: "sections",
    type: "folder",
    children: [
      { id: "abstract.tex", name: "abstract.tex", type: "file" },
      { id: "introduction.tex", name: "introduction.tex", type: "file" },
      { id: "results.tex", name: "results.tex", type: "file" },
    ],
  },
  {
    id: "figures",
    name: "figures",
    type: "folder",
    children: [
      { id: "architecture.png", name: "architecture.png", type: "file" },
      { id: "performance_chart.pdf", name: "performance_chart.pdf", type: "file" },
    ],
  },
  {
    id: "references.bib",
    name: "references.bib",
    type: "file",
    content: `@article{vance2026overbranch,
  author = {Vance, Alice and Chen, Bob},
  title = {Mobile Collaborative LaTeX Workspace Architecture},
  journal = {IEEE Transactions on Software Engineering},
  year = {2026}
}`,
  },
];

const quickTexSymbols = [
  { label: "\\begin", insert: "\\begin{equation}\n  \n\\end{equation}" },
  { label: "\\cite", insert: "\\cite{}" },
  { label: "\\ref", insert: "\\ref{}" },
  { label: "$...$", insert: "$ $" },
  { label: "\\sec", insert: "\\section{}" },
  { label: "\\pkg", insert: "\\usepackage{}" },
  { label: "{}", insert: "{}" },
  { label: "\\alpha", insert: "\\alpha" },
  { label: "\\sum", insert: "\\sum_{i=1}^{N}" },
];

export function LatexEditorView() {
  const [activeFileId, setActiveFileId] = useState("main.tex");
  const [editorContent, setEditorContent] = useState(initialFileTree[0].content || "");
  const [isCompiling, setIsCompiling] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [mobileMode, setMobileMode] = useState<"code" | "files" | "pdf" | "coauthors">("code");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleCompile = () => {
    setIsCompiling(true);
    setTimeout(() => {
      setIsCompiling(false);
      toast.success("LaTeX PDF compiled successfully with pdfLaTeX engine.");
    }, 1100);
  };

  const handleInsertSymbol = (snippet: string) => {
    if (!textareaRef.current) return;
    const start = textareaRef.current.selectionStart;
    const end = textareaRef.current.selectionEnd;
    const text = editorContent;
    const newText = text.substring(0, start) + snippet + text.substring(end);
    setEditorContent(newText);
    toast.info(`Inserted ${snippet.split("{")[0]}`);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-background overflow-hidden border border-border/60 rounded-2xl shadow-2xl relative">
      <div className="h-14 px-3 sm:px-4 border-b border-border/40 bg-card/60 backdrop-blur-xl flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
            <FileCode2 className="w-4 h-4 sm:w-5 sm:h-5" />
          </div>
          <div className="truncate">
            <div className="flex items-center gap-1.5">
              <h1 className="font-bold text-xs sm:text-sm text-foreground tracking-tight truncate">
                IEEE_Paper_OverBranch_v1.tex
              </h1>
              <span className="hidden sm:inline-block px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Mobile Ready
              </span>
            </div>
            <p className="text-[10px] text-muted-foreground font-mono truncate">IEEEtran · main.tex</p>
          </div>
        </div>

        <CollaboratorAvatars />
      </div>

      <CompileToolbar onCompile={handleCompile} isCompiling={isCompiling} />

      <div className="flex md:hidden items-center border-b border-border/40 bg-muted/40 p-1 gap-1 text-xs font-mono shrink-0">
        <button
          onClick={() => setMobileMode("code")}
          className={`flex-1 py-1.5 rounded-lg transition-colors flex items-center justify-center gap-1.5 ${
            mobileMode === "code" ? "bg-card text-foreground font-bold shadow-sm" : "text-muted-foreground"
          }`}
        >
          <FileCode2 className="w-3.5 h-3.5 text-indigo-400" />
          <span>TeX Code</span>
        </button>

        <button
          onClick={() => setMobileMode("pdf")}
          className={`flex-1 py-1.5 rounded-lg transition-colors flex items-center justify-center gap-1.5 ${
            mobileMode === "pdf" ? "bg-card text-foreground font-bold shadow-sm" : "text-muted-foreground"
          }`}
        >
          <Eye className="w-3.5 h-3.5 text-cyan-400" />
          <span>PDF Preview</span>
        </button>

        <button
          onClick={() => setMobileMode("files")}
          className={`flex-1 py-1.5 rounded-lg transition-colors flex items-center justify-center gap-1.5 ${
            mobileMode === "files" ? "bg-card text-foreground font-bold shadow-sm" : "text-muted-foreground"
          }`}
        >
          <Folder className="w-3.5 h-3.5 text-amber-400" />
          <span>Files</span>
        </button>
      </div>

      <div className="flex-1 grid grid-cols-1 md:grid-cols-12 overflow-hidden relative">
        <div
          className={`${
            mobileMode === "files" ? "flex" : "hidden"
          } md:flex md:col-span-2 border-r border-border/40 bg-muted/10 flex-col justify-between p-3 select-none text-xs h-full`}
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between text-muted-foreground uppercase font-mono text-[10px] tracking-wider font-semibold px-2">
              <span>Files & Assets</span>
              <div className="flex items-center gap-1">
                <button onClick={() => toast.info("New TeX File")} className="p-1 hover:text-foreground rounded">
                  <FilePlus className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="space-y-1 font-mono">
              {initialFileTree.map((item) => (
                <div key={item.id}>
                  {item.type === "file" ? (
                    <button
                      onClick={() => {
                        setActiveFileId(item.id);
                        if (item.content) setEditorContent(item.content);
                        setMobileMode("code");
                      }}
                      className={`w-full flex items-center gap-2 px-2 py-2 rounded-lg text-left transition-colors ${
                        activeFileId === item.id
                          ? "bg-indigo-500/10 text-indigo-400 font-semibold border border-indigo-500/20"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent/40"
                      }`}
                    >
                      <FileCode2 className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate">{item.name}</span>
                    </button>
                  ) : (
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 px-2 py-1 text-muted-foreground font-semibold">
                        <Folder className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                        <span>{item.name}</span>
                      </div>
                      <div className="pl-4 space-y-1">
                        {item.children?.map((child) => (
                          <button
                            key={child.id}
                            onClick={() => {
                              setActiveFileId(child.id);
                              setMobileMode("code");
                            }}
                            className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-[11px] text-muted-foreground hover:text-foreground"
                          >
                            <FileText className="w-3 h-3 shrink-0" />
                            <span className="truncate">{child.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div
          className={`${
            mobileMode === "code" ? "flex" : "hidden"
          } md:flex md:col-span-5 border-r border-border/40 flex-col bg-background/50 relative overflow-hidden h-full`}
        >
          <div className="h-8 px-3 border-b border-border/30 bg-muted/20 flex items-center justify-between text-xs font-mono text-muted-foreground shrink-0">
            <span className="text-foreground font-bold">{activeFileId}</span>
            <span className="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 text-[10px] flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping" />
              Alice Vance editing
            </span>
          </div>

          <div className="px-2 py-1 border-b border-border/30 bg-card/40 flex items-center gap-1.5 overflow-x-auto shrink-0 font-mono text-[11px]">
            <span className="text-[10px] text-muted-foreground uppercase px-1 font-semibold shrink-0">Quick TeX:</span>
            {quickTexSymbols.map((sym) => (
              <button
                key={sym.label}
                onClick={() => handleInsertSymbol(sym.insert)}
                className="px-2 py-1 rounded bg-muted/60 hover:bg-accent text-indigo-300 hover:text-white border border-border/40 shrink-0 transition-colors"
              >
                {sym.label}
              </button>
            ))}
          </div>

          <div className="flex-1 p-3 font-mono text-xs flex gap-3 overflow-y-auto leading-relaxed">
            <div className="select-none text-muted-foreground/40 text-right space-y-1 font-mono text-[11px]">
              {Array.from({ length: 28 }).map((_, i) => (
                <div key={i}>{i + 1}</div>
              ))}
            </div>

            <textarea
              ref={textareaRef}
              value={editorContent}
              onChange={(e) => setEditorContent(e.target.value)}
              inputMode="text"
              autoCapitalize="none"
              autoCorrect="off"
              className="w-full h-full bg-transparent text-foreground outline-none resize-none font-mono text-xs leading-relaxed selection:bg-indigo-500/30"
              spellCheck={false}
            />
          </div>
        </div>

        <div
          className={`${
            mobileMode === "pdf" ? "flex" : "hidden"
          } md:flex md:col-span-5 flex-col bg-muted/20 relative h-full`}
        >
          <div className="h-8 px-3 border-b border-border/30 bg-muted/30 flex items-center justify-between text-xs font-mono shrink-0">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Eye className="w-3.5 h-3.5 text-cyan-400" />
              <span>PDF Preview</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setZoomLevel(Math.max(70, zoomLevel - 15))} className="p-1 hover:text-foreground text-muted-foreground">
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="text-[10px] text-muted-foreground">{zoomLevel}%</span>
              <button onClick={() => setZoomLevel(Math.min(150, zoomLevel + 15))} className="p-1 hover:text-foreground text-muted-foreground">
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="flex-1 p-4 sm:p-6 overflow-y-auto flex justify-center bg-zinc-950/40 relative">
            {isCompiling && (
              <div className="absolute inset-0 z-20 bg-background/70 backdrop-blur-sm flex flex-col items-center justify-center gap-3">
                <RotateCw className="w-7 h-7 text-emerald-400 animate-spin" />
                <span className="text-xs font-mono text-emerald-400 font-semibold">Compiling TeX PDF...</span>
              </div>
            )}

            <div
              style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
              className="w-full max-w-lg bg-card border border-border/80 rounded-xl p-5 sm:p-8 shadow-2xl space-y-4 text-foreground text-left transition-all"
            >
              <div className="text-center space-y-1 border-b border-border/40 pb-3">
                <h2 className="text-sm sm:text-base font-extrabold tracking-tight font-serif leading-tight">
                  OverBranch: Mobile Collaborative LaTeX Platforms
                </h2>
                <p className="text-[10px] text-muted-foreground font-serif italic">
                  Alice Vance¹, Bob Chen², Carol Zhang¹
                </p>
              </div>

              <div className="space-y-1 text-xs leading-relaxed bg-muted/30 p-2.5 rounded-lg border border-border/40 font-serif">
                <span className="font-bold uppercase tracking-wider text-[9px] block font-sans text-indigo-400">
                  Abstract
                </span>
                <p className="text-[10px] sm:text-[11px] text-foreground/90">
                  We present OverBranch, a collaborative LaTeX platform designed for mobile phone co-editing, sub-10ms UI latency, and touch-optimized PDF recompilation.
                </p>
              </div>

              <div className="space-y-2 text-xs font-serif">
                <h3 className="font-bold text-xs uppercase font-sans text-foreground">
                  I. Introduction
                </h3>
                <p className="text-[10px] text-muted-foreground">
                  Scientific collaboration on mobile devices requires fast TeX symbol insertion and side-by-side paper rendering.
                </p>
                <div className="py-1.5 my-1 text-center bg-background/80 rounded border border-border/30 font-mono text-indigo-300 text-[10px]">
                  L_mobile = min_θ ∑ ‖ T_compile - T_touch ‖²
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button
        onClick={handleCompile}
        disabled={isCompiling}
        className="md:hidden fixed bottom-6 right-6 z-40 w-12 h-12 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 text-white flex items-center justify-center shadow-2xl shadow-emerald-500/40 active:scale-95 transition-transform"
        title="Quick Recompile PDF"
      >
        {isCompiling ? <RotateCw className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
      </button>
    </div>
  );
}
