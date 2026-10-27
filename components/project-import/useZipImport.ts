"use client";

/**
 * useZipImport — client for POST /api/projects/import-zip (same-origin proxy -> backend).
 * A single multipart upload over XMLHttpRequest (fetch exposes no upload progress), no polling:
 * the backend validates, extracts and responds in one request.
 *
 *   idle -> uploading (progress 0..1) -> extracting (bytes sent, awaiting response) -> done | error
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthHeaders } from "@/lib/api-client";

export const IMPORT_ZIP_ENDPOINT = "/api/projects/import-zip";

export type ZipImportState = "idle" | "uploading" | "extracting" | "done" | "error";

export interface ImportedProject {
  project_id: string;
  name: string;
  /** Top-level archive folder this project came from (null for a single-project archive). */
  folder?: string | null;
  files_count: number;
  assets_count: number;
  /** The project's main document (may be in a sub-folder, e.g. "thesis/thesis.tex"). */
  main_file?: string;
  main_tex_path: string;
  created_main_tex: boolean;
}

/**
 * The import response. The top-level fields describe the FIRST project (back-compat with the
 * single-project shape); `projects` lists every project an archive produced (a Prism-style
 * archive with one folder per project creates several).
 */
export interface ZipImportResult extends ImportedProject {
  projects?: ImportedProject[];
  projects_count?: number;
}

/** Every project an import created, whichever response shape the server used. */
export function importedProjects(result: ZipImportResult): ImportedProject[] {
  return result.projects && result.projects.length > 0 ? result.projects : [result];
}

export const EXPORT_PROJECT_ENDPOINT = "/api/projects/export";
export const EXPORT_ALL_ENDPOINT = "/api/projects/export-all";

/**
 * Starts a browser download of an endpoint with a same-origin <a download> click: the Next
 * proxy routes carry the session cookie and stream the backend's .zip. Never a backend URL.
 */
function triggerDownload(href: string, fileName: string) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = fileName;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

/** Downloads one project as "<project name>.zip". */
export function downloadProjectZip(projectId: string, projectName?: string) {
  if (!projectId) return;
  triggerDownload(
    `${EXPORT_PROJECT_ENDPOINT}?project_id=${encodeURIComponent(projectId)}`,
    `${(projectName || "project").trim() || "project"}.zip`,
  );
}

/** Downloads every project the user can access: one top-level folder per project. */
export function downloadAllProjectsZip() {
  triggerDownload(EXPORT_ALL_ENDPOINT, "overbranch-projects.zip");
}

/** Backend `detail` codes -> friendly sentences. */
export const ZIP_IMPORT_ERRORS: Record<string, string> = {
  "too-large": "This ZIP is too large to import (the upload limit is 50 MB, and the unpacked project must stay under 200 MB).",
  encrypted: "This ZIP is password-protected. Remove the password and upload it again.",
  "empty-archive": "This ZIP has no importable files. Hidden files and system folders are ignored.",
  "unsafe-path": "This ZIP contains files with unsafe paths (absolute paths or \"..\"), so it was rejected.",
  "unsafe-symlink": "This ZIP contains symbolic links, which are not allowed. Re-create it without them.",
  "ratio-exceeded": "This ZIP expands far more than normal data would, so it was rejected as a possible zip bomb.",
  "file-too-large": "A file inside this ZIP is larger than 25 MB, which is the per-file limit.",
  "too-many-files": "This ZIP contains too many files to import.",
  "bad-zip": "That file is not a valid ZIP archive.",
  "extract-failed": "Something went wrong while unpacking the ZIP. Nothing was created; please try again.",
};

export function describeZipImportError(status: number, detail: unknown): { code: string; message: string } {
  const code = typeof detail === "string" ? detail : (detail as any)?.code;
  if (typeof code === "string" && ZIP_IMPORT_ERRORS[code]) return { code, message: ZIP_IMPORT_ERRORS[code] };
  if (status === 401) return { code: "unauthorized", message: "Please sign in to import a project." };
  if (status === 413) return { code: "too-large", message: ZIP_IMPORT_ERRORS["too-large"] };
  if (status === 429) return { code: "rate-limited", message: "You've imported too many projects recently. Please try again later." };
  const text = typeof detail === "string" ? detail : (detail as any)?.message;
  return { code: "unknown", message: text || `Import failed (HTTP ${status}).` };
}

export function useZipImport() {
  const [state, setState] = useState<ZipImportState>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [result, setResult] = useState<ZipImportResult | null>(null);
  const xhrRef = useRef<XMLHttpRequest | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      xhrRef.current?.abort();
    };
  }, []);

  const fail = useCallback((code: string, message: string) => {
    if (!mounted.current) return;
    setState("error");
    setErrorCode(code);
    setError(message);
  }, []);

  const reset = useCallback(() => {
    xhrRef.current?.abort();
    xhrRef.current = null;
    setState("idle");
    setProgress(0);
    setError(null);
    setErrorCode(null);
    setResult(null);
  }, []);

  /** Uploads the ZIP; resolves with the result, or null on failure (see `error`). */
  const start = useCallback(
    async (file: File, projectName?: string): Promise<ZipImportResult | null> => {
      if (xhrRef.current) return null; // one import at a time
      setState("uploading");
      setProgress(0);
      setError(null);
      setErrorCode(null);
      setResult(null);

      const form = new FormData();
      form.append("file", file, file.name);
      if (projectName?.trim()) form.append("project_name", projectName.trim());

      const headers = await getAuthHeaders();

      return new Promise<ZipImportResult | null>((resolve) => {
        const xhr = new XMLHttpRequest();
        xhrRef.current = xhr;
        const done = (value: ZipImportResult | null) => {
          xhrRef.current = null;
          resolve(value);
        };

        xhr.open("POST", IMPORT_ZIP_ENDPOINT);
        xhr.withCredentials = true;
        xhr.responseType = "text";
        for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && mounted.current) setProgress(e.total ? e.loaded / e.total : 0);
        };
        // All bytes sent: the server is now validating and extracting (indeterminate phase).
        xhr.upload.onload = () => {
          if (mounted.current) {
            setProgress(1);
            setState("extracting");
          }
        };
        xhr.onload = () => {
          let body: any = null;
          try {
            body = JSON.parse(xhr.responseText);
          } catch {
            /* non-JSON error page */
          }
          if (xhr.status >= 200 && xhr.status < 300 && body?.project_id) {
            if (mounted.current) {
              setResult(body as ZipImportResult);
              setState("done");
            }
            done(body as ZipImportResult);
          } else {
            const { code, message } = describeZipImportError(xhr.status, body?.detail ?? xhr.statusText);
            fail(code, message);
            done(null);
          }
        };
        xhr.onerror = () => {
          fail("network", "Could not reach the server. Check your connection and try again.");
          done(null);
        };
        xhr.onabort = () => done(null);
        xhr.send(form);
      });
    },
    [fail],
  );

  return { start, reset, progress, error, errorCode, state, result };
}
