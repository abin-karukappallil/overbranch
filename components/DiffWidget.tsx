"use client";

import React, { useState, useEffect } from "react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import { Check, X, Sparkles, LayoutGrid, Layers, FileCode2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface DiffWidgetProps {
  originalChunk: string;
  proposedChunk: string;
  explanation?: string;
  onAccept: (originalChunk: string, proposedChunk: string) => void;
  onReject: () => void;
}

export function DiffWidget({
  originalChunk,
  proposedChunk,
  explanation,
  onAccept,
  onReject,
}: DiffWidgetProps) {
  const [isDesktop, setIsDesktop] = useState(true);

  useEffect(() => {
    const handleResize = () => {
      setIsDesktop(window.innerWidth >= 768);
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const customStyles = {
    variables: {
      dark: {
        diffViewerBackground: "#090d16",
        diffViewerColor: "#e2e8f0",
        addedBackground: "rgba(16, 185, 129, 0.15)",
        addedColor: "#6ee7b7",
        removedBackground: "rgba(244, 63, 94, 0.15)",
        removedColor: "#fda4af",
        wordAddedBackground: "rgba(16, 185, 129, 0.35)",
        wordRemovedBackground: "rgba(244, 63, 94, 0.35)",
        gutterBackground: "#0f172a",
        gutterColor: "#64748b",
        gutterBackgroundAdded: "rgba(16, 185, 129, 0.2)",
        gutterBackgroundRemoved: "rgba(244, 63, 94, 0.2)",
        codeFoldGutterBackground: "#0f172a",
        codeFoldBackground: "#0f172a",
        emptyLineBackground: "#090d16",
      },
    },
    line: {
      fontFamily: "var(--font-geist-mono), monospace",
      fontSize: "12px",
      lineHeight: "1.6",
    },
  };

  return (
    <div className="w-full h-full flex flex-col bg-card/95 border border-border/80 rounded-2xl shadow-2xl overflow-hidden backdrop-blur-2xl">
      {/* Widget Header */}
      <div className="px-4 py-3 border-b border-border/50 bg-muted/30 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2 truncate">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-bold text-sm text-foreground tracking-tight flex items-center gap-2">
              <span>Proposed AI LaTeX Edit</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                Nemotron RAG
              </span>
            </h3>
            {explanation && (
              <p className="text-xs text-muted-foreground line-clamp-1">{explanation}</p>
            )}
          </div>
        </div>

        {/* View Mode Indicator */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-background/80 border border-border/40 text-[11px] font-mono text-muted-foreground shrink-0">
          {isDesktop ? (
            <>
              <LayoutGrid className="w-3.5 h-3.5 text-indigo-400" />
              <span>Side-by-Side</span>
            </>
          ) : (
            <>
              <Layers className="w-3.5 h-3.5 text-indigo-400" />
              <span>Unified Mobile</span>
            </>
          )}
        </div>
      </div>

      {/* Diff Viewer Body */}
      <div className="flex-1 overflow-y-auto overflow-x-auto p-2 bg-[#090d16] font-mono">
        <ReactDiffViewer
          oldValue={originalChunk || "% (Empty original section)"}
          newValue={proposedChunk}
          splitView={isDesktop}
          useDarkTheme={true}
          styles={customStyles}
          compareMethod={DiffMethod.WORDS}
          leftTitle="Original TeX Code"
          rightTitle="Proposed AI Edit"
        />
      </div>

      {/* Bottom Sticky Action Bar */}
      <div className="sticky bottom-0 z-20 px-4 py-3 border-t border-border/60 bg-card/95 backdrop-blur-xl flex items-center justify-between gap-3 shrink-0">
        <div className="text-xs text-muted-foreground hidden sm:flex items-center gap-1.5 font-mono">
          <FileCode2 className="w-3.5 h-3.5 text-indigo-400" />
          <span>Review changes before applying to editor</span>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          <Button
            variant="destructive"
            onClick={onReject}
            className="flex-1 sm:flex-initial bg-rose-600 hover:bg-rose-500 text-white font-semibold px-4 py-2 rounded-xl shadow-lg shadow-rose-600/20 active:scale-95 transition-all flex items-center justify-center gap-2 text-xs"
          >
            <X className="w-4 h-4" />
            <span>Reject Changes</span>
          </Button>

          <Button
            onClick={() => onAccept(originalChunk, proposedChunk)}
            className="flex-1 sm:flex-initial bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-4 py-2 rounded-xl shadow-lg shadow-emerald-600/20 active:scale-95 transition-all flex items-center justify-center gap-2 text-xs"
          >
            <Check className="w-4 h-4" />
            <span>Accept Changes</span>
          </Button>
        </div>
      </div>
    </div>
  );
}
