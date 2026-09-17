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
    <div className="h-11 px-3 sm:px-4 border-b border-[#282A30] bg-[#141519] flex items-center justify-between gap-2 text-xs font-mono text-[#E2E4E9] overflow-x-auto shrink-0 select-none">
      <div className="flex items-center gap-2 shrink-0">
        <Button
          size="sm"
          onClick={onCompile}
          disabled={isCompiling}
          className="h-7 px-3.5 bg-[#10B981] hover:bg-[#059669] text-white font-archivo font-bold rounded-lg border border-[#10B981]/30 shadow-sm text-xs cursor-pointer transition-all flex items-center gap-1.5"
        >
          {isCompiling ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin text-white" />
              <span>Compiling...</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current text-white" />
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
              ? "border-[#282A30] bg-[#22242C] text-[#10B981] font-semibold"
              : "border-[#282A30] text-[#9E9E9E] hover:bg-[#1A1C22] hover:text-[#E2E4E9]"
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${autoCompile ? "bg-[#10B981] animate-pulse" : "bg-[#62666D]"}`} />
          <span className="hidden sm:inline">Auto-Compile</span>
          <span className="sm:hidden">Auto</span>
        </button>

        <select
          value={engine}
          onChange={(e) => setEngine(e.target.value)}
          className="h-7 px-2.5 rounded-lg border border-[#282A30] bg-[#1A1C22] text-[#E2E4E9] outline-none text-[11px] font-mono shrink-0 cursor-pointer hover:border-[#282A30] transition-colors"
        >
          <option value="pdfLaTeX">pdfLaTeX</option>
          <option value="XeLaTeX">XeLaTeX</option>
          <option value="LuaLaTeX">LuaLaTeX</option>
        </select>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="hidden md:flex items-center gap-2">
          <span className="px-2 py-0.5 rounded-md bg-[#1A1C22] text-[#10B981] border border-[#282A30] flex items-center gap-1 text-[11px] font-mono font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
            <span>0 Errors</span>
          </span>
          <span className="px-2 py-0.5 rounded-md bg-[#1A1C22] text-[#FF9900] border border-[#282A30] flex items-center gap-1 text-[11px] font-mono font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-[#FF9900]" />
            <span>1 Warning</span>
          </span>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={handleDownloadPdf}
          className="h-7 px-2.5 border-[#282A30] bg-[#1A1C22] hover:bg-[#22242C] text-[#E2E4E9] font-mono font-medium text-xs rounded-lg cursor-pointer flex items-center gap-1"
          title="Download PDF"
        >
          <FileDown className="w-3.5 h-3.5 text-[#10B981]" />
          <span>PDF</span>
        </Button>
      </div>
    </div>
  );
}

