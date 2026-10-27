"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "@/lib/api-client";

export interface ProjectFile {
  path: string;
  name: string;
  size: number;
  type: "document" | "image";
  ext: string;
  /** True for the project's main document (list-files `is_main`). */
  is_main?: boolean;
}

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

// In-memory SWR cache for instant file tree display across views and re-renders.
// Module-level on purpose: every consumer (the Files panel, the @mention popover,
// both the desktop and mobile layouts) shares one cache and one fetch.
const fileListCache = new Map<string, { files: ProjectFile[]; mainFile: string | null; timestamp: number }>();
const listeners = new Map<string, Set<(files: ProjectFile[], mainFile: string | null) => void>>();
const inFlight = new Map<string, Promise<void>>();
// Bumped per request so an older response can never overwrite a newer one.
const requestSeq = new Map<string, number>();

function publish(projectId: string, files: ProjectFile[], mainFile: string | null) {
  listeners.get(projectId)?.forEach((fn) => fn(files, mainFile));
}

/** Fetch the list into the shared cache. Non-forced calls join a request already in flight. */
function loadFiles(projectId: string, force: boolean): Promise<void> {
  const pending = inFlight.get(projectId);
  if (pending && !force) return pending;

  const seq = (requestSeq.get(projectId) ?? 0) + 1;
  requestSeq.set(projectId, seq);

  const request = (async () => {
    try {
      const res = await authFetch(`${BACKEND_URL}/api/projects/list-files?project_id=${projectId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.files && Array.isArray(data.files) && requestSeq.get(projectId) === seq) {
          // list-files reports the project's MAIN document (it can live in a sub-folder).
          const mainFile = typeof data.main_file === "string" && data.main_file ? data.main_file : null;
          fileListCache.set(projectId, { files: data.files, mainFile, timestamp: Date.now() });
          publish(projectId, data.files, mainFile);
        }
      }
    } catch (err) {
      console.warn("Failed to fetch project files list:", err);
    } finally {
      if (requestSeq.get(projectId) === seq) inFlight.delete(projectId);
    }
  })();
  inFlight.set(projectId, request);
  return request;
}

/**
 * The project's file list, shared through a module-level cache.
 *
 * `refetch()` drops the cache and reloads with the spinner (use it after a file is
 * created, renamed, deleted or uploaded). `refreshTrigger` changing reloads quietly,
 * keeping whatever is cached on screen. `mainFile` is the project's main document path
 * from list-files (null until the first list arrives).
 */
export function useProjectFiles(
  projectId: string,
  refreshTrigger?: unknown,
): { files: ProjectFile[]; mainFile: string | null; loading: boolean; refetch: () => void } {
  const [files, setFiles] = useState<ProjectFile[]>(() => fileListCache.get(projectId)?.files || []);
  const [mainFile, setMainFile] = useState<string | null>(() => fileListCache.get(projectId)?.mainFile ?? null);
  const [loading, setLoading] = useState(() => !fileListCache.has(projectId));
  const projectRef = useRef(projectId);
  projectRef.current = projectId;

  // Follow the shared cache for the current project.
  useEffect(() => {
    if (!projectId) return;
    const cached = fileListCache.get(projectId);
    setFiles(cached?.files || []);
    setMainFile(cached?.mainFile ?? null);
    setLoading(!cached);

    const fn = (next: ProjectFile[], nextMain: string | null) => {
      setFiles(next);
      setMainFile(nextMain);
    };
    let set = listeners.get(projectId);
    if (!set) listeners.set(projectId, (set = new Set()));
    set.add(fn);
    return () => {
      set!.delete(fn);
      if (set!.size === 0 && listeners.get(projectId) === set) listeners.delete(projectId);
    };
  }, [projectId]);

  const fetchNow = useCallback((forceSpinner: boolean) => {
    const id = projectRef.current;
    if (!id) return;
    const cached = fileListCache.get(id);
    const hasCache = !!cached && cached.files.length > 0;
    if (!hasCache || forceSpinner) setLoading(true);
    loadFiles(id, forceSpinner).finally(() => {
      if (projectRef.current === id) setLoading(false);
    });
  }, []);

  useEffect(() => {
    fetchNow(false);
  }, [projectId, refreshTrigger, fetchNow]);

  const refetch = useCallback(() => {
    const id = projectRef.current;
    if (id) fileListCache.delete(id);
    fetchNow(true);
  }, [fetchNow]);

  return { files, mainFile, loading, refetch };
}
