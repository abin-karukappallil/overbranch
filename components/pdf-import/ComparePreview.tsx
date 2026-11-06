"use client";

/**
 * ComparePreview — the original PDF page next to the compiled LaTeX page, with a page picker,
 * the page's match score and an optional difference heatmap. Images come from the backend
 * preview endpoint through authFetch (blob -> object URL), never as a direct backend URL.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authFetch } from "@/lib/api-client";
import { BACKEND_URL } from "./usePdfConversionJob";
import { pct } from "./shared";

type Which = "original" | "converted" | "diff";

export interface ComparePreviewProps {
  jobId: string;
  /** Source page count (the picker walks source pages). */
  pageCount: number;
  page: number;
  onPageChange: (page: number) => void;
  /** 0..1 match score of each source page (index = page - 1); null when not measured. */
  scoreFor?: (page: number) => number | null | undefined;
  /** Source page -> output pages (rebuild jobs); only used for the caption. */
  pageMap?: Record<string, number[]> | null;
}

/**
 * Preview images fetched once per (page, which) and kept for the life of the component, so
 * flipping pages or toggling the heatmap does not refetch. Every object URL is revoked on
 * unmount or when the job changes.
 */
function usePreviewCache(jobId: string) {
  const urls = useRef(new Map<string, string>());
  const inflight = useRef(new Set<string>());
  const failedKeys = useRef(new Set<string>());
  const [failed, setFailed] = useState<Set<string>>(() => new Set());
  const [, bump] = useState(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    const cache = urls.current;
    const pending = inflight.current;
    return () => {
      alive.current = false;
      cache.forEach((u) => URL.revokeObjectURL(u));
      cache.clear();
      pending.clear();
      failedKeys.current.clear();
    };
  }, [jobId]);

  const request = useCallback(
    (page: number, which: Which) => {
      const key = `${page}:${which}`;
      if (urls.current.has(key) || inflight.current.has(key) || failedKeys.current.has(key)) return;
      inflight.current.add(key);
      authFetch(`${BACKEND_URL}/api/convert/pdf/${jobId}/preview/${page}?which=${which}`)
        .then(async (r) => {
          if (!r.ok) throw new Error(String(r.status));
          const url = URL.createObjectURL(await r.blob());
          // StrictMode's remount clears `inflight`, so the same key can land twice.
          if (!alive.current || urls.current.has(key)) {
            URL.revokeObjectURL(url);
            return;
          }
          urls.current.set(key, url);
          bump((n) => n + 1);
        })
        .catch(() => {
          if (!alive.current) return;
          failedKeys.current.add(key);
          setFailed((prev) => new Set(prev).add(key));
        })
        .finally(() => inflight.current.delete(key));
    },
    [jobId]
  );

  const get = (page: number, which: Which) => {
    const key = `${page}:${which}`;
    return { url: urls.current.get(key) ?? null, failed: failed.has(key) };
  };

  const retry = (page: number, which: Which) => {
    const key = `${page}:${which}`;
    failedKeys.current.delete(key);
    setFailed((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    request(page, which);
  };

  return { request, get, retry };
}

export function ComparePreview({ jobId, pageCount, page, onPageChange, scoreFor, pageMap }: ComparePreviewProps) {
  const [showDiff, setShowDiff] = useState(false);
  const [draft, setDraft] = useState(String(page));
  const cache = usePreviewCache(jobId);
  const { request } = cache;
  const total = Math.max(1, pageCount);
  const rightWhich: Which = showDiff ? "diff" : "converted";

  useEffect(() => setDraft(String(page)), [page]);

  useEffect(() => {
    request(page, "original");
    request(page, rightWhich);
  }, [request, page, rightWhich]);

  const go = useCallback(
    (n: number) => {
      if (!Number.isFinite(n)) return;
      onPageChange(Math.min(total, Math.max(1, Math.round(n))));
    },
    [onPageChange, total]
  );

  // Arrow keys flip pages unless the user is typing somewhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      if (e.key === "ArrowLeft" && page > 1) {
        e.preventDefault();
        go(page - 1);
      } else if (e.key === "ArrowRight" && page < total) {
        e.preventDefault();
        go(page + 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, page, total]);

  const outPages = pageMap?.[String(page)];
  const outLabel =
    outPages && outPages.length
      ? outPages.length === 1
        ? `output p.${outPages[0]}`
        : `output p.${outPages[0]}–${outPages[outPages.length - 1]}`
      : null;
  const score = scoreFor?.(page);

  const original = cache.get(page, "original");
  const right = cache.get(page, rightWhich);

  return (
    <div className="space-y-2" id="pdf-import-compare">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-[#8A8F98] font-medium uppercase tracking-wider">Original vs compiled</div>
        <div className="flex flex-wrap items-center gap-1.5">
          <label className="flex items-center gap-1.5 text-[11px] text-[#8A8F98] mr-1 cursor-pointer select-none">
            <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
            Highlight differences
          </label>
          <Button variant="outline" size="icon" aria-label="Previous page" disabled={page <= 1} onClick={() => go(page - 1)}
            className="h-7 w-7 border-[#23252A] bg-[#191A1B]"><ChevronLeft className="w-3.5 h-3.5" /></Button>
          <form
            className="flex items-center gap-1 text-[11px] font-mono tabular-nums"
            onSubmit={(e) => {
              e.preventDefault();
              go(Number(draft));
            }}
          >
            <input
              aria-label="Page number"
              inputMode="numeric"
              value={draft}
              onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={() => (draft ? go(Number(draft)) : setDraft(String(page)))}
              className="w-9 h-7 rounded-md border border-[#23252A] bg-[#191A1B] text-center text-[#F7F8F8] outline-none focus:border-[#5E6AD2]"
            />
            <span className="text-[#8A8F98]">/ {total}</span>
          </form>
          <Button variant="outline" size="icon" aria-label="Next page" disabled={page >= total} onClick={() => go(page + 1)}
            className="h-7 w-7 border-[#23252A] bg-[#191A1B]"><ChevronRight className="w-3.5 h-3.5" /></Button>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Pane
          label={`Original · p.${page}`}
          alt={`Original page ${page}`}
          url={original.url}
          failed={original.failed}
          onRetry={() => cache.retry(page, "original")}
        />
        <Pane
          label={`${showDiff ? "Differences" : "Compiled"}${outLabel ? ` · ${outLabel}` : ""}${score != null ? ` · match ${pct(score)}` : ""}`}
          alt={`${showDiff ? "Difference heatmap" : "Compiled page"} for page ${page}`}
          url={right.url}
          failed={right.failed}
          onRetry={() => cache.retry(page, rightWhich)}
        />
      </div>
      <p className="text-[10px] text-[#62666D]">
        Use ← / → to flip pages. {score != null ? "The match score compares the rendered pages. " : ""}Closest match, not pixel-exact.
      </p>
    </div>
  );
}

function Pane({ label, alt, url, failed, onRetry }: { label: string; alt: string; url: string | null; failed: boolean; onRetry: () => void }) {
  return (
    <figure className="rounded-lg border border-[#23252A] bg-white/95 overflow-hidden min-w-0">
      <figcaption className="px-2 py-1 text-[10px] uppercase tracking-wider bg-[#191A1B] text-[#8A8F98] truncate" title={label}>
        {label}
      </figcaption>
      <div className="aspect-[1/1.3] flex items-center justify-center">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={alt} className="w-full h-full object-contain" />
        ) : failed ? (
          <div className="flex flex-col items-center gap-1.5">
            <span className="text-[11px] text-[#62666D]">Preview unavailable</span>
            <button type="button" onClick={onRetry} className="text-[11px] text-[#5E6AD2] hover:underline">
              Retry
            </button>
          </div>
        ) : (
          <Loader2 className="w-4 h-4 animate-spin text-[#8A8F98]" aria-label="Loading preview" />
        )}
      </div>
    </figure>
  );
}
