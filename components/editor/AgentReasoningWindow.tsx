"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { Zap, Square, ArrowDown, Check, Loader2 } from "lucide-react";

export interface AgentProgressStep {
  step: string;
  message: string;
  icon?: string;
}

interface AgentReasoningWindowProps {
  steps: AgentProgressStep[];
  onStop: () => void;
  className?: string;
  compact?: boolean;
}

export function AgentReasoningWindow({
  steps,
  onStop,
  className = "",
  compact = false,
}: AgentReasoningWindowProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomAnchorRef = useRef<HTMLDivElement>(null);
  const [isAutoScrollPinned, setIsAutoScrollPinned] = useState<boolean>(true);
  const [userHasScrolledUp, setUserHasScrolledUp] = useState<boolean>(false);

  // Smoothly scroll the steps list to bottom
  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    el.scrollTo({
      top: el.scrollHeight,
      behavior,
    });
  }, []);

  // Monitor user scroll inside the reasoning box:
  // If user scrolls up to inspect previous steps, pause pinning.
  // If user scrolls back down near the bottom (within 24px), re-enable pinning.
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const threshold = 24;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const isAtBottom = distanceToBottom <= threshold;

    setIsAutoScrollPinned(isAtBottom);
    setUserHasScrolledUp(!isAtBottom);
  }, []);

  // Auto-scroll when steps change or updates arrive
  useEffect(() => {
    if (isAutoScrollPinned) {
      // Use requestAnimationFrame to ensure DOM rendering completes before scrolling
      const frameId = requestAnimationFrame(() => {
        scrollToBottom("smooth");
      });
      return () => cancelAnimationFrame(frameId);
    }
  }, [steps, isAutoScrollPinned, scrollToBottom]);

  // Initial mount scroll
  useEffect(() => {
    scrollToBottom("auto");
  }, [scrollToBottom]);

  const handleResumeAutoScroll = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsAutoScrollPinned(true);
    setUserHasScrolledUp(false);
    scrollToBottom("smooth");
  };

  const activeStepNumber = steps.length > 0 ? steps.length : 1;

  return (
    <div
      className={`p-3 rounded-2xl bg-zinc-900/95 border border-[#00CC68]/30 text-zinc-100 font-mono space-y-2 shadow-xl animate-in fade-in slide-in-from-bottom-1 relative ${
        compact ? "text-[11px]" : "text-xs"
      } ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between font-bold border-b border-zinc-800/80 pb-2 text-[#00CC68]">
        <div className="flex items-center gap-2 min-w-0">
          <Zap className="w-3.5 h-3.5 text-[#00CC68] animate-pulse shrink-0" />
          <span className="truncate">AI Agent Reasoning</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-[#00CC68]/15 text-[#00CC68] border border-[#00CC68]/25 font-mono font-semibold shrink-0">
            Step {activeStepNumber}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {userHasScrolledUp && (
            <button
              type="button"
              onClick={handleResumeAutoScroll}
              className="px-2 py-0.5 rounded-md bg-[#00CC68]/15 hover:bg-[#00CC68]/25 text-[#00CC68] border border-[#00CC68]/30 text-[10px] font-mono font-bold flex items-center gap-1 transition-all cursor-pointer shadow-xs animate-bounce"
              title="Resume auto-scroll to latest step"
            >
              <ArrowDown className="w-2.5 h-2.5 text-[#00CC68]" />
              <span>Latest</span>
            </button>
          )}

          <button
            type="button"
            onClick={onStop}
            className={`px-2 py-0.5 rounded-md bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 border border-rose-500/40 font-mono font-bold flex items-center gap-1 transition-colors shrink-0 cursor-pointer ${
              compact ? "text-[10px]" : "text-xs"
            }`}
            title="Stop AI agent thinking"
          >
            <Square className="w-2.5 h-2.5 fill-current text-rose-300" />
            <span>Stop</span>
          </button>
        </div>
      </div>

      {/* Reasoning Steps Container with Efficient Auto-Scroll */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className={`space-y-1.5 overflow-y-auto pr-1 scroll-smooth ${
          compact ? "max-h-28" : "max-h-36"
        }`}
        style={{
          scrollbarWidth: "thin",
          scrollbarColor: "#27272a transparent",
        }}
      >
        {steps.length === 0 ? (
          <div className="flex items-center gap-2 text-[#00CC68]/90 animate-pulse py-1 font-mono text-[11px]">
            <Loader2 className="w-3 h-3 text-[#00CC68] animate-spin shrink-0" />
            <span>Initializing TeX intelligence engine...</span>
          </div>
        ) : (
          steps.map((s, idx) => {
            const isLatest = idx === steps.length - 1;
            return (
              <div
                key={idx}
                className={`flex items-start gap-2 py-1 px-2 rounded-lg transition-all font-mono ${
                  compact ? "text-[10px]" : "text-[11px]"
                } ${
                  isLatest
                    ? "text-[#00CC68] bg-[#00CC68]/10 border border-[#00CC68]/30 font-semibold shadow-xs"
                    : "text-zinc-400 bg-zinc-950/40 border border-zinc-800/40 font-normal hover:text-zinc-300"
                }`}
              >
                <div className="mt-0.5 shrink-0">
                  {isLatest ? (
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#00CC68] opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-[#00CC68]" />
                    </span>
                  ) : (
                    <Check className="w-3 h-3 text-[#00CC68]/70" />
                  )}
                </div>
                <div className="flex-1 min-w-0 break-words leading-relaxed">
                  <span title={s.message}>{s.message}</span>
                </div>
              </div>
            );
          })
        )}
        <div ref={bottomAnchorRef} className="h-0 w-0 pointer-events-none" />
      </div>
    </div>
  );
}
