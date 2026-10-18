"use client";

import React, { useState } from "react";
import {
  Play,
  Loader2,
  FileDown,
  RotateCw,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export const TEX_ENGINES = ["pdfLaTeX", "XeLaTeX", "LuaLaTeX"] as const;
export type TexEngine = (typeof TEX_ENGINES)[number];

export function isTexEngine(value: unknown): value is TexEngine {
  return typeof value === "string" && (TEX_ENGINES as readonly string[]).includes(value);
}

interface CompileSplitButtonProps {
  onCompile: () => void;
  isCompiling: boolean;
  /** Compiling is waiting out a "server busy" backoff, not running TeX yet. */
  busy?: boolean;
  engine: TexEngine;
  onEngineChange: (engine: TexEngine) => void;
  /** Hide the "Compile" label below the `xs` breakpoint (compact header). */
  compact?: boolean;
  className?: string;
}

/**
 * The Compile button with the TeX engine fused to it: the green button
 * compiles, the narrow chevron beside it opens the engine list. The one engine
 * control in the app — the header uses it at every breakpoint.
 */
export function CompileSplitButton({
  onCompile,
  isCompiling,
  busy = false,
  engine,
  onEngineChange,
  compact = false,
  className,
}: CompileSplitButtonProps) {
  return (
    <div className={cn("flex items-stretch h-8 shrink-0 rounded-lg shadow-sm", className)}>
      <Button
        size="sm"
        onClick={onCompile}
        disabled={isCompiling}
        className={cn(
          "h-8 bg-[#10B981] hover:bg-[#059669] text-white font-archivo font-bold text-xs border border-[#10B981]/30 border-r-0 flex items-center gap-1.5 cursor-pointer rounded-l-lg rounded-r-none shadow-none",
          compact ? "px-2 sm:px-2.5" : "px-3.5"
        )}
        title={
          isCompiling && busy
            ? "Server busy: queued behind other compiles, retrying shortly"
            : `Compile TeX with ${engine} (Ctrl+Enter / Cmd+Enter)`
        }
        aria-busy={isCompiling || undefined}
      >
        {isCompiling ? (
          <RotateCw className="w-3.5 h-3.5 animate-spin text-white" />
        ) : (
          <Play className="w-3.5 h-3.5 fill-current text-white" />
        )}
        <span className={compact ? "hidden xs:inline text-[11px]" : undefined}>
          {isCompiling && busy ? "Queued\u2026" : "Compile"}
        </span>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild disabled={isCompiling}>
          <button
            type="button"
            disabled={isCompiling}
            aria-label={`TeX engine: ${engine}. Change engine`}
            title={`TeX engine: ${engine}`}
            className="h-8 w-6 flex items-center justify-center rounded-r-lg bg-[#10B981] hover:bg-[#059669] text-white border border-[#10B981]/30 border-l border-l-white/30 cursor-pointer disabled:opacity-50 disabled:pointer-events-none transition-colors"
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[10rem] font-mono">
          <DropdownMenuLabel className="text-[11px] text-muted-foreground font-normal">
            TeX engine
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {TEX_ENGINES.map((name) => (
            <DropdownMenuCheckboxItem
              key={name}
              checked={engine === name}
              onCheckedChange={() => onEngineChange(name)}
              className="text-xs cursor-pointer"
            >
              {name}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

interface CompileToolbarProps {
  onCompile: () => void;
  isCompiling: boolean;
  onDownloadPdf?: () => void;
}

export function CompileToolbar({
  onCompile,
  isCompiling,
  onDownloadPdf,
}: CompileToolbarProps) {
  const [autoCompile, setAutoCompile] = useState(true);

  const handleDownloadPdf = () => {
    if (onDownloadPdf) {
      onDownloadPdf();
    }
  };

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

