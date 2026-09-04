"use client";

import React, { useState } from "react";
import {
  Play,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  FileDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface CompileToolbarProps {
  onCompile: () => void;
  isCompiling: boolean;
}

export function CompileToolbar({
  onCompile,
  isCompiling,
}: CompileToolbarProps) {
  const [autoCompile, setAutoCompile] = useState(true);
  const [engine, setEngine] = useState("pdfLaTeX");

  const handleDownloadPdf = () => {};

  return (
    <div className="h-12 px-3 sm:px-4 border-b border-zinc-800 bg-zinc-950 flex items-center justify-between gap-2 text-xs font-mono text-zinc-100 overflow-x-auto shrink-0 select-none">
      <div className="flex items-center gap-2 shrink-0">
        <Button
          size="sm"
          onClick={onCompile}
          disabled={isCompiling}
          className="h-8 px-4 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider rounded-lg border border-black shadow-[3px_3px_0px_0px_#000000] text-xs cursor-pointer transition-all"
        >
          {isCompiling ? (
            <>
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin text-black" />
              <span>Compiling...</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 mr-1.5 fill-current text-black" />
              <span>Compile TeX</span>
            </>
          )}
        </Button>

        <button
          onClick={() => {
            setAutoCompile(!autoCompile);
          }}
          className={`hidden xs:flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-mono transition-colors shrink-0 cursor-pointer ${
            autoCompile
              ? "border-[#00CC68]/30 bg-[#00CC68]/10 text-[#00CC68] font-bold"
              : "border-zinc-800 text-zinc-400 hover:bg-zinc-900"
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${autoCompile ? "bg-[#00CC68] animate-pulse" : "bg-zinc-500"}`} />
          <span className="hidden sm:inline">Auto-Compile</span>
          <span className="sm:hidden">Auto</span>
        </button>

        <select
          value={engine}
          onChange={(e) => setEngine(e.target.value)}
          className="h-8 px-2.5 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-200 outline-none text-[11px] font-mono shrink-0 cursor-pointer"
        >
          <option value="pdfLaTeX">pdfLaTeX</option>
          <option value="XeLaTeX">XeLaTeX</option>
          <option value="LuaLaTeX">LuaLaTeX</option>
        </select>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="hidden md:flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded bg-[#00CC68]/10 text-[#00CC68] border border-[#00CC68]/20 flex items-center gap-1 text-[11px] font-mono font-bold">
            <CheckCircle2 className="w-3 h-3" /> 0 Errors
          </span>
          <span className="px-2.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1 text-[11px] font-mono font-bold">
            <AlertTriangle className="w-3 h-3" /> 1 Warning
          </span>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={handleDownloadPdf}
          className="h-8 px-3 border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-white font-mono font-bold text-xs rounded-lg cursor-pointer"
          title="Download PDF"
        >
          <FileDown className="w-3.5 h-3.5 mr-1.5 text-[#00CC68]" />
          <span>PDF</span>
        </Button>
      </div>
    </div>
  );
}
