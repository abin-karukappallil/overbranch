"use client";

/**
 * usePdfConversionJob — client for the backend PDF → LaTeX importer (/api/convert/pdf).
 * Starts a job (multipart upload), polls its progress, and finishes jobs that wait
 * for overwrite confirmation. Shared by the dashboard, /convert page, editor and copilot.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "@/lib/api-client";

export const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

const POLL_MS = 1500;
const TERMINAL = new Set(["done", "error", "needs_confirmation", "cancelled"]);

export interface ConversionConfig {
  llm_available: boolean;
  model: string;
  max_file_mb: number;
  max_pages: number;
  threshold: number;
}

export type PageFallback = "layout" | "image" | null;

export interface PageStatus {
  number: number;
  status: string;
  similarity: number | null;
  text_coverage?: number | null;
  attempts: number;
  fallback?: PageFallback;
  warnings?: string[];
}

export interface PageReport {
  number: number;
  status: string;
  similarity: number | null;
  ssim: number | null;
  pixel_diff: number | null;
  text_coverage: number | null;
  extra_ratio: number | null;
  shift_pt: number | null;
  displacement: number | null;
  attempts: number;
  compile_repairs: number;
  fallback: PageFallback;
  overflow: boolean;
  warnings: string[];
}

export interface ConversionReport {
  page_count: number;
  pages: PageReport[];
  warnings: string[];
  threshold: number;
  coverage_target: number;
  max_displacement: number;
  compiled: boolean;
  compiled_page_count: number | null;
  model: string;
  llm_used: boolean;
  disclaimer: string;
  mean_similarity: number | null;
}

export interface ConversionJob {
  job_id: string;
  project_id: string;
  filename: string;
  status: string;
  stage: string;
  message: string;
  progress: number;
  page_count: number;
  pages: PageStatus[];
  report: ConversionReport | null;
  result: { tex_path: string; files: string[]; assets: string[] } | null;
  error: string | null;
  conflict_path?: string | null;
}

export class ConversionRequestError extends Error {
  status: number;
  jobId?: string;
  constructor(message: string, status: number, jobId?: string) {
    super(message);
    this.status = status;
    this.jobId = jobId;
  }
}

async function readError(res: Response): Promise<{ message: string; jobId?: string }> {
  let message = "";
  let jobId: string | undefined;
  try {
    const body = await res.json();
    jobId = body?.job_id;
    const detail = body?.detail;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) message = detail.map((d: any) => d?.msg || String(d)).join("; ");
  } catch {
    /* fall through */
  }
  if (!message) {
    switch (res.status) {
      case 401:
        message = "Please sign in (or start a guest session) to import PDFs.";
        break;
      case 409:
        message = "A conversion is already running for your account.";
        break;
      case 413:
        message = "The PDF is too large.";
        break;
      case 429:
        message = "Too many conversions. Please wait before trying again.";
        break;
      default:
        message = `Request failed (${res.status}).`;
    }
  }
  return { message, jobId };
}

function persistGuestToken(token?: string) {
  if (!token || typeof window === "undefined") return;
  localStorage.setItem("ob_guest_token", token);
  document.cookie = `ob_guest_token=${token}; path=/; max-age=86400; SameSite=Lax`;
}

export function useConversionConfig() {
  const [config, setConfig] = useState<ConversionConfig | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`${BACKEND_URL}/api/convert/pdf/config`)
      .then((r) => (r.ok ? r.json() : null))
      .then((c) => !cancelled && c && setConfig(c))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return config;
}

export interface StartOptions {
  projectId?: string;
  projectName?: string;
  overwrite?: boolean;
  cancelPrevious?: boolean;
}

