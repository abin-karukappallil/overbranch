"use client";

import React, { useState } from "react";
import {
  Play,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  FileDown,
  ChevronDown,
  Settings2,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface CompileToolbarProps {
  onCompile: () => void;
  isCompiling: boolean;
}

export function CompileToolbar({ onCompile, isCompiling }: CompileToolbarProps) {
  const [autoCompile, setAutoCompile] = useState(true);
  const [engine, setEngine] = useState("pdfLaTeX");

  const handleDownloadPdf = () => {
    toast.success("Downloading compiled paper PDF (main.pdf)...");
  };

  return (
    <div className="h-12 px-3 sm:px-4 border-b border-border/40 bg-card/60 backdrop-blur-xl flex items-center justify-between gap-2 text-xs font-mono overflow-x-auto">
      <div className="flex items-center gap-2 shrink-0">
        <Button
          size="sm"
          onClick={onCompile}
          disabled={isCompiling}
          className="h-8 px-3 sm:px-4 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg shadow-sm shadow-emerald-500/20 text-xs"
        >
          {isCompiling ? (
            <>
              <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
              <span className="hidden sm:inline">Compiling...</span>
              <span className="sm:hidden">TeX...</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 mr-1 fill-current" />
              <span>Compile</span>
            </>
          )}
        </Button>

        <button
          onClick={() => {
            setAutoCompile(!autoCompile);
            toast.info(`Auto-compile on edit: ${!autoCompile ? "ENABLED" : "DISABLED"}`);
          }}
          className={`hidden xs:flex items-center gap-1.5 px-2 py-1 rounded-md border text-[11px] transition-colors shrink-0 ${
            autoCompile
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-semibold"
              : "border-border/60 text-muted-foreground hover:bg-accent"
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${autoCompile ? "bg-emerald-400 animate-pulse" : "bg-muted-foreground"}`} />
          <span className="hidden sm:inline">Auto-Compile</span>
          <span className="sm:hidden">Auto</span>
        </button>

        <select
          value={engine}
          onChange={(e) => setEngine(e.target.value)}
          className="h-8 px-1.5 sm:px-2 rounded-lg border border-border/60 bg-background text-foreground outline-none text-[10px] sm:text-[11px] shrink-0"
        >
          <option value="pdfLaTeX">pdfLaTeX</option>
          <option value="XeLaTeX">XeLaTeX</option>
          <option value="LuaLaTeX">LuaLaTeX</option>
        </select>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="hidden md:flex items-center gap-2">
          <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1 text-[11px]">
            <CheckCircle2 className="w-3 h-3" /> 0 Errors
          </span>
          <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1 text-[11px]">
            <AlertTriangle className="w-3 h-3" /> 1 Warning
          </span>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={handleDownloadPdf}
          className="h-8 px-2.5 border-border/60 bg-background/60 hover:bg-accent text-foreground text-xs"
          title="Download PDF"
        >
          <FileDown className="w-3.5 h-3.5 sm:mr-1 text-indigo-400" />
          <span className="hidden sm:inline">PDF</span>
        </Button>
      </div>
    </div>
  );
}
