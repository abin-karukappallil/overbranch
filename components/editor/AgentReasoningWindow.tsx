"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { Square, ArrowDown, Check, Loader2, AlertTriangle } from "lucide-react";

export interface AgentProgressStep {
  step: string;
  message: string;
  icon?: string;
  /** For step === "phase": finding_target | applying | compiling | checking_layout | repairing | done | failed */
  phase?: string;
  /** Structured failure detail (operation, target, attempts) — shown in development only. */
  details?: Record<string, unknown> | null;
  /** For step === "page_snapshot": a small data-URL image of what the agent looked at. */
  image?: string;
  label?: string;
}

const PHASE_LABELS: Record<string, string> = {
  finding_target: "Finding target\u2026",
  applying: "Applying patch\u2026",
  compiling: "Compiling\u2026",
  checking_layout: "Checking layout\u2026",
  repairing: "Repairing\u2026",
  done: "Done",
  failed: "Not applied",
};

/** A failed phase caused by the model gateways being down, not by the edit itself. */
function isModelOutage(step?: AgentProgressStep): boolean {
  return (
    step?.phase === "failed" &&
    (step.details?.operation === "llm_call" || (step.message || "").startsWith("Model outage"))
  );
}

const SHOW_DEBUG_DETAILS = process.env.NODE_ENV !== "production";

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

  const isHiddenStep = (msg: string) => {
    const lower = msg.toLowerCase().trim();
    return (
      lower.startsWith("edit scope") ||
      lower.includes("edit scope detected") ||
      lower.startsWith("analyzed document") ||
      lower.startsWith("analyze document") ||
      lower.startsWith("context strategy")
    );
  };

  const visibleSteps = steps
    .filter((s) => !isHiddenStep(s.message || ""))
    .map((s) => {
      const msg = s.message || "";
      if (
        s.step === "tool_call" ||
        msg.toLowerCase().trim().startsWith("tool calling")
      ) {
        return {
          ...s,
          message: "Tool calling\u2026",
        };
      }
      return s;
    });

  // Auto-scroll when steps change or updates arrive
  useEffect(() => {
    if (isAutoScrollPinned) {
      const frameId = requestAnimationFrame(() => {
        scrollToBottom("smooth");
      });
      return () => cancelAnimationFrame(frameId);
    }
  }, [visibleSteps, isAutoScrollPinned, scrollToBottom]);

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

  const activeStepNumber = visibleSteps.length > 0 ? visibleSteps.length : 1;
  const currentPhase = [...visibleSteps].reverse().find((s) => s.step === "phase" && s.phase);
  const phaseFailed = currentPhase?.phase === "failed";

  return (
    <div
      className={`relative space-y-2 rounded-xl border border-ob-line bg-ob-card p-3 font-mono text-ob-text shadow-sm ${
        compact ? "text-[11px]" : "text-xs"
      } ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-ob-line pb-2 font-mono text-xs text-ob-text">
        <div className="flex min-w-0 items-center gap-2">
          <Loader2 className="size-3.5 animate-spin text-ob-accent shrink-0" />
          <span className="truncate font-medium text-ob-text">Reasoning</span>
          <span className="shrink-0 rounded border border-ob-line bg-ob-raised px-1.5 py-0.5 font-mono text-[10px] text-ob-muted tabular-nums">
            Step {activeStepNumber}
          </span>
          {currentPhase?.phase && (
            <span
              className={`shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] ${
                phaseFailed
                  ? "border-ob-negative/20 bg-ob-raised text-ob-negative"
                  : "border-ob-line bg-ob-raised text-ob-text-2"
              }`}
              title={currentPhase.message}
            >
              {isModelOutage(currentPhase) ? "Model outage" : PHASE_LABELS[currentPhase.phase] || currentPhase.phase}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {userHasScrolledUp && (
            <button
              type="button"
              onClick={handleResumeAutoScroll}
              className="flex cursor-pointer items-center gap-1 rounded border border-ob-line bg-ob-raised px-2 py-0.5 font-mono text-[10px] text-ob-text transition-colors hover:bg-ob-deep"
              title="Resume auto-scroll"
            >
              <ArrowDown className="size-2.5 text-ob-muted" />
              <span>Latest</span>
            </button>
          )}

          <button
            type="button"
            onClick={onStop}
            className={`flex cursor-pointer items-center gap-1 rounded border border-ob-negative/20 bg-ob-raised px-2 py-0.5 font-mono text-ob-negative transition-colors hover:bg-ob-negative/10 ${
              compact ? "text-[10px]" : "text-xs"
            }`}
            title="Stop AI reasoning"
          >
            <Square className="size-2.5 fill-current text-ob-negative" />
            <span>Stop</span>
          </button>
        </div>
      </div>

      {/* Reasoning Steps Container */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className={`ob-thin-scroll space-y-1 overflow-y-auto pr-1 scroll-smooth ${
          compact ? "max-h-28" : "max-h-36"
        }`}
      >
        {visibleSteps.length === 0 ? (
          <div className="flex items-center gap-2 py-1 font-mono text-[11px] text-ob-muted">
            <Loader2 className="size-3 animate-spin text-ob-muted shrink-0" />
            <span>Initializing pipeline\u2026</span>
          </div>
        ) : (
          visibleSteps.map((s, idx) => {
            const isLatest = idx === visibleSteps.length - 1;
            return (
              <div
                key={idx}
                className={`flex items-start gap-2 rounded-lg px-2 py-1 font-mono transition-colors ${
                  compact ? "text-[10px]" : "text-[11px]"
                } ${
                  isLatest
                    ? "border border-ob-line bg-ob-raised font-medium text-ob-text"
                    : "border border-transparent text-ob-muted hover:text-ob-text"
                }`}
              >
                <div className="mt-1 shrink-0">
                  {s.step === "phase" && s.phase === "failed" ? (
                    <AlertTriangle className="size-3 text-ob-negative" />
                  ) : isLatest ? (
                    <span className="block size-1.5 rounded-full bg-ob-accent" />
                  ) : (
                    <Check className="size-3 text-ob-muted" />
                  )}
                </div>
                <div className="min-w-0 flex-1 break-words leading-relaxed">
                  <span title={s.message}>{s.message}</span>
                  {s.step === "page_snapshot" && s.image && s.image.startsWith("data:image/") && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={s.image}
                      alt={s.label ? `Rendered ${s.label}` : "Rendered page"}
                      className="mt-1 block max-h-40 max-w-full rounded border border-ob-line bg-ob-card object-contain"
                    />
                  )}
                  {SHOW_DEBUG_DETAILS && s.details && (
                    <pre className="mt-1 whitespace-pre-wrap text-[10px] text-ob-muted">
                      {JSON.stringify(s.details, null, 1)}
                    </pre>
                  )}
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
