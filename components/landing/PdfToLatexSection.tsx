"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  FileCode,
  Terminal,
  ArrowRight,
  FolderTree,
  FileCheck2,
  HardDrive,
  Cpu,
  Layers,
} from "lucide-react";

export function LandingPdfToLatex() {
  const [activeTab, setActiveTab] = useState<"code" | "assets" | "bib">("code");

  return (
    <section
      id="pdf-to-latex"
      className="bg-black text-white py-24 px-4 sm:px-8 lg:px-16 border-b-2 border-white/20 select-none relative"
    >
      <div className="max-w-7xl mx-auto space-y-14">
        {/* Section Header - Direct, Technical, Anti-Slop */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div className="space-y-3 max-w-3xl">
            <div className="inline-flex items-center gap-2 font-mono text-xs sm:text-sm font-bold text-[#00CC68] tracking-widest uppercase">
              <Terminal className="w-4 h-4 text-[#00CC68]" />
              <span>02 // PDF DECOMPILER</span>
            </div>
            <h2 className="font-archivo font-black uppercase text-3xl sm:text-5xl lg:text-7xl text-white tracking-[-0.04em] leading-[0.92]">
              DECOMPILE PDFS INTO REAL LATEX.
            </h2>
            <p className="font-sans text-base sm:text-xl text-zinc-300 leading-relaxed pt-2">
              Stop re-typing papers by hand. Upload any paper, thesis, or problem set and get a clean, compilable project directory with native math environments and extracted assets.
            </p>
          </div>

          <Link
            href="/dashboard"
            className="inline-flex items-center gap-3 bg-[#00CC68] text-black px-6 py-3.5 rounded-full font-mono text-xs sm:text-sm font-bold uppercase tracking-wider border-2 border-black shadow-[4px_4px_0px_0px_#ffffff] hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none transition-all duration-150 shrink-0 self-start md:self-end"
          >
            <span>DECOMPILE A PDF</span>
            <ArrowRight className="w-4 h-4 stroke-[3]" />
          </Link>
        </div>

        {/* Technical Workbench Preview */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-stretch font-mono">
          {/* Left Column: Extraction Telemetry & Stream Analysis */}
          <div className="lg:col-span-5 bg-zinc-950 border-2 border-white/20 p-6 rounded-2xl flex flex-col justify-between space-y-6 shadow-xl">
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2 text-xs font-bold text-[#00CC68] uppercase">
                  <Cpu className="w-4 h-4" />
                  <span>PARSER PIPELINE</span>
                </div>
                <span className="text-[11px] text-zinc-500 font-bold">
                  PyMuPDF v1.24
                </span>
              </div>

              {/* Source Document File Information */}
              <div className="bg-black border border-white/15 p-4 rounded-xl space-y-2">
                <div className="text-xs text-zinc-400 uppercase tracking-wider">Source Artifact</div>
                <div className="text-sm font-bold text-white truncate">
                  arxiv_2403.08912_distributed_consensus.pdf
                </div>
                <div className="flex flex-wrap gap-2 pt-1 text-[11px] text-zinc-400">
                  <span className="bg-white/5 px-2 py-0.5 rounded border border-white/10">14 pages</span>
                  <span className="bg-white/5 px-2 py-0.5 rounded border border-white/10">38 equations</span>
                  <span className="bg-white/5 px-2 py-0.5 rounded border border-white/10">6 raster figures</span>
                  <span className="bg-white/5 px-2 py-0.5 rounded border border-white/10">29 bib entries</span>
                </div>
              </div>

              {/* Execution Log Telemetry */}
              <div className="space-y-2 text-xs">
                <div className="text-zinc-500 text-[11px] uppercase tracking-wider">Extraction Telemetry</div>
                <div className="bg-black border border-white/15 p-3 rounded-xl space-y-1.5 text-zinc-300 text-[11px]">
                  <div className="text-[#00CC68]">[✓] Disassembled PDF DOM & bounding boxes</div>
                  <div className="text-[#00CC68]">[✓] Extracted 6 raw figure streams to assets/</div>
                  <div className="text-[#00CC68]">[✓] Synthesized LaTeX equations (align* / equation)</div>
                  <div className="text-[#00CC68]">[✓] Extracted BibTeX bibliography keys</div>
                  <div className="text-white font-bold">[✓] Verified zero-error compilation with pdflatex</div>
                </div>
              </div>
            </div>

            {/* Generated Workspace Directory Spec */}
            <div className="border-t border-white/10 pt-4 flex items-center justify-between text-xs text-zinc-400">
              <div className="flex items-center gap-2">
                <FolderTree className="w-4 h-4 text-[#00CC68]" />
                <span>Output: Multi-file project</span>
              </div>
              <span className="text-[#00CC68] font-bold">READY TO COMPILE</span>
            </div>
          </div>

          {/* Right Column: Code & File Tree Inspector */}
          <div className="lg:col-span-7 bg-zinc-950 border-2 border-white/20 rounded-2xl overflow-hidden flex flex-col shadow-xl">
            {/* Top Bar with Real Tabs */}
            <div className="bg-zinc-900 px-4 py-2.5 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setActiveTab("code")}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors ${
                    activeTab === "code"
                      ? "bg-black text-[#00CC68] border border-white/20"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  main.tex
                </button>
                <button
                  onClick={() => setActiveTab("bib")}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors ${
                    activeTab === "bib"
                      ? "bg-black text-[#00CC68] border border-white/20"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  refs.bib
                </button>
                <button
                  onClick={() => setActiveTab("assets")}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors ${
                    activeTab === "assets"
                      ? "bg-black text-[#00CC68] border border-white/20"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  assets/ (6)
                </button>
              </div>

              <div className="text-[11px] text-zinc-400 hidden sm:block">
                target: pdflatex
              </div>
            </div>

            {/* Code / Content Area */}
            <div className="p-6 flex-1 text-xs leading-relaxed overflow-x-auto bg-[#0a0a0c]">
              {activeTab === "code" && (
                <div className="space-y-1 text-zinc-300 font-mono">
                  <div className="text-zinc-500">{"% Decompiled from arxiv_2403.08912.pdf"}</div>
                  <div className="text-[#00CC68] font-bold">{"\\documentclass[10pt,journal,compsoc]{IEEEtran}"}</div>
                  <div>{"\\usepackage[utf8]{inputenc}"}</div>
                  <div>{"\\usepackage{amsmath,amssymb,amsfonts}"}</div>
                  <div>{"\\usepackage{graphicx}"}</div>
                  <div>{"\\usepackage{booktabs}"}</div>
                  <div>{"\\usepackage{cite}"}</div>
                  <div className="pt-2 text-[#00CC68] font-bold">{"\\begin{document}"}</div>
                  <div className="pl-4 text-white font-bold">{"\\title{Byzantine Fault-Tolerant Consensus on Async Networks}"}</div>
                  <div className="pl-4">{"\\author{Devon Vance, Marcus Sterling, and H. K. Rao}"}</div>
                  <div className="pl-4">{"\\maketitle"}</div>
                  <div className="pt-2 pl-4 text-emerald-300">{"\\section{System Formalization}"}</div>
                  <div className="pl-4 text-zinc-400">
                    {"Let $\\mathcal{N} = \\{1, \\dots, n\\}$ denote the set of distributed validator nodes..."}
                  </div>
                  <div className="pt-2 pl-4 text-amber-300">{"\\begin{align}"}</div>
                  <div className="pl-8 text-amber-200">
                    {"Q_{valid} &\\ge \\left\\lfloor \\frac{2n + 1}{3} \\right\\rfloor + f_{byz}, \\quad \\forall r \\in \\mathcal{R}"}
                  </div>
                  <div className="pl-4 text-amber-300">{"\\end{align}"}</div>
                  <div className="pt-2 pl-4 text-zinc-400">{"\\includegraphics[width=0.9\\linewidth]{assets/figure_1.png}"}</div>
                  <div className="pt-2 text-[#00CC68] font-bold">{"\\end{document}"}</div>
                </div>
              )}

              {activeTab === "bib" && (
                <div className="space-y-2 text-zinc-300 font-mono">
                  <div className="text-zinc-500">{"% Parsed BibTeX citations"}</div>
                  <div className="text-sky-300">{"@article{castro2002practical,"}</div>
                  <div className="pl-4">{"title = {Practical Byzantine fault tolerance and proactive recovery},"}</div>
                  <div className="pl-4">{"author = {Castro, Miguel and Liskov, Barbara},"}</div>
                  <div className="pl-4">{"journal = {ACM TOCS},"}</div>
                  <div className="pl-4">{"volume = {20},"}</div>
                  <div className="pl-4">{"year = {2002}"}</div>
                  <div className="text-sky-300">{"}"}</div>
                  <div className="text-sky-300 pt-2">{"@inproceedings{lamport1982byzantine,"}</div>
                  <div className="pl-4">{"title = {The Byzantine Generals Problem},"}</div>
                  <div className="pl-4">{"author = {Lamport, Leslie and Shostak, Robert and Pease, Marshall},"}</div>
                  <div className="pl-4">{"year = {1982}"}</div>
                  <div className="text-sky-300">{"}"}</div>
                </div>
              )}

              {activeTab === "assets" && (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {["topology_diagram.png", "throughput_latency.png", "consensus_rounds.png", "validator_quorum.png", "network_partition.png", "memory_footprint.png"].map((name, i) => (
                    <div
                      key={name}
                      className="p-3 bg-black border border-white/15 rounded-xl space-y-1.5 text-center flex flex-col items-center justify-center hover:border-[#00CC68] transition-colors"
                    >
                      <HardDrive className="w-5 h-5 text-[#00CC68]" />
                      <span className="text-[11px] text-zinc-300 font-mono block truncate w-full">
                        {name}
                      </span>
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-white/10 text-zinc-400 font-mono">
                        extracted #{i + 1}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 3 Concrete Technical Capabilities */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-sans">
          <div className="p-6 bg-zinc-950 border-2 border-white/20 rounded-2xl space-y-3">
            <div className="font-mono text-xs font-bold text-[#00CC68] uppercase flex items-center gap-2">
              <Layers className="w-4 h-4" />
              <span>AST & MATH ENVIRONMENTS</span>
            </div>
            <h3 className="font-archivo font-bold uppercase text-lg text-white">
              Native Equation Decompilation
            </h3>
            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
              No character OCR mush. Multi-line proofs, matrices, and sub/superscripts are mapped directly into standard <code className="text-zinc-200">align*</code>, <code className="text-zinc-200">bmatrix</code>, and <code className="text-zinc-200">equation</code> blocks.
            </p>
          </div>

          <div className="p-6 bg-zinc-950 border-2 border-white/20 rounded-2xl space-y-3">
            <div className="font-mono text-xs font-bold text-[#00CC68] uppercase flex items-center gap-2">
              <HardDrive className="w-4 h-4" />
              <span>LOSSLESS FIGURE EXTRACTION</span>
            </div>
            <h3 className="font-archivo font-bold uppercase text-lg text-white">
              Raw Figure Streams to assets/
            </h3>
            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
              Charts, plots, and diagrams are uncompressed directly from the PDF stream into your project folder. Every <code className="text-zinc-200">\includegraphics</code> call resolves out of the box.
            </p>
          </div>

          <div className="p-6 bg-zinc-950 border-2 border-white/20 rounded-2xl space-y-3">
            <div className="font-mono text-xs font-bold text-[#00CC68] uppercase flex items-center gap-2">
              <FileCheck2 className="w-4 h-4" />
              <span>COLLABORATIVE WORKSPACE</span>
            </div>
            <h3 className="font-archivo font-bold uppercase text-lg text-white">
              Instant Editor Fork
            </h3>
            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
              One click opens your decompiled project in the OverBranch editor with real-time compilation, SyncTeX cursor jumping, and multi-author editing.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
