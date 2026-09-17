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

  // Monitor user scroll inside the reasoning box
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
      className={`p-3 rounded-2xl bg-[#141519] border border-[#282A30] text-[#E2E4E9] font-mono space-y-2 shadow-xl animate-in fade-in slide-in-from-bottom-1 relative ${
        compact ? "text-[11px]" : "text-xs"
      } ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between font-archivo font-bold border-b border-[#282A30] pb-2 text-[#E2E4E9]">
        <div className="flex items-center gap-2 min-w-0">
          <Zap className="w-3.5 h-3.5 text-[#10B981] animate-pulse shrink-0" />
          <span className="truncate">Agent Reasoning</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-[#22242C] text-[#9E9E9E] border border-[#282A30] font-mono font-medium shrink-0">
            Step {activeStepNumber}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {userHasScrolledUp && (
            <button
              type="button"
              onClick={handleResumeAutoScroll}
              className="px-2 py-0.5 rounded-md bg-[#22242C] hover:bg-[#2A2C36] text-[#10B981] border border-[#282A30] text-[10px] font-mono font-medium flex items-center gap-1 transition-all cursor-pointer shadow-xs animate-bounce"
              title="Resume auto-scroll to latest step"
            >
              <ArrowDown className="w-2.5 h-2.5 text-[#10B981]" />
              <span>Latest</span>
            </button>
          )}

          <button
            type="button"
            onClick={onStop}
            className={`px-2 py-0.5 rounded-md bg-[#EB5757]/10 hover:bg-[#EB5757]/20 text-[#EB5757] border border-[#EB5757]/30 font-mono font-semibold flex items-center gap-1 transition-colors shrink-0 cursor-pointer ${
              compact ? "text-[10px]" : "text-xs"
            }`}
            title="Stop AI agent thinking"
          >
            <Square className="w-2.5 h-2.5 fill-current text-[#EB5757]" />
            <span>Stop</span>
          </button>
        </div>
      </div>

      {/* Reasoning Steps Container */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className={`space-y-1.5 overflow-y-auto pr-1 scroll-smooth ${
          compact ? "max-h-28" : "max-h-36"
        }`}
        style={{
          scrollbarWidth: "thin",
          scrollbarColor: "#282A30 transparent",
        }}
      >
        {steps.length === 0 ? (
          <div className="flex items-center gap-2 text-[#9E9E9E] animate-pulse py-1 font-mono text-[11px]">
            <Loader2 className="w-3 h-3 text-[#10B981] animate-spin shrink-0" />
            <span>Initializing LaTeX pipeline...</span>
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
                    ? "text-[#E2E4E9] bg-[#22242C] border border-[#282A30] font-medium"
                    : "text-[#9E9E9E] bg-[#1A1C22] border border-[#282A30]/60 font-normal hover:text-[#E2E4E9]"
                }`}
              >
                <div className="mt-0.5 shrink-0">
                  {isLatest ? (
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#10B981] opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-[#10B981]" />
                    </span>
                  ) : (
                    <Check className="w-3 h-3 text-[#10B981]" />
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