export function usePdfConversionJob() {
  const [job, setJob] = useState<ConversionJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorJobId, setErrorJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeId = useRef<string | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const poll = useCallback(
    async (jobId: string) => {
      if (activeId.current !== jobId) return;
      try {
        const res = await authFetch(`${BACKEND_URL}/api/convert/pdf/${jobId}`);
        if (!res.ok) {
          const err = await readError(res);
          throw new ConversionRequestError(err.message, res.status, err.jobId);
        }
        const data: ConversionJob = await res.json();
        if (activeId.current !== jobId) return;
        setJob(data);
        if (data.status === "error") setError(data.error || "Conversion failed.");
        if (TERMINAL.has(data.status)) return;
      } catch (e) {
        // Transient network errors: keep polling; a missing job is final
        if (e instanceof ConversionRequestError && e.status === 404) {
          setError("This conversion job no longer exists.");
          return;
        }
      }
      timer.current = setTimeout(() => poll(jobId), POLL_MS);
    },
    []
  );

  const attach = useCallback(
    (jobId: string) => {
      stopPolling();
      activeId.current = jobId;
      setError(null);
      setErrorJobId(null);
      poll(jobId);
    },
    [poll, stopPolling]
  );

  const start = useCallback(
    async (file: File, opts: StartOptions = {}) => {
      setStarting(true);
      setError(null);
      setErrorJobId(null);
      try {
        const form = new FormData();
        form.append("file", file);
        if (opts.projectId) form.append("project_id", opts.projectId);
        if (opts.projectName) form.append("project_name", opts.projectName);
        if (opts.overwrite) form.append("overwrite", "true");
        if (opts.cancelPrevious) form.append("cancel_previous", "true");
        const res = await authFetch(`${BACKEND_URL}/api/convert/pdf`, { method: "POST", body: form });
        if (!res.ok) {
          const err = await readError(res);
          throw new ConversionRequestError(err.message, res.status, err.jobId);
        }
        const body = await res.json();
        persistGuestToken(body.guest_token);
        setJob({
          job_id: body.job_id,
          project_id: body.project_id,
          filename: file.name,
          status: "queued",
          stage: "queued",
          message: "Upload complete — starting conversion…",
          progress: 0,
          page_count: body.page_count,
          pages: [],
          report: null,
          result: null,
          error: null,
        });
        attach(body.job_id);
        return body as { job_id: string; project_id: string };
      } catch (e) {
        if (e instanceof ConversionRequestError) {
          setError(e.message);
          if (e.jobId) setErrorJobId(e.jobId);
        } else {
          setError(e instanceof Error ? e.message : "Upload failed.");
        }
        return null;
      } finally {
        setStarting(false);
      }
    },
    [attach]
  );

  const cancel = useCallback(
    async (jobId?: string) => {
      const targetId = jobId || activeId.current || job?.job_id;
      if (!targetId) return false;
      try {
        const res = await authFetch(`${BACKEND_URL}/api/convert/pdf/${targetId}/cancel`, {
          method: "POST",
        });
        if (res.ok) {
          stopPolling();
          setJob((prev) => (prev ? { ...prev, status: "cancelled", message: "Conversion cancelled." } : null));
          setError(null);
          setErrorJobId(null);
          return true;
        }
      } catch {
        /* ignore */
      }
      return false;
    },
    [job, stopPolling]
  );

  const commit = useCallback(
    async (opts: { overwrite?: boolean; targetPath?: string }) => {
      if (!job) return false;
      setError(null);
      const res = await authFetch(`${BACKEND_URL}/api/convert/pdf/${job.job_id}/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ overwrite: !!opts.overwrite, target_path: opts.targetPath || "main.tex" }),
      });
      if (!res.ok) {
        const err = await readError(res);
        setError(err.message);
        return false;
      }
      attach(job.job_id);
      return true;
    },
    [job, attach]
  );

  const reset = useCallback(() => {
    stopPolling();
    activeId.current = null;
    setJob(null);
    setError(null);
    setErrorJobId(null);
  }, [stopPolling]);

  useEffect(() => stopPolling, [stopPolling]);

  return { job, error, errorJobId, starting, start, cancel, attach, commit, reset };
}

/** Loads an authenticated preview PNG (original / converted / diff) as an object URL. */
export function usePagePreview(jobId: string | null, page: number, which: "original" | "converted" | "diff") {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!jobId) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    setUrl(null);
    setFailed(false);
    authFetch(`${BACKEND_URL}/api/convert/pdf/${jobId}/preview/${page}?which=${which}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(String(r.status));
        objectUrl = URL.createObjectURL(await r.blob());
        if (!cancelled) setUrl(objectUrl);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [jobId, page, which]);
  return { url, failed };
}
