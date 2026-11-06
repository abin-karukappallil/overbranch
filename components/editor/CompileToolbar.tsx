"use client";

import React, { useState } from "react";
import {
  Play,
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
    <div className={cn("flex items-stretch h-8 shrink-0 rounded-lg overflow-hidden border border-ob-line", className)}>
      <Button
        size="sm"
        onClick={onCompile}
        disabled={isCompiling}
        className={cn(
          "h-8 bg-ob-accent hover:bg-ob-accent-hover text-ob-on-accent font-medium text-xs flex items-center gap-1.5 cursor-pointer rounded-none border-0 shadow-none",
          compact ? "px-2 sm:px-2.5" : "px-3"
        )}
        title={
          isCompiling && busy
            ? "Server busy: queued behind other compiles, retrying shortly"
            : `Compile TeX with ${engine} (Ctrl+Enter / Cmd+Enter)`
        }
        aria-busy={isCompiling || undefined}
      >
        {isCompiling ? (
          <RotateCw className="size-3.5 animate-spin" />
        ) : (
          <Play className="size-3.5 fill-current" />
        )}
        <span className={compact ? "hidden xs:inline text-xs" : undefined}>
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
            className="flex h-8 w-6 cursor-pointer items-center justify-center border-l border-l-black/15 bg-ob-accent text-ob-on-accent transition-colors hover:bg-ob-accent-hover disabled:pointer-events-none disabled:opacity-50"
          >
            <ChevronDown className="size-3.5" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[10rem] border-ob-line bg-ob-card text-ob-text font-mono">
          <DropdownMenuLabel className="text-[11px] font-normal text-ob-muted">
            TeX engine
          </DropdownMenuLabel>
          <DropdownMenuSeparator className="bg-ob-line" />
          {TEX_ENGINES.map((name) => (
            <DropdownMenuCheckboxItem
              key={name}
              checked={engine === name}
              onCheckedChange={() => onEngineChange(name)}
              className="cursor-pointer text-xs focus:bg-ob-raised focus:text-ob-text"
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
    <div className="flex h-10 shrink-0 select-none items-center justify-between gap-2 overflow-x-auto border-b border-ob-line bg-ob-card px-3 text-xs text-ob-text sm:px-4">
      <div className="flex shrink-0 items-center gap-2">
        <Button
          size="sm"
          onClick={onCompile}
          disabled={isCompiling}
          variant="ob-primary"
          className="h-7 cursor-pointer text-xs"
        >
          {isCompiling ? (
            <>
              <RotateCw className="size-3.5 animate-spin" />
              <span>Compiling\u2026</span>
            </>
          ) : (
            <>
              <Play className="size-3.5 fill-current" />
              <span>Compile TeX</span>
            </>
          )}
        </Button>

        <button
          onClick={() => {
            setAutoCompile(!autoCompile);
          }}
          className={`hidden cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-colors xs:flex shrink-0 ${
            autoCompile
              ? "border-ob-line bg-ob-raised text-ob-text font-medium"
              : "border-ob-line text-ob-muted hover:text-ob-text hover:bg-ob-raised"
          }`}
        >
          <span className={`size-1.5 rounded-full ${autoCompile ? "bg-ob-accent" : "bg-ob-muted"}`} />
          <span className="hidden sm:inline">Auto-compile</span>
          <span className="sm:hidden">Auto</span>
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Button
          variant="ob-quiet"
          size="sm"
          onClick={handleDownloadPdf}
          className="h-7 cursor-pointer text-xs"
          title="Download PDF"
        >
          <FileDown className="size-3.5 text-ob-muted" />
          <span>PDF</span>
        </Button>
      </div>
    </div>
  );
}
