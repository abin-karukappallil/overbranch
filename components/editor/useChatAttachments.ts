"use client";

/**
 * useChatAttachments — the files attached to the agent chat of one project.
 *
 * Files are uploaded once, as multipart, to `POST /api/agent/attachments`, and
 * the chat then refers to them by being in the same server-side session. The
 * editor used to keep a single file as a base64 string in React state, send it
 * inside every agent request and mirror it into localStorage: a real paper
 * overran the request body limit, and the mirror overran the storage quota.
 *
 * Only metadata lives here. The server is the source of truth (it holds the
 * bytes, and expires them), so the list is re-read on mount and after every
 * change rather than trusted from local state.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

export const ATTACHMENT_ACCEPT =
  ".pdf,.png,.jpg,.jpeg,.webp,.txt,.md,.tex,.bib,.csv,.json,application/pdf,image/png,image/jpeg,image/webp,text/*";

export interface ChatAttachment {
  /** Server id once uploaded; a local id while uploading. */
  id: string;
  filename: string;
  file_type?: string;
  kind?: "pdf" | "image" | "text";
  page_count?: number;
  size_bytes?: number;
  figure_count?: number | null;
  is_scanned?: boolean;
  status: "uploading" | "ready" | "error";
  error?: string;
}

interface ServerList {
  attachments?: Array<Omit<ChatAttachment, "status">>;
  max_files?: number;
  max_mb?: number;
  detail?: string;
}

const DEFAULT_MAX_FILES = 5;
const DEFAULT_MAX_MB = 25;

export function describeAttachment(a: ChatAttachment): string {
  if (a.status === "uploading") return "Uploading…";
  if (a.status === "error") return a.error || "Upload failed";
  const parts: string[] = [];
  if (a.kind === "pdf") {
    parts.push(`${a.page_count ?? 1} page${(a.page_count ?? 1) === 1 ? "" : "s"}`);
    if (typeof a.figure_count === "number") {
      parts.push(`${a.figure_count} figure${a.figure_count === 1 ? "" : "s"}`);
    }
    if (a.is_scanned) parts.push("scanned, no text");
  } else if (a.kind === "image") {
    parts.push("image");
  } else {
    parts.push("text");
  }
  if (a.size_bytes) {
    parts.push(a.size_bytes >= 1048576 ? `${(a.size_bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(a.size_bytes / 1024))} KB`);
  }
  return parts.join(" · ");
}

