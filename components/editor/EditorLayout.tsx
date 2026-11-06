"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";

import Editor, { OnMount } from "@monaco-editor/react";
import { Drawer } from "vaul";
import Link from "next/link";
import {
  ArrowLeft,
  FolderGit2,
  FileCode2,
  Eye,
  Bot,
  Columns2,
  Play,
  RotateCw,
  Send,
  ZoomIn,
  ZoomOut,
  X,
  GripVertical,
  Save,
  Key,
  Settings2,
  Cpu,
  CheckCheck,
  Check,
  HardDrive,
  ShieldAlert,
  AlertTriangle,
  Lock,
  ClipboardPaste,
  CheckSquare,
  MousePointerClick,
  Paperclip,
  Square,
  File,
  AlertCircle,
  Palette,
  Zap,
  ChevronDown,
  ChevronUp,
  PlusCircle,
  Trash2,
  Search,
  Sparkles,
  Undo2,
  Redo2,
  Maximize2,
  Sun,
  Moon,
} from "lucide-react";
import { useTheme } from "next-themes";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { CollaboratorAvatars } from "@/components/editor/CollaboratorAvatars";
import { CollabPresenceBar } from "@/components/editor/CollabPresenceBar";
import { useCollaboration } from "@/lib/collab/useCollaboration";
import { applyTextToEditor, computeLineEdits } from "@/lib/collab/text-diff";
import { collabLog } from "@/lib/collab/log";
import { authClient } from "@/lib/auth-client";
import { PDFViewer, type PDFViewerRefHandle } from "@/components/editor/PDFViewer";
import type { PDFViewerViewState } from "@/components/extend/pdf-viewer";
import { readStoredView } from "@/lib/pdf-view-state";
import { CompileSplitButton, isTexEngine, type TexEngine } from "@/components/editor/CompileToolbar";
import { PresentationView } from "@/components/editor/PresentationView";
import { ModelSelector, type ProviderGroup } from "@/components/editor/ModelSelector";
import type { SyncTeXForwardResult, SyncState } from "@/types/sync";
import { ProjectFilesPanel } from "@/components/editor/ProjectFilesPanel";
import { useProjectFiles } from "@/components/editor/useProjectFiles";
import { ImportPdfDialog } from "@/components/pdf-import/ImportPdfDialog";
import { InlineDiffEditor, EditItem } from "@/components/editor/InlineDiffEditor";
import { EditorSearchBar } from "@/components/editor/EditorSearchBar";
import { MobileEditorAssist } from "@/components/editor/MobileEditorAssist";
import { CopyButton } from "@/components/editor/CopyButton";
import { FileAnalyzerModal } from "@/components/editor/FileAnalyzerModal";
import { ApiSettingsModal } from "@/components/editor/ApiSettingsModal";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { classifyCompileResponse, nextRetryDelay, type CompileOutcome } from "@/lib/compile-retry";
import { trpc, trpcClient } from "@/trpc/client";
import { pickLine, pickOccurrence, pickWithinLine } from "@/lib/pdf-sync";
import { COARSE_POINTER_QUERY, shouldSendOnEnter } from "@/lib/chat-input";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { ChatModeToggle, type ChatMode } from "@/components/editor/ChatModeToggle";
import { EditHistoryStore, type EditHistory } from "@/lib/EditHistoryStore";
import { ChatMessageContent } from "@/components/editor/ChatMessageContent";
import { AgentReasoningWindow } from "@/components/editor/AgentReasoningWindow";
import { computeContentHash, getCachedDocumentChunks, setCachedDocumentChunks } from "@/lib/IndexedDBEmbeddingCache";
import { authFetch } from "@/lib/api-client";
import {
  applyEditItems,
  SAFE_APPLY_FAILURE,
  type AppliedEditItem,
  type ApplyOutcome,
} from "@/lib/latex-edit-apply";
import { resolveEditsOnServer } from "@/lib/latex-validate";
import { ChatAttachments } from "@/components/editor/ChatAttachments";
import { MentionChips } from "@/components/editor/MentionChips";
import { addMention, makeFileMention, makeMention, removeMention, type MentionRef } from "@/lib/mentions";
import { FileMentionPopover } from "@/components/editor/FileMentionPopover";
import { blockStats, buildReviewBlocks, placeBlocks, type ReviewHunk } from "@/lib/inline-diff";
import { InlineDiffController, type InlineDiffState } from "@/lib/inline-diff-monaco";
import { ATTACHMENT_ACCEPT, useChatAttachments } from "@/components/editor/useChatAttachments";

const SHOW_EDIT_DEBUG = process.env.NODE_ENV !== "production";

// The only thing a user is told when the model gateways are down (the backend cycles its whole
// gateway chain before it gives up, so this means "try again", never "your document is broken").
const MODEL_OUTAGE_MESSAGE = "Model outage — please retry.";
// How long the agent stream may be completely silent before the client gives up on it. The backend
// sends a keep-alive every 3s, so a live run never gets near this.
const AGENT_IDLE_TIMEOUT_MS = 60_000;

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

const AUXILIARY_EXT_REGEX = /\.(aux|lof|lot|toc|log|out|synctex(\.gz)?|fls|fdb_latexmk|nav|snm|vrb|bcf|run\.xml|blg|idx|ind|ilg|glo|gls|glg|acn|acr|alg|nlo|nls|nlg|ist|dvi|xdv)$/i;

function isAuxiliaryFilePath(path: string | null | undefined): boolean {
  if (!path) return false;
  return AUXILIARY_EXT_REGEX.test(path.trim());
}

interface EditorLayoutProps {
  projectId?: string;
  isGuest?: boolean;
  expiresAt?: string | null;
}

interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  text: string;
  time: string;
  mode?: ChatMode;
  edits?: EditItem[];
  /** The file these edits were computed against; they may only be applied to it. */
  editsFile?: string;
  isApplied?: boolean;
  isReverted?: boolean;
  historyEntryId?: string;
  /** Inline review progress: how many of the proposal's changes were accepted. */
  appliedChanges?: number;
  totalChanges?: number;
  diff?: {
    original_chunk: string;
    proposed_chunk: string;
    explanation: string;
  };
  failure?: any;
  detailedErrors?: any[];
}

interface AuthoritativeDoc {
  file: string;
  originalCode: string;
  proposedCode: string;
  /** Structurally closed change blocks (apply contract v4), for the inline review. */
  hunks?: ReviewHunk[];
}

interface DiffData {
  original_chunk: string;
  proposed_chunk: string;
  explanation: string;
  /**
   * The backend's full healed+validated buffer for this file. When the live
   * document still matches `originalCode`, this is written verbatim instead of
   * replaying chunks — see lib/latex-edit-apply.ts.
   */
  authoritative?: AuthoritativeDoc;
}

class EditorErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.warn("Monaco Editor exception intercepted by ErrorBoundary:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-4 bg-background text-foreground text-xs font-mono space-y-3">
          <AlertTriangle className="w-8 h-8 text-amber-400" />
          <span className="font-semibold text-amber-700 dark:text-amber-300">Editor Intercepted Event Exception</span>
          <p className="text-muted-foreground text-center text-[11px] max-w-xs">
            The editor safely recovered from clipboard/input exception.
          </p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-bold shadow-md"
          >
            Reload Editor
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// No mock code — real content loaded from backend API on mount
const initialLatexCode = "";

const quickSymbols = [
  { label: "\\begin", insert: "\\begin{equation}\n  \n\\end{equation}" },
  { label: "\\cite", insert: "\\cite{}" },
  { label: "\\ref", insert: "\\ref{}" },
  { label: "$...$", insert: "$ $" },
  { label: "\\sec", insert: "\\section{}" },
  { label: "\\pkg", insert: "\\usepackage{}" },
  { label: "{}", insert: "{}" },
  { label: "\\alpha", insert: "\\alpha" },
  { label: "\\sum", insert: "\\sum_{i=1}^{N}" },
];

interface ModelsResponse {
  providers: ProviderGroup[];
  default_model: string;
}

export function extractLatexFromResponse(response: string): string | null {
  const pattern = new RegExp("```(?:latex)?\\s*\\n([\\s\\S]*?)```");
  const match = response.match(pattern);
  if (match) return match[1].trim();

  const rawDocMatch = response.match(/(\\documentclass[\s\S]*?\\end\{document\}|\\begin\{frame\}[\s\S]*?\\end\{frame\}|\\begin\{[a-zA-Z*]+\}[\s\S]*?\\end\{[a-zA-Z*]+\})/);
  if (rawDocMatch) return rawDocMatch[1].trim();

  return null;
}

export function extractChunkLatex(response: string): string | null {
  const marker = response.indexOf("UPDATED_LATEX:");
  if (marker === -1) {
    return extractLatexFromResponse(response);
  }
  const afterMarker = response.slice(marker);
  return extractLatexFromResponse(afterMarker);
}

export function sanitizeChunkReferences(text: string): string {
  if (!text) return "";
  let cleaned = text
    .replace(/(?:\b(?:in|from|for|of)?\s*\[?CHUNK\s*\d+\]?:?\s*)/gi, "")
    .replace(/^\s*[:\-]\s*/, "")
    .replace(/\s+([.,!?;])/g, "$1")
    .trim();
  if (cleaned.length > 0) {
    cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }
  return cleaned;
}

export function extractChunkId(response: string): number | null {
  const match = response.match(/CHUNK_ID:\s*(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

export function extractChangesSummary(response: string): string | null {
  const marker = response.indexOf("CHANGES_SUMMARY:");
  if (marker === -1) return null;
  return response.slice(marker + "CHANGES_SUMMARY:".length).trim();
}

/**
 * Clears the applied/reverted flags on messages that share one `historyEntryId`.
 *
 * Accepting from the floating diff card used to stamp every message that still
 * carried an `edits` array with the same history id, so one Revert flipped them
 * all. The code path is fixed, but chats already persisted in localStorage keep
 * the corrupted flags — and would keep reproducing the symptom — until they are
 * cleaned up once on load.
 */
export function repairSharedEditHistoryIds<T extends { historyEntryId?: string }>(
  messages: T[],
): T[] {
  const counts = new Map<string, number>();
  for (const m of messages) {
    if (m.historyEntryId) {
      counts.set(m.historyEntryId, (counts.get(m.historyEntryId) ?? 0) + 1);
    }
  }
  const shared = new Set(
    [...counts.entries()].filter(([, n]) => n > 1).map(([id]) => id),
  );
  if (shared.size === 0) return messages;
  return messages.map((m) =>
    m.historyEntryId && shared.has(m.historyEntryId)
      ? { ...m, isApplied: false, isReverted: false, historyEntryId: undefined }
      : m,
  );
}

/**
 * Non-error notes the compiler attaches to a SUCCESSFUL compile: `notices` (strings) and
 * diagnostics of type "FONT" (severity "warning"), de-duplicated.
 */
function collectCompileNotices(body: any): string[] {
  const out: string[] = [];
  const add = (v: unknown) => {
    const t = typeof v === "string" ? v.trim() : "";
    if (t && !out.includes(t)) out.push(t);
  };
  if (Array.isArray(body?.notices)) body.notices.forEach(add);
  if (Array.isArray(body?.diagnostics)) {
    for (const d of body.diagnostics) {
      if (d && d.type === "FONT") add(d.message);
    }
  }
  return out;
}

export function EditorLayout({
  projectId,
  isGuest: propIsGuest,
  expiresAt: propExpiresAt,
}: EditorLayoutProps) {
  const [code, setCode] = useState(initialLatexCode);
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");
  const [activeMobileTab, setActiveMobileTab] = useState<"code" | "files" | "pdf" | "ai" | "split">("code");
  const [filesOpen, setFilesOpen] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth >= 1200;
    }
    return true;
  });
  const [activeFilePath, setActiveFilePath] = useState("main.tex");
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [isCompiling, setIsCompiling] = useState(false);
  // True while a compile is waiting out a 429 backoff rather than running TeX.
  const [compileBusy, setCompileBusy] = useState(false);
  const [engine, setEngineState] = useState<TexEngine>("pdfLaTeX");
  // The engine is remembered per project (a XeLaTeX document stays XeLaTeX).
  const engineStorageKey = `overbranch:engine:${projectId || "default"}`;
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(engineStorageKey);
      if (isTexEngine(saved)) setEngineState(saved);
    } catch {
      // Storage blocked (private window, sandboxed iframe): keep the default.
    }
  }, [engineStorageKey]);
  const setEngine = useCallback(
    (next: TexEngine) => {
      setEngineState(next);
      try {
        window.localStorage.setItem(engineStorageKey, next);
      } catch {
        // Not persisted; the choice still applies to this session.
      }
    },
    [engineStorageKey]
  );
  const [pdfBase64, setPdfBase64] = useState<string | null>(null);
  const [errorLog, setErrorLog] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  // Selections pinned to the next chat message with "@ Mention".
  const [mentions, setMentions] = useState<MentionRef[]>([]);
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const [diffData, setDiffData] = useState<DiffData | null>(null);
  const [diffEditsList, setDiffEditsList] = useState<EditItem[]>([]);
  // Find & replace bar; shared by the desktop and mobile editors.
  const [searchOpen, setSearchOpen] = useState(false);
  /**
   * The assistant message whose edits are currently in `diffEditsList`.
   * The floating diff cards used to accept edits with no message id, which
   * made commitEditOutcome mark EVERY past message as applied under one shared
   * history id — so a single Revert flipped all of them.
   */
  const pendingEditsMsgIdRef = useRef<string | null>(null);
  // Inline review of the pending proposal (lib/inline-diff-monaco.ts).
  const inlineDiffRef = useRef<InlineDiffController | null>(null);
  const [reviewState, setReviewState] = useState<InlineDiffState | null>(null);
  const [reviewStats, setReviewStats] = useState<{ added: number; removed: number } | null>(null);
  /** The document as it was just before the first change of this review was accepted. */
  const reviewBaselineRef = useRef<string | null>(null);
  const reviewHandlersRef = useRef<{
    accepted: (state: InlineDiffState) => void;
    rejected: (state: InlineDiffState) => void;
  } | null>(null);

  // In-memory SWR file cache for instantaneous file switching
  const fileContentCacheRef = useRef<Map<string, { content: string; timestamp: number }>>(new Map());
  // Latest active file, readable from callbacks that must not re-subscribe
  // every time the user switches file (the collaboration remote-change handler).
  const activeFilePathRef = useRef(activeFilePath);
  activeFilePathRef.current = activeFilePath;
  // The file whose text the editor currently holds. `activeFilePath` flips the moment a tab is
  // chosen, but the editor keeps showing the PREVIOUS file until the new one's content arrives;
  // a change reported in that window used to be saved under the new path, overwriting it with
  // the old file's text (main.tex ended up holding details.tex). Saves are gated on this.
  const loadedFilePathRef = useRef<string | null>(null);
  // Monaco commands (Ctrl+S) are registered once at mount; they must call the CURRENT render's
  // save/compile, not the first render's (whose activeFilePath is "main.tex" forever).
  const editorActionsRef = useRef<{
    save: (code: string, showToast?: boolean) => Promise<void>;
    compile: (code?: string) => Promise<void>;
  } | null>(null);
  // Main-file auto-open bookkeeping (see the effect after handleSelectFile).
  const userPickedFileRef = useRef(false);
  const autoOpeningMainRef = useRef(false);
  const autoOpenedFileRef = useRef<string | null>(null);
  const mainFileAppliedForRef = useRef<string | null>(null);
  const prevActiveFilePathRef = useRef(activeFilePath);
  // The backend's authoritative healed+validated buffer for the current proposal.
  const authoritativeDocRef = useRef<AuthoritativeDoc | null>(null);

  // Theme Support
  const { theme: appTheme, setTheme: setAppTheme, resolvedTheme } = useTheme();
  const [themeMounted, setThemeMounted] = useState(false);

  useEffect(() => {
    setThemeMounted(true);
  }, []);

  const isDark = themeMounted
    ? (resolvedTheme ? resolvedTheme === "dark" : appTheme === "dark")
    : (typeof document !== "undefined" ? document.documentElement.classList.contains("dark") : true);

  const activeMonacoTheme = isDark ? "kinetic-emerald" : "kinetic-emerald-light";
  const monacoTheme = activeMonacoTheme;

  const handleToggleTheme = useCallback(() => {
    const nextDark = !isDark;
    const nextTheme = nextDark ? "dark" : "light";
    setAppTheme(nextTheme);

    // Synchronously update HTML root class to eliminate any transition delay or latching
    if (typeof document !== "undefined") {
      if (nextDark) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    }

    const nextMonacoTheme = nextDark ? "kinetic-emerald" : "kinetic-emerald-light";
    try {
      if (monacoRef.current) {
        monacoRef.current.editor.setTheme(nextMonacoTheme);
      }
      if (typeof window !== "undefined" && (window as any).monaco) {
        (window as any).monaco.editor.setTheme(nextMonacoTheme);
      }
      if (desktopEditorRef.current) {
        desktopEditorRef.current.updateOptions({ theme: nextMonacoTheme });
      }
      if (mobileEditorRef.current) {
        mobileEditorRef.current.updateOptions({ theme: nextMonacoTheme });
      }
    } catch (e) {
      console.warn("Error toggling Monaco theme:", e);
    }
  }, [isDark, setAppTheme]);

  useEffect(() => {
    const targetTheme = isDark ? "kinetic-emerald" : "kinetic-emerald-light";
    try {
      if (monacoRef.current) {
        monacoRef.current.editor.setTheme(targetTheme);
      }
      if (typeof window !== "undefined" && (window as any).monaco) {
        (window as any).monaco.editor.setTheme(targetTheme);
      }
      if (desktopEditorRef.current) {
        desktopEditorRef.current.updateOptions({ theme: targetTheme });
      }
      if (mobileEditorRef.current) {
        mobileEditorRef.current.updateOptions({ theme: targetTheme });
      }
    } catch (_) {}
  }, [isDark]);

  // AI Agent Assistant & Editor Refs
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRequestIdRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastSelectionRef = useRef<any>(null);
  const lastPositionRef = useRef<any>(null);
  // Files attached to the agent chat (up to five). Uploaded once; only metadata lives here.
  const chatAttachments = useChatAttachments(projectId, projectId || "proj-default");
  const hasAttachments = chatAttachments.ready.length > 0;
  // Attachments already named in a chat message, so each is announced once.
  const announcedAttachmentsRef = useRef<Set<string>>(new Set());
  const [isFileAnalyzerOpen, setIsFileAnalyzerOpen] = useState<boolean>(false);
  const [isApiSettingsOpen, setIsApiSettingsOpen] = useState<boolean>(false);
  const [activeModelName, setActiveModelName] = useState<string>("gemini-3.7-flash");
  const [agentProgressSteps, setAgentProgressSteps] = useState<{ step: string; message: string; icon: string }[]>([]);
  const [filesRefreshTrigger, setFilesRefreshTrigger] = useState<number>(0);
  const [pdfImportOpen, setPdfImportOpen] = useState(false);
  const [pdfImportJobId, setPdfImportJobId] = useState<string | null>(null);
  const [fileReloadNonce, setFileReloadNonce] = useState(0);
  const [chatMode, setChatMode] = useState<ChatMode>("edit");
  const editHistoryStoreRef = useRef<EditHistoryStore | null>(null);

  useEffect(() => {
    editHistoryStoreRef.current = new EditHistoryStore(projectId || "default");
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (activeRequestIdRef.current) {
        try {
          authFetch(`${BACKEND_URL}/api/agent/stop`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            keepalive: true,
            body: JSON.stringify({
              request_id: activeRequestIdRef.current,
              project_id: projectId || undefined,
            }),
          }).catch(() => {});
        } catch (_) {}
      }
    };
  }, [projectId]);

  const monacoRef = useRef<any>(null);
  const pdfViewerRef = useRef<PDFViewerRefHandle>(null);
  // One remembered PDF view (page/zoom/offset) shared by all three PDFViewer
  // mounts (desktop pane, mobile split, mobile PDF tab), so a recompile restores
  // where the reader actually is whichever pane they read it in.
  const pdfViewMemoryRef = useRef<PDFViewerViewState>({ page: 1 });
  // ...and seeded from the last session, so reopening the project returns the
  // reader to the page they left off on instead of page 1. Seeded in an effect
  // rather than in the ref's initialiser: `localStorage` does not exist while
  // this renders on the server, and a compile cannot finish before this runs.
  const pdfViewSeededRef = useRef(false);
  useEffect(() => {
    if (pdfViewSeededRef.current) return;
    pdfViewSeededRef.current = true;
    const stored = readStoredView(projectId);
    if (stored) pdfViewMemoryRef.current = stored;
  }, [projectId]);
  const desktopEditorRef = useRef<any>(null);
  const mobileEditorRef = useRef<any>(null);
  const isReverseSyncingRef = useRef<boolean>(false);
  // When the coordinate (SyncTeX) path last placed the cursor. A ctrl- or
  // double-click is both a sync click and a word selection, so both paths fire
  // for one gesture and whichever resolved last used to win; the coordinate one
  // is the accurate one, so the text-search path stands down just after it.
  const lastReverseSyncAtRef = useRef<number>(0);
  const pendingJumpRef = useRef<{ line: number; col?: number; matchRange?: any; timestamp: number } | null>(null);
  const [isPresentationMode, setIsPresentationMode] = useState<boolean>(false);
  const forwardSyncTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Global Presentation Mode Shortcut (Ctrl + Alt + P)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.altKey && (e.key === "p" || e.key === "P")) {
        e.preventDefault();
        setIsPresentationMode((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleReverseSyncJump = (file: string, line: number, column: number) => {
    lastReverseSyncAtRef.current = Date.now();
    // Suppress forward sync loop while navigating from PDF to code
    if (forwardSyncTimerRef.current) {
      clearTimeout(forwardSyncTimerRef.current);
    }
    isReverseSyncingRef.current = true;
    setTimeout(() => {
      isReverseSyncingRef.current = false;
    }, 1000);

    const monaco = monacoRef.current;
    if (file && !isAuxiliaryFilePath(file) && file !== activeFilePath) {
      setActiveFilePath(file);
    }

    const targetCol = column || 1;
    pendingJumpRef.current = { line, col: targetCol, timestamp: Date.now() };

    setActiveMobileTab("code");

    const editors = [desktopEditorRef.current, mobileEditorRef.current].filter(Boolean);
    const uniqueEditors = Array.from(new Set(editors));

    for (const ed of uniqueEditors) {
      try {
        const model = ed.getModel();
        if (!model) continue;

        ed.revealLineInCenter(line, 0);
        ed.setPosition({ lineNumber: line, column: targetCol });
        ed.focus();

        if (monaco) {
          const decorations = ed.deltaDecorations([], [
            {
              range: new monaco.Range(line, 1, line, 1),
              options: {
                isWholeLine: true,
                className: "synctex-highlight-line",
                glyphMarginClassName: "synctex-gutter-marker",
              },
            },
          ]);
          setTimeout(() => {
            try {
              ed.deltaDecorations(decorations, []);
            } catch (_) { }
          }, 1200);
        }
      } catch (_) { }
    }

    // Auto-release browser selection in the PDF so user doesn't have to click away
    setTimeout(() => {
      try {
        window.getSelection()?.removeAllRanges();
      } catch (_) { }
    }, 250);

    // Mobile jump guarantee: layout and reveal once tab is active
    setTimeout(() => {
      if (mobileEditorRef.current) {
        try {
          mobileEditorRef.current.layout();
          mobileEditorRef.current.revealLineInCenter(line, 0);
          mobileEditorRef.current.setPosition({ lineNumber: line, column: targetCol });
          mobileEditorRef.current.focus();
        } catch (_) { }
      }
    }, 80);
    setTimeout(() => {
      if (mobileEditorRef.current) {
        try {
          mobileEditorRef.current.layout();
          mobileEditorRef.current.revealLineInCenter(line, 0);
          mobileEditorRef.current.setPosition({ lineNumber: line, column: targetCol });
          mobileEditorRef.current.focus();
        } catch (_) { }
      }
    }, 250);
  };

  /**
   * Jump to selected PDF text in the source.
   *
   * `hintLine` is where SyncTeX says the selection physically is. Without it the
   * only thing available is a text search, which lands on the FIRST occurrence
   * of the selected words — so selecting the second copy of a repeated sentence
   * jumped to the first copy, often in another section entirely. With it, the
   * occurrence nearest that line wins, which is the one the reader selected.
   */
  const jumpToSelectedPdfText = (
    selectedText: string,
    hintLine?: number | null,
    hintFile?: string | null,
    xFraction?: number | null,
  ) => {
    const monaco = monacoRef.current;
    const trimmed = selectedText.trim();
    if (!trimmed || trimmed.length < 2) return;

    if (hintFile && !isAuxiliaryFilePath(hintFile) && hintFile !== activeFilePath) {
      setActiveFilePath(hintFile);
    }

    const editors = [desktopEditorRef.current, mobileEditorRef.current].filter(Boolean);
    const uniqueEditors = Array.from(new Set(editors));

    for (const ed of uniqueEditors) {
      try {
        const model = ed.getModel();
        if (!model) continue;

        let matchRange: any = null;

        // 1. Try exact match first
        let matches = model.findMatches(trimmed, true, false, true, null, true);

        // 2. Try case-insensitive
        if (!matches || matches.length === 0) {
          matches = model.findMatches(trimmed, false, false, false, null, true);
        }

        // 3. Try word sequence search
        if (!matches || matches.length === 0) {
          const words = trimmed
            .split(/\s+/)
            .map((w) => w.replace(/[^a-zA-Z0-9]/g, ""))
            .filter((w) => w.length >= 3);

          if (words.length > 0) {
            for (let count = Math.min(3, words.length); count >= 1; count--) {
              const searchPhrase = words.slice(0, count).join("[\\s\\S]{0,60}?");
              try {
                matches = model.findMatches(searchPhrase, false, true, false, null, true);
                if (matches && matches.length > 0) break;
              } catch (_) { }
            }
          }
        }

        // 4. Substring scan across lines
        if (!matches || matches.length === 0) {
          const cleanSnippet = trimmed.slice(0, 15).toLowerCase();
          const lineCount = model.getLineCount();
          const candidates: number[] = [];
          for (let i = 1; i <= lineCount; i++) {
            if (model.getLineContent(i).toLowerCase().includes(cleanSnippet)) {
              candidates.push(i);
              // With no hint the first hit is the answer, as before.
              if (!hintLine) break;
            }
          }
          const line = pickLine(candidates, hintLine);
          if (line) {
            matchRange = new monaco.Range(line, 1, line, model.getLineMaxColumn(line));
          }
        } else {
          // The occurrence SyncTeX points at, not the first one in the file.
          // Within a single line that holds the phrase twice, SyncTeX gives no
          // column (it reports -1), so the selection's horizontal position on
          // the page breaks the tie.
          const picked =
            pickWithinLine(matches as any[], hintLine, xFraction) ??
            pickOccurrence(matches as any[], hintLine);
          matchRange = picked ? picked.range : null;
        }

        if (matchRange) {
          const targetLine = matchRange.startLineNumber;
          const col = matchRange.startColumn || 1;
          pendingJumpRef.current = { line: targetLine, col, matchRange, timestamp: Date.now() };

          ed.revealLineInCenter(targetLine, 0);
          ed.setSelection(matchRange);
          ed.setPosition({
            lineNumber: targetLine,
            column: col,
          });
          ed.focus();

          // Release cursor in that line after brief flash so the selection does not stay selected/blocked
          setTimeout(() => {
            try {
              ed.setSelection(new monaco.Range(targetLine, col, targetLine, col));
              ed.setPosition({ lineNumber: targetLine, column: col });
            } catch (_) { }
          }, 400);

          if (monaco) {
            const decorations = ed.deltaDecorations([], [
              {
                range: new monaco.Range(targetLine, 1, targetLine, 1),
                options: {
                  isWholeLine: true,
                  className: "synctex-highlight-line",
                  glyphMarginClassName: "synctex-gutter-marker",
                },
              },
            ]);
            setTimeout(() => {
              try {
                ed.deltaDecorations(decorations, []);
              } catch (_) { }
            }, 1200);
          }
        }
      } catch (_) { }
    }



    // Mobile jump guarantee: layout and reveal once tab is active
    setTimeout(() => {
      if (mobileEditorRef.current) {
        try {
          mobileEditorRef.current.layout();
          if (pendingJumpRef.current) {
            mobileEditorRef.current.revealLineInCenter(pendingJumpRef.current.line, 0);
            mobileEditorRef.current.setPosition({
              lineNumber: pendingJumpRef.current.line,
              column: pendingJumpRef.current.col || 1,
            });
            mobileEditorRef.current.focus();
          }
        } catch (_) { }
      }
    }, 80);
    setTimeout(() => {
      if (mobileEditorRef.current) {
        try {
          mobileEditorRef.current.layout();
          if (pendingJumpRef.current) {
            mobileEditorRef.current.revealLineInCenter(pendingJumpRef.current.line, 0);
            mobileEditorRef.current.setPosition({
              lineNumber: pendingJumpRef.current.line,
              column: pendingJumpRef.current.col || 1,
            });
            mobileEditorRef.current.focus();
          }
        } catch (_) { }
      }
    }, 250);
  };

  /**
   * Text selected in the PDF. `anchor` is where that selection physically is;
   * SyncTeX turns it into the source line, and the jump then goes to the
   * occurrence there rather than to the first occurrence in the file.
   *
   * The search still runs when SyncTeX cannot answer (no .synctex.gz yet, or a
   * point it has no record for), so the behaviour degrades to what it was
   * rather than to nothing.
   */
  const handlePdfTextSelected = (
    selectedText: string,
    anchor?: { page: number; x: number; y: number; xFraction?: number },
  ) => {
    // Suppress forward sync loop while navigating from PDF to code
    if (forwardSyncTimerRef.current) {
      clearTimeout(forwardSyncTimerRef.current);
    }
    isReverseSyncingRef.current = true;
    setTimeout(() => {
      isReverseSyncingRef.current = false;
    }, 1000);

    const trimmed = selectedText.trim();
    if (!trimmed || trimmed.length < 2) return;

    // A ctrl/double-click is BOTH a sync click and a word selection, so both
    // paths fire for one gesture. The coordinate path is the accurate one, so
    // if it has just landed, leave its result alone.
    if (Date.now() - lastReverseSyncAtRef.current < 1200) return;

    if (!anchor || !projectId) {
      jumpToSelectedPdfText(trimmed);
      return;
    }

    trpcClient.synctex.backward
      .mutate({ projectId, page: anchor.page, x: anchor.x, y: anchor.y })
      .then((data) => {
        jumpToSelectedPdfText(trimmed, data?.line ?? null, data?.file ?? null,
          anchor.xFraction ?? null);
      })
      .catch(() => {
        jumpToSelectedPdfText(trimmed, null, null, anchor.xFraction ?? null);
      });
  };

  // Re-sync jump whenever activeMobileTab switches to "code"
  useEffect(() => {
    if (activeMobileTab === "code") {
      setTimeout(() => {
        if (mobileEditorRef.current) {
          mobileEditorRef.current.layout();
          if (pendingJumpRef.current && Date.now() - pendingJumpRef.current.timestamp < 6000) {
            const jump = pendingJumpRef.current;
            mobileEditorRef.current.revealLineInCenter(jump.line, 0);
            mobileEditorRef.current.setPosition({ lineNumber: jump.line, column: jump.col || 1 });
            mobileEditorRef.current.focus();
          }
        }
      }, 70);
    }
  }, [activeMobileTab]);

  // ─── Model Selector State ────────────────────────────────────────────────
  const [availableModels, setAvailableModels] = useState<ProviderGroup[]>([
    {
      name: "Gemini Web2API",
      models: [
        { id: "gemini-3.7-flash", label: "Gemini 3.7 Flash", default: true },
        { id: "gemini-3.6-flash", label: "Gemini 3.6 Flash", default: false },
        { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash", default: false },
        { id: "gemini-3.5-flash-thinking", label: "Gemini 3.5 Flash Thinking", default: false },
        { id: "gemini-3.5-flash-thinking-lite", label: "Gemini 3.5 Flash Thinking Lite", default: false },
      ],
    },
    {
      name: "FreeLLM API",
      models: [
        { id: "auto:smart", label: "FreeLLM Auto Smart", default: false },
        { id: "auto", label: "FreeLLM Auto Router", default: false },
        { id: "auto:fast", label: "FreeLLM Auto Fast", default: false },
        { id: "openai/gpt-oss-120b", label: "GPT-OSS-120B", default: false },
      ],
    },
    {
      name: "OpenRouter",
      models: [
        { id: "nvidia/nemotron-3-ultra-550b-a55b:free", label: "Nemotron 3 Ultra Free", default: false },
        { id: "minimax/minimax-m3:free", label: "Minimax 3 Free", default: false },
        { id: "deepseek/deepseek-v4-flash:free", label: "DeepSeek V4 Flash Free", default: false },
      ],
    },
  ]);

  // Fetch available models via protected tRPC on mount
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const data = await trpcClient.ai.models.query();
        if (data?.providers && Array.isArray(data.providers) && data.providers.length > 0) {
          setAvailableModels(data.providers);
          if (data.defaultModel) {
            setActiveModelName(data.defaultModel);
          }
        } else if (Array.isArray(data) && data.length > 0) {
          setAvailableModels(data);
          const firstDefault = data.flatMap((g: any) => g.models).find((m: any) => m.default)?.id;
          if (firstDefault) {
            setActiveModelName(firstDefault);
          }
        }
      } catch (err) {
        console.warn("Failed to fetch models via tRPC:", err);
      }
    };
    fetchModels();
  }, []);





  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    void chatAttachments.addFiles(e.target.files);
    if (e.target) e.target.value = "";
  };

  const handleStopAgentResponse = () => {
    const reqId = activeRequestIdRef.current;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    activeRequestIdRef.current = null;
    setIsAgentThinking(false);
    setAgentProgressSteps([]);

    // Immediately notify backend to halt AI call & release resources
    try {
      authFetch(`${BACKEND_URL}/api/agent/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        keepalive: true,
        body: JSON.stringify({
          project_id: projectId || undefined,
          request_id: reqId || undefined,
        }),
      }).catch((err) => {
        console.warn("Stop request failed to reach backend:", err);
      });
    } catch (_) {}

    setMessages((prev) => [
      ...prev,
      {
        id: `ai-stop-${Date.now()}`,
        sender: "assistant",
        text: "Response generation was stopped by user.",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  };

  // Fetch real project metadata & user authorization status
  const {
    data: projectDetail,
    isLoading: isProjectLoading,
    isError: isProjectError,
    error: projectError,
  } = trpc.projects.getById.useQuery(
    { projectId: projectId! },
    {
      enabled: !!projectId,
      retry: false,
    }
  );

  const isViewer = projectDetail?.role === "Viewer";
  const isGuestMode = propIsGuest || !!(projectDetail as any)?.isGuest;

  // ─── Realtime collaboration (Yjs CRDT over the backend's /ws/collab) ──────
  // The session identity comes from the existing Better-Auth client; nothing
  // about the user is hardcoded or supplied by the collaboration layer itself.
  const { data: authSession } = authClient.useSession();
  const collabUser = authSession?.user;

  const collabMirrorTimerRef = useRef<NodeJS.Timeout | null>(null);

  /**
   * Remote (and AI) text that arrived through the CRDT, mirrored into React
   * state so download / the file cache keep seeing the live document. Never
   * flips saveStatus to "unsaved": the room persists on the server, and the
   * save indicator is driven by `collab.savedAt` while bound.
   */
  const handleCollabRemoteChange = useCallback(
    (value: string, file: string) => {
      fileContentCacheRef.current.set(file, { content: value, timestamp: Date.now() });

      // Mirroring on a trailing throttle, not per remote keystroke: setCode
      // re-renders this whole shell, and a collaborator typing a paragraph
      // would otherwise force a render per character. Nothing reads the mirror
      // for correctness — `currentDocumentText()` goes to the Monaco model.
      if (collabMirrorTimerRef.current) clearTimeout(collabMirrorTimerRef.current);
      collabMirrorTimerRef.current = setTimeout(() => {
        collabMirrorTimerRef.current = null;
        if (file === activeFilePathRef.current) setCode(value);
        try {
          localStorage.setItem(`overbranch_code_${projectId || "default"}_${file}`, value);
        } catch (_) {
          // Quota or private mode: the room is still the source of truth.
        }
      }, 150);
    },
    [projectId],
  );

  useEffect(
    () => () => {
      if (collabMirrorTimerRef.current) clearTimeout(collabMirrorTimerRef.current);
    },
    [],
  );

  const collab = useCollaboration({
    projectId,
    filePath: activeFilePath,
    user: collabUser
      ? {
          id: collabUser.id,
          name: collabUser.name,
          email: collabUser.email,
          image: (collabUser as any).image ?? null,
        }
      : null,
    isGuest: isGuestMode,
    readOnly: isViewer,
    onRemoteChange: handleCollabRemoteChange,
  });

  const collabBound = collab.bound;
  const collabBoundRef = useRef(false);
  collabBoundRef.current = collabBound;
  const guestExpiresAt = propExpiresAt || (projectDetail as any)?.expiresAt;
  const [guestTimeLeft, setGuestTimeLeft] = useState<string>("");

  useEffect(() => {
    if (!isGuestMode || !guestExpiresAt) return;
    const calculate = () => {
      const diff = new Date(guestExpiresAt).getTime() - Date.now();
      if (diff <= 0) {
        setGuestTimeLeft("Expired");
        return;
      }
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);
      setGuestTimeLeft(
        `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
      );
    };
    calculate();
    const interval = setInterval(calculate, 1000);
    return () => clearInterval(interval);
  }, [isGuestMode, guestExpiresAt]);

  // No mock messages — only real conversation from API interactions
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const projStorageKey = projectId || "proj-default";

  // ─── Local Storage Chat & PDF Context Persistence ─────────────────────────
  // Load chat messages from localStorage on mount / project change
  useEffect(() => {
    try {
      const savedMessages = localStorage.getItem(`overbranch_${projStorageKey}_chat_messages`);
      if (savedMessages) {
        const parsed = JSON.parse(savedMessages);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(repairSharedEditHistoryIds(parsed));
        }
      }
    } catch (e) {
      console.warn("Failed to load chat messages from localStorage:", e);
    }
    // Mentions point at lines of the previous project's files.
    setMentions([]);
    mentionsRef.current = [];
  }, [projStorageKey]);

  // Save chat messages to localStorage whenever they update
  useEffect(() => {
    try {
      if (messages.length > 0) {
        localStorage.setItem(`overbranch_${projStorageKey}_chat_messages`, JSON.stringify(messages));
      } else {
        localStorage.removeItem(`overbranch_${projStorageKey}_chat_messages`);
      }
    } catch (e) {
      console.warn("Failed to save chat messages to localStorage:", e);
    }
  }, [messages, projStorageKey]);

  const handleNewChat = () => {
    setMessages([]);
    setMentions([]);
    mentionsRef.current = [];
    void chatAttachments.clear();
    announcedAttachmentsRef.current = new Set();
    setDiffData(null);
    setDiffEditsList([]);
    pendingEditsMsgIdRef.current = null;
    setAgentProgressSteps([]);
    try {
      localStorage.removeItem(`overbranch_${projStorageKey}_chat_messages`);
    } catch (_) { }
  };

  const handleClearChat = () => {
    if (messages.length === 0 && chatAttachments.attachments.length === 0) return;
    if (confirm("Are you sure you want to delete all chat history and document context for this project?")) {
      setMessages([]);
      void chatAttachments.clear();
      announcedAttachmentsRef.current = new Set();
      setDiffData(null);
      setDiffEditsList([]);
      pendingEditsMsgIdRef.current = null;
      setAgentProgressSteps([]);
      try {
        localStorage.removeItem(`overbranch_${projStorageKey}_chat_messages`);
      } catch (_) { }
    }
  };

  /**
   * Both Monaco instances (desktop + mobile) are always mounted and merely
   * hidden with CSS, so a single shared `editorRef` was always clobbered by
   * whichever mounted last — the mobile one, which is later in the JSX. Every
   * toolbar action was therefore driving a hidden, zero-sized editor even on
   * desktop. Resolve the editor that is actually on screen instead.
   */
  const [editorsNonce, setEditorsNonce] = useState(0);
  const isMobileViewport = () =>
    typeof window !== "undefined" && window.innerWidth < 768;

  /**
   * Whether the only keyboard here is the on-screen one.
   *
   * On a phone there is no Shift+Enter, so Enter-to-send left no way to type a
   * second line in the chat box at all: every newline sent the message
   * half-written. On such a device Enter inserts a newline and the send button
   * sends, which is what every phone messaging app does.
   *
   * `(pointer: coarse)` is the right test rather than a width breakpoint: it
   * asks whether the PRIMARY input is a finger, so a narrow desktop window
   * keeps Enter-to-send and a tablet with a hardware keyboard — which does have
   * Shift+Enter — is the one case this gets wrong, in the harmless direction.
   */
  const [softKeyboardOnly, setSoftKeyboardOnly] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(COARSE_POINTER_QUERY);
    const sync = () => setSoftKeyboardOnly(mq.matches);
    sync();
    // Safari < 14 has no addEventListener on MediaQueryList.
    if (mq.addEventListener) {
      mq.addEventListener("change", sync);
      return () => mq.removeEventListener("change", sync);
    }
    mq.addListener(sync);
    return () => mq.removeListener(sync);
  }, []);

  /**
   * What the user has highlighted in the visible editor, for the agent.
   *
   * `elaborate_content(target="selection")` and `humanize_document` act on this
   * when it is present; without it they fall back to resolving the block from
   * the request's own words.
   */
  const activeSelection = () => {
    try {
      const editor = getActiveEditor();
      const sel = editor?.getSelection?.();
      const model = editor?.getModel?.();
      if (!editor || !sel || !model || sel.isEmpty()) return null;
      const text = model.getValueInRange(sel);
      if (!text || !text.trim()) return null;
      return {
        text,
        start_line: sel.startLineNumber,
        end_line: sel.endLineNumber,
        file: activeFilePath || "main.tex",
      };
    } catch (_) {
      return null;
    }
  };

  // @file mentions: the two chat textareas (as state, so the popovers re-render
  // once the node exists) and whether either popover is showing.
  const [desktopChatTextarea, setDesktopChatTextarea] = useState<HTMLTextAreaElement | null>(null);
  const [mobileChatTextarea, setMobileChatTextarea] = useState<HTMLTextAreaElement | null>(null);
  const mentionOpenRef = useRef({ desktop: false, mobile: false });
  const setDesktopMentionOpen = useCallback((open: boolean) => { mentionOpenRef.current.desktop = open; }, []);
  const setMobileMentionOpen = useCallback((open: boolean) => { mentionOpenRef.current.mobile = open; }, []);

  /** Swap the `@query` the user typed for `@basename ` and pin the whole file to the message. */
  const handleInsertMention = useCallback((file: string, triggerIndex: number, queryLength: number) => {
    const basename = file.slice(file.lastIndexOf("/") + 1);
    const inserted = `@${basename} `;
    const caretAfter = triggerIndex + inserted.length;
    setChatInput((prev) => prev.slice(0, triggerIndex) + inserted + prev.slice(triggerIndex + 1 + queryLength));

    const result = addMention(mentionsRef.current, makeFileMention(file));
    if (result.error) {
      toast.error(result.error);
    } else {
      mentionsRef.current = result.list;
      setMentions(result.list);
    }

    // Wait for React to write the new value, then put the caret after the token.
    const active = document.activeElement;
    const target = active === desktopChatTextarea || active === mobileChatTextarea
      ? (active as HTMLTextAreaElement)
      : desktopChatTextarea ?? mobileChatTextarea;
    requestAnimationFrame(() => {
      if (!target) return;
      target.focus();
      target.setSelectionRange(caretAfter, caretAfter);
    });
  }, [desktopChatTextarea, mobileChatTextarea]);

  /** One Enter-key policy for both chat boxes (see lib/chat-input.ts). */
  const handleChatKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // The @file list owns these keys while it is open (the popover also swallows
    // them in the capture phase; this keeps Enter from sending if it ever doesn't).
    if (
      (mentionOpenRef.current.desktop || mentionOpenRef.current.mobile) &&
      ["ArrowUp", "ArrowDown", "Enter", "Tab", "Escape"].includes(e.key)
    ) {
      e.preventDefault();
      return;
    }
    if (!shouldSendOnEnter({
      key: e.key,
      shiftKey: e.shiftKey,
      isComposing: (e.nativeEvent as KeyboardEvent)?.isComposing,
      keyCode: e.keyCode,
      softKeyboardOnly,
    })) return;
    e.preventDefault();
    if ((chatInput.trim() || hasAttachments) && !isAgentThinking) {
      handleSendPrompt(e as unknown as React.FormEvent);
    }
  };
  const getActiveEditor = useCallback(() => {
    const mobile = mobileEditorRef.current;
    const desktop = desktopEditorRef.current;
    return (isMobileViewport() ? mobile ?? desktop : desktop ?? mobile) ?? null;
  }, []);

  // The list is mirrored in a ref so back-to-back mentions (and the Monaco
  // command / widget, which are registered once at mount) never see a stale one.
  const mentionsRef = useRef<MentionRef[]>([]);
  mentionsRef.current = mentions;

  const addMentionFromSelection = useCallback(() => {
    const editor = getActiveEditor();
    const sel = editor?.getSelection?.();
    const model = editor?.getModel?.();
    if (!editor || !model || !sel || sel.isEmpty()) return;
    const next = makeMention(
      activeFilePath || "main.tex",
      sel.startLineNumber,
      sel.endLineNumber,
      model.getValueInRange(sel),
    );
    const result = addMention(mentionsRef.current, next);
    if (result.error) {
      toast.error(result.error);
      return;
    }
    mentionsRef.current = result.list;
    setMentions(result.list);
  }, [getActiveEditor, activeFilePath]);

  const removeMentionById = useCallback((id: string) => {
    const list = removeMention(mentionsRef.current, id);
    mentionsRef.current = list;
    setMentions(list);
  }, []);

  // Monaco registrations below outlive the render that created them.
  const addMentionRef = useRef<() => void>(() => {});
  addMentionRef.current = addMentionFromSelection;
  const isAgentThinkingRef = useRef(false);
  isAgentThinkingRef.current = isAgentThinking;
  // One "re-evaluate the floating @ Mention button" function per desktop editor.
  const mentionWidgetSyncs = useRef<Set<() => void>>(new Set());
  useEffect(() => {
    mentionWidgetSyncs.current.forEach((sync) => sync());
  }, [isAgentThinking]);
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);
  // Last (file, content) handleCodeChange acted on, to collapse the duplicate
  // notifications the two shared-model editors produce for one edit.
  const lastCodeChangeRef = useRef<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const mobileChatEndRef = useRef<HTMLDivElement>(null);

  // Render 403 Forbidden Access Denied screen if user lacks authorization
  if (projectId && isProjectError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-6 text-center space-y-6 animate-fade-in">
        <div className="p-4 rounded-3xl bg-rose-500/10 border border-rose-500/30 text-rose-400 shadow-xl">
          <ShieldAlert className="w-12 h-12" />
        </div>
        <div className="space-y-2 max-w-md">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">403 Forbidden — Access Denied</h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {projectError?.message || "You do not have permission to view or edit this project. Access is restricted exclusively to the project owner and invited co-authors."}
          </p>
        </div>
        <Button asChild size="lg" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-medium px-6 shadow-lg shadow-indigo-500/20">
          <Link href="/dashboard">Return to Dashboard</Link>
        </Button>
      </div>
    );
  }

  // Auto-scroll chat window to bottom when new messages, thinking state, diffs, or agent progress steps update
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    mobileChatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isAgentThinking, diffData, agentProgressSteps.length]);

  // Inline review: the pending proposal drawn in the editor — removed lines red,
  // added lines green beneath them, Accept / Reject per change. The document is
  // not modified until a change is accepted.
  const reviewDoc = diffData?.authoritative;
  useEffect(() => {
    const editor = getActiveEditor();
    const monaco = monacoRef.current;
    const model = editor?.getModel?.();
    const file = activeFilePath || "main.tex";
    if (!reviewDoc || !editor || !monaco || !model || (reviewDoc.file && reviewDoc.file !== file)) {
      setReviewState(null);
      setReviewStats(null);
      return;
    }
    const blocks = placeBlocks(
      reviewDoc.originalCode,
      model.getValue(),
      buildReviewBlocks(reviewDoc.originalCode, reviewDoc.proposedCode, reviewDoc.hunks),
    );
    if (blocks.length === 0) {
      setReviewState(null);
      setReviewStats(null);
      return;
    }
    reviewBaselineRef.current = null;
    setReviewStats(blockStats(blocks));
    const controller = new InlineDiffController(editor, monaco, blocks, {
      readOnly: isViewer,
      onState: setReviewState,
      onBeforeApply: () => {
        if (reviewBaselineRef.current === null) reviewBaselineRef.current = model.getValue();
      },
      onAccepted: (_id, state) => reviewHandlersRef.current?.accepted(state),
      onRejected: (_id, state) => reviewHandlersRef.current?.rejected(state),
    });
    inlineDiffRef.current = controller;
    controller.reveal(0);
    return () => {
      controller.dispose();
      if (inlineDiffRef.current === controller) inlineDiffRef.current = null;
    };
    // editorsNonce: the editors mount after this effect first runs, and
    // getActiveEditor() reads a ref, so without it the review never appears.
  }, [reviewDoc, activeFilePath, getActiveEditor, editorsNonce, isViewer]);

  // Responsive Sidebar Panels
  const [aiOpen, setAiOpen] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth >= 1280;
    }
    return false;
  });
  const [pdfOpen, setPdfOpen] = useState(true);

  const handleToggleFiles = () => {
    setFilesOpen((prev) => {
      const next = !prev;
      if (next && typeof window !== "undefined" && window.innerWidth < 1100 && aiOpen) {
        setAiOpen(false);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    const editor = getActiveEditor();
    if (editor) {
      editor.focus();
      const model = editor.getModel();
      if (model) {
        const fullRange = model.getFullModelRange();
        editor.setSelection(fullRange);
        lastSelectionRef.current = fullRange;
      }
    }
  };

  const handleSelectLine = () => {
    const editor = getActiveEditor();
    if (editor) {
      editor.focus();
      const pos = lastPositionRef.current || editor.getPosition();
      if (pos) {
        const model = editor.getModel();
        const maxCol = model ? model.getLineMaxColumn(pos.lineNumber) : 1;
        const lineRange = {
          startLineNumber: pos.lineNumber,
          startColumn: 1,
          endLineNumber: pos.lineNumber,
          endColumn: maxCol,
        };
        editor.setSelection(lineRange);
        lastSelectionRef.current = lineRange;
      }
    }
  };

  /**
   * Undo in a shared document cannot be Monaco's undo stack: that stack also
   * contains edits whose surroundings a collaborator has since changed, and it
   * knows nothing about which changes were *this* user's. The Yjs UndoManager
   * tracks only this client's own transactions, so Ctrl+Z means "undo my last
   * edit" and never silently deletes someone else's paragraph.
   */
  const handleUndo = () => {
    const editor = getActiveEditor();
    if (editor) editor.focus();
    if (collab.undo()) return;
    editor?.trigger("toolbar", "undo", null);
  };

  const handleRedo = () => {
    const editor = getActiveEditor();
    if (editor) editor.focus();
    if (collab.redo()) return;
    editor?.trigger("toolbar", "redo", null);
  };

  // Monaco commands are registered once at mount, so they must reach the
  // *current* handlers rather than the ones from the mounting render.
  const handleUndoRef = useRef<() => void>(() => {});
  const handleRedoRef = useRef<() => void>(() => {});
  handleUndoRef.current = handleUndo;
  handleRedoRef.current = handleRedo;

  const toggleAi = () => {
    setAiOpen((prev) => {
      const next = !prev;
      if (next) {
        if (typeof window !== "undefined" && window.innerWidth < 1100 && filesOpen) {
          setFilesOpen(false);
        }
        setTimeout(() => {
          const inputEl = document.getElementById("ai-chat-input");
          if (inputEl) inputEl.focus();
        }, 100);
      }
      return next;
    });
  };

  const togglePdf = () => {
    setPdfOpen((prev) => !prev);
  };

  // Keyboard shortcut: Cmd+L / Ctrl+L to add/toggle AI Agent
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "l") {
        e.preventDefault();
        if (window.innerWidth < 768) {
          setActiveMobileTab("ai");
          setTimeout(() => {
            const inputEl = document.getElementById("ai-chat-input-2");
            if (inputEl) inputEl.focus();
          }, 150);
        } else {
          setAiOpen((prev) => {
            const next = !prev;
            if (next) {
              setTimeout(() => {
                const inputEl = document.getElementById("ai-chat-input");
                if (inputEl) inputEl.focus();
              }, 150);
            }
            return next;
          });
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const storageKey = `overbranch_code_${projectId || 'default'}_${activeFilePath}`;

  const handleSelectFile = useCallback((filePath: string) => {
    // A pending AI diff belongs to the file it was computed against. Accepting it
    // after switching files wrote main.tex's proposal into the newly opened file.
    setDiffData(null);
    setDiffEditsList([]);
    authoritativeDocRef.current = null;
    pendingEditsMsgIdRef.current = null;
    // The duplicate-change guard compares against the last edit it saw; a new
    // file starts with no history of its own.
    lastCodeChangeRef.current = null;
    // A click (or any caller but the main-file auto-open below) is an explicit choice.
    if (!autoOpeningMainRef.current) userPickedFileRef.current = true;
    setActiveFilePath(filePath);
    // Instant cache lookup for 0ms transition
    const cached = fileContentCacheRef.current.get(filePath);
    if (cached) {
      loadedFilePathRef.current = filePath;
      setCode(cached.content);
      setSaveStatus("saved");
    } else {
      const savedKey = `overbranch_code_${projectId || 'default'}_${filePath}`;
      try {
        const saved = localStorage.getItem(savedKey);
        if (saved !== null) {
          loadedFilePathRef.current = filePath;
          setCode(saved);
          setSaveStatus("saved");
          fileContentCacheRef.current.set(filePath, { content: saved, timestamp: Date.now() });
        }
      } catch (_) {}
    }
  }, [projectId]);

  // Open the project's real MAIN document. An imported project can keep it in a sub-folder
  // (thesis/thesis.tex) with no root main.tex, while the editor starts on "main.tex". Once the
  // file list first reports `main_file`, switch to it - but only if the user has not already
  // chosen a file (a click, a SyncTeX jump, a reverse-sync target all count as a choice). The
  // ref makes this run once per project load, so it can never fight the user or loop.
  const { mainFile: projectMainFile } = useProjectFiles(projectId || "");
  useEffect(() => {
    if (activeFilePath !== prevActiveFilePathRef.current) {
      prevActiveFilePathRef.current = activeFilePath;
      if (autoOpenedFileRef.current === activeFilePath) autoOpenedFileRef.current = null;
      else userPickedFileRef.current = true; // moved by something other than the auto-open
    }
  }, [activeFilePath]);
  useEffect(() => {
    if (!projectId || !projectMainFile) return;
    if (mainFileAppliedForRef.current === projectId) return;
    mainFileAppliedForRef.current = projectId;
    if (userPickedFileRef.current) return;
    if (activeFilePathRef.current !== "main.tex") return;
    if (projectMainFile === "main.tex") return;
    autoOpenedFileRef.current = projectMainFile;
    autoOpeningMainRef.current = true;
    try {
      handleSelectFile(projectMainFile);
    } finally {
      autoOpeningMainRef.current = false;
    }
  }, [projectId, projectMainFile, handleSelectFile]);

  // 1. Load saved code from backend API (Supabase DB + Disk) or LocalStorage when activeFilePath or projectId changes
  useEffect(() => {
    let isCancelled = false;

    // Fast synchronous cache hit
    const cached = fileContentCacheRef.current.get(activeFilePath);
    if (cached) {
      loadedFilePathRef.current = activeFilePath;
      setCode(cached.content);
      setSaveStatus("saved");
    } else {
      // Nothing local for this file yet: until the server copy lands the editor still shows
      // the previous file, so no change may be saved under this path.
      loadedFilePathRef.current = null;
      try {
        const savedCode = localStorage.getItem(storageKey);
        if (savedCode !== null) {
          loadedFilePathRef.current = activeFilePath;
          setCode(savedCode);
          setSaveStatus("saved");
          fileContentCacheRef.current.set(activeFilePath, { content: savedCode, timestamp: Date.now() });
        }
      } catch (e) {}
    }

    const loadSavedDocument = async () => {
      try {
        const activeProj = projectId || "proj-1";
        // Same-origin proxy: cookies travel naturally, no cross-origin Bearer
        // race, and the backend URL stays hidden. See app/api/projects/get-file.
        const res = await fetch(
          `/api/projects/get-file?project_id=${encodeURIComponent(activeProj)}&file_path=${encodeURIComponent(activeFilePath)}`,
          { credentials: "same-origin", cache: "no-store" }
        );
        // A late-arriving REST snapshot must never win over the live
        // collaborative document: the room already seeded itself from the same
        // storage and may be many keystrokes ahead of it. This is the "late
        // joiner must not overwrite the active session" rule.
        if (collabBoundRef.current) {
          collabLog("COLLAB_SYNC", { stage: "rest_snapshot_ignored", file: activeFilePath });
          return;
        }
        if (res.ok && !isCancelled) {
          const data = await res.json();
          if (data.raw_code !== undefined) {
            loadedFilePathRef.current = activeFilePath;
            setCode(data.raw_code);
            setSaveStatus("saved");
            fileContentCacheRef.current.set(activeFilePath, { content: data.raw_code, timestamp: Date.now() });
            localStorage.setItem(storageKey, data.raw_code);
            return;
          }
          // The server answered but holds no text for this file: it is genuinely empty.
          loadedFilePathRef.current = activeFilePath;
          setCode("");
          setSaveStatus("saved");
          return;
        }
      } catch (err) {
        console.warn("Backend load failed, falling back to LocalStorage:", err);
      }

      // Fallback to LocalStorage
      if (!isCancelled) {
        try {
          const savedCode = localStorage.getItem(storageKey);
          if (savedCode !== null) {
            loadedFilePathRef.current = activeFilePath;
            setCode(savedCode);
            setSaveStatus("saved");
          }
        } catch (e) {}
      }
    };

    loadSavedDocument();
    return () => {
      isCancelled = true;
    };
  }, [projectId, activeFilePath, storageKey, fileReloadNonce]);

  // 2. Save Document function (Saves to Supabase latex_documents DB, Local Disk, and syncs Qdrant vectors)
  const saveDocument = async (newCode: string, showToast = true) => {
    const activeProj = projectId || "proj-1";
    // See loadedFilePathRef: never write text that was not loaded for this file into it.
    if (loadedFilePathRef.current !== activeFilePath) return;
    fileContentCacheRef.current.set(activeFilePath, { content: newCode, timestamp: Date.now() });

    // While a collaboration room is bound, the *server* persists the document
    // (debounced, from the CRDT). Posting a whole snapshot from here as well
    // would race the room and could reinstate text a collaborator just
    // deleted — a full-document last-write-wins through the back door.
    if (collabBoundRef.current) {
      try {
        localStorage.setItem(storageKey, newCode);
      } catch (_) {}
      return;
    }

    setSaveStatus("saving");
    try {
      // Always save to LocalStorage immediately for crash protection
      localStorage.setItem(storageKey, newCode);

      // Save to Supabase latex_documents DB + Local Disk + Qdrant Vector Sync
      const res = await authFetch(`${BACKEND_URL}/api/projects/save-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: activeProj,
          file_path: activeFilePath,
          raw_code: newCode,
        }),
      });

      if (res.ok) {
        setSaveStatus("saved");
      } else {
        setSaveStatus("unsaved");
      }
    } catch (err) {
      setSaveStatus("unsaved");
      console.error("Save document failed:", err);
    }
  };


  // 3. Handle code changes with debounced auto-save
  /**
   * The content of the editor changed.
   *
   * Called more than once for a single keystroke: the desktop and mobile
   * Monaco instances share one model (they must — see handleEditorMount), so
   * each of their `onChange` props fires for the same edit, and several child
   * components report document changes through here too. Everything below is
   * idempotent, but doing it twice per character still means two localStorage
   * writes and two debounce resets, so identical consecutive content is
   * dropped. Keyed by file as well as text: switching between two files that
   * happen to hold the same content is a real change.
   */
  const handleCodeChange = (newCode: string | undefined) => {
    const updated = newCode ?? "";
    // Text that belongs to another file (the editor has not caught up with a tab switch, or a
    // child reported a stale snapshot) must never be cached or saved under this file's path.
    if (loadedFilePathRef.current !== activeFilePath) return;
    const signature = `${activeFilePath}\u0000${updated}`;
    if (lastCodeChangeRef.current === signature) return;
    lastCodeChangeRef.current = signature;
    setCode(updated);
    fileContentCacheRef.current.set(activeFilePath, { content: updated, timestamp: Date.now() });

    // Instantly persist in LocalStorage for crash resilience
    try {
      localStorage.setItem(storageKey, updated);
    } catch (e) { }

    // Bound to a collaboration room: the keystroke is already a CRDT update on
    // its way to every peer, and the room persists it. Debouncing a whole-file
    // POST on top of that would be both redundant and a stale-snapshot risk.
    if (collabBoundRef.current) return;

    setSaveStatus("unsaved");
    // Debounced vector sync after 1.5s inactivity
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(() => {
      saveDocument(updated, false);
    }, 1500);
  };

  const setupDefaultLatexSyntaxAndEmeraldTheme = (monaco: any, editor?: any) => {
    if (!monaco) return;

    try {
      // Register custom LaTeX monarch syntax token rules with single-line TeX comment scoping
      monaco.languages.register({ id: "latex" });
      monaco.languages.setMonarchTokensProvider("latex", {
        defaultToken: "",
        tokenPostfix: ".latex",
        tokenizer: {
          root: [
            [/%[^\r\n]*/, "comment.latex"],
            [/\\@?[a-zA-Z]+/, "keyword.latex"],
            [/\$\$?/, "delimiter.math.latex", "@math"],
            [/\{/, "delimiter.bracket.latex"],
            [/\}/, "delimiter.bracket.latex"],
            [/\[/, "delimiter.square.latex"],
            [/\]/, "delimiter.square.latex"],
          ],
          math: [
            [/\$\$?/, "delimiter.math.latex", "@pop"],
            [/\\@?[a-zA-Z]+/, "keyword.math.latex"],
            [/[0-9]+(?:\.[0-9]+)?/, "number.math.latex"],
            [/[a-zA-Z]+/, "variable.math.latex"],
            [/./, "string.math.latex"],
          ],
        },
      });

      // Define default Kinetic Emerald Theme for Dark mode
      monaco.editor.defineTheme("kinetic-emerald", {
        base: "vs-dark",
        inherit: true,
        rules: [
          { token: "", foreground: "ffffff" },
          { token: "keyword.latex", foreground: "00CC68", fontStyle: "bold" },
          { token: "keyword", foreground: "00CC68", fontStyle: "bold" },
          { token: "comment.latex", foreground: "a1a1aa", fontStyle: "italic" },
          { token: "comment", foreground: "a1a1aa", fontStyle: "italic" },
          { token: "delimiter.math.latex", foreground: "38bdf8", fontStyle: "bold" },
          { token: "keyword.math.latex", foreground: "34d399", fontStyle: "bold" },
          { token: "number.math.latex", foreground: "fbbf24" },
          { token: "variable.math.latex", foreground: "ffffff" },
          { token: "delimiter.bracket.latex", foreground: "6ee7b7", fontStyle: "bold" },
          { token: "delimiter.square.latex", foreground: "f472b6" },
          { token: "string.math.latex", foreground: "e4e4e7" },
        ],
        colors: {
          "editor.background": "#121b17",
          "editor.foreground": "#ffffff",
          "editor.lineHighlightBackground": "#1c2b25",
          "editorCursor.foreground": "#10b981",
          "editorLineNumber.foreground": "#71717a",
          "editorLineNumber.activeForeground": "#10b981",
          "editorIndentGuide.background": "#273e35",
          "editorIndentGuide.activeBackground": "#10b981",
        },
      });

      // Define Kinetic Emerald Theme for Light mode
      monaco.editor.defineTheme("kinetic-emerald-light", {
        base: "vs",
        inherit: true,
        rules: [
          { token: "", foreground: "1e293b" },
          { token: "keyword.latex", foreground: "047857", fontStyle: "bold" },
          { token: "keyword", foreground: "047857", fontStyle: "bold" },
          { token: "comment.latex", foreground: "64748b", fontStyle: "italic" },
          { token: "comment", foreground: "64748b", fontStyle: "italic" },
          { token: "delimiter.math.latex", foreground: "0284c7", fontStyle: "bold" },
          { token: "keyword.math.latex", foreground: "059669", fontStyle: "bold" },
          { token: "number.math.latex", foreground: "d97706" },
          { token: "variable.math.latex", foreground: "1e293b" },
          { token: "delimiter.bracket.latex", foreground: "059669", fontStyle: "bold" },
          { token: "delimiter.square.latex", foreground: "db2777" },
          { token: "string.math.latex", foreground: "334155" },
        ],
        colors: {
          "editor.background": "#F8F9FA",
          "editor.foreground": "#1e293b",
          "editor.lineHighlightBackground": "#f1f5f9",
          "editorCursor.foreground": "#059669",
          "editorLineNumber.foreground": "#94a3b8",
          "editorLineNumber.activeForeground": "#059669",
          "editorIndentGuide.background": "#e2e8f0",
          "editorIndentGuide.activeBackground": "#10b981",
        },
      });

      const isCurrentlyDark = themeMounted
        ? (resolvedTheme ? resolvedTheme === "dark" : appTheme === "dark")
        : (typeof document !== "undefined" ? document.documentElement.classList.contains("dark") : true);

      monaco.editor.setTheme(isCurrentlyDark ? "kinetic-emerald" : "kinetic-emerald-light");
    } catch (e) {
      console.warn("Handled LaTeX syntax initialization exception:", e);
    }
  };

  const handleEditorMount = (editor: any, monaco: any, isDesktop: boolean = true) => {
    // The two Monaco instances (desktop + mobile) MUST share one model.
    //
    // They did not. @monaco-editor/react resolves a model with
    // `getModel(Uri.parse(path)) || createModel(value, lang, path ? uri :
    // undefined)`, and with no `path` prop that argument is `""` — falsy — so
    // each instance quietly got its own anonymous model. The collaboration
    // binding syncs text to the single model it was handed while attaching
    // cursor decorations to *every* editor, so remote carets appeared and
    // moved correctly while not one character of text ever crossed: the
    // binding was reading and writing the hidden editor's model, and the user
    // was typing in the visible one. Adopting the peer's model makes the
    // binding's own stated assumption true.
    const peer = isDesktop ? mobileEditorRef.current : desktopEditorRef.current;
    const shared = peer?.getModel?.();
    if (shared && !shared.isDisposed?.() && editor.getModel() !== shared) {
      const own = editor.getModel();
      editor.setModel(shared);
      if (own && own !== shared) {
        try {
          own.dispose();
        } catch {
          /* already gone */
        }
      }
    }

    if (isDesktop) {
      desktopEditorRef.current = editor;
    } else {
      mobileEditorRef.current = editor;
    }
    monacoRef.current = monaco;
    // Let effects that need an editor instance re-run now that one exists.
    setEditorsNonce((n) => n + 1);

    // Hand the instance to the collaboration session. Both editors now share
    // one model, so the binding attaches to the model once and only the
    // cursor decorations are per-editor.
    collab.registerEditor(editor, monaco);
    editor.onDidDispose(() => collab.unregisterEditor(editor));

    setupDefaultLatexSyntaxAndEmeraldTheme(monaco, editor);

    const isCurrentlyDark = themeMounted
      ? (resolvedTheme ? resolvedTheme === "dark" : appTheme === "dark")
      : (typeof document !== "undefined" ? document.documentElement.classList.contains("dark") : true);
    try {
      monaco.editor.setTheme(isCurrentlyDark ? "kinetic-emerald" : "kinetic-emerald-light");
    } catch (_) {}

    // Desktop only: a floating "@ Mention" button over a non-empty selection.
    // Touch has no hover surface; MobileEditorAssist carries its own button.
    let syncMentionWidget: () => void = () => {};
    if (isDesktop) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "@ Mention";
      button.setAttribute("aria-label", "Mention selection to the AI");
      const dark = () => document.documentElement.classList.contains("dark");
      Object.assign(button.style, {
        padding: "2px 8px",
        borderRadius: "6px",
        fontSize: "11px",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        lineHeight: "16px",
        cursor: "pointer",
        border: "1px solid transparent",
      });
      // mousedown + preventDefault: a click would first blur the editor and
      // clear the very selection we are about to read.
      button.addEventListener("mousedown", (e) => {
        e.preventDefault();
        addMentionRef.current();
      });
      const widget = {
        getId: () => "overbranch.mention.widget",
        getDomNode: () => button,
        getPosition: () => {
          const sel = editor.getSelection();
          if (!sel) return null;
          return {
            position: { lineNumber: sel.startLineNumber, column: sel.startColumn },
            preference: [
              monaco.editor.ContentWidgetPositionPreference.ABOVE,
              monaco.editor.ContentWidgetPositionPreference.BELOW,
            ],
          };
        },
      };
      let shown = false;
      syncMentionWidget = () => {
        const sel = editor.getSelection?.();
        const want = !!sel && !sel.isEmpty() && !isAgentThinkingRef.current;
        if (want) {
          const isDark = dark();
          button.style.background = isDark ? "#1A1C22" : "#ffffff";
          button.style.color = isDark ? "#F7F8F8" : "#0f172a";
          button.style.borderColor = isDark ? "#282A30" : "#cbd5e1";
          if (shown) {
            editor.layoutContentWidget(widget);
          } else {
            editor.addContentWidget(widget);
            shown = true;
          }
        } else if (shown) {
          editor.removeContentWidget(widget);
          shown = false;
        }
      };
      mentionWidgetSyncs.current.add(syncMentionWidget);
      editor.onDidDispose(() => {
        mentionWidgetSyncs.current.delete(syncMentionWidget);
        if (shown) {
          try {
            editor.removeContentWidget(widget);
          } catch {
            /* editor already torn down */
          }
          shown = false;
        }
      });
    }

    editor.onDidChangeCursorSelection((e: any) => {
      if (e.selection) {
        lastSelectionRef.current = e.selection;
      }
      syncMentionWidget();
    });

    editor.onDidChangeCursorPosition((e: any) => {
      if (e.position) {
        lastPositionRef.current = e.position;
      }
    });

    // Register Ctrl+S / Cmd+S save shortcut inside Monaco Editor
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      const currentVal = editor.getValue();
      editorActionsRef.current?.save(currentVal, true);
      editorActionsRef.current?.compile(currentVal);
    });

    // Ctrl/Cmd+M: pin the selection to the chat message (both editors).
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyM, () => {
      addMentionRef.current();
    });

    // Our own find bar deliberately replaces Monaco's built-in widget: the
    // built-in one needs a hardware keyboard and has no UI trigger, so it is
    // unreachable on mobile. One bar keeps both platforms identical.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyF, () => {
      setSearchOpen(true);
    });

    // Route the keyboard through the same resolver as the toolbar buttons, so
    // a collaborative session gets per-user undo instead of Monaco's
    // document-wide stack (see handleUndo).
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyZ, () => {
      if (!collabBoundRef.current) {
        editor.trigger("keyboard", "undo", null);
        return;
      }
      handleUndoRef.current?.();
    });
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyZ, () => {
      if (!collabBoundRef.current) {
        editor.trigger("keyboard", "redo", null);
        return;
      }
      handleRedoRef.current?.();
    });
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyY, () => {
      if (!collabBoundRef.current) {
        editor.trigger("keyboard", "redo", null);
        return;
      }
      handleRedoRef.current?.();
    });
  };

  const lastSyncedHashRef = useRef<string>("");

  const syncVectorDatabase = async (updatedCode: string) => {
    try {
      const fileHash = computeContentHash(updatedCode);
      if (lastSyncedHashRef.current === fileHash) {
        return;
      }

      const response = await fetch(`${BACKEND_URL}/api/sync-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId || "00000000-0000-0000-0000-000000000000",
          file_path: activeFilePath || "main.tex",
          new_code: updatedCode,
        }),
      });
      const data = await response.json();
      if (data.synced) {
        lastSyncedHashRef.current = fileHash;
        setSaveStatus("saved");

        // Cache document chunks in local IndexedDB
        if (data.chunks && Array.isArray(data.chunks) && data.chunks.length > 0) {
          setCachedDocumentChunks(
            projectId || "proj-default",
            activeFilePath || "main.tex",
            fileHash,
            data.chunks
          ).catch((e) => console.warn("IndexedDB chunk save note:", e));
        }
      }
    } catch (err) {
      console.warn("Background vector sync failed:", err);
    }
  };

  /**
   * The text to act on right now. While a collaboration room is bound, the
   * Monaco model is the live document and the `code` state is a throttled
   * mirror of it, so anything that must be exact (compile, the agent) reads
   * the model instead of waiting for the mirror to catch up.
   */
  const currentDocumentText = (): string => {
    if (collabBoundRef.current) {
      const value = getActiveEditor()?.getModel?.()?.getValue?.();
      if (typeof value === "string") return value;
    }
    return code;
  };

  const handleCompile = async (currentCodeOverride?: string) => {
    const targetCode = currentCodeOverride ?? currentDocumentText();
    if (!targetCode) return;
    setIsCompiling(true);
    setCompileBusy(false);
    setErrorLog(null);
    // One toast id for the whole retry sequence, so retries update a single
    // toast rather than stacking (M8).
    const busyToastId = "compile-busy";
    try {
      let attempt = 0;
      for (;;) {
        let outcome: CompileOutcome;
        try {
          const res = await authFetch(`${BACKEND_URL}/api/compile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              latex_code: targetCode,
              project_id: projectId || "",
              engine: engine,
              // Compile the PROJECT's main document, with the open tab's text
              // overlaid at its own path — so an imported multi-file project
              // builds the real main.tex, not whatever file happens to be open.
              active_file: isAuxiliaryFilePath(activeFilePath) ? (projectMainFile || "main.tex") : (activeFilePath || "main.tex"),
              active_text: targetCode,
            }),
          });
          const data = await res.json().catch(() => null);
          outcome = classifyCompileResponse(res.status, data);
        } catch {
          outcome = {
            kind: "network",
            message: "Network error or Python backend is not running.",
          };
        }

        if (outcome.kind === "ok") {
          // A PDF was produced: show it, and nothing else. TeX's recoverable
          // complaints in nonstopmode are not surfaced as a warning band.
          toast.dismiss(busyToastId);
          setPdfBase64(outcome.body.pdf_base64);
          // Server-side font substitution is information, never an error: the PDF is already
          // showing; this only says which fonts were swapped (and how to keep the originals).
          const compileNotices = collectCompileNotices(outcome.body);
          if (compileNotices.length > 0) {
            toast.info("Fonts substituted", {
              id: "compile-font-notice",
              description: compileNotices.join(" "),
              duration: 12000,
            });
          }
          return;
        }
        if (outcome.kind === "busy") {
          // The server is queueing work, not rejecting the LaTeX: never touch errorLog.
          const delay = nextRetryDelay(attempt);
          if (delay === null) {
            toast.dismiss(busyToastId);
            toast.error("Server is busy. Try again in a moment.");
            return;
          }
          attempt += 1;
          setCompileBusy(true);
          toast.loading("Server busy \u2014 retrying\u2026", { id: busyToastId });
          await new Promise((resolve) => setTimeout(resolve, delay));
          continue;
        }
        toast.dismiss(busyToastId);
        if (outcome.kind === "failed") {
          setErrorLog(outcome.errorLog);
          toast.error("LaTeX compilation failed.");
        } else {
          setErrorLog(outcome.message);
          toast.error("Failed to connect to backend compiler.");
        }
        return;
      }
    } finally {
      setCompileBusy(false);
      setIsCompiling(false);
    }
  };

  editorActionsRef.current = { save: saveDocument, compile: handleCompile };

  const sendPromptMessage = async (customPrompt?: string, modeOverride?: ChatMode) => {
    // "Ask AI to Fix" must run in Edit mode whatever the toggle says: in Ask mode the
    // agent cannot change the document, so the fix could never be applied.
    const effectiveMode: ChatMode = modeOverride ?? chatMode;
    const rawUserText = customPrompt !== undefined ? customPrompt : chatInput;
    if ((!rawUserText.trim() && !hasAttachments) || isAgentThinking) return;
    if (chatAttachments.isUploading) {
      toast.info("Your files are still uploading. Send again in a moment.");
      return;
    }

    const attachedNames = chatAttachments.ready.map((a) => a.filename);
    const userText = rawUserText.trim() || (hasAttachments ? `[Uploaded files: ${attachedNames.join(", ")}]` : "");
    // Name each attachment in the chat once, when it first travels with a message.
    const newlyAttached = chatAttachments.ready.filter(
      (a) => !announcedAttachmentsRef.current.has(a.id) && !userText.includes(a.filename),
    );
    chatAttachments.ready.forEach((a) => announcedAttachmentsRef.current.add(a.id));
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        sender: "user",
        text: newlyAttached.length > 0
          ? `${userText}\n\n📎 Attached: ${newlyAttached.map((a) => a.filename).join(", ")}`
          : userText,
        time: now,
      },
    ]);

    if (customPrompt === undefined) {
      setChatInput("");
      setMentions([]);
      mentionsRef.current = [];
      if (typeof document !== "undefined") {
        document.querySelectorAll<HTMLTextAreaElement>("textarea[id*='chat-input']").forEach((el) => {
          el.style.height = "auto";
        });
      }
      // Attachments stay for follow-up messages; they are removed with the (x) on
      // their chip or by clearing the chat.
    }
    setIsAgentThinking(true);
    setAgentProgressSteps([]);

    abortControllerRef.current = new AbortController();
    const reqId = `chat-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    activeRequestIdRef.current = reqId;

    // Liveness, not a deadline: the backend sends bytes (progress events or a ": keep-alive"
    // comment every 3s) for as long as the run is alive, so a slow run that keeps talking is
    // never aborted. Only a connection that has gone silent for AGENT_IDLE_TIMEOUT_MS is.
    const requestController = abortControllerRef.current;
    let idleTripped = false;
    let idleTimer: ReturnType<typeof setTimeout> | undefined;
    const armIdleTimer = () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        idleTripped = true;
        requestController.abort();
      }, AGENT_IDLE_TIMEOUT_MS);
    };
    armIdleTimer();

    try {
      // Check for user-provided API keys
      let customApiKeys = null;
      try {
        const storedKeys = localStorage.getItem("ob_api_keys");
        if (storedKeys) customApiKeys = JSON.parse(storedKeys);
      } catch (e) {
        console.warn("Failed to parse API keys from localStorage", e);
      }

      const response = await authFetch(`${BACKEND_URL}/api/agent/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          project_id: projectId || "proj-default",
          session_id: projStorageKey || projectId || "proj-default",
          request_id: reqId,
          file_path: activeFilePath || "main.tex",
          user_prompt: userText,
          current_code: currentDocumentText(),
          model: activeModelName || "auto:smart",
          // Attached files are already on the server (see useChatAttachments); the
          // agent reads them from this chat's session.
          mode: effectiveMode,
          // What the user had highlighted when they asked. "Elaborate this" and
          // "humanize this" mean the selection when there is one, and the
          // request text alone cannot say which block that was.
          // With mentions the first one stands in for `selection`, so
          // elaborate/humanize keep working unchanged.
          selection: mentions.length > 0
            ? {
                text: mentions[0].text,
                start_line: mentions[0].start_line,
                end_line: mentions[0].end_line,
                file: mentions[0].file,
              }
            : activeSelection() || undefined,
          mentions: mentions.length > 0
            ? mentions.map((m) => ({
                id: m.id,
                file: m.file,
                start_line: m.start_line,
                end_line: m.end_line,
                text: m.text,
                label: m.label,
              }))
            : undefined,
          api_keys: customApiKeys || undefined,
        }),
      });
      armIdleTimer();

      if (!response.ok) {
        if (response.status >= 500) {
          console.error("Agent request failed with status", response.status);
          throw new Error(MODEL_OUTAGE_MESSAGE);
        }
        if (response.status === 413) {
          throw new Error("The uploaded file is too large for the server. Try a smaller PDF or ask about the document without attaching it.");
        }
        const errText = await response.text();
        let errMsg = errText;
        try {
          const parsed = JSON.parse(errText);
          if (parsed.detail) {
            errMsg = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
          } else if (parsed.message) {
            errMsg = parsed.message;
          }
        } catch {
          // not JSON, keep errText
        }
        throw new Error(errMsg || `AI Agent returned status ${response.status}`);
      }

      // Read SSE stream
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";
      let finalData: any = null;
      // final_diff arrives once per modified file; keyed by file so an auxiliary
      // file's payload cannot clobber the main one (and so aux edits are visible
      // instead of silently discarded).
      const finalDiffsByFile: Record<string, any> = {};
      let sseError: Error | null = null;

      try {
        let currentEventType = "";

        const parseSSELines = (lines: string[]) => {
          for (const line of lines) {
            const trimmed = line.replace(/\r$/, "");
            if (trimmed.startsWith("event: ")) {
              currentEventType = trimmed.slice(7).trim();
            } else if (trimmed.startsWith("data: ")) {
              const rawData = trimmed.slice(6);
              try {
                const parsed = JSON.parse(rawData);

                if (currentEventType === "coverage_check" || parsed.type === "coverage_check") {
                  const total = parsed.total_chunks ?? 0;
                  const edited = parsed.edited_chunks ?? 0;
                  const missing = parsed.missing_chunk_ids || [];
                  const msg = parsed.passed
                    ? `✓ Coverage Verified: All ${total} chunks successfully updated.`
                    : `Coverage Check: ${edited}/${total} chunks edited. Missing: ${missing.join(", ")}`;
                  setAgentProgressSteps((prev) => [...prev, {
                    step: "coverage_check",
                    message: parsed.message || msg,
                    icon: parsed.passed ? "check" : "alert",
                    ...parsed,
                  }]);
                } else if (currentEventType === "progress") {
                  const msg = (parsed.message || "").toLowerCase().trim();
                  if (
                    msg.startsWith("edit scope") ||
                    msg.includes("edit scope detected") ||
                    msg.startsWith("analyzed document") ||
                    msg.startsWith("analyze document") ||
                    msg.startsWith("context strategy")
                  ) {
                    continue;
                  }
                  const stepItem =
                    parsed.step === "tool_call" || msg.startsWith("tool calling")
                      ? { ...parsed, message: "Tool calling..." }
                      : parsed;
                  setAgentProgressSteps((prev) => [...prev, stepItem]);
                } else if (["thought", "tool_call", "tool_result", "compile_error", "coverage_check"].includes(currentEventType)) {
                  let msg = parsed.content || parsed.message || (typeof parsed === "string" ? parsed : JSON.stringify(parsed));
                  if (currentEventType === "tool_call" || (typeof msg === "string" && msg.toLowerCase().trim().startsWith("tool calling"))) {
                    msg = "Tool calling...";
                  }
                  setAgentProgressSteps((prev) => [...prev, {
                    step: currentEventType,
                    message: msg,
                    icon: currentEventType === "compile_error" ? "alert" : currentEventType === "thought" ? "brain" : currentEventType === "tool_call" ? "wrench" : "check",
                    ...parsed,
                  }]);
                } else if (currentEventType === "result" && finalData) {
                  // `result` arrives last and repeats the run. It carries `proposed_chunk`,
                  // so it used to fall into the final_diff branch below and REPLACE
                  // finalData — dropping final_diff's original_code / proposed_code, so the
                  // backend's validated, compiled buffer was never written and every
                  // Accept replayed anchors (any miss: "Couldn't safely apply this change").
                  // final_diff's document fields win; run-level fields come from `result`.
                  const base: any = finalData;
                  finalData = {
                    ...parsed,
                    ...base,
                    explanation: parsed.explanation || base.explanation || "",
                    failure: parsed.failure,
                    partial: parsed.partial,
                    compile_verified: parsed.compile_verified,
                  };
                } else if (
                  currentEventType === "final_diff" ||
                  parsed.type === "final_diff" ||
                  parsed.proposed_code !== undefined ||
                  parsed.proposed_chunk !== undefined ||
                  (Array.isArray(parsed.edits) && parsed.edits.length > 0)
                ) {
                  const hasExplicitNoChanges = parsed.has_changes === false;
                  const editsArr = hasExplicitNoChanges
                    ? []
                    : (Array.isArray(parsed.edits) && parsed.edits.length > 0
                        ? parsed.edits
                        : ((parsed.proposed_code || parsed.proposed_chunk) && (parsed.proposed_code !== parsed.original_code || parsed.proposed_chunk !== parsed.original_chunk)
                            ? [{
                                original_chunk: parsed.original_code || parsed.original_chunk || "",
                                proposed_chunk: parsed.proposed_code || parsed.proposed_chunk || "",
                                explanation: parsed.explanation || "",
                              }]
                            : []));
                  const diffFile =
                    parsed.file || activeFilePath || "main.tex";
                  const normalizedDiff = {
                    ...parsed,
                    file: diffFile,
                    original_chunk: parsed.original_code || parsed.original_chunk || "",
                    proposed_chunk: parsed.proposed_code || parsed.proposed_chunk || "",
                    explanation: parsed.explanation || "",
                    edits: editsArr,
                  };
                  finalDiffsByFile[diffFile] = normalizedDiff;
                  // Only the active file drives the inline diff UI.
                  if (diffFile === (activeFilePath || "main.tex")) {
                    finalData = normalizedDiff;
                  } else if (!finalData) {
                    finalData = normalizedDiff;
                  }
                } else if (currentEventType === "pdf_conversion" && parsed.job_id) {
                  // The copilot started a PDF import: show its live progress & report
                  setPdfImportJobId(parsed.job_id);
                  setPdfImportOpen(true);
                } else if (currentEventType === "result") {
                  finalData = { ...(finalData || {}), ...parsed };
                } else if (currentEventType === "cancelled") {
                  console.log("AI Agent generation cleanly stopped by user:", parsed);
                  return;
                } else if (currentEventType === "error" || (parsed.type === "error" && (parsed.message || parsed.detail || parsed.error))) {
                  // The detail (provider, status, stack) belongs in the console, not in front of the user.
                  console.error("Agent stream error:", parsed);
                  sseError = new Error(MODEL_OUTAGE_MESSAGE);
                }
              } catch {
                // Non-JSON or fragmented data chunk: safely skip
              }
            } else if (trimmed.startsWith(":")) {
              // SSE keep-alive comment: safely ignore
              continue;
            } else if (trimmed === "") {
              currentEventType = "";
            }
          }
        };

        while (true) {
          if (sseError) break;
          const { done, value } = await reader.read();
          if (done) break;
          armIdleTimer(); // any bytes, keep-alive comments included, prove the run is alive

          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          parseSSELines(lines);
        }

        if (buffer.trim() && !sseError) {
          const remainingLines = buffer.split("\n");
          parseSSELines(remainingLines);
          buffer = "";
        }
      } finally {
        try { reader.cancel(); } catch (_) { }
        try { reader.releaseLock(); } catch (_) { }
      }

      if (sseError) throw sseError;
      if (!finalData) {
        // Fallback: check if we received any progress error or step
        const lastErrStep = agentProgressSteps.slice().reverse().find((s: any) => s.step === "compile_error" || s.icon === "alert");
        const fallbackMsg = lastErrStep?.message || "AI completed processing, but no modifications were produced.";
        finalData = {
          original_chunk: "",
          proposed_chunk: "",
          explanation: fallbackMsg,
          edits: [],
          has_changes: false,
        };
      }

      const data = finalData;
      const assistantTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });



      const rawExplanation = data.explanation || "I have processed your LaTeX request.";
      const responseText = sanitizeChunkReferences(rawExplanation);

      const isAskModeResponse = effectiveMode === "ask" || data.mode === "ask";

      // Build explicit edits list (only in Edit mode)
      let editsList: EditItem[] = (!isAskModeResponse && data.edits && Array.isArray(data.edits) && data.edits.length > 0)
        ? data.edits
          .filter((e: any) => e.original_chunk || e.proposed_chunk)
          .map((e: any, idx: number) => ({
            // Keep the apply-contract fields (line range, is_full_document, node_id):
            // the appliers need them to place the edit.
            ...e,
            id: `edit-${Date.now()}-${idx}`,
            original_chunk: e.original_chunk || "",
            proposed_chunk: e.proposed_chunk || "",
            explanation: sanitizeChunkReferences(e.explanation || rawExplanation),
          }))
        : (!isAskModeResponse && (data.original_chunk || data.proposed_chunk))
          ? [{
            id: `edit-${Date.now()}-0`,
            original_chunk: data.original_chunk || "",
            proposed_chunk: data.proposed_chunk || "",
            explanation: sanitizeChunkReferences(data.explanation || "AI Proposed Edit"),
          }]
          : [];

      // Fallback: extract LaTeX from raw explanation ONLY in Edit mode when not an explicit no-change/failure
      if (!isAskModeResponse && editsList.length === 0 && data.has_changes !== false && !data.document_unchanged && !data.failure) {
        const extractedCode = extractLatexFromResponse(rawExplanation);
        if (extractedCode) {
          editsList = [{
            id: `edit-${Date.now()}-fallback`,
            original_chunk: "",
            proposed_chunk: extractedCode,
            explanation: "Extracted LaTeX proposal.",
          }];
        }
      }

      const hasEdits = editsList.length > 0;
      const assistantMsgId = `ai-${Date.now()}`;
      // Bind the pending diff to this message so accepting it from the
      // floating card marks exactly one card applied.
      pendingEditsMsgIdRef.current = hasEdits ? assistantMsgId : null;

      setMessages((prev) => [
        ...prev,
        {
          id: assistantMsgId,
          sender: "assistant",
          text: responseText,
          time: assistantTime,
          mode: effectiveMode,
          edits: editsList,
          editsFile: data.file || activeFilePath || "main.tex",
          isApplied: false,
          failure: data.failure,
          detailedErrors: data.detailed_errors || data.failure?.detailed_errors,
        },
      ]);

      if (hasEdits) {
        setDiffEditsList(editsList);
        const activeFile = activeFilePath || "main.tex";
        const authoritativeDoc: AuthoritativeDoc | undefined =
          typeof data.original_code === "string" && typeof data.proposed_code === "string"
            ? {
              file: data.file || activeFile,
              originalCode: data.original_code,
              proposedCode: data.proposed_code,
              hunks: Array.isArray(data.hunks) ? data.hunks : undefined,
            }
            : undefined;
        authoritativeDocRef.current = authoritativeDoc ?? null;
        setDiffData({
          original_chunk: data.original_chunk || editsList[0].original_chunk,
          proposed_chunk: data.proposed_chunk || editsList[0].proposed_chunk,
          explanation: sanitizeChunkReferences(data.explanation || "AI Suggested Modifications"),
          authoritative: authoritativeDoc,
        });
      } else {
        authoritativeDocRef.current = null;
        setDiffEditsList([]);
        setDiffData(null);
      }

      if (data.pdf_conversion_job_id) {
        setPdfImportJobId(data.pdf_conversion_job_id);
        setPdfImportOpen(true);
      }
      // Figures the agent imported from attached files are new project files.
      if (Array.isArray(data.imported_assets) && data.imported_assets.length > 0) {
        setFilesRefreshTrigger((n) => n + 1);
      }
    } catch (err: any) {
      if (idleTimer) clearTimeout(idleTimer);
      if (err.name === "AbortError") {
        console.log("AI Agent chat request aborted.", idleTripped ? "(connection went silent)" : "(stopped)");
        setMessages((prev) => [
          ...prev,
          {
            id: `ai-abort-${Date.now()}`,
            sender: "assistant",
            // A stop is the user's own doing; only a dead connection is an outage.
            text: idleTripped ? MODEL_OUTAGE_MESSAGE : "Stopped.",
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        return;
      }

      let userErrMsg = err.message || MODEL_OUTAGE_MESSAGE;
      if (userErrMsg.includes("input stream") || userErrMsg.includes("network") || userErrMsg.includes("Failed to fetch")) {
        userErrMsg = MODEL_OUTAGE_MESSAGE;
      }
      const warningMsg = userErrMsg;
      toast.error(warningMsg, { duration: 6000 });
      setMessages((prev) => [
        ...prev,
        {
          id: `ai-err-${Date.now()}`,
          sender: "assistant",
          text: warningMsg,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      if (idleTimer) clearTimeout(idleTimer);
      setIsAgentThinking(false);
      setAgentProgressSteps([]);
      abortControllerRef.current = null;
      activeRequestIdRef.current = null;
    }
  };

  const handleSendPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    await sendPromptMessage();
  };

  const handleAskAiToFix = (error: string) => {
    setAiOpen(true);
    setActiveMobileTab("ai");
    const cleanErr = error ? error.trim() : "Compilation error";
    const prompt = `Please fix this LaTeX compilation error:\n\n\`\`\`\n${cleanErr}\n\`\`\`\n\nPlease locate the error in the document, inspect the surrounding code, and apply the necessary in-place fix.`;
    sendPromptMessage(prompt, "edit");
  };

  const replaceAllCaseInsensitive = (text: string, search: string, replacement: string): string => {
    if (!search) return text;
    const escapedSearch = search
      .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      .replace(/\s+/g, '\\s+');
    const regex = new RegExp(escapedSearch, 'gi');
    return text.replace(regex, (match) => {
      if (match === match.toUpperCase()) {
        return replacement.toUpperCase();
      }
      if (match === match.toLowerCase()) {
        return replacement.toLowerCase();
      }
      return replacement;
    });
  };

  const insertSnippetSafely = (text: string, snippet: string): string => {
    // If document contains bibliography, insert before bibliography rather than after it
    const biblioIndex = text.indexOf("\\begin{thebibliography}");
    if (biblioIndex !== -1 && !snippet.includes("\\begin{thebibliography}")) {
      return text.slice(0, biblioIndex) + snippet + "\n\n" + text.slice(biblioIndex);
    }
    const bibMatch = text.match(/\\(?:bibliographystyle\{[^}]+\}\s*)?\\bibliography\{[^}]+\}/);
    if (bibMatch && bibMatch.index !== undefined && !snippet.includes("\\bibliography")) {
      return text.slice(0, bibMatch.index) + snippet + "\n\n" + text.slice(bibMatch.index);
    }
    const endDocIndex = text.lastIndexOf("\\end{document}");
    if (endDocIndex !== -1) {
      return text.slice(0, endDocIndex) + "\n\n" + snippet + "\n\n" + text.slice(endDocIndex);
    }
    return text + "\n\n" + snippet;
  };

  /**
   * The single place that commits an apply outcome to the editor.
   *
   * Previously this logic was copy-pasted across several accept handlers, each
   * with subtly different history IDs and message flags — and each silently
   * dropping edits whose anchor was missing or ambiguous. Skips are now always
   * surfaced, and a partial apply is re-validated before it is saved.
   *
   * `opts.msgId` identifies the one chat message these edits belong to; it is
   * also the history id, so each card can revert exactly its own edit.
   */
  const commitEditOutcome = async (
    outcome: ApplyOutcome,
    opts: {
      codeBeforeEdit: string;
      historyId: string;
      historyLabel: string;
      source: string;
      msgId?: string;
      clearDiffState: boolean;
      markMessagesApplied?: boolean;
    },
  ) => {
    let { code: updatedCode } = outcome;
    const { applied, skipped } = outcome;
    const file = activeFilePath || "main.tex";

    if (applied.length === 0 && skipped.length === 0) {
      toast.error("No edits could be applied to this document.");
      return;
    }

    // Some edits could not be placed by exact text (the document moved under
    // them). Rather than dropping them — or applying the rest and leaving a
    // half-done change — the backend re-locates every item with the agent's
    // locator (node → normalised text → similarity) and applies all or none.
    if (skipped.length > 0) {
      const allItems = [...applied, ...skipped.map((s) => s.item)];
      const server = await resolveEditsOnServer(
        opts.codeBeforeEdit,
        allItems,
        authoritativeDocRef.current?.originalCode,
        projectId,
        file,
      );
      if (!server.success) {
        if (SHOW_EDIT_DEBUG) {
          console.info("[edit-apply] could not place edits", {
            skipped: skipped.map((s) => ({ reason: s.reason, node_id: s.item.node_id, op: s.item.op })),
            server: server.unavailable ? "unreachable" : server.failed,
          });
        }
        const detail = SHOW_EDIT_DEBUG
          ? server.unavailable
            ? "Server re-location unavailable."
            : server.failed
                .slice(0, 2)
                .map((f) => `${f.op} ${f.target ?? ""}: ${f.reason} (tried ${f.attempts.map((a) => a.method).join(" → ") || "—"})`)
                .join("; ")
          : undefined;
        toast.error(SAFE_APPLY_FAILURE, detail ? { description: detail, duration: 8000 } : undefined);
        return;
      }
      updatedCode = server.code;
      if (SHOW_EDIT_DEBUG) {
        console.info("[edit-apply] edits re-located on the server", server.applied);
      }
    }

    const editor = getActiveEditor();
    const model = editor?.getModel?.();
    if (editor && model) {
      // Minimal line edits, not a full-model replace: a replace spanning the
      // whole document is last-write-wins over every concurrent keystroke and
      // sends every collaborator's cursor to line 1. The surgical edits are
      // what the Yjs binding turns into CRDT operations, so an accepted AI
      // change reaches the other users through exactly the same path as typing.
      const operations = applyTextToEditor(editor, monacoRef.current, updatedCode, opts.source);
      collabLog("COLLAB_AI_EDIT", {
        source: opts.source,
        operations,
        collaborative: collabBoundRef.current,
      });
    }
    setCode(updatedCode);

    if (opts.clearDiffState) {
      setDiffData(null);
      setDiffEditsList([]);
      authoritativeDocRef.current = null;
    }

    const userPrompt =
      messages.filter((m) => m.sender === "user").pop()?.text || opts.historyLabel;
    if (editHistoryStoreRef.current) {
      editHistoryStoreRef.current.pushEdit({
        id: opts.historyId,
        timestamp: Date.now(),
        model: activeModelName,
        prompt: userPrompt,
        files: [file],
        beforeCode: { [file]: opts.codeBeforeEdit },
        afterCode: { [file]: updatedCode },
        cursorState: {
          file,
          line: editor?.getPosition()?.lineNumber || 1,
          column: editor?.getPosition()?.column || 1,
          scrollTop: editor?.getScrollTop() || 0,
        },
        isReverted: false,
      });
    }

    // Only the message these edits came from is marked applied. The old
    // `else` branch marked every message that still carried an `edits` array,
    // badging untouched proposals as "Applied" and giving them all the same
    // historyEntryId — which is why one Revert click flipped every card and
    // could restore the wrong document.
    if (opts.markMessagesApplied && opts.msgId) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === opts.msgId
            ? { ...m, isApplied: true, isReverted: false, historyEntryId: opts.historyId }
            : m,
        ),
      );
    }

    saveDocument(updatedCode, true);
    handleCompile(updatedCode);
  };

  /** Resolves the authoritative buffer for the active file, if one is in hand. */
  const authoritativeForActiveFile = (): { originalText?: string; authoritativeText?: string } => {
    const doc = authoritativeDocRef.current;
    const file = activeFilePath || "main.tex";
    if (!doc || (doc.file && doc.file !== file)) return {};
    return { originalText: doc.originalCode, authoritativeText: doc.proposedCode };
  };

  const handleAcceptAllEdits = (itemsToApply: EditItem[], msgId?: string) => {
    const targetFile = msgId ? messages.find((m) => m.id === msgId)?.editsFile : undefined;
    const activeFile = activeFilePath || "main.tex";
    if (targetFile && targetFile !== activeFile) {
      toast.error(`These edits were made for ${targetFile}. Open ${targetFile} to apply them.`);
      return;
    }
    // Part-way through an inline review the document already holds the accepted
    // changes: replaying every item on top of it would apply those twice. The
    // rest are applied where the review has them.
    const review = inlineDiffRef.current;
    const progress = review?.getState();
    if (review && progress && progress.accepted + progress.rejected > 0
        && (!msgId || msgId === pendingEditsMsgIdRef.current)) {
      review.acceptAll();
      const after = review.getState();
      if (after.pending === 0 && inlineDiffRef.current === review) finishInlineReview(after);
      return;
    }

    const editor = getActiveEditor();
    const model = editor?.getModel?.();
    const codeBeforeEdit = model ? model.getValue() : code;

    // Accept All prefers the backend's full healed+validated buffer, so the text
    // in the editor is byte-identical to what passed pre-commit validation.
    // applyEditItems falls back to replaying chunks if the document changed
    // while the agent was streaming (the editor is not locked during a stream).
    const outcome = applyEditItems(
      codeBeforeEdit,
      itemsToApply as AppliedEditItem[],
      authoritativeForActiveFile(),
    );

    if (outcome.strategy === "chunks" && authoritativeDocRef.current) {
      toast.info("Document changed while the AI was working — applying edits individually.");
    }

    void commitEditOutcome(outcome, {
      codeBeforeEdit,
      historyId: msgId || `edit-${Date.now()}`,
      historyLabel: "AI Document Edit",
      source: "ai-accept-all",
      msgId,
      clearDiffState: true,
      markMessagesApplied: true,
    });
  };

  /**
   * The text in the editor right now. `code` is React state and lags the model by
   * a render — an edit applied a moment ago in the same handler is not in it yet.
   */
  const liveEditorText = (): string => {
    const value = getActiveEditor()?.getModel?.()?.getValue?.();
    return typeof value === "string" ? value : code;
  };

  const handleRejectAllEdits = () => {
    // Changes already accepted in the inline review stay; only what is pending is dropped.
    const acceptedSome = (inlineDiffRef.current?.getState().accepted ?? 0) > 0;
    const updated = acceptedSome ? liveEditorText() : null;
    inlineDiffRef.current = null;
    setDiffData(null);
    setDiffEditsList([]);
    authoritativeDocRef.current = null;
    pendingEditsMsgIdRef.current = null;
    if (updated !== null) {
      saveDocument(updated, true);
      handleCompile(updated);
    }
  };

  /** Ends the inline review once every change has been accepted, rejected or withdrawn. */
  const finishInlineReview = (state: InlineDiffState) => {
    if (!inlineDiffRef.current) return; // already finished (accept-all reports once per change)
    inlineDiffRef.current = null;
    const updated = liveEditorText();
    if (state.unplaced > 0) {
      toast.info(
        `${state.unplaced} change${state.unplaced === 1 ? " was" : "s were"} not applied: the document was edited at ${state.unplaced === 1 ? "that place" : "those places"} while you were reviewing.`,
      );
    }
    setDiffData(null);
    setDiffEditsList([]);
    authoritativeDocRef.current = null;
    pendingEditsMsgIdRef.current = null;
    if (state.accepted > 0) {
      saveDocument(updated, true);
      handleCompile(updated);
    }
  };

  /** Records an accepted change: editor mirror, one history entry per proposal, the chat card. */
  const recordReviewProgress = (state: InlineDiffState) => {
    const file = activeFilePath || "main.tex";
    const editor = getActiveEditor();
    const updated = liveEditorText();
    setCode(updated);
    const msgId = pendingEditsMsgIdRef.current ?? undefined;
    const historyId = msgId || `edit-review-${file}`;
    editHistoryStoreRef.current?.pushEdit({
      id: historyId,
      timestamp: Date.now(),
      model: activeModelName,
      prompt: messages.filter((m) => m.sender === "user").pop()?.text || "AI Document Edit",
      files: [file],
      beforeCode: { [file]: reviewBaselineRef.current ?? updated },
      afterCode: { [file]: updated },
      cursorState: {
        file,
        line: editor?.getPosition?.()?.lineNumber || 1,
        column: editor?.getPosition?.()?.column || 1,
        scrollTop: editor?.getScrollTop?.() || 0,
      },
      isReverted: false,
    });
    if (msgId) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
              ...m,
              isApplied: true,
              isReverted: false,
              historyEntryId: historyId,
              appliedChanges: state.accepted,
              totalChanges: state.total,
            }
            : m,
        ),
      );
    }
  };

  // Re-bound every render so the controller's callbacks always see current state.
  reviewHandlersRef.current = {
    accepted: (state) => {
      recordReviewProgress(state);
      if (state.pending === 0) finishInlineReview(state);
    },
    rejected: (state) => {
      if (state.pending === 0) finishInlineReview(state);
    },
  };

  /**
   * One bar for the pending proposal: how many changes are left, stepping
   * between them, and accept / reject for all of them. The changes themselves
   * are drawn in the editor, each with its own Accept / Reject.
   */
  const renderReviewBar = (variant: "editor" | "sidebar" | "mobile") => {
    if (!diffData || diffEditsList.length === 0) return null;
    const review = reviewState;
    const compact = variant === "mobile";
    const position =
      variant === "sidebar"
        ? "mb-2"
        : `absolute ${compact ? "bottom-2" : "bottom-3"} left-1/2 -translate-x-1/2 z-20 max-w-[calc(100%-1rem)]`;
    const step = (dir: 1 | -1) => (dir === 1 ? inlineDiffRef.current?.next() : inlineDiffRef.current?.previous());
    const acceptAll = () => {
      handleAcceptAllEdits(diffEditsList, pendingEditsMsgIdRef.current ?? undefined);
      if (variant === "sidebar" && typeof window !== "undefined" && window.innerWidth < 768) {
        setActiveMobileTab("code");
      }
    };
    const navBtn =
      "h-6 w-6 rounded-md flex items-center justify-center text-slate-600 dark:text-[#9E9E9E] hover:bg-slate-200 dark:hover:bg-[#22242C] hover:text-slate-900 dark:hover:text-[#E2E4E9] transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default";

    return (
      <div
        className={`${position} flex items-center ${variant === "sidebar" ? "flex-wrap" : "flex-nowrap"} gap-x-2 gap-y-1.5 px-2.5 py-1.5 rounded-xl bg-white dark:bg-[#141519] border border-slate-200 dark:border-[#282A30] shadow-xl font-mono text-[11px] text-slate-700 dark:text-[#C9CCD3] animate-in fade-in`}
        role="group"
        aria-label="Review AI changes"
      >
        {review && review.pending > 0 ? (
          <>
            <div className="flex items-center gap-0.5">
              <button type="button" className={navBtn} onClick={() => step(-1)} disabled={review.pending < 2} title="Previous change" aria-label="Previous change">
                <ChevronUp className="w-3.5 h-3.5" />
              </button>
              <span className="px-1 tabular-nums whitespace-nowrap font-semibold text-slate-900 dark:text-[#E2E4E9]">
                {review.current + 1} / {review.pending}
              </span>
              <button type="button" className={navBtn} onClick={() => step(1)} disabled={review.pending < 2} title="Next change" aria-label="Next change">
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </div>
            {!compact && reviewStats && (
              <span className="whitespace-nowrap">
                <span className="text-emerald-600 dark:text-[#10B981] font-semibold">+{reviewStats.added}</span>{" "}
                <span className="text-red-600 dark:text-[#EB5757] font-semibold">−{reviewStats.removed}</span>
                {review.accepted + review.rejected > 0 && (
                  <span className="text-slate-500 dark:text-[#8A8F98]"> · {review.accepted} accepted</span>
                )}
              </span>
            )}
          </>
        ) : (
          <span className="font-semibold text-slate-900 dark:text-[#E2E4E9] whitespace-nowrap">
            {diffEditsList.length} pending edit{diffEditsList.length === 1 ? "" : "s"}
          </span>
        )}
        {review && review.unplaced > 0 && (
          <span
            className="text-amber-700 dark:text-amber-300 whitespace-nowrap"
            title="The document was edited where these changes apply, so they cannot be shown inline."
          >
            {review.unplaced} not shown
          </span>
        )}
        <div className="flex items-center gap-1.5 ml-auto">
          <button
            type="button"
            onClick={handleRejectAllEdits}
            className="h-7 px-2.5 rounded-lg bg-red-50 hover:bg-red-100 dark:bg-[#EB5757]/10 dark:hover:bg-[#EB5757]/20 border border-red-200 dark:border-[#EB5757]/30 text-red-600 dark:text-[#EB5757] font-semibold flex items-center gap-1 transition-colors cursor-pointer whitespace-nowrap"
          >
            <X className="w-3.5 h-3.5" />
            <span>Reject all</span>
          </button>
          {!isViewer && (
            <button
              type="button"
              onClick={acceptAll}
              className="h-7 px-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-archivo font-bold flex items-center gap-1 transition-colors border border-emerald-600 shadow-sm cursor-pointer whitespace-nowrap"
            >
              <Check className="w-3.5 h-3.5 stroke-[2.5]" />
              <span>Accept all</span>
            </button>
          )}
        </div>
      </div>
    );
  };

  const handleRevertEdit = (editId: string) => {
    if (!editHistoryStoreRef.current) return;
    const entry = editHistoryStoreRef.current.revertEdit(editId);
    if (!entry) return; // Silent safety: Never throw raw exceptions or developer errors

    const file = activeFilePath || "main.tex";
    const restoredCode = entry.beforeCode[file] ?? Object.values(entry.beforeCode)[0];
    if (restoredCode === undefined) return;

    const editor = getActiveEditor();
    const model = editor?.getModel?.();
    if (editor && model) {
      applyTextToEditor(editor, monacoRef.current, restoredCode, "ai-revert");

      // Restore cursor position, selection & scroll
      if (entry.cursorState) {
        editor.setPosition({
          lineNumber: entry.cursorState.line || 1,
          column: entry.cursorState.column || 1,
        });
        editor.setScrollTop(entry.cursorState.scrollTop || 0);
        editor.revealPositionInCenterIfOutsideViewport({
          lineNumber: entry.cursorState.line || 1,
          column: entry.cursorState.column || 1,
        });
      }
    } else {
      setCode(restoredCode);
    }

    setCode(restoredCode);
    saveDocument(restoredCode, true);
    handleCompile(restoredCode);

    // Exactly one card: prefer the message that owns this history entry, and
    // fall back to an id match only when no message claims it.
    setMessages((prev) => {
      const target =
        prev.find((m) => m.historyEntryId === editId) ??
        prev.find((m) => m.id === editId);
      if (!target) return prev;
      return prev.map((m) => (m === target ? { ...m, isReverted: true } : m));
    });
  };

  const handleReapplyEdit = (editId: string) => {
    if (!editHistoryStoreRef.current) return;
    const entry = editHistoryStoreRef.current.reapplyEdit(editId);
    if (!entry) return;

    const file = activeFilePath || "main.tex";
    const reappliedCode = entry.afterCode[file] ?? Object.values(entry.afterCode)[0];
    if (reappliedCode === undefined) return;

    const editor = getActiveEditor();
    const model = editor?.getModel?.();
    if (editor && model) {
      applyTextToEditor(editor, monacoRef.current, reappliedCode, "ai-reapply");
    } else {
      setCode(reappliedCode);
    }

    setCode(reappliedCode);
    saveDocument(reappliedCode, true);
    handleCompile(reappliedCode);

    setMessages((prev) => {
      const target =
        prev.find((m) => m.historyEntryId === editId) ??
        prev.find((m) => m.id === editId);
      if (!target) return prev;
      return prev.map((m) => (m === target ? { ...m, isReverted: false } : m));
    });
  };

  const getEditLineRange = (
    originalChunk: string,
    proposedChunk: string,
    item?: AppliedEditItem,
  ): string => {
    if (!code) return "Line 1";

    // Prefer the apply contract's line numbers, and report only the *inner*
    // changed range: anchors now carry surrounding context, so the raw chunk
    // bounds would overstate what actually changed.
    if (item?.orig_start_line && item.orig_end_line !== undefined) {
      const innerStart = item.orig_start_line + (item.context_before ?? 0);
      const innerEnd = item.orig_end_line - (item.context_after ?? 0);
      if (innerEnd < innerStart) {
        return `Line ${innerStart} (Insertion)`;
      }
      return innerStart === innerEnd
        ? `Line ${innerStart}`
        : `Lines ${innerStart}–${innerEnd}`;
    }

    if (originalChunk && code.includes(originalChunk)) {
      const startIdx = code.indexOf(originalChunk);
      const startLine = code.slice(0, startIdx).split("\n").length;
      const lineCount = originalChunk.split("\n").length;
      const endLine = startLine + lineCount - 1;

      if (startLine === endLine) {
        return `Line ${startLine}`;
      }
      return `Lines ${startLine}–${endLine}`;
    }

    if (proposedChunk) {
      const endDocIndex = code.lastIndexOf("\\end{document}");
      if (endDocIndex !== -1) {
        const insertLine = code.slice(0, endDocIndex).split("\n").length;
        return `Line ${insertLine} (Insertion)`;
      }
      const lastLine = code.split("\n").length;
      return `Line ${lastLine} (Insertion)`;
    }

    return "Document Edit";
  };

  const renderMessageEditsCard = (m: ChatMessage) => {
    if (!m.edits || m.edits.length === 0) return null;
    const firstEdit = m.edits[0];
    // The first line that actually changes. An edit's chunks carry context (a
    // whole-document edit carries the whole document), so their first lines are
    // usually identical and say nothing about the change.
    const preview = (() => {
      if (!firstEdit) return { removed: "", added: "" };
      const before = firstEdit.original_chunk || "";
      const after = firstEdit.proposed_chunk || "";
      const change = before && after ? computeLineEdits(before, after)[0] : undefined;
      if (!change) return { removed: before.split("\n")[0], added: after.split("\n")[0] };
      const removedLines = before.split("\n").slice(change.startLine - 1, change.endLine - 1);
      return {
        removed: removedLines.find((l) => l.trim()) ?? removedLines[0] ?? "",
        added: change.lines.find((l) => l.trim()) ?? change.lines[0] ?? "",
      };
    })();

    return (
      <div className="mt-2.5 p-2.5 rounded-xl bg-slate-50 dark:bg-zinc-950 border border-slate-200 dark:border-zinc-800 text-xs font-mono space-y-2">
        <div className="flex items-center justify-between font-bold text-indigo-600 dark:text-indigo-400">
          <div className="flex items-center gap-1.5 text-xs">
            <span>Proposed TeX Edit ({m.edits.length})</span>
          </div>
          {m.isApplied ? (
            <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-600/20 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-500/30 font-bold flex items-center gap-1">
              <Check className="w-3 h-3" /> Applied
            </span>
          ) : (
            <span className="text-[10px] px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30 font-bold">
              Pending
            </span>
          )}
        </div>

        {firstEdit && (firstEdit.original_chunk || firstEdit.proposed_chunk) && (
          <div className="bg-white dark:bg-black/80 p-2 rounded-lg text-[10px] space-y-1 overflow-x-auto border border-slate-200 dark:border-zinc-800 font-mono max-h-28">
            {preview.removed && (
              <div className="text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40 px-1.5 py-0.5 rounded line-through border-l-2 border-rose-500 truncate">
                - {preview.removed}
              </div>
            )}
            {preview.added && (
              <div className="text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 px-1.5 py-0.5 rounded border-l-2 border-emerald-500 truncate">
                + {preview.added}
              </div>
            )}
          </div>
        )}

        {!m.isApplied ? (
          <div className="flex items-center gap-2 pt-1 font-bold">
            <button
              type="button"
              onClick={() => handleRejectAllEdits()}
              className="flex-1 h-7 rounded-lg bg-rose-50 dark:bg-rose-600/20 hover:bg-rose-100 dark:hover:bg-rose-600/30 border border-rose-200 dark:border-rose-500/40 text-rose-700 dark:text-rose-300 text-xs font-mono flex items-center justify-center gap-1 transition-colors cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
              <span>Reject</span>
            </button>
            <button
              type="button"
              onClick={() => {
                handleAcceptAllEdits(m.edits!, m.id);
                if (typeof window !== "undefined" && window.innerWidth < 768) {
                  setActiveMobileTab("code");
                }
              }}
              className="flex-1 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-mono font-bold flex items-center justify-center gap-1 transition-colors border border-indigo-700 shadow-sm shadow-indigo-500/20 cursor-pointer"
            >
              <Check className="w-3.5 h-3.5 text-white stroke-[3]" />
              <span>Accept Edit</span>
            </button>
          </div>
        ) : (
          <div className="pt-1.5 border-t border-slate-200 dark:border-zinc-800/80 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1 text-[11px] font-mono font-bold text-indigo-600 dark:text-indigo-400">
              <Check className="w-3.5 h-3.5" />
              <span>
                {m.isReverted
                  ? "Reverted"
                  : m.totalChanges && m.appliedChanges !== undefined && m.appliedChanges < m.totalChanges
                    ? `Applied ${m.appliedChanges} of ${m.totalChanges} changes`
                    : "Applied to TeX"}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {!m.isReverted ? (
                (() => {
                  const targetId = m.historyEntryId || m.id;
                  const hasHistory = editHistoryStoreRef.current?.hasEntry(targetId) ?? false;
                  return (
                    <button
                      type="button"
                      disabled={!hasHistory}
                      onClick={() => handleRevertEdit(targetId)}
                      className={`px-2 py-1 rounded-md border text-[10px] font-mono font-bold flex items-center gap-1 transition-all shadow-xs ${hasHistory
                          ? "bg-white dark:bg-zinc-900 hover:bg-slate-100 dark:hover:bg-zinc-800 text-amber-700 dark:text-amber-300 hover:text-amber-800 dark:hover:text-amber-200 border-slate-200 dark:border-zinc-800 cursor-pointer active:scale-95"
                          : "bg-slate-100 dark:bg-zinc-900 border-slate-200 dark:border-zinc-800 opacity-35 text-slate-500 dark:text-zinc-500 cursor-not-allowed"
                        }`}
                      title={hasHistory ? "Revert this AI edit" : "Edit history unavailable"}
                    >
                      <Undo2 className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                      <span>Revert</span>
                    </button>
                  );
                })()
              ) : (
                (() => {
                  const targetId = m.historyEntryId || m.id;
                  const hasHistory = editHistoryStoreRef.current?.hasEntry(targetId) ?? false;
                  return (
                    <button
                      type="button"
                      disabled={!hasHistory}
                      onClick={() => handleReapplyEdit(targetId)}
                      className={`px-2 py-1 rounded-md border text-[10px] font-mono font-bold flex items-center gap-1 transition-all shadow-xs ${hasHistory
                          ? "bg-indigo-50 dark:bg-indigo-600/20 hover:bg-indigo-100 dark:hover:bg-indigo-600/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-500/40 cursor-pointer active:scale-95"
                          : "bg-slate-100 dark:bg-zinc-900 border-slate-200 dark:border-zinc-800 opacity-35 text-slate-500 dark:text-zinc-500 cursor-not-allowed"
                        }`}
                      title={hasHistory ? "Reapply this AI edit" : "Edit history unavailable"}
                    >
                      <Redo2 className="w-3 h-3 text-indigo-600 dark:text-indigo-400" />
                      <span>Reapply</span>
                    </button>
                  );
                })()
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  const insertSymbol = (symbolInsert: string) => {
    const editor = getActiveEditor();
    if (editor) {
      editor.focus();

      const lastSel = lastSelectionRef.current;
      const lastPos = lastPositionRef.current;
      const currentSel = editor.getSelection();
      const currentPos = editor.getPosition();

      let targetRange = currentSel && !currentSel.isEmpty() ? currentSel : (lastSel && !lastSel.isEmpty() ? lastSel : null);

      if (!targetRange || (typeof targetRange.isEmpty === "function" && targetRange.isEmpty())) {
        const pos = currentPos || lastPos;
        if (pos) {
          targetRange = {
            startLineNumber: pos.lineNumber,
            startColumn: pos.column,
            endLineNumber: pos.lineNumber,
            endColumn: pos.column,
          };
        }
      }

      if (targetRange) {
        editor.executeEdits("insert-symbol", [
          {
            range: targetRange,
            text: symbolInsert,
            forceMoveMarkers: true,
          },
        ]);
        const endPos = editor.getPosition();
        if (endPos) {
          editor.setPosition(endPos);
          editor.revealPositionInCenterIfOutsideViewport(endPos);
        }
        handleCodeChange(editor.getValue());
      } else {
        const newText = code ? `${code}\n${symbolInsert}` : symbolInsert;
        handleCodeChange(newText);
      }
    } else {
      const newText = code ? `${code}\n${symbolInsert}` : symbolInsert;
      handleCodeChange(newText);
    }
  };

  return (
    <div className="ob-app fixed inset-0 flex h-dvh w-full max-w-full flex-col overflow-hidden bg-ob-bg text-ob-text select-none">
      {/* Guest Session Notification Banner */}
      {isGuestMode && (
        <div className="flex shrink-0 select-none flex-wrap items-center justify-between gap-2 border-b border-ob-line bg-ob-raised px-3 py-2 text-xs sm:px-4">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-amber-500" />
            <span className="font-mono text-[11px] text-amber-500">
              Guest session
            </span>
            <span className="font-mono text-xs text-ob-text-2">
              Expires in: <strong className="font-medium text-ob-text">{guestTimeLeft || "24:00:00"}</strong>
            </span>
            <span className="hidden text-xs text-ob-muted md:inline">
              · Read-only preview. Sign up to save this project permanently.
            </span>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href={`/register?redirect=${encodeURIComponent(`/editor/${projectId || ""}`)}`}
              className="flex h-7 items-center rounded-md bg-ob-accent px-2.5 text-xs font-medium text-ob-on-accent transition-colors hover:bg-ob-accent-hover"
            >
              Save permanently
            </Link>
            <Link
              href={`/login?redirect=${encodeURIComponent(`/editor/${projectId || ""}`)}`}
              className="flex h-7 items-center rounded-md border border-ob-line bg-ob-card px-2.5 text-xs text-ob-text transition-colors hover:bg-ob-raised"
            >
              Sign in
            </Link>
          </div>
        </div>
      )}

      {/* Main Top Navigation Header */}
      <header className="flex h-12 shrink-0 select-none items-center justify-between gap-2 border-b border-ob-line bg-ob-deep px-3 sm:px-4 text-ob-text">
        {/* Left Column: Return to Dashboard & Project Title */}
        <div className="flex min-w-0 max-w-[48%] shrink items-center gap-2 sm:gap-3 md:max-w-none">
          <Link
            href="/dashboard"
            className="group flex shrink-0 cursor-pointer items-center gap-2"
            title="Return to dashboard"
          >
            <div className="flex size-7 items-center justify-center rounded-lg border border-ob-line bg-ob-card text-ob-muted transition-colors group-hover:bg-ob-raised group-hover:text-ob-text">
              <ArrowLeft className="size-3.5 transition-transform group-hover:-translate-x-0.5" />
            </div>
            <OverBranchLogo
              size="sm"
              variant="icon"
              colored={false}
              animated={false}
              iconClassName="[&_svg]:text-ob-accent!"
            />
          </Link>

          <div className="hidden h-4 w-px bg-ob-line sm:block" />

          <div className="min-w-0 truncate">
            <h1 className="truncate text-xs font-medium text-ob-text sm:text-sm">
              {projectDetail?.name || (projectId ? `${projectId}.tex` : "main.tex")}
            </h1>
            <p className="hidden font-mono text-[10px] text-ob-muted truncate xs:block">
              {activeFilePath} · {projectDetail?.template && projectDetail.template !== "None" ? projectDetail.template : "LaTeX"}
            </p>
          </div>
        </div>

        {/* Center Column: Layout View Switcher & Compile Action (Desktop >= xl) */}
        <div className="hidden items-center gap-2 xl:flex shrink-0">
          {/* View Toggle */}
          <div className="flex items-center rounded-lg border border-ob-line bg-ob-raised p-0.5 font-mono text-xs">
            <button
              onClick={() => setPdfOpen(false)}
              className={`flex h-7 cursor-pointer items-center justify-center rounded-md px-2.5 transition-colors ${
                !pdfOpen
                  ? "bg-ob-card font-medium text-ob-text"
                  : "text-ob-muted hover:text-ob-text"
              }`}
              title="Code editor"
            >
              Code
            </button>
            <button
              onClick={() => setPdfOpen(true)}
              className={`flex h-7 cursor-pointer items-center justify-center rounded-md px-2.5 transition-colors ${
                pdfOpen
                  ? "bg-ob-card font-medium text-ob-text"
                  : "text-ob-muted hover:text-ob-text"
              }`}
              title="Split view (Code + PDF)"
            >
              Split
            </button>
          </div>

          {/* Compile, with the TeX engine fused to it */}
          <CompileSplitButton
            onCompile={() => handleCompile()}
            isCompiling={isCompiling}
            busy={compileBusy}
            engine={engine}
            onEngineChange={setEngine}
          />
        </div>

        {/* Compact & Mobile Header Actions (< xl) */}
        <div className="flex items-center gap-1.5 sm:gap-2 xl:hidden shrink-0">
          <div className="hidden items-center rounded-lg border border-ob-line bg-ob-raised p-0.5 font-mono text-xs sm:flex">
            <button
              onClick={() => setActiveMobileTab("code")}
              className={`flex h-7 cursor-pointer items-center justify-center rounded-md px-2 transition-colors lg:px-2.5 ${
                activeMobileTab === "code"
                  ? "bg-ob-card font-medium text-ob-text"
                  : "text-ob-muted hover:text-ob-text"
              }`}
              title="Code editor"
            >
              Code
            </button>
            <button
              onClick={() => setActiveMobileTab("split")}
              className={`flex h-7 cursor-pointer items-center justify-center rounded-md px-2 transition-colors lg:px-2.5 ${
                activeMobileTab === "split"
                  ? "bg-ob-card font-medium text-ob-text"
                  : "text-ob-muted hover:text-ob-text"
              }`}
              title="Split view (Code + PDF)"
            >
              Split
            </button>
          </div>

          <CompileSplitButton
            onCompile={() => handleCompile()}
            isCompiling={isCompiling}
            busy={compileBusy}
            engine={engine}
            onEngineChange={setEngine}
            compact
          />
        </div>

        {/* Right Column: Status & Action Toggles */}
        <div className="flex shrink-0 items-center gap-1 sm:gap-1.5 lg:gap-2">
          {/* Save Status */}
          <span className="hidden h-8 shrink-0 items-center gap-1.5 rounded-lg border border-ob-line bg-ob-card px-2.5 font-mono text-xs text-ob-muted xl:flex">
            {collabBound ? (
              <>
                <span
                  className={`size-1.5 rounded-full ${
                    collab.status === "connected"
                      ? "bg-ob-positive"
                      : "bg-ob-warn animate-pulse"
                  }`}
                />
                <span className="hidden lg:inline text-ob-muted">
                  {collab.status === "connected"
                    ? collab.savedAt
                      ? "Synced"
                      : "Live"
                    : "Local only"}
                </span>
              </>
            ) : null}
            {!collabBound && saveStatus === "saved" && (
              <>
                <span className="size-1.5 rounded-full bg-ob-positive" />
                <span className="hidden lg:inline text-ob-muted">Saved</span>
              </>
            )}
            {!collabBound && saveStatus === "saving" && (
              <>
                <RotateCw className="size-3 animate-spin text-ob-warn" />
                <span className="hidden lg:inline text-ob-warn">Saving\u2026</span>
              </>
            )}
            {!collabBound && saveStatus === "unsaved" && (
              <>
                <span className="size-1.5 rounded-full bg-ob-warn animate-pulse" />
                <span className="hidden lg:inline text-ob-warn">Unsaved</span>
              </>
            )}
          </span>

          {/* Files Panel Toggle */}
          <button
            onClick={handleToggleFiles}
            className={`hidden h-8 cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 font-mono text-xs transition-colors xl:flex shrink-0 ${
              filesOpen
                ? "border-ob-text/15 bg-ob-raised font-medium text-ob-text"
                : "border-ob-line bg-ob-card text-ob-text-2 hover:bg-ob-raised hover:text-ob-text"
            }`}
            title={filesOpen ? "Hide files" : "Show files"}
          >
            <FolderGit2 className="size-3.5" />
            <span className="hidden xl:inline">Files</span>
          </button>

          {/* AI Agent Toggle Button */}
          <button
            onClick={toggleAi}
            className={`hidden h-8 cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 font-mono text-xs transition-colors xl:flex shrink-0 ${
              aiOpen
                ? "border-ob-text/15 bg-ob-raised font-medium text-ob-text"
                : "border-ob-line bg-ob-card text-ob-text-2 hover:bg-ob-raised hover:text-ob-text"
            }`}
            title="Toggle AI Agent (Cmd+L / Ctrl+L)"
          >
            <Bot className="size-3.5" />
            <span className="hidden xl:inline">Agent</span>
          </button>

          {/* Find & replace — mobile only */}
          <button
            onClick={() => setSearchOpen((v) => !v)}
            className={`flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border transition-colors xl:hidden ${
              searchOpen
                ? "border-ob-text/15 bg-ob-raised text-ob-text"
                : "border-ob-line bg-ob-card text-ob-muted hover:bg-ob-raised hover:text-ob-text"
            }`}
            title="Find & replace"
            aria-label="Find and replace"
          >
            <Search className="size-3.5" />
          </button>

          {/* Theme Toggle Button */}
          <button
            onClick={handleToggleTheme}
            className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-ob-line bg-ob-card text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
            title={isDark ? "Switch to Light theme" : "Switch to Dark theme"}
            aria-label="Toggle theme"
          >
            {themeMounted ? (
              isDark ? (
                <Sun className="size-3.5 text-amber-500" />
              ) : (
                <Moon className="size-3.5 text-ob-text" />
              )
            ) : (
              <div className="size-3.5 rounded-full border border-current opacity-30" />
            )}
          </button>

          {/* Settings Button */}
          <button
            onClick={() => setIsApiSettingsOpen(true)}
            className="hidden size-8 cursor-pointer items-center justify-center rounded-lg border border-ob-line bg-ob-card text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text sm:flex"
            title="API keys and settings"
          >
            <Settings2 className="size-3.5" />
          </button>

          {collab.enabled && (
            <CollabPresenceBar
              status={collab.status}
              peers={collab.peers}
              selfName={collabUser?.name || collabUser?.email || "You"}
              selfColor={collab.selfColor}
              selfImage={(collabUser as any)?.image ?? null}
              activeFilePath={activeFilePath}
              fatalError={collab.fatalError}
              onRetry={collab.reconnect}
            />
          )}

          <CollaboratorAvatars projectId={projectId} />
        </div>
      </header>

      {/* Desktop Main Split Workspace */}
      <div className="hidden xl:flex flex-1 overflow-hidden relative min-h-0 min-w-0">
        <div className="w-full h-full flex overflow-hidden min-h-0 min-w-0">
          {/* Panel 1 (Far Left): Project Files & Asset Panel */}
          <ProjectFilesPanel
            projectId={projectId || "proj-1"}
            activeFilePath={activeFilePath}
            isOpen={filesOpen}
            onClose={() => setFilesOpen(false)}
            onSelectFile={(filePath) => handleSelectFile(filePath)}
            onInsertLatexSnippet={(snippet) => insertSymbol(snippet)}
            refreshTrigger={filesRefreshTrigger}
            onImportPdf={() => {
              setPdfImportJobId(null);
              setPdfImportOpen(true);
            }}
          />

          {/* Panel 2 (Middle Left): Monaco Code Editor */}
          <div className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden border-r border-ob-line bg-ob-bg">
            {/* Editor Tab Bar */}
            <div className="flex h-9 shrink-0 select-none items-center justify-between border-b border-ob-line bg-ob-deep px-3 font-mono text-xs text-ob-text">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5 font-mono text-xs text-ob-text">
                  <FileCode2 className="size-3.5 text-ob-accent" />
                  <span>{activeFilePath}</span>
                </span>
              </div>

              {/* Search / Undo / Redo Actions */}
              <div className="flex items-center gap-0.5">
                <button
                  type="button"
                  onClick={() => setSearchOpen((v) => !v)}
                  className={`flex size-6 cursor-pointer items-center justify-center rounded transition-colors ${
                    searchOpen
                      ? "bg-ob-raised text-ob-text"
                      : "text-ob-muted hover:bg-ob-raised hover:text-ob-text"
                  }`}
                  title="Find & replace (Ctrl+F / Cmd+F)"
                >
                  <Search className="size-3" />
                </button>
                <button
                  type="button"
                  onClick={handleUndo}
                  className="flex size-6 cursor-pointer items-center justify-center rounded text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
                  title="Undo (Ctrl+Z / Cmd+Z)"
                >
                  <Undo2 className="size-3" />
                </button>
                <button
                  type="button"
                  onClick={handleRedo}
                  className="flex size-6 cursor-pointer items-center justify-center rounded text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
                  title="Redo (Ctrl+Y / Cmd+Shift+Z)"
                >
                  <Redo2 className="size-3" />
                </button>
              </div>
            </div>

            {/* Monaco Editor Container */}
            <div className="flex-1 overflow-hidden relative">
              <Editor
                height="100%"
                defaultLanguage={activeFilePath.endsWith(".bib") ? "bibtex" : "latex"}
                theme={monacoTheme}
                // Once the Yjs binding owns the model, React must stop setting
                // `value`: @monaco-editor/react implements a value change as a
                // full-model-range replace, which under a CRDT means "delete
                // the whole document and insert a new one" — wiping concurrent
                // edits and resetting every remote cursor.
                value={collabBound ? undefined : code}
                defaultValue={code}
                beforeMount={(monaco) => setupDefaultLatexSyntaxAndEmeraldTheme(monaco)}
                onMount={(editor, monaco) => handleEditorMount(editor, monaco, true)}
                onChange={handleCodeChange}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  automaticLayout: true,
                  contextmenu: true,
                  selectOnLineNumbers: true,
                  cursorBlinking: "blink",
                  cursorSmoothCaretAnimation: "on",
                  cursorStyle: "line",
                  cursorWidth: 2,
                  roundedSelection: true,
                  copyWithSyntaxHighlighting: false,
                  readOnly: isViewer,
                }}
              />

              <EditorSearchBar
                editor={desktopEditorRef.current}
                monaco={monacoRef.current}
                open={searchOpen}
                onClose={() => setSearchOpen(false)}
                readOnly={isViewer}
                onDocumentChange={handleCodeChange}
              />

              {/* Review bar for the pending AI proposal (changes are drawn inline in the editor) */}
              {renderReviewBar("editor")}
            </div>

            {/* Bottom Status Bar */}
            <div className="h-6 px-2.5 sm:px-3 border-t border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#141519] flex items-center justify-between text-[10px] font-mono text-slate-500 dark:text-[#9E9E9E] shrink-0 select-none overflow-hidden min-w-0">
              <div className="flex items-center gap-2 sm:gap-3 truncate min-w-0">
                <span className="flex items-center gap-1 text-slate-800 dark:text-[#E2E4E9] truncate min-w-0">
                  <FileCode2 className="w-3 h-3 text-emerald-600 dark:text-[#10B981] shrink-0" />
                  <span className="truncate">{activeFilePath}</span>
                </span>
                <span className="text-slate-300 dark:text-[#282A30] hidden 2xl:inline">|</span>
                <span className="hidden 2xl:inline">SyncTeX Active</span>
              </div>
              <div className="flex items-center gap-2 sm:gap-3 shrink-0">
                <span className="hidden xl:inline">UTF-8</span>
                <span>{activeFilePath.endsWith(".bib") ? "BibTeX" : "LaTeX"}</span>
                <span className="text-slate-300 dark:text-[#282A30] hidden lg:inline">|</span>
                <a
                  href="https://upzare.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hidden lg:inline-flex items-center gap-1 hover:underline text-slate-700 dark:text-[#E2E4E9] font-bold group"
                  title="Powered By UPZARE Technologies Private Limited"
                >
                  <span className="text-slate-400 dark:text-[#9E9E9E] font-normal">Powered By</span>
                  <img
                    src="https://cdn.upzare.com/assets/logo.png"
                    alt="UPZARE Technologies Private Limited"
                    className="h-3 w-auto object-contain"
                  />
                  <span className="group-hover:text-emerald-600 dark:group-hover:text-emerald-400">UPZARE</span>
                </a>
              </div>
            </div>
          </div>

          {/* Panel 3 (Middle Right): PDF Viewer */}
          <div
            className={`h-full bg-slate-100 dark:bg-[#0E0F12] transition-all duration-300 ease-in-out overflow-hidden flex flex-col min-w-0 max-w-full ${pdfOpen ? "flex-1 min-w-0 border-r border-slate-200 dark:border-[#282A30]" : "w-0 opacity-0 pointer-events-none border-r-0"
              }`}
          >
            <div className="flex-1 h-full min-w-0 max-w-full w-full flex flex-col overflow-hidden">
              <PDFViewer
                ref={pdfViewerRef}
                pdfBase64={pdfBase64}
                isCompiling={isCompiling}
                onRecompile={() => handleCompile()}
                onAskAiToFix={handleAskAiToFix}
                errorLog={errorLog}
                projectId={projectId}
                projectName={projectDetail?.name}
                viewMemoryRef={pdfViewMemoryRef}
                onReverseSync={handleReverseSyncJump}
                onTextSelected={handlePdfTextSelected}
                onEnterPresentation={() => setIsPresentationMode(true)}
              />
            </div>
          </div>

          {/* Panel 4 (Far Right): AI Assistant Sidebar */}
          <div
            className={`flex h-full shrink-0 flex-col overflow-hidden border-l border-ob-line bg-ob-deep text-ob-text transition-all duration-200 ${
              aiOpen ? "w-[300px] opacity-100 lg:w-[320px] xl:w-[350px]" : "pointer-events-none w-0 border-l-0 opacity-0"
            }`}
          >
            <div className="flex h-full w-full min-w-0 flex-col justify-between overflow-hidden p-2.5 text-xs sm:p-3">
              <div className="flex flex-1 flex-col gap-3 overflow-hidden">
                <div className="flex shrink-0 select-none flex-col gap-2 border-b border-ob-line pb-2.5">
                  <div className="flex items-center justify-between gap-1.5">
                    <div className="flex shrink-0 items-center gap-1.5">
                      {/* Chat Options Dropdown */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            disabled={isAgentThinking}
                            className="flex size-7 cursor-pointer items-center justify-center rounded-lg border border-ob-line bg-ob-card text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text disabled:opacity-50"
                            title="Chat options"
                          >
                            <Bot className="size-4" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="min-w-[140px] border-ob-line bg-ob-card p-1 font-mono text-xs text-ob-text z-[99999]">
                          <DropdownMenuItem
                            onClick={handleNewChat}
                            disabled={isAgentThinking}
                            className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-ob-text transition-colors hover:bg-ob-raised"
                          >
                            <PlusCircle className="size-3.5 text-ob-accent" />
                            <span>New chat</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={handleClearChat}
                            disabled={isAgentThinking || (messages.length === 0 && chatAttachments.attachments.length === 0)}
                            className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-ob-negative transition-colors hover:bg-ob-raised"
                          >
                            <Trash2 className="size-3.5" />
                            <span>Clear chat</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>

                      <ChatModeToggle mode={chatMode} onModeChange={setChatMode} disabled={isAgentThinking} />
                    </div>

                    <div className="flex min-w-0 items-center gap-1.5">
                      <ModelSelector
                        activeModelName={activeModelName}
                        onSelectModel={setActiveModelName}
                        availableModels={availableModels}
                        disabled={isAgentThinking}
                      />
                    </div>
                  </div>
                </div>

                {/* Chat Message Stream */}
                <div className="flex-1 space-y-3 overflow-y-auto pr-1 font-mono">
                  {messages.map((m) => (
                    <div
                      key={m.id}
                      className={`group flex flex-col gap-1.5 rounded-xl border border-ob-line p-3 ${
                        m.sender === "user"
                          ? "ml-4 bg-ob-card text-ob-text font-medium"
                          : "mr-4 bg-ob-raised text-ob-text"
                      }`}
                    >
                      <div className="flex items-center justify-between font-mono text-[10px] text-ob-muted">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-ob-text">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                          {m.mode && (
                            <span className="rounded border border-ob-line bg-ob-deep px-1.5 py-0.2 font-mono text-[9px] text-ob-muted">
                              {m.mode}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-0.5">
                          <CopyButton
                            text={m.text}
                            title={m.sender === "user" ? "Copy prompt" : "Copy reply"}
                            className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                          />
                          <span>{m.time}</span>
                        </div>
                      </div>
                      {m.sender === "assistant" ? (
                        <ChatMessageContent text={m.text} />
                      ) : (
                        <p className="break-words whitespace-pre-wrap text-xs leading-relaxed text-ob-text">{m.text}</p>
                      )}
                      {renderMessageEditsCard(m)}
                    </div>
                  ))}
                  {isAgentThinking && (
                    <AgentReasoningWindow
                      steps={agentProgressSteps}
                      onStop={handleStopAgentResponse}
                      compact
                    />
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* Review bar for the pending AI proposal */}
                {renderReviewBar("sidebar")}

                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  multiple
                  accept={ATTACHMENT_ACCEPT}
                  aria-label="Attach files to the chat"
                  className="hidden"
                />

                <ChatAttachments
                  attachments={chatAttachments.attachments}
                  maxFiles={chatAttachments.maxFiles}
                  onRemove={chatAttachments.remove}
                  disabled={isAgentThinking}
                />

                <MentionChips mentions={mentions} onRemove={removeMentionById} disabled={isAgentThinking} />

                {/* Chat Input Form */}
                <form onSubmit={handleSendPrompt} className="relative flex shrink-0 items-end gap-2 border-t border-ob-line pt-2.5 font-mono">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isAgentThinking}
                    className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-ob-line bg-ob-card text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text disabled:opacity-50"
                    title={`Attach files (up to ${chatAttachments.maxFiles})`}
                  >
                    <Paperclip className="size-4" />
                  </button>

                  <div className="relative flex-1 font-mono">
                    <textarea
                      ref={setDesktopChatTextarea}
                      id="ai-chat-input"
                      rows={1}
                      placeholder={chatMode === "ask" ? "Ask about LaTeX or your document" : "Ask agent to edit LaTeX"}
                      value={chatInput}
                      disabled={isAgentThinking}
                      onChange={(e) => {
                        setChatInput(e.target.value);
                        e.target.style.height = "auto";
                        e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
                      }}
                      onKeyDown={handleChatKeyDown}
                      className="max-h-44 min-h-[36px] w-full resize-none overflow-y-auto rounded-lg border border-ob-line bg-ob-raised px-3 py-2 font-mono text-xs leading-relaxed text-ob-text placeholder:text-ob-muted outline-none transition-colors focus:border-ob-text/20 disabled:opacity-50"
                    />
                    <FileMentionPopover
                      textarea={desktopChatTextarea}
                      projectId={projectId || "proj-1"}
                      chatInput={chatInput}
                      onInsertMention={handleInsertMention}
                      onOpenChange={setDesktopMentionOpen}
                    />
                  </div>

                  {isAgentThinking ? (
                    <Button
                      type="button"
                      onClick={handleStopAgentResponse}
                      size="sm"
                      variant="ob-danger"
                      className="h-9 shrink-0 cursor-pointer text-xs"
                    >
                      <Square className="size-3.5 fill-current" />
                      <span>Stop</span>
                    </Button>
                  ) : (
                    <Button
                      type="submit"
                      disabled={(!chatInput.trim() && !hasAttachments) || isAgentThinking}
                      size="sm"
                      variant="ob-primary"
                      className="size-9 shrink-0 cursor-pointer p-0"
                    >
                      <Send className="size-3.5" />
                    </Button>
                  )}
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Compact & Mobile Viewports */}
      <div className="flex xl:hidden flex-1 min-h-0 overflow-hidden relative">
        <div className={`flex-1 flex flex-col bg-white dark:bg-[#0E0F12] overflow-hidden relative min-h-0 ${activeMobileTab === "files" ? "flex" : "hidden"}`}>
          <ProjectFilesPanel
            projectId={projectId || "proj-1"}
            activeFilePath={activeFilePath}
            isOpen={true}
            onClose={() => setActiveMobileTab("code")}
            onSelectFile={(filePath) => {
              handleSelectFile(filePath);
              setActiveMobileTab("code");
            }}
            onInsertLatexSnippet={(snippet) => insertSymbol(snippet)}
            refreshTrigger={filesRefreshTrigger}
            onImportPdf={() => {
              setPdfImportJobId(null);
              setPdfImportOpen(true);
            }}
          />
        </div>

        {/* Compact & Mobile: Code Editor View & Split View */}
        <div className={`flex-1 flex overflow-hidden relative min-h-0 ${activeMobileTab === "code" || activeMobileTab === "split" ? "flex" : "hidden"}`}>
          {/* Main Left: Monaco Code Editor */}
          <div className="flex-1 min-w-0 bg-white dark:bg-[#0E0F12] flex flex-col h-full overflow-hidden relative min-h-0">
            <div className="flex-1 min-h-0 overflow-hidden relative">
              <EditorErrorBoundary>
                <Editor
                  height="100%"
                  defaultLanguage={activeFilePath.endsWith(".bib") ? "bibtex" : "latex"}
                  theme={monacoTheme}
                  value={collabBound ? undefined : code}
                  defaultValue={code}
                  beforeMount={(monaco) => setupDefaultLatexSyntaxAndEmeraldTheme(monaco)}
                  onMount={(editor, monaco) => handleEditorMount(editor, monaco, false)}
                  onChange={handleCodeChange}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    lineNumbers: "on",
                    scrollBeyondLastLine: false,
                    wordWrap: "on",
                    automaticLayout: true,
                    contextmenu: false,
                    selectOnLineNumbers: true,
                    cursorBlinking: "blink",
                    cursorStyle: "line",
                    cursorWidth: 2,
                    roundedSelection: true,
                    copyWithSyntaxHighlighting: false,
                    readOnly: isViewer,
                  }}
                />
              </EditorErrorBoundary>

              <MobileEditorAssist
                editor={mobileEditorRef.current}
                monaco={monacoRef.current}
                readOnly={isViewer}
                active={activeMobileTab === "code" || activeMobileTab === "split"}
                onOpenSearch={() => setSearchOpen(true)}
                onDocumentChange={handleCodeChange}
                onUndo={handleUndo}
                onRedo={handleRedo}
                onMention={addMentionFromSelection}
              />

              <EditorSearchBar
                editor={mobileEditorRef.current}
                monaco={monacoRef.current}
                open={searchOpen}
                onClose={() => setSearchOpen(false)}
                readOnly={isViewer}
                onDocumentChange={handleCodeChange}
                compact
              />
              {renderReviewBar("mobile")}
            </div>
          </div>

          {/* Side Right: In Split Mode, render PDF Viewer simultaneously */}
          {activeMobileTab === "split" && (
            <div className="flex-1 min-w-0 bg-slate-100 dark:bg-[#0E0F12] flex flex-col h-full border-l border-slate-200 dark:border-[#282A30] overflow-hidden relative min-h-0">
              <PDFViewer
                ref={pdfViewerRef}
                pdfBase64={pdfBase64}
                isCompiling={isCompiling}
                onRecompile={() => handleCompile()}
                onAskAiToFix={handleAskAiToFix}
                errorLog={errorLog}
                projectId={projectId}
                projectName={projectDetail?.name}
                viewMemoryRef={pdfViewMemoryRef}
                onReverseSync={(file, line, col) => {
                  handleReverseSyncJump(file, line, col);
                }}
                onTextSelected={(text, anchor) => {
                  handlePdfTextSelected(text, anchor);
                }}
                onEnterPresentation={() => setIsPresentationMode(true)}
              />
            </div>
          )}
        </div>

        <div className={`flex-1 flex flex-col bg-slate-100 dark:bg-[#0E0F12] overflow-hidden min-h-0 ${activeMobileTab === "pdf" ? "flex" : "hidden"}`}>
          <PDFViewer
            ref={pdfViewerRef}
            pdfBase64={pdfBase64}
            isCompiling={isCompiling}
            onRecompile={() => handleCompile()}
            onAskAiToFix={handleAskAiToFix}
            errorLog={errorLog}
            projectId={projectId}
            projectName={projectDetail?.name}
            viewMemoryRef={pdfViewMemoryRef}
            onReverseSync={(file, line, col) => {
              setActiveMobileTab("code");
              handleReverseSyncJump(file, line, col);
            }}
            onTextSelected={(text, anchor) => {
              handlePdfTextSelected(text, anchor);
            }}
            onEnterPresentation={() => setIsPresentationMode(true)}
          />
        </div>

        <div className={`flex-1 flex-col overflow-hidden relative min-h-0 p-3 space-y-3 bg-ob-deep text-ob-text ${activeMobileTab === "ai" ? "flex" : "hidden"}`}>
          <div className="flex shrink-0 select-none flex-col gap-2 border-b border-ob-line pb-2.5">
            <div className="flex items-center justify-between gap-1.5">
              <div className="flex shrink-0 items-center gap-1.5">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      disabled={isAgentThinking}
                      className="flex size-7 cursor-pointer items-center justify-center rounded-lg border border-ob-line bg-ob-card text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text disabled:opacity-50"
                      title="Chat options"
                    >
                      <Bot className="size-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="min-w-[140px] border-ob-line bg-ob-card p-1 font-mono text-xs text-ob-text z-[99999]">
                    <DropdownMenuItem
                      onClick={handleNewChat}
                      disabled={isAgentThinking}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-ob-text transition-colors hover:bg-ob-raised"
                    >
                      <PlusCircle className="size-3.5 text-ob-accent" />
                      <span>New chat</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={handleClearChat}
                      disabled={isAgentThinking || (messages.length === 0 && chatAttachments.attachments.length === 0)}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-ob-negative transition-colors hover:bg-ob-raised"
                    >
                      <Trash2 className="size-3.5" />
                      <span>Clear chat</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                <ChatModeToggle mode={chatMode} onModeChange={setChatMode} disabled={isAgentThinking} />
              </div>
              <div className="flex min-w-0 items-center gap-1.5">
                <ModelSelector
                  activeModelName={activeModelName}
                  onSelectModel={setActiveModelName}
                  availableModels={availableModels}
                  disabled={isAgentThinking}
                />
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1 font-mono text-xs">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex flex-col gap-1.5 rounded-xl border border-ob-line p-3 ${
                  m.sender === "user"
                    ? "ml-4 bg-ob-card text-ob-text font-medium"
                    : "mr-4 bg-ob-raised text-ob-text"
                }`}
              >
                <div className="flex items-center justify-between font-mono text-[10px] text-ob-muted">
                  <span className="font-medium text-ob-text">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                  <div className="flex items-center gap-0.5">
                    <CopyButton
                      text={m.text}
                      title={m.sender === "user" ? "Copy prompt" : "Copy reply"}
                    />
                    <span>{m.time}</span>
                  </div>
                </div>
                {m.sender === "assistant" ? (
                  <ChatMessageContent text={m.text} />
                ) : (
                  <p className="break-words whitespace-pre-wrap text-xs leading-relaxed text-ob-text">{m.text}</p>
                )}
                {renderMessageEditsCard(m)}
              </div>
            ))}
            {isAgentThinking && (
              <AgentReasoningWindow
                steps={agentProgressSteps}
                onStop={handleStopAgentResponse}
              />
            )}
            <div ref={mobileChatEndRef} />
          </div>

          <ChatAttachments
            attachments={chatAttachments.attachments}
            maxFiles={chatAttachments.maxFiles}
            onRemove={chatAttachments.remove}
            disabled={isAgentThinking}
          />

          <MentionChips mentions={mentions} onRemove={removeMentionById} disabled={isAgentThinking} />

          <form onSubmit={handleSendPrompt} className="relative flex shrink-0 items-end gap-2 border-t border-ob-line pt-2.5 font-mono">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isAgentThinking}
              className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-ob-line bg-ob-card text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text disabled:opacity-50"
              title={`Attach files (up to ${chatAttachments.maxFiles})`}
            >
              <Paperclip className="size-4" />
            </button>

            <div className="relative min-w-0 flex-1">
              <textarea
                ref={setMobileChatTextarea}
                id="ai-chat-input-2"
                rows={1}
                placeholder={chatMode === "ask"
                  ? (softKeyboardOnly ? "Ask a question" : "Ask a question")
                  : (softKeyboardOnly ? "Ask agent to edit LaTeX" : "Ask agent to edit LaTeX")}
                value={chatInput}
                disabled={isAgentThinking}
                onChange={(e) => {
                  setChatInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
                }}
                onKeyDown={handleChatKeyDown}
                className="max-h-40 min-h-[36px] w-full resize-none overflow-y-auto rounded-lg border border-ob-line bg-ob-raised px-3 py-2 font-mono text-xs leading-relaxed text-ob-text placeholder:text-ob-muted outline-none transition-colors focus:border-ob-text/20 disabled:opacity-50"
              />
              <FileMentionPopover
                textarea={mobileChatTextarea}
                projectId={projectId || "proj-1"}
                chatInput={chatInput}
                onInsertMention={handleInsertMention}
                onOpenChange={setMobileMentionOpen}
              />
            </div>

            {isAgentThinking ? (
              <Button
                type="button"
                onClick={handleStopAgentResponse}
                size="sm"
                variant="ob-danger"
                className="h-9 shrink-0 cursor-pointer text-xs"
              >
                <Square className="size-3.5 fill-current" />
                <span>Stop</span>
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={(!chatInput.trim() && !hasAttachments) || isAgentThinking}
                size="sm"
                variant="ob-primary"
                className="size-9 shrink-0 cursor-pointer p-0"
              >
                <Send className="size-3.5" />
              </Button>
            )}
          </form>
        </div>
      </div>

      {/* Bottom Navigation for Compact & Mobile View */}
      <nav className="shrink-0 select-none border-t border-ob-line bg-ob-deep pb-[env(safe-area-inset-bottom,0px)] xl:hidden">
        <div className="flex h-12 w-full items-center justify-around font-mono">
          <button
            onClick={() => setActiveMobileTab("files")}
            className={`flex h-full flex-1 cursor-pointer flex-col items-center justify-center gap-0.5 text-xs transition-colors ${
              activeMobileTab === "files" ? "font-medium text-ob-accent" : "text-ob-muted hover:text-ob-text"
            }`}
          >
            <FolderGit2 className="size-4" />
            <span className="text-[10px]">Files</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("code")}
            className={`flex h-full flex-1 cursor-pointer flex-col items-center justify-center gap-0.5 text-xs transition-colors ${
              activeMobileTab === "code" ? "font-medium text-ob-accent" : "text-ob-muted hover:text-ob-text"
            }`}
          >
            <FileCode2 className="size-4" />
            <span className="text-[10px]">Code</span>
          </button>

          {/* Split view tab: enabled on screens >= 540px */}
          <button
            onClick={() => setActiveMobileTab("split")}
            className={`hidden h-full flex-1 cursor-pointer flex-col items-center justify-center gap-0.5 text-xs transition-colors sm:flex ${
              activeMobileTab === "split" ? "font-medium text-ob-accent" : "text-ob-muted hover:text-ob-text"
            }`}
          >
            <Columns2 className="size-4" />
            <span className="text-[10px]">Split</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("pdf")}
            className={`flex h-full flex-1 cursor-pointer flex-col items-center justify-center gap-0.5 text-xs transition-colors ${
              activeMobileTab === "pdf" ? "font-medium text-ob-accent" : "text-ob-muted hover:text-ob-text"
            }`}
          >
            <Eye className="size-4" />
            <span className="text-[10px]">PDF</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("ai")}
            className={`flex h-full flex-1 cursor-pointer flex-col items-center justify-center gap-0.5 text-xs transition-colors ${
              activeMobileTab === "ai" ? "font-medium text-ob-accent" : "text-ob-muted hover:text-ob-text"
            }`}
          >
            <Bot className="size-4" />
            <span className="text-[10px]">Agent</span>
          </button>
        </div>
      </nav>

      {/* Fullscreen Presentation Mode View */}
      {isPresentationMode && (
        <PresentationView
          blobUrl={pdfViewerRef.current?.getBlobUrl() || null}
          onExit={() => setIsPresentationMode(false)}
        />
      )}

      {isApiSettingsOpen && (
        <ApiSettingsModal onClose={() => setIsApiSettingsOpen(false)} />
      )}

      <ImportPdfDialog
        open={pdfImportOpen}
        onOpenChange={(open) => {
          setPdfImportOpen(open);
          if (!open) setPdfImportJobId(null);
        }}
        projectId={projectId || "proj-1"}
        attachJobId={pdfImportJobId}
        onCompleted={({ texPath }) => {
          // Drop stale cached copies so the editor shows the converted file from the server
          fileContentCacheRef.current.delete(texPath);
          try {
            localStorage.removeItem(`overbranch_code_${projectId || "default"}_${texPath}`);
          } catch (_) {}
          setFilesRefreshTrigger((prev) => prev + 1);
          if (texPath === activeFilePath) setFileReloadNonce((n) => n + 1);
          else setActiveFilePath(texPath);
          toast.success(`PDF imported into ${texPath}`, { icon: "📄" });
        }}
      />
    </div>
  );
}