export function useChatAttachments(projectId: string | undefined, storageKey: string) {
  const project = projectId || "proj-default";
  const cacheKey = `overbranch_${storageKey}_attachments`;
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [limits, setLimits] = useState({ maxFiles: DEFAULT_MAX_FILES, maxMb: DEFAULT_MAX_MB });
  const projectRef = useRef(project);
  projectRef.current = project;
  const attachmentsRef = useRef(attachments);
  attachmentsRef.current = attachments;

  const adoptServer = useCallback((data: ServerList, keepLocal: ChatAttachment[] = []) => {
    if (data.max_files || data.max_mb) {
      setLimits((prev) => ({ maxFiles: data.max_files || prev.maxFiles, maxMb: data.max_mb || prev.maxMb }));
    }
    if (!Array.isArray(data.attachments)) return;
    const ready: ChatAttachment[] = data.attachments.map((a) => ({ ...a, status: "ready" as const }));
    setAttachments([...ready, ...keepLocal]);
  }, []);

  const refresh = useCallback(async () => {
    const asked = projectRef.current;
    try {
      const res = await authFetch(`${BACKEND_URL}/api/agent/attachments?project_id=${encodeURIComponent(asked)}`);
      if (!res.ok || projectRef.current !== asked) return;
      const data: ServerList = await res.json();
      // Uploads still in flight are not on the server yet; keep showing them.
      setAttachments((prev) => {
        const local = prev.filter((a) => a.status === "uploading");
        const ready = (data.attachments || []).map((a) => ({ ...a, status: "ready" as const }));
        return [...ready, ...local];
      });
      if (data.max_files || data.max_mb) {
        setLimits((prev) => ({ maxFiles: data.max_files || prev.maxFiles, maxMb: data.max_mb || prev.maxMb }));
      }
    } catch {
      // Offline or signed out: the cached chips stay; the next agent run reports what it has.
    }
  }, []);

  // Cached metadata first (instant chips), then the server's own list.
  useEffect(() => {
    try {
      const cached = localStorage.getItem(cacheKey);
      const parsed = cached ? JSON.parse(cached) : [];
      setAttachments(Array.isArray(parsed) ? parsed.filter((a: ChatAttachment) => a && a.status === "ready") : []);
      // The single-file predecessor of this hook stored the file itself here.
      localStorage.removeItem(`overbranch_${storageKey}_attached_file`);
    } catch {
      setAttachments([]);
    }
    void refresh();
  }, [cacheKey, storageKey, refresh, project]);

  useEffect(() => {
    try {
      const ready = attachments.filter((a) => a.status === "ready");
      if (ready.length) localStorage.setItem(cacheKey, JSON.stringify(ready));
      else localStorage.removeItem(cacheKey);
    } catch {
      // metadata only; losing the cache costs one request on the next mount
    }
  }, [attachments, cacheKey]);

  const addFiles = useCallback(
    async (input: FileList | File[] | null | undefined) => {
      const files = Array.from(input || []);
      if (!files.length) return;

      const current = attachmentsRef.current.filter((a) => a.status !== "error");
      // Re-uploading a name replaces that file, so it does not count against the cap.
      const names = new Set(current.map((a) => a.filename));
      const room = limits.maxFiles - current.length;
      const accepted: File[] = [];
      let overCap = 0;
      for (const f of files) {
        if (f.size > limits.maxMb * 1048576) {
          toast.error(`${f.name} is ${(f.size / 1048576).toFixed(1)} MB. The limit is ${limits.maxMb} MB per file.`);
        } else if (names.has(f.name) || accepted.filter((a) => !names.has(a.name)).length < room) {
          accepted.push(f);
        } else {
          overCap += 1;
        }
      }
      if (overCap > 0) {
        toast.error(
          `A chat can hold at most ${limits.maxFiles} attached files. ${overCap} file${overCap === 1 ? " was" : "s were"} not added.`,
        );
      }
      if (!accepted.length) return;

      const placeholders: ChatAttachment[] = accepted.map((f, i) => ({
        id: `local-${Date.now()}-${i}`,
        filename: f.name,
        file_type: f.type,
        size_bytes: f.size,
        status: "uploading",
      }));
      setAttachments((prev) => [
        ...prev.filter((a) => a.status !== "error" && !accepted.some((f) => f.name === a.filename)),
        ...placeholders,
      ]);

      // One at a time: the server enforces the cap per upload, and order is preserved.
      for (let i = 0; i < accepted.length; i += 1) {
        const file = accepted[i];
        const localId = placeholders[i].id;
        const fail = (message: string) => {
          setAttachments((prev) => prev.map((a) => (a.id === localId ? { ...a, status: "error", error: message } : a)));
          toast.error(`${file.name}: ${message}`);
        };
        try {
          const form = new FormData();
          form.append("project_id", projectRef.current);
          form.append("file", file, file.name);
          const res = await authFetch(`${BACKEND_URL}/api/agent/attachments`, { method: "POST", body: form });
          const data: ServerList = await res.json().catch(() => ({}));
          if (!res.ok) {
            fail(typeof data.detail === "string" ? data.detail : `Upload failed (${res.status}).`);
            continue;
          }
          setAttachments((prev) => {
            const stillLocal = prev.filter((a) => a.status !== "ready" && a.id !== localId);
            const ready = (data.attachments || []).map((a) => ({ ...a, status: "ready" as const }));
            return [...ready, ...stillLocal];
          });
          if (data.max_files || data.max_mb) adoptServer({ max_files: data.max_files, max_mb: data.max_mb });
        } catch {
          fail("Could not reach the server.");
        }
      }
    },
    [limits.maxFiles, limits.maxMb, adoptServer],
  );

  const remove = useCallback(async (attachment: ChatAttachment) => {
    setAttachments((prev) => prev.filter((a) => a.id !== attachment.id));
    if (attachment.status !== "ready") return;
    try {
      const res = await authFetch(
        `${BACKEND_URL}/api/agent/attachments/${encodeURIComponent(attachment.id)}?project_id=${encodeURIComponent(projectRef.current)}`,
        { method: "DELETE" },
      );
      if (res.ok) {
        const data: ServerList = await res.json();
        setAttachments((prev) => {
          const local = prev.filter((a) => a.status !== "ready");
          return [...(data.attachments || []).map((a) => ({ ...a, status: "ready" as const })), ...local];
        });
      }
    } catch {
      void refresh();
    }
  }, [refresh]);

  const clear = useCallback(async () => {
    setAttachments([]);
    try {
      await authFetch(
        `${BACKEND_URL}/api/agent/attachments?project_id=${encodeURIComponent(projectRef.current)}`,
        { method: "DELETE" },
      );
    } catch {
      // the server expires them on its own
    }
  }, []);

  const ready = useMemo(() => attachments.filter((a) => a.status === "ready"), [attachments]);
  const isUploading = attachments.some((a) => a.status === "uploading");

  return { attachments, ready, isUploading, maxFiles: limits.maxFiles, maxMb: limits.maxMb, addFiles, remove, clear, refresh };
}
