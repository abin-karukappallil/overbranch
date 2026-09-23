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
  Copy,
  ClipboardPaste,
  CheckSquare,
  MousePointerClick,
  Paperclip,
  Square,
  FileText,
  File,
  AlertCircle,
  Palette,
  Zap,
  ChevronDown,
  PlusCircle,
  Trash2,
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
import { PDFViewer, type PDFViewerRefHandle } from "@/components/editor/PDFViewer";
import { PresentationView } from "@/components/editor/PresentationView";
import { ModelSelector, type ProviderGroup } from "@/components/editor/ModelSelector";
import type { SyncTeXForwardResult, SyncState } from "@/types/sync";
import { ProjectFilesPanel } from "@/components/editor/ProjectFilesPanel";
import { InlineDiffEditor, EditItem } from "@/components/editor/InlineDiffEditor";
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
import { trpc, trpcClient } from "@/trpc/client";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { ChatModeToggle, type ChatMode } from "@/components/editor/ChatModeToggle";
import { EditHistoryStore, type EditHistory } from "@/lib/EditHistoryStore";
import { ChatMessageContent } from "@/components/editor/ChatMessageContent";
import { AgentReasoningWindow } from "@/components/editor/AgentReasoningWindow";
import { computeContentHash, getCachedDocumentChunks, setCachedDocumentChunks } from "@/lib/IndexedDBEmbeddingCache";
import { authFetch } from "@/lib/api-client";

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

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
  isApplied?: boolean;
  isReverted?: boolean;
  historyEntryId?: string;
  diff?: {
    original_chunk: string;
    proposed_chunk: string;
    explanation: string;
  };
}

interface DiffData {
  original_chunk: string;
  proposed_chunk: string;
  explanation: string;
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
          <span className="font-semibold text-amber-300">Editor Intercepted Event Exception</span>
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

export const DEFAULT_MODEL = "auto:smart";

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

export function EditorLayout({
  projectId,
  isGuest: propIsGuest,
  expiresAt: propExpiresAt,
}: EditorLayoutProps) {
  const [code, setCode] = useState(initialLatexCode);
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");
  const [activeMobileTab, setActiveMobileTab] = useState<"code" | "files" | "pdf" | "ai">("code");
  const [filesOpen, setFilesOpen] = useState(true);
  const [activeFilePath, setActiveFilePath] = useState("main.tex");
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [isCompiling, setIsCompiling] = useState(false);
  const [pdfBase64, setPdfBase64] = useState<string | null>(null);
  const [errorLog, setErrorLog] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const [diffData, setDiffData] = useState<DiffData | null>(null);
  const [diffEditsList, setDiffEditsList] = useState<EditItem[]>([]);

  // In-memory SWR file cache for instantaneous file switching
  const fileContentCacheRef = useRef<Map<string, { content: string; timestamp: number }>>(new Map());

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
  const [attachedFile, setAttachedFile] = useState<{ filename: string; content: string; file_type: string } | null>(null);
  const [isFileAnalyzerOpen, setIsFileAnalyzerOpen] = useState<boolean>(false);
  const [isApiSettingsOpen, setIsApiSettingsOpen] = useState<boolean>(false);
  const [activeModelName, setActiveModelName] = useState<string>("gemini-3.7-flash");
  const [fallbackModelNotice, setFallbackModelNotice] = useState<string | null>(null);
  const [agentProgressSteps, setAgentProgressSteps] = useState<{ step: string; message: string; icon: string }[]>([]);
  const [filesRefreshTrigger, setFilesRefreshTrigger] = useState<number>(0);
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
  const desktopEditorRef = useRef<any>(null);
  const mobileEditorRef = useRef<any>(null);
  const isReverseSyncingRef = useRef<boolean>(false);
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
    // Suppress forward sync loop while navigating from PDF to code
    if (forwardSyncTimerRef.current) {
      clearTimeout(forwardSyncTimerRef.current);
    }
    isReverseSyncingRef.current = true;
    setTimeout(() => {
      isReverseSyncingRef.current = false;
    }, 1000);

    const monaco = monacoRef.current;
    if (file && file !== activeFilePath) {
      setActiveFilePath(file);
    }

    const targetCol = column || 1;
    pendingJumpRef.current = { line, col: targetCol, timestamp: Date.now() };

    setActiveMobileTab("code");

    const editors = [desktopEditorRef.current, mobileEditorRef.current, editorRef.current].filter(Boolean);
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

  // Instant selection-to-LaTeX synchronization
  const handlePdfTextSelected = (selectedText: string) => {
    // Suppress forward sync loop while navigating from PDF to code
    if (forwardSyncTimerRef.current) {
      clearTimeout(forwardSyncTimerRef.current);
    }
    isReverseSyncingRef.current = true;
    setTimeout(() => {
      isReverseSyncingRef.current = false;
    }, 1000);

    const monaco = monacoRef.current;
    const trimmed = selectedText.trim();
    if (!trimmed || trimmed.length < 2) return;

    const editors = [desktopEditorRef.current, mobileEditorRef.current, editorRef.current].filter(Boolean);
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
          for (let i = 1; i <= lineCount; i++) {
            const lineText = model.getLineContent(i).toLowerCase();
            if (lineText.includes(cleanSnippet)) {
              matchRange = new monaco.Range(i, 1, i, model.getLineMaxColumn(i));
              break;
            }
          }
        } else {
          matchRange = matches[0].range;
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
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    // Allow up to 50MB for large PDFs (30+ pages)
    if (selectedFile.size > 50 * 1024 * 1024) {
      toast.error("File size exceeds 50MB limit.");
      return;
    }

    const reader = new FileReader();
    const filename = selectedFile.name;
    const lowerName = filename.toLowerCase();
    const fileType = selectedFile.type || (lowerName.endsWith(".pdf") ? "application/pdf" : "text/plain");

    const isBinaryOrPdf = fileType.startsWith("image/") || fileType === "application/pdf" || lowerName.endsWith(".pdf");

    reader.onerror = () => {
      toast.error(`Failed to read file: ${filename}. The file may be too large or corrupted.`);
    };

    if (isBinaryOrPdf) {
      reader.readAsDataURL(selectedFile);
      reader.onload = () => {
        setAttachedFile({
          filename,
          content: reader.result as string,
          file_type: fileType,
        });
      };
    } else {
      reader.readAsText(selectedFile);
      reader.onload = () => {
        setAttachedFile({
          filename,
          content: reader.result as string,
          file_type: fileType,
        });
      };
    }

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
          setMessages(parsed);
        }
      }
    } catch (e) {
      console.warn("Failed to load chat messages from localStorage:", e);
    }
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

  // Load persistent attached PDF/file from localStorage on mount / project change
  useEffect(() => {
    try {
      const savedFile = localStorage.getItem(`overbranch_${projStorageKey}_attached_file`);
      if (savedFile) {
        const parsed = JSON.parse(savedFile);
        if (parsed && parsed.filename) {
          setAttachedFile(parsed);
        }
      }
    } catch (e) {
      console.warn("Failed to load attached file from localStorage:", e);
    }
  }, [projStorageKey]);

  // Save/remove attached file in localStorage when attachedFile changes
  useEffect(() => {
    try {
      if (attachedFile) {
        localStorage.setItem(`overbranch_${projStorageKey}_attached_file`, JSON.stringify(attachedFile));
      } else {
        localStorage.removeItem(`overbranch_${projStorageKey}_attached_file`);
      }
    } catch (e) {
      console.warn("Failed to update attached file in localStorage:", e);
    }
  }, [attachedFile, projStorageKey]);

  const handleNewChat = () => {
    setMessages([]);
    setAttachedFile(null);
    setDiffData(null);
    setDiffEditsList([]);
    setFallbackModelNotice(null);
    setAgentProgressSteps([]);
    try {
      localStorage.removeItem(`overbranch_${projStorageKey}_chat_messages`);
      localStorage.removeItem(`overbranch_${projStorageKey}_attached_file`);
    } catch (_) { }
  };

  const handleClearChat = () => {
    if (messages.length === 0 && !attachedFile) return;
    if (confirm("Are you sure you want to delete all chat history and document context for this project?")) {
      setMessages([]);
      setAttachedFile(null);
      setDiffData(null);
      setDiffEditsList([]);
      setFallbackModelNotice(null);
      setAgentProgressSteps([]);
      try {
        localStorage.removeItem(`overbranch_${projStorageKey}_chat_messages`);
        localStorage.removeItem(`overbranch_${projStorageKey}_attached_file`);
      } catch (_) { }
    }
  };

  const editorRef = useRef<any>(null);
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const decorationsRef = useRef<string[]>([]);
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

  // Apply native line decorations (red deletion highlights) directly inside Monaco Editor
  useEffect(() => {
    if (!editorRef.current) return;
    const editor = editorRef.current;
    const model = editor.getModel();
    if (!model) return;

    if (!diffEditsList || diffEditsList.length === 0) {
      decorationsRef.current = editor.deltaDecorations(decorationsRef.current, []);
      return;
    }

    const newDecorations: any[] = [];
    const text = model.getValue();
    const lines = text.split("\n");

    diffEditsList.forEach((edit) => {
      const orig = edit.original_chunk;
      if (orig && text.includes(orig)) {
        const startIdx = text.indexOf(orig);
        const startLine = text.slice(0, startIdx).split("\n").length;
        const lineCount = orig.split("\n").length;
        const endLine = startLine + lineCount - 1;

        newDecorations.push({
          range: {
            startLineNumber: startLine,
            startColumn: 1,
            endLineNumber: endLine,
            endColumn: (lines[endLine - 1] || "").length + 1,
          },
          options: {
            isWholeLine: true,
            className: "bg-rose-950/60 text-rose-200 border-l-4 border-rose-500 font-mono",
            glyphMarginClassName: "bg-rose-500",
          },
        });
      }
    });

    decorationsRef.current = editor.deltaDecorations(decorationsRef.current, newDecorations);
  }, [diffEditsList, code]);

  // Responsive Sidebar Panels
  const [aiOpen, setAiOpen] = useState(true);
  const [pdfOpen, setPdfOpen] = useState(true);

  const handleCustomCopy = async () => {
    if (editorRef.current) {
      const editor = editorRef.current;
      const selection = editor.getSelection();
      const model = editor.getModel();
      const selectedText = selection && model && !selection.isEmpty() ? model.getValueInRange(selection) : "";
      const textToCopy = selectedText || editor.getValue();

      if (!textToCopy) {
        return;
      }

      // 1. Try modern Async Clipboard API
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(textToCopy);
          return;
        }
      } catch (err) {
        console.warn("navigator.clipboard.writeText error, attempting fallback:", err);
      }

      // 2. Fallback: execCommand('copy') with hidden textarea
      try {
        const textarea = document.createElement("textarea");
        textarea.value = textToCopy;
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        textarea.style.top = "-9999px";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const success = document.execCommand("copy");
        document.body.removeChild(textarea);
        if (success) {
          // Restore Monaco selection
          if (selection) editor.setSelection(selection);
          return;
        }
      } catch (fallbackErr) {
        console.warn("execCommand copy fallback error:", fallbackErr);
      }
    } else if (code) {
      try {
        await navigator.clipboard.writeText(code);
        return;
      } catch (err) { }
    }
    toast.error("Unable to access clipboard. Use Ctrl+C or Cmd+C.");
  };

  const handleCustomPaste = async () => {
    // Try Clipboard Read API
    try {
      if (navigator.clipboard && navigator.clipboard.readText) {
        const text = await navigator.clipboard.readText();
        if (text) {
          insertSymbol(text);
          return;
        }
      }
    } catch (err) {
      console.warn("Direct clipboard read blocked by browser permissions:", err);
    }

    // Focus editor so user can press Ctrl+V / Cmd+V
    if (editorRef.current) {
      editorRef.current.focus();
    }
  };

  const handleSelectAll = () => {
    if (editorRef.current) {
      const editor = editorRef.current;
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
    if (editorRef.current) {
      const editor = editorRef.current;
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

  const handleUndo = () => {
    if (editorRef.current) {
      editorRef.current.focus();
      editorRef.current.trigger("toolbar", "undo", null);
    }
  };

  const handleRedo = () => {
    if (editorRef.current) {
      editorRef.current.focus();
      editorRef.current.trigger("toolbar", "redo", null);
    }
  };

  const toggleAi = () => {
    setAiOpen((prev) => {
      const next = !prev;
      if (next) {
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
    setActiveFilePath(filePath);
    // Instant cache lookup for 0ms transition
    const cached = fileContentCacheRef.current.get(filePath);
    if (cached) {
      setCode(cached.content);
      setSaveStatus("saved");
    } else {
      const savedKey = `overbranch_code_${projectId || 'default'}_${filePath}`;
      try {
        const saved = localStorage.getItem(savedKey);
        if (saved !== null) {
          setCode(saved);
          setSaveStatus("saved");
          fileContentCacheRef.current.set(filePath, { content: saved, timestamp: Date.now() });
        }
      } catch (_) {}
    }
  }, [projectId]);

  // 1. Load saved code from backend API (Supabase DB + Disk) or LocalStorage when activeFilePath or projectId changes
  useEffect(() => {
    let isCancelled = false;

    // Fast synchronous cache hit
    const cached = fileContentCacheRef.current.get(activeFilePath);
    if (cached) {
      setCode(cached.content);
      setSaveStatus("saved");
    } else {
      try {
        const savedCode = localStorage.getItem(storageKey);
        if (savedCode !== null) {
          setCode(savedCode);
          setSaveStatus("saved");
          fileContentCacheRef.current.set(activeFilePath, { content: savedCode, timestamp: Date.now() });
        }
      } catch (e) {}
    }

    const loadSavedDocument = async () => {
      try {
        const activeProj = projectId || "proj-1";
        const res = await authFetch(`${BACKEND_URL}/api/projects/get-file?project_id=${activeProj}&file_path=${encodeURIComponent(activeFilePath)}`);
        if (res.ok && !isCancelled) {
          const data = await res.json();
          if (data.raw_code !== undefined) {
            setCode(data.raw_code);
            setSaveStatus("saved");
            fileContentCacheRef.current.set(activeFilePath, { content: data.raw_code, timestamp: Date.now() });
            localStorage.setItem(storageKey, data.raw_code);
            return;
          }
        }
      } catch (err) {
        console.warn("Backend load failed, falling back to LocalStorage:", err);
      }

      // Fallback to LocalStorage
      if (!isCancelled) {
        try {
          const savedCode = localStorage.getItem(storageKey);
          if (savedCode !== null) {
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
  }, [projectId, activeFilePath, storageKey]);

  // 2. Save Document function (Saves to Supabase latex_documents DB, Local Disk, and syncs Qdrant vectors)
  const saveDocument = async (newCode: string, showToast = true) => {
    setSaveStatus("saving");
    const activeProj = projectId || "proj-1";
    fileContentCacheRef.current.set(activeFilePath, { content: newCode, timestamp: Date.now() });

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
  const handleCodeChange = (newCode: string | undefined) => {
    const updated = newCode ?? "";
    setCode(updated);
    setSaveStatus("unsaved");
    fileContentCacheRef.current.set(activeFilePath, { content: updated, timestamp: Date.now() });

    // Instantly persist in LocalStorage for crash resilience
    try {
      localStorage.setItem(storageKey, updated);
    } catch (e) { }

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
    if (isDesktop) {
      desktopEditorRef.current = editor;
    } else {
      mobileEditorRef.current = editor;
    }
    editorRef.current = editor;
    monacoRef.current = monaco;

    setupDefaultLatexSyntaxAndEmeraldTheme(monaco, editor);

    const isCurrentlyDark = themeMounted
      ? (resolvedTheme ? resolvedTheme === "dark" : appTheme === "dark")
      : (typeof document !== "undefined" ? document.documentElement.classList.contains("dark") : true);
    try {
      monaco.editor.setTheme(isCurrentlyDark ? "kinetic-emerald" : "kinetic-emerald-light");
    } catch (_) {}

    editor.onDidChangeCursorSelection((e: any) => {
      if (e.selection) {
        lastSelectionRef.current = e.selection;
      }
    });

    editor.onDidChangeCursorPosition((e: any) => {
      if (e.position) {
        lastPositionRef.current = e.position;
      }
    });

    // Attach touch/mobile fallback paste listener only on touch-enabled devices
    try {
      const isTouchDevice = typeof window !== "undefined" && ("ontouchstart" in window || navigator.maxTouchPoints > 0);
      const containerNode = editor.getContainerDomNode();
      if (containerNode && isTouchDevice) {
        containerNode.addEventListener(
          "paste",
          (e: ClipboardEvent) => {
            try {
              const pastedText = e.clipboardData?.getData("text/plain");
              if (pastedText !== undefined && pastedText !== null && editorRef.current) {
                const activeEd = editorRef.current;
                const selection = activeEd.getSelection();
                if (selection && !selection.isEmpty()) {
                  e.preventDefault();
                  e.stopPropagation();
                  activeEd.pushUndoStop();
                  activeEd.executeEdits("safe-mobile-paste", [
                    {
                      range: selection,
                      text: pastedText,
                      forceMoveMarkers: true,
                    },
                  ]);
                  activeEd.pushUndoStop();
                  handleCodeChange(activeEd.getValue());
                }
              }
            } catch (pasteErr) {
              console.warn("Handled mobile paste fallback exception:", pasteErr);
            }
          },
          false
        );
      }
    } catch (err) {
      console.warn("Failed to attach touch paste event listener:", err);
    }

    // Register Ctrl+S / Cmd+S save shortcut inside Monaco Editor
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      const currentVal = editor.getValue();
      saveDocument(currentVal, true);
      handleCompile(currentVal);
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

  const handleCompile = async (currentCodeOverride?: string) => {
    const targetCode = currentCodeOverride ?? code;
    if (!targetCode) return;
    setIsCompiling(true);
    setErrorLog(null);
    try {
      const res = await authFetch(`${BACKEND_URL}/api/compile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latex_code: targetCode,
          project_id: projectId || "",
          engine: "pdfLaTeX",
        }),
      });
      const data = await res.json();
      if (data.success) {
        setPdfBase64(data.pdf_base64);
      } else {
        setErrorLog(data.error_log || "Compilation failed.");
        toast.error("LaTeX compilation failed.");
      }
    } catch (err) {
      setErrorLog("Network error or Python backend is not running.");
      toast.error("Failed to connect to backend compiler.");
    } finally {
      setIsCompiling(false);
    }
  };

  const sendPromptMessage = async (customPrompt?: string) => {
    const rawUserText = customPrompt !== undefined ? customPrompt : chatInput;
    if ((!rawUserText.trim() && !attachedFile) || isAgentThinking) return;

    const userText = rawUserText.trim() || (attachedFile ? `[Uploaded file: ${attachedFile.filename}]` : "");
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        sender: "user",
        text: (customPrompt === undefined && attachedFile)
          ? `${userText}\n\n📎 Attached File: ${attachedFile.filename}`
          : userText,
        time: now,
      },
    ]);

    const currentFilePayload = customPrompt === undefined ? attachedFile : null;
    if (customPrompt === undefined) {
      setChatInput("");
      if (typeof document !== "undefined") {
        document.querySelectorAll<HTMLTextAreaElement>("textarea[id*='chat-input']").forEach((el) => {
          el.style.height = "auto";
        });
      }
      setAttachedFile(null);
    }
    setIsAgentThinking(true);
    setFallbackModelNotice(null);
    setAgentProgressSteps([]);

    abortControllerRef.current = new AbortController();
    const reqId = `chat-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    activeRequestIdRef.current = reqId;

    // Scale timeout based on whether there's a large attached file (600s for files, 300s otherwise)
    const hasLargeFile = currentFilePayload && currentFilePayload.content && currentFilePayload.content.length > 500000;
    const timeoutMs = hasLargeFile ? 600000 : 300000;
    const timeoutId = setTimeout(() => abortControllerRef.current?.abort(), timeoutMs);

    try {
      // Prepare the attached file payload — for very large files (>5MB content),
      // truncate to avoid 413 errors from reverse proxies (Nginx, cloud LBs).
      // The backend has its own PDF text extraction as fallback.
      let filePayload: { filename: string; content: string; file_type: string } | null = null;
      if (currentFilePayload) {
        filePayload = {
          filename: currentFilePayload.filename,
          content: currentFilePayload.content,
          file_type: currentFilePayload.file_type,
        };
      }

      // Check for user-provided API keys
      let customApiKeys = null;
      try {
        const storedKeys = localStorage.getItem("ob_api_keys");
        if (storedKeys) customApiKeys = JSON.parse(storedKeys);
      } catch (e) {
        console.warn("Failed to parse API keys from localStorage", e);
      }

      const response = await authFetch(`${BACKEND_URL}/api/agent/opencode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          project_id: projectId || "proj-default",
          request_id: reqId,
          file_path: activeFilePath || "main.tex",
          user_prompt: userText,
          current_code: code,
          model: activeModelName || "auto:smart",
          attached_file: filePayload,
          mode: chatMode,
          api_keys: customApiKeys || undefined,
        }),
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        if (response.status === 413) {
          throw new Error("The uploaded file is too large for the server. Try a smaller PDF or ask about the document without attaching it.");
        }
        const errText = await response.text();
        throw new Error(errText || `AI Agent returned status ${response.status}`);
      }

      // Read SSE stream
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";
      let finalData: any = null;
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
                  setAgentProgressSteps((prev) => [...prev, parsed]);
                } else if (["thought", "tool_call", "tool_result", "compile_error", "coverage_check"].includes(currentEventType)) {
                  setAgentProgressSteps((prev) => [...prev, {
                    step: currentEventType,
                    message: parsed.content || parsed.message || (typeof parsed === "string" ? parsed : JSON.stringify(parsed)),
                    icon: currentEventType === "compile_error" ? "alert" : currentEventType === "thought" ? "brain" : currentEventType === "tool_call" ? "wrench" : "check",
                    ...parsed,
                  }]);
                } else if (
                  currentEventType === "final_diff" ||
                  parsed.type === "final_diff" ||
                  parsed.proposed_code !== undefined ||
                  parsed.proposed_chunk !== undefined ||
                  (Array.isArray(parsed.edits) && parsed.edits.length > 0)
                ) {
                  finalData = {
                    ...parsed,
                    original_chunk: parsed.original_code || parsed.original_chunk || "",
                    proposed_chunk: parsed.proposed_code || parsed.proposed_chunk || "",
                    explanation: parsed.explanation || "",
                    edits: parsed.edits && parsed.edits.length > 0 ? parsed.edits : [{
                      original_chunk: parsed.original_code || parsed.original_chunk || "",
                      proposed_chunk: parsed.proposed_code || parsed.proposed_chunk || "",
                      explanation: parsed.explanation || "",
                    }],
                  };
                } else if (currentEventType === "result") {
                  finalData = parsed;
                } else if (currentEventType === "cancelled") {
                  console.log("AI Agent generation cleanly stopped by user:", parsed);
                  return;
                } else if (currentEventType === "error" || (parsed.type === "error" && parsed.message)) {
                  sseError = new Error(parsed.message || "AI Agent error");
                }
              } catch (parseErr: any) {
                if (parseErr.message && !parseErr.message.includes("JSON")) {
                  sseError = parseErr;
                }
              }
            } else if (trimmed === "") {
              currentEventType = "";
            }
          }
        };

        while (true) {
          if (sseError) break;
          const { done, value } = await reader.read();
          if (done) break;

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
      if (!finalData) throw new Error("No result received from AI agent");

      const data = finalData;
      const assistantTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });



      if (data.is_fallback && data.fallback_notice) {
        setFallbackModelNotice(data.fallback_notice);
        toast.warning(data.fallback_notice, { duration: 6000 });
      }

      const rawExplanation = data.explanation || "I have processed your LaTeX request.";
      const responseText = sanitizeChunkReferences(rawExplanation);

      const isAskModeResponse = chatMode === "ask" || data.mode === "ask";

      // Build explicit edits list (only in Edit mode)
      let editsList: EditItem[] = (!isAskModeResponse && data.edits && Array.isArray(data.edits) && data.edits.length > 0)
        ? data.edits
          .filter((e: any) => e.original_chunk || e.proposed_chunk)
          .map((e: any, idx: number) => ({
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

      // Fallback: extract LaTeX from raw explanation ONLY in Edit mode
      if (!isAskModeResponse && editsList.length === 0) {
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

      setMessages((prev) => [
        ...prev,
        {
          id: `ai-${Date.now()}`,
          sender: "assistant",
          text: responseText + (data.is_fallback ? `\n\n*(⚠️ Fallback Model Used: ${data.model_used})*` : ""),
          time: assistantTime,
          mode: chatMode,
          edits: editsList,
          isApplied: false,
        },
      ]);

      if (hasEdits) {
        setDiffEditsList(editsList);
        setDiffData({
          original_chunk: data.original_chunk || editsList[0].original_chunk,
          proposed_chunk: data.proposed_chunk || editsList[0].proposed_chunk,
          explanation: sanitizeChunkReferences(data.explanation || "AI Suggested Modifications"),
        });
      } else {
        setDiffEditsList([]);
        setDiffData(null);
      }

      if (data.is_pdf_conversion || (data.files_written && data.files_written.length > 0)) {
        setFilesRefreshTrigger((prev) => prev + 1);
        setFilesOpen(true);
        toast.success(
          `Project updated from PDF! ${data.files_written?.length || 0} file(s) and ${data.assets_written?.length || 0} asset(s) saved in assets/.`,
          { icon: "📄" }
        );
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name === "AbortError") {
        console.log("AI Agent chat request aborted.");
        setMessages((prev) => [
          ...prev,
          {
            id: `ai-abort-${Date.now()}`,
            sender: "assistant",
            text: "⏱️ Request timed out or was stopped. Try a simpler prompt or click Send again.",
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        return;
      }

      let userErrMsg = err.message || "Failed to reach AI service";
      if (userErrMsg.includes("input stream") || userErrMsg.includes("network") || userErrMsg.includes("Failed to fetch")) {
        userErrMsg = "Connection interrupted while streaming. Please try sending your request again.";
      }
      const warningMsg = `AI Agent Error: ${userErrMsg}`;
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
    sendPromptMessage(prompt);
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

  const applySingleEditInPlace = (currentText: string, orig: string, prop: string): string => {
    const propVal = prop !== undefined && prop !== null ? prop : "";
    if (!propVal && !orig) return currentText;

    // 1. Full document replacement
    if (propVal.includes("\\documentclass") && propVal.includes("\\begin{document}")) {
      return propVal;
    }

    // 2. Direct exact verbatim match (including deletions where propVal is "")
    if (orig && currentText.includes(orig)) {
      let res = currentText.replace(orig, propVal);
      if (!propVal.trim()) {
        res = res.replace(/\n{3,}/g, "\n\n");
      }
      return res;
    }

    // 3. Whitespace-tolerant regex match
    if (orig && orig.trim()) {
      const escaped = orig.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
      try {
        const regex = new RegExp(escaped, 'i');
        if (regex.test(currentText)) {
          let res = currentText.replace(regex, propVal);
          if (!propVal.trim()) {
            res = res.replace(/\n{3,}/g, "\n\n");
          }
          return res;
        }
      } catch {
        // continue to next strategy
      }
    }

    // If this was a deletion operation and exact/regex matching failed, don't append empty snippet
    if (!propVal.trim()) {
      return currentText;
    }

    // 4. In-place Beamer frame replacement (prevents duplicate slides at bottom of document)
    if (propVal.includes("\\begin{frame}") && propVal.includes("\\end{frame}")) {
      const normalizeTitle = (t: string): string => {
        if (!t) return "";
        let clean = t.replace(/\\[a-zA-Z]+(?:\[[^\]]*\])?\{([^}]*)\}/g, "$1");
        clean = clean.replace(/\\[a-zA-Z]+/g, "");
        clean = clean.replace(/^\s*\d+[\.\:\-\s]*/, "");
        clean = clean.replace(/^\d+/, "");
        clean = clean.replace(/[^a-zA-Z0-9\s]/g, " ");
        return clean.replace(/\s+/g, " ").trim().toLowerCase();
      };

      const isPropTitleSlide = propVal.includes("\\titlepage") || (propVal.startsWith("\\begin{frame}[plain]") && (propVal.toLowerCase().includes("presented by") || propVal.toLowerCase().includes("seminar")));
      const isPropRefSlide = propVal.includes("\\begin{thebibliography}") || propVal.includes("\\bibitem") || propVal.toLowerCase().slice(0, 150).includes("reference");
      const isPropTableSlide = (propVal.includes("\\begin{table}") || propVal.includes("\\begin{tabular")) && (propVal.toLowerCase().includes("comparative") || propVal.toLowerCase().includes("comparison"));

      const titleMatch = propVal.match(/\\begin\{frame\}(?:\[[^\]]*\])?\s*\{([^}]+)\}/);
      const cleanPropTitle = titleMatch ? normalizeTitle(titleMatch[1]) : "";
      const fracMatch = propVal.match(/\(?(\d+\/\d+)\)?/);
      const numMatch = propVal.match(/\b(?:survey|paper|slide|frame)\s*#?\s*(\d+)\b/i);

      const frameRegex = /\\begin\{frame\}[\s\S]*?\\end\{frame\}/g;
      let m: RegExpExecArray | null;
      let bestMatch: { index: number; length: number } | null = null;

      while ((m = frameRegex.exec(currentText)) !== null) {
        const existingFrame = m[0];
        const isExistingTitleSlide = existingFrame.includes("\\titlepage") || (existingFrame.startsWith("\\begin{frame}[plain]") && (existingFrame.toLowerCase().includes("presented by") || existingFrame.toLowerCase().includes("seminar")));

        // Never overwrite a Title Slide with a content slide
        if (isExistingTitleSlide && !isPropTitleSlide) {
          continue;
        }

        // References slide matching
        if (isPropRefSlide && (existingFrame.includes("\\begin{thebibliography}") || existingFrame.includes("\\bibitem") || existingFrame.toLowerCase().includes("reference"))) {
          bestMatch = { index: m.index, length: existingFrame.length };
          break;
        }

        // Comparative analysis table slide matching
        if (isPropTableSlide && (existingFrame.includes("\\begin{table}") || existingFrame.includes("\\begin{tabular")) && (existingFrame.toLowerCase().includes("comparative") || existingFrame.toLowerCase().includes("comparison"))) {
          bestMatch = { index: m.index, length: existingFrame.length };
          break;
        }

        // Match by fraction like (7/7)
        if (fracMatch && existingFrame.includes(fracMatch[1])) {
          bestMatch = { index: m.index, length: existingFrame.length };
          break;
        }

        // Match by normalized title (handles '3Literature Survey' vs '3. Literature Survey')
        if (cleanPropTitle) {
          const exTitleMatch = existingFrame.match(/\\begin\{frame\}(?:\[[^\]]*\])?\s*\{([^}]+)\}/);
          if (exTitleMatch) {
            const cleanExTitle = normalizeTitle(exTitleMatch[1]);
            if (cleanPropTitle === cleanExTitle || (cleanPropTitle.length >= 4 && cleanExTitle.includes(cleanPropTitle)) || (cleanExTitle.length >= 4 && cleanPropTitle.includes(cleanExTitle))) {
              bestMatch = { index: m.index, length: existingFrame.length };
              break;
            }
          }
        }

        // Match by survey/slide number
        if (numMatch && (existingFrame.includes(`(${numMatch[1]}/`) || existingFrame.includes(` ${numMatch[1]}/`))) {
          bestMatch = { index: m.index, length: existingFrame.length };
          break;
        }
      }

      if (bestMatch) {
        return currentText.slice(0, bestMatch.index) + propVal + currentText.slice(bestMatch.index + bestMatch.length);
      }
    }

    // 5. In-place Section / Chapter / Subsection replacement
    const secMatch = propVal.match(/\\(chapter|section\*?|subsection|subsubsection)\{([^}]+)\}/);
    if (secMatch) {
      const secTitle = secMatch[2].trim();
      const escapedTitle = secTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      try {
        const nextSecRegex = new RegExp(
          `\\\\(?:chapter|section\\*?|subsection|subsubsection)\\{${escapedTitle}\\}[\\s\\S]*?(?=\\\\(?:chapter|section|subsection|subsubsection|begin\\{thebibliography\\}|bibliography|end\\{document\\})|$)`,
          'i'
        );
        if (nextSecRegex.test(currentText)) {
          return currentText.replace(nextSecRegex, propVal + "\n\n");
        }
      } catch {
        // continue
      }
    }

    // 6. Safeguards before fallback append:
    // Never append a duplicate \documentclass or \begin{document} into an existing document
    if (propVal.includes("\\documentclass") || propVal.includes("\\begin{document}")) {
      return currentText;
    }

    // If an original anchor was given but not found at all, and propVal contains a duplicate section header, do not append blindly
    if (orig && secMatch) {
      const secTitle = secMatch[2].trim();
      if (currentText.toLowerCase().includes(secTitle.toLowerCase())) {
        return currentText;
      }
    }

    // 7. Append safely before \end{document}
    return insertSnippetSafely(currentText, propVal);
  };

  const handleAcceptDiff = (originalChunk: string, proposedChunk: string) => {
    const editor = editorRef.current;
    const model = editor?.getModel?.();
    const currentText = model ? model.getValue() : code;
    const updatedCode = applySingleEditInPlace(currentText, originalChunk, proposedChunk);

    if (editor && model) {
      editor.pushUndoStop();
      editor.executeEdits("ai-diff-edit", [
        {
          range: model.getFullModelRange(),
          text: updatedCode,
          forceMoveMarkers: true,
        },
      ]);
      editor.pushUndoStop();
    } else {
      setCode(updatedCode);
    }

    setCode(updatedCode);
    setDiffData(null);
    setDiffEditsList([]);

    // Auto-save to Supabase & Qdrant
    saveDocument(updatedCode, true);
    handleCompile(updatedCode);
  };

  const handleAcceptAllEdits = (itemsToApply: EditItem[], msgId?: string) => {
    const editor = editorRef.current;
    const model = editor?.getModel?.();
    const codeBeforeEdit = model ? model.getValue() : code;
    let updatedCode = codeBeforeEdit;

    itemsToApply.forEach((item) => {
      const orig = item.original_chunk;
      const prop = item.proposed_chunk;
      updatedCode = applySingleEditInPlace(updatedCode, orig, prop);
    });

    if (editor && model) {
      editor.pushUndoStop();
      editor.executeEdits("ai-accept-all", [
        {
          range: model.getFullModelRange(),
          text: updatedCode,
          forceMoveMarkers: true,
        },
      ]);
      editor.pushUndoStop();
    } else {
      setCode(updatedCode);
    }

    setCode(updatedCode);
    setDiffData(null);
    setDiffEditsList([]);

    const historyId = msgId || `edit-${Date.now()}`;
    const userPrompt = messages.filter((m) => m.sender === "user").pop()?.text || "AI Document Edit";

    if (editHistoryStoreRef.current) {
      editHistoryStoreRef.current.pushEdit({
        id: historyId,
        timestamp: Date.now(),
        model: activeModelName,
        prompt: userPrompt,
        files: [activeFilePath || "main.tex"],
        beforeCode: { [activeFilePath || "main.tex"]: codeBeforeEdit },
        afterCode: { [activeFilePath || "main.tex"]: updatedCode },
        cursorState: {
          file: activeFilePath || "main.tex",
          line: editor?.getPosition()?.lineNumber || 1,
          column: editor?.getPosition()?.column || 1,
          scrollTop: editor?.getScrollTop() || 0,
        },
        isReverted: false,
      });
    }

    if (msgId) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, isApplied: true, isReverted: false, historyEntryId: historyId }
            : m
        )
      );
    } else {
      setMessages((prev) =>
        prev.map((m) =>
          m.edits && m.edits.length > 0
            ? { ...m, isApplied: true, isReverted: false, historyEntryId: historyId }
            : m
        )
      );
    }

    saveDocument(updatedCode, true);
    handleCompile(updatedCode);
  };

  const handleRejectAllEdits = () => {
    setDiffData(null);
    setDiffEditsList([]);
  };

  const handleAcceptSingleEdit = (item: EditItem) => {
    const editor = editorRef.current;
    const model = editor?.getModel?.();
    const codeBeforeEdit = model ? model.getValue() : code;
    const orig = item.original_chunk;
    const prop = item.proposed_chunk;

    const updatedCode = applySingleEditInPlace(codeBeforeEdit, orig, prop);

    if (editor && model) {
      editor.pushUndoStop();
      editor.executeEdits("ai-accept-single", [
        {
          range: model.getFullModelRange(),
          text: updatedCode,
          forceMoveMarkers: true,
        },
      ]);
      editor.pushUndoStop();
    } else {
      setCode(updatedCode);
    }

    setCode(updatedCode);

    const remaining = diffEditsList.filter((e) => e.id !== item.id);
    setDiffEditsList(remaining);
    if (remaining.length === 0) {
      setDiffData(null);
    }

    saveDocument(updatedCode, true);
    handleCompile(updatedCode);
  };

  const handleRevertEdit = (editId: string) => {
    if (!editHistoryStoreRef.current) return;
    const entry = editHistoryStoreRef.current.revertEdit(editId);
    if (!entry) return; // Silent safety: Never throw raw exceptions or developer errors

    const file = activeFilePath || "main.tex";
    const restoredCode = entry.beforeCode[file] ?? Object.values(entry.beforeCode)[0];
    if (restoredCode === undefined) return;

    const editor = editorRef.current;
    const model = editor?.getModel?.();
    if (editor && model) {
      editor.pushUndoStop();
      editor.executeEdits("ai-revert", [
        {
          range: model.getFullModelRange(),
          text: restoredCode,
          forceMoveMarkers: true,
        },
      ]);
      editor.pushUndoStop();

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

    setMessages((prev) =>
      prev.map((m) =>
        (m.historyEntryId === editId || m.id === editId)
          ? { ...m, isReverted: true }
          : m
      )
    );
  };

  const handleReapplyEdit = (editId: string) => {
    if (!editHistoryStoreRef.current) return;
    const entry = editHistoryStoreRef.current.reapplyEdit(editId);
    if (!entry) return;

    const file = activeFilePath || "main.tex";
    const reappliedCode = entry.afterCode[file] ?? Object.values(entry.afterCode)[0];
    if (reappliedCode === undefined) return;

    const editor = editorRef.current;
    const model = editor?.getModel?.();
    if (editor && model) {
      editor.pushUndoStop();
      editor.executeEdits("ai-reapply", [
        {
          range: model.getFullModelRange(),
          text: reappliedCode,
          forceMoveMarkers: true,
        },
      ]);
      editor.pushUndoStop();
    } else {
      setCode(reappliedCode);
    }

    setCode(reappliedCode);
    saveDocument(reappliedCode, true);
    handleCompile(reappliedCode);

    setMessages((prev) =>
      prev.map((m) =>
        (m.historyEntryId === editId || m.id === editId)
          ? { ...m, isReverted: false }
          : m
      )
    );
  };

  const handleRejectSingleEdit = (itemId: string) => {
    const remaining = diffEditsList.filter((e) => e.id !== itemId);
    setDiffEditsList(remaining);
    if (remaining.length === 0) {
      setDiffData(null);
    }
  };

  const getEditLineRange = (originalChunk: string, proposedChunk: string): string => {
    if (!code) return "Line 1";

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

    return (
      <div className="mt-2.5 p-2.5 rounded-xl bg-zinc-950 border border-zinc-800 text-xs font-mono space-y-2">
        <div className="flex items-center justify-between font-bold text-indigo-400">
          <div className="flex items-center gap-1.5 text-xs">
            <span>Proposed TeX Edit ({m.edits.length})</span>
          </div>
          {m.isApplied ? (
            <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 font-bold flex items-center gap-1">
              <Check className="w-3 h-3" /> Applied
            </span>
          ) : (
            <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold">
              Pending
            </span>
          )}
        </div>

        {firstEdit && (firstEdit.original_chunk || firstEdit.proposed_chunk) && (
          <div className="bg-black/80 p-2 rounded-lg text-[10px] space-y-1 overflow-x-auto border border-zinc-800 font-mono max-h-28">
            {firstEdit.original_chunk && (
              <div className="text-rose-300 bg-rose-950/40 px-1.5 py-0.5 rounded line-through border-l-2 border-rose-500 truncate">
                - {firstEdit.original_chunk.split("\n")[0]}
              </div>
            )}
            {firstEdit.proposed_chunk && (
              <div className="text-indigo-400 bg-indigo-600/10 px-1.5 py-0.5 rounded border-l-2 border-indigo-500 truncate">
                + {firstEdit.proposed_chunk.split("\n")[0]}
              </div>
            )}
          </div>
        )}

        {!m.isApplied ? (
          <div className="flex items-center gap-2 pt-1 font-bold">
            <button
              type="button"
              onClick={() => handleRejectAllEdits()}
              className="flex-1 h-7 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center justify-center gap-1 transition-colors cursor-pointer"
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
              <Check className="w-3.5 h-3.5 text-black stroke-[3]" />
              <span>Accept Edit</span>
            </button>
          </div>
        ) : (
          <div className="pt-1.5 border-t border-zinc-800/80 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1 text-[11px] font-mono font-bold text-indigo-400">
              <Check className="w-3.5 h-3.5" />
              <span>{m.isReverted ? "Reverted" : "Applied to TeX"}</span>
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
                          ? "bg-zinc-900 hover:bg-zinc-800 text-amber-300 hover:text-amber-200 border-zinc-800 cursor-pointer active:scale-95"
                          : "bg-zinc-900 border-zinc-800 opacity-35 text-zinc-500 cursor-not-allowed"
                        }`}
                      title={hasHistory ? "Revert this AI edit" : "Edit history unavailable"}
                    >
                      <Undo2 className="w-3 h-3 text-amber-400" />
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
                          ? "bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-400 border-indigo-500/40 cursor-pointer active:scale-95"
                          : "bg-zinc-900 border-zinc-800 opacity-35 text-zinc-500 cursor-not-allowed"
                        }`}
                      title={hasHistory ? "Reapply this AI edit" : "Edit history unavailable"}
                    >
                      <Redo2 className="w-3 h-3 text-indigo-400" />
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
    if (editorRef.current) {
      const editor = editorRef.current;
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
    <div className="fixed inset-0 h-[100dvh] w-full max-w-full bg-[#F4F5F7] dark:bg-[#0E0F12] text-slate-900 dark:text-[#E2E4E9] overflow-hidden selection:bg-emerald-500/20 selection:text-emerald-900 dark:selection:bg-[#22242C] dark:selection:text-white flex flex-col relative z-0 transition-colors">
      {/* Guest Session Notification Banner */}
      {isGuestMode && (
        <div className="bg-amber-50 dark:bg-[#1A1C22] border-b border-amber-200 dark:border-[#282A30] px-3 sm:px-4 py-2 flex flex-wrap items-center justify-between gap-2.5 text-xs z-30 shrink-0 select-none">
          <div className="flex items-center gap-2.5">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
            </span>
            <span className="font-mono font-medium text-amber-800 dark:text-amber-400 uppercase tracking-wider text-[10px] sm:text-[11px] bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30">
              Guest Session
            </span>
            <span className="text-amber-900 dark:text-[#9E9E9E] text-xs font-mono">
              Expires in: <strong className="text-amber-950 dark:text-amber-300 font-bold">{guestTimeLeft || "24:00:00"}</strong>
            </span>
            <span className="text-amber-700 dark:text-[#62666D] text-xs hidden md:inline">
              · Read-only preview. Sign up to save this project permanently.
            </span>
          </div>

          <div className="flex items-center gap-2 font-mono">
            <Link
              href={`/register?redirect=${encodeURIComponent(`/editor/${projectId || ""}`)}`}
              className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold text-xs border border-emerald-600 dark:border-[#282A30] transition-all flex items-center gap-1 cursor-pointer"
            >
              <span>Save Permanently</span>
              <span>→</span>
            </Link>
            <Link
              href={`/login?redirect=${encodeURIComponent(`/editor/${projectId || ""}`)}`}
              className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] text-slate-700 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] text-xs border border-slate-200 dark:border-[#282A30] transition-colors"
            >
              Sign In
            </Link>
          </div>
        </div>
      )}

      {/* Main Top Navigation Header */}
      <header className="h-12 border-b border-slate-200 dark:border-[#282A30] bg-[#FAFAFC] dark:bg-[#141519] px-3 sm:px-4 flex items-center justify-between gap-3 shrink-0 z-10 select-none transition-colors">
        {/* Left Column: Integrated Back to Dashboard Brand Block & Project Title */}
        <div className="flex items-center gap-3 overflow-hidden min-w-0">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 group hover:opacity-90 transition-opacity cursor-pointer shrink-0"
            title="Return to Dashboard"
          >
            <div className="h-7 w-7 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-[#1A1C22] group-hover:bg-slate-200 dark:group-hover:bg-[#22242C] border border-slate-200 dark:border-[#282A30] text-slate-500 dark:text-[#9E9E9E] group-hover:text-slate-900 dark:group-hover:text-[#E2E4E9] transition-all">
              <ArrowLeft className="w-3.5 h-3.5 text-slate-500 dark:text-[#9E9E9E] group-hover:text-slate-900 dark:group-hover:text-[#E2E4E9] group-hover:-translate-x-0.5 transition-transform" />
            </div>
            <OverBranchLogo size="sm" variant="icon" colored />
          </Link>

          <div className="w-[1px] h-4 bg-slate-200 dark:bg-[#282A30] shrink-0 hidden sm:block" />

          <div className="truncate min-w-0">
            <h1 className="font-archivo font-bold text-xs sm:text-sm text-slate-900 dark:text-[#E2E4E9] tracking-tight truncate">
              {projectDetail?.name || (projectId ? `${projectId}.tex` : "main.tex")}
            </h1>
            <p className="text-[10px] text-slate-500 dark:text-[#9E9E9E] font-mono truncate">
              {activeFilePath} · {projectDetail?.template && projectDetail.template !== "None" ? projectDetail.template : "LaTeX"}
            </p>
          </div>
        </div>

        {/* Center Column: Layout View Switcher & Primary Fast Compile Action */}
        <div className="hidden md:flex items-center gap-2 shrink-0">
          {/* View Toggle */}
          <div className="flex items-center p-0.5 rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-xs font-mono">
            <button
              onClick={() => setPdfOpen(false)}
              className={`h-7 px-2.5 flex items-center justify-center rounded-md transition-all cursor-pointer ${
                !pdfOpen
                  ? "bg-white dark:bg-[#22242C] text-slate-900 dark:text-[#E2E4E9] font-semibold shadow-xs"
                  : "text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9]"
              }`}
              title="Code Editor View"
            >
              Code
            </button>
            <button
              onClick={() => setPdfOpen(true)}
              className={`h-7 px-2.5 flex items-center justify-center rounded-md transition-all cursor-pointer ${
                pdfOpen
                  ? "bg-white dark:bg-[#22242C] text-slate-900 dark:text-[#E2E4E9] font-semibold shadow-xs"
                  : "text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9]"
              }`}
              title="Split View (Code + PDF)"
            >
              Split
            </button>
          </div>

          <Button
            size="sm"
            onClick={() => handleCompile()}
            disabled={isCompiling}
            className="h-8 px-3.5 bg-[#10B981] hover:bg-[#059669] text-white font-archivo font-bold rounded-lg text-xs border border-[#10B981]/30 flex items-center gap-1.5 cursor-pointer shadow-sm"
            title="Compile TeX (Ctrl+Enter / Cmd+Enter)"
          >
            {isCompiling ? (
              <RotateCw className="w-3.5 h-3.5 animate-spin text-white" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-current text-white" />
            )}
            <span>Compile</span>
          </Button>
        </div>

        {/* Right Column: Status & Action Toggles */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Save Status */}
          <span className="hidden sm:flex items-center gap-1.5 px-2.5 h-8 rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-[11px] font-mono">
            {saveStatus === "saved" && (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                <span className="text-slate-500 dark:text-[#9E9E9E]">Saved</span>
              </>
            )}
            {saveStatus === "saving" && (
              <>
                <RotateCw className="w-3 h-3 text-[#FF9900] animate-spin" />
                <span className="text-[#FF9900]">Saving...</span>
              </>
            )}
            {saveStatus === "unsaved" && (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-[#FF9900] animate-pulse" />
                <span className="text-[#FF9900]">Unsaved</span>
              </>
            )}
          </span>

          {/* Files Panel Toggle */}
          <button
            onClick={() => setFilesOpen(!filesOpen)}
            className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 rounded-lg border transition-colors cursor-pointer ${
              filesOpen
                ? "bg-slate-200 dark:bg-[#22242C] border-slate-300 dark:border-[#383B46] text-slate-900 dark:text-[#E2E4E9] font-semibold"
                : "bg-slate-100 dark:bg-[#1A1C22] hover:bg-slate-200 dark:hover:bg-[#22242C] border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9]"
            }`}
            title={filesOpen ? "Hide Project Files" : "Show Project Files"}
          >
            <FolderGit2 className="w-3.5 h-3.5" />
            <span>Files</span>
          </button>

          {/* AI Agent Toggle Button */}
          <button
            onClick={toggleAi}
            className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 rounded-lg border transition-colors cursor-pointer ${
              aiOpen
                ? "bg-slate-200 dark:bg-[#22242C] border-slate-300 dark:border-[#383B46] text-slate-900 dark:text-[#E2E4E9] font-semibold"
                : "bg-slate-100 dark:bg-[#1A1C22] hover:bg-slate-200 dark:hover:bg-[#22242C] border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9]"
            }`}
            title="Toggle AI Agent (Cmd+L / Ctrl+L)"
          >
            <Bot className="w-3.5 h-3.5" />
            <span>Agent</span>
          </button>


          {/* Theme Toggle Button */}
          <button
            onClick={handleToggleTheme}
            className="h-8 w-8 items-center justify-center rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-slate-700 dark:text-[#E2E4E9] hover:bg-slate-200 dark:hover:bg-[#22242C] transition-colors cursor-pointer flex shrink-0"
            title={isDark ? "Switch to Light Theme" : "Switch to Dark Theme"}
            aria-label="Toggle Theme"
          >
            {themeMounted ? (
              isDark ? (
                <Sun className="w-3.5 h-3.5 text-amber-400" />
              ) : (
                <Moon className="w-3.5 h-3.5 text-slate-700" />
              )
            ) : (
              <div className="w-3.5 h-3.5 rounded-full border border-current opacity-30" />
            )}
          </button>

          {/* Settings Button */}
          <button
            onClick={() => setIsApiSettingsOpen(true)}
            className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] hover:bg-slate-200 dark:hover:bg-[#22242C] transition-colors cursor-pointer"
            title="API Keys & Settings"
          >
            <Settings2 className="w-3.5 h-3.5" />
          </button>

          <CollaboratorAvatars projectId={projectId} />
        </div>
      </header>

      {/* Desktop Main Split Workspace */}
      <div className="hidden md:flex flex-1 overflow-hidden relative">
        <div className="w-full h-full flex overflow-hidden">
          {/* Panel 1 (Far Left): Project Files & Asset Panel */}
          <ProjectFilesPanel
            projectId={projectId || "proj-1"}
            activeFilePath={activeFilePath}
            isOpen={filesOpen}
            onClose={() => setFilesOpen(false)}
            onSelectFile={(filePath) => handleSelectFile(filePath)}
            onInsertLatexSnippet={(snippet) => insertSymbol(snippet)}
            refreshTrigger={filesRefreshTrigger}
          />

          {/* Panel 2 (Middle Left): Monaco Code Editor */}
          <div className="flex-1 min-w-[320px] bg-[#F8F9FA] dark:bg-[#0E0F12] flex flex-col h-full border-r border-slate-200 dark:border-[#282A30] relative overflow-hidden">
            {/* Minimalist Editor Tab Bar */}
            <div className="px-3 h-9 border-b border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#141519] flex items-center justify-between font-mono text-xs shrink-0 select-none">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5 text-xs text-slate-900 dark:text-[#E2E4E9] font-archivo font-bold">
                  <FileCode2 className="w-3.5 h-3.5 text-[#10B981]" />
                  <span>{activeFilePath}</span>
                </span>
              </div>

              {/* Subtle Undo & Redo Actions inside Code Editor Tab Bar */}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={handleUndo}
                  className="h-6 w-6 flex items-center justify-center rounded-md bg-white dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30] transition-colors cursor-pointer shadow-xs"
                  title="Undo (Ctrl+Z / Cmd+Z)"
                >
                  <Undo2 className="w-3 h-3" />
                </button>
                <button
                  type="button"
                  onClick={handleRedo}
                  className="h-6 w-6 flex items-center justify-center rounded-md bg-white dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30] transition-colors cursor-pointer shadow-xs"
                  title="Redo (Ctrl+Y / Cmd+Shift+Z)"
                >
                  <Redo2 className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* Monaco Editor Container */}
            <div className="flex-1 overflow-hidden relative">
              <Editor
                height="100%"
                defaultLanguage={activeFilePath.endsWith(".bib") ? "bibtex" : "latex"}
                theme={monacoTheme}
                value={code}
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

              {/* Floating In-Editor Accept/Reject Action Bar */}
              {diffData && diffEditsList.length > 0 && (
                <div className="absolute top-3 right-4 z-20 max-w-sm p-3 rounded-2xl bg-white dark:bg-[#141519] border border-slate-200 dark:border-[#282A30] shadow-2xl animate-in fade-in zoom-in-95 font-mono text-xs space-y-2">
                  <div className="flex items-center justify-between font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">
                    <div className="flex items-center gap-1.5 text-emerald-600 dark:text-[#10B981]">
                      <span>In-Editor Diff</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-100 dark:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] border border-slate-200 dark:border-[#282A30] font-mono">
                      {getEditLineRange(diffEditsList[0].original_chunk, diffEditsList[0].proposed_chunk)}
                    </span>
                  </div>

                  {/* Red / Green Line Preview */}
                  <div className="max-h-24 overflow-y-auto bg-slate-50 dark:bg-[#0E0F12] p-2 rounded-xl text-[10px] space-y-1 border border-slate-200 dark:border-[#282A30] font-mono">
                    {diffEditsList[0].original_chunk && (
                      <div className="text-rose-600 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40 px-1.5 py-0.5 rounded line-through border-l-2 border-rose-500 truncate">
                        - {diffEditsList[0].original_chunk.split("\n")[0]}
                      </div>
                    )}
                    {diffEditsList[0].proposed_chunk && (
                      <div className="text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 px-1.5 py-0.5 rounded border-l-2 border-emerald-500 truncate font-semibold">
                        + {diffEditsList[0].proposed_chunk.split("\n")[0]}
                      </div>
                    )}
                  </div>

                  {/* Action Buttons: Copy Patch, Reject, Accept */}
                  <div className="flex items-center gap-1.5 pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        let patch = "";
                        diffEditsList.forEach((e) => {
                          if (e.original_chunk) patch += e.original_chunk.split("\n").map((l) => `-${l}`).join("\n") + "\n";
                          if (e.proposed_chunk) patch += e.proposed_chunk.split("\n").map((l) => `+${l}`).join("\n") + "\n";
                        });
                        navigator.clipboard.writeText(patch.trim());
                      }}
                      className="h-7 px-2.5 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] border border-slate-200 dark:border-[#282A30] text-xs font-mono font-medium flex items-center justify-center gap-1 transition-colors cursor-pointer"
                      title="Copy diff patch"
                    >
                      <Copy className="w-3 h-3 text-slate-500 dark:text-[#9E9E9E]" />
                      <span>Copy</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleRejectAllEdits}
                      className="flex-1 h-7 rounded-lg bg-red-50 hover:bg-red-100 dark:bg-[#EB5757]/10 dark:hover:bg-[#EB5757]/20 border border-red-200 dark:border-[#EB5757]/30 text-red-600 dark:text-[#EB5757] text-xs font-mono font-semibold flex items-center justify-center gap-1 transition-colors cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleAcceptAllEdits(diffEditsList)}
                      className="flex-1 h-7 rounded-lg bg-emerald-600 hover:bg-emerald-700 dark:bg-[#10B981] dark:hover:bg-[#059669] text-white text-xs font-archivo font-bold flex items-center justify-center gap-1 transition-colors border border-emerald-600 dark:border-[#10B981]/30 shadow-sm cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5 text-white stroke-[2.5]" />
                      <span>Accept</span>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Bottom Status Bar */}
            <div className="h-6 px-3 border-t border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#141519] flex items-center justify-between text-[10px] font-mono text-slate-500 dark:text-[#9E9E9E] shrink-0 select-none">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1 text-slate-800 dark:text-[#E2E4E9]">
                  <FileCode2 className="w-3 h-3 text-emerald-600 dark:text-[#10B981]" />
                  <span>{activeFilePath}</span>
                </span>
                <span className="text-slate-300 dark:text-[#282A30]">|</span>
                <span className="hidden sm:inline">SyncTeX Active</span>
              </div>
              <div className="flex items-center gap-3">
                <span>UTF-8</span>
                <span>{activeFilePath.endsWith(".bib") ? "BibTeX" : "LaTeX"}</span>
                <span className="text-slate-300 dark:text-[#282A30]">|</span>
                <a
                  href="https://upzare.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:underline text-slate-700 dark:text-[#E2E4E9] font-bold group"
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
            className={`h-full bg-slate-100 dark:bg-[#0E0F12] transition-all duration-300 ease-in-out overflow-hidden flex flex-col min-w-0 max-w-full ${pdfOpen ? "flex-1 min-w-[280px] border-r border-slate-200 dark:border-[#282A30]" : "w-0 opacity-0 pointer-events-none border-r-0"
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
                onReverseSync={handleReverseSyncJump}
                onTextSelected={handlePdfTextSelected}
                onEnterPresentation={() => setIsPresentationMode(true)}
              />
            </div>
          </div>

          {/* Panel 4 (Far Right): AI Assistant Sidebar */}
          <div
            className={`h-full border-l border-slate-200 dark:border-[#282A30] bg-[#FAFAFC] dark:bg-[#141519] transition-all duration-300 ease-in-out overflow-hidden flex flex-col shrink-0 text-slate-900 dark:text-[#E2E4E9] ${aiOpen ? "w-[350px] opacity-100" : "w-0 opacity-0 pointer-events-none border-l-0"
              }`}
          >
            <div className="flex flex-col h-full justify-between p-3 text-xs min-w-[350px]">
              <div className="space-y-3 flex-1 flex flex-col overflow-hidden">
                <div className="border-b border-[#282A30] pb-2.5 shrink-0 space-y-2 select-none">
                  <div className="flex items-center justify-between gap-1.5">
                    <div className="flex items-center gap-1.5 shrink-0">
                      {/* Chat Options Dropdown */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            disabled={isAgentThinking}
                            className="p-1 rounded-lg bg-[#1A1C22] hover:bg-[#22242C] text-[#10B981] border border-[#282A30] transition-all cursor-pointer flex items-center justify-center shrink-0 disabled:opacity-50"
                            title="Chat options"
                          >
                            <Bot className="w-4 h-4 text-[#10B981]" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="bg-[#141519] border-[#282A30] text-[#E2E4E9] min-w-[140px] p-1 font-mono z-[99999]">
                          <DropdownMenuItem
                            onClick={handleNewChat}
                            disabled={isAgentThinking}
                            className="flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-[#1A1C22] hover:text-white cursor-pointer rounded-md focus:bg-[#1A1C22]"
                          >
                            <PlusCircle className="w-3.5 h-3.5 text-[#10B981]" />
                            <span>New Chat</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={handleClearChat}
                            disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                            className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-[#EB5757] hover:bg-[#EB5757]/10 cursor-pointer rounded-md focus:bg-[#EB5757]/10"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>Clear Chat</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>

                      <ChatModeToggle mode={chatMode} onModeChange={setChatMode} disabled={isAgentThinking} />
                    </div>

                    <div className="flex items-center gap-1.5 min-w-0">
                      <ModelSelector
                        activeModelName={activeModelName}
                        onSelectModel={setActiveModelName}
                        availableModels={availableModels}
                        disabled={isAgentThinking}
                      />
                    </div>
                  </div>

                  {fallbackModelNotice && (
                    <div className="px-2.5 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 truncate">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                        <span className="truncate">{fallbackModelNotice}</span>
                      </div>
                      <button onClick={() => setFallbackModelNotice(null)} className="text-amber-400 hover:text-white p-0.5">
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>

                {/* Chat Message Stream */}
                <div className="flex-1 overflow-y-auto space-y-3 pr-1 font-mono">
                  {messages.map((m) => (
                    <div
                      key={m.id}
                      className={`p-3 rounded-2xl border space-y-1.5 ${m.sender === "user"
                        ? "bg-emerald-50/80 dark:bg-[#18191B] border-emerald-200/80 dark:border-[#23252A] text-slate-900 dark:text-[#F7F8F8] ml-4 font-mono font-semibold shadow-2xs"
                        : "bg-slate-100/90 dark:bg-[#141517] border-slate-200/90 dark:border-[#23252A] text-slate-800 dark:text-[#F7F8F8] mr-4 font-sans"
                        }`}
                    >
                      <div className="flex items-center justify-between text-[10px] text-slate-500 dark:text-[#8A8F98] font-mono">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-slate-900 dark:text-[#F7F8F8]">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                          {m.mode && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded font-mono uppercase text-slate-600 dark:text-[#8A8F98] bg-slate-200/70 dark:bg-[#0F1011] border border-slate-300 dark:border-[#23252A]">
                              {m.mode}
                            </span>
                          )}
                        </div>
                        <span>{m.time}</span>
                      </div>
                      {m.sender === "assistant" ? (
                        <ChatMessageContent text={m.text} />
                      ) : (
                        <p className="leading-relaxed whitespace-pre-wrap break-words text-xs text-slate-900 dark:text-[#F7F8F8]">{m.text}</p>
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

                {/* Diff Control Card */}
                {diffData && diffEditsList.length > 0 && (
                  <div className="mb-2 p-3 rounded-2xl bg-white dark:bg-[#141517] border border-slate-200 dark:border-[#23252A] shadow-xl space-y-2 font-mono text-[11px] animate-in fade-in slide-in-from-bottom-2">
                    <div className="flex items-center justify-between font-semibold text-slate-900 dark:text-[#F7F8F8]">
                      <div className="flex items-center gap-1.5">
                        <Zap className="w-3.5 h-3.5 text-indigo-600 dark:text-[#5E6AD2]" />
                        <span>Proposed TeX Patch</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-100 dark:bg-[#18191B] text-slate-600 dark:text-[#8A8F98] border border-slate-200 dark:border-[#23252A] font-medium">
                        {getEditLineRange(diffEditsList[0].original_chunk, diffEditsList[0].proposed_chunk)}
                      </span>
                    </div>

                    <div className="max-h-28 overflow-y-auto bg-slate-50 dark:bg-[#08090A] p-2 rounded-xl text-[10px] space-y-1 font-mono border border-slate-200 dark:border-[#23252A]">
                      {diffEditsList[0].original_chunk && (
                        <div className="text-rose-600 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40 px-1.5 py-0.5 rounded line-through border-l-2 border-rose-500 truncate">
                          - {diffEditsList[0].original_chunk.split("\n")[0]}
                        </div>
                      )}
                      {diffEditsList[0].proposed_chunk && (
                        <div className="text-indigo-600 dark:text-[#5E6AD2] bg-indigo-50 dark:bg-[#5E6AD2]/10 px-1.5 py-0.5 rounded border-l-2 border-indigo-500 dark:border-[#5E6AD2] truncate font-semibold">
                          + {diffEditsList[0].proposed_chunk.split("\n")[0]}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5 pt-1 font-semibold">
                      <button
                        type="button"
                        onClick={() => {
                          let patch = "";
                          diffEditsList.forEach((e) => {
                            if (e.original_chunk) patch += e.original_chunk.split("\n").map((l) => `-${l}`).join("\n") + "\n";
                            if (e.proposed_chunk) patch += e.proposed_chunk.split("\n").map((l) => `+${l}`).join("\n") + "\n";
                          });
                          navigator.clipboard.writeText(patch.trim());
                        }}
                        className="h-8 px-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-[#18191B] dark:hover:bg-[#23252A] text-slate-600 dark:text-[#8A8F98] hover:text-slate-900 dark:hover:text-[#F7F8F8] border border-slate-200 dark:border-[#23252A] text-xs font-mono flex items-center justify-center gap-1 transition-colors cursor-pointer"
                        title="Copy diff patch"
                      >
                        <Copy className="w-3.5 h-3.5 text-slate-500 dark:text-[#8A8F98]" />
                        <span>Copy</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleRejectAllEdits}
                        className="flex-1 h-8 rounded-xl bg-red-50 hover:bg-red-100 dark:bg-[#EB5757]/10 dark:hover:bg-[#EB5757]/20 border border-red-200 dark:border-[#EB5757]/30 text-red-600 dark:text-[#EB5757] text-xs font-mono flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                      >
                        <X className="w-3.5 h-3.5" />
                        <span>Reject</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleAcceptAllEdits(diffEditsList)}
                        className="flex-1 h-8 rounded-xl bg-indigo-600 hover:bg-indigo-700 dark:bg-[#5E6AD2] dark:hover:bg-[#4F5BBE] text-white text-xs font-mono font-semibold flex items-center justify-center gap-1.5 transition-colors border border-indigo-600 dark:border-[#6875E5]/30 shadow-sm cursor-pointer"
                      >
                        <Check className="w-3.5 h-3.5 text-white stroke-[2.5]" />
                        <span>Accept All</span>
                      </button>
                    </div>
                  </div>
                )}

                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  className="hidden"
                />

                {attachedFile && (
                  <div className="space-y-1.5 mb-2">
                    <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-slate-100 dark:bg-[#141517] border border-slate-200 dark:border-[#23252A] text-slate-900 dark:text-[#F7F8F8] text-[11px] font-mono animate-in fade-in font-medium">
                      <div className="flex items-center gap-2 truncate">
                        <Paperclip className="w-3.5 h-3.5 text-indigo-600 dark:text-[#5E6AD2] shrink-0" />
                        <span className="truncate">{attachedFile.filename}</span>
                        <span className="text-[9px] text-indigo-700 dark:text-[#5E6AD2] bg-indigo-50 dark:bg-[#18191B] border border-indigo-200 dark:border-[#23252A] px-1.5 py-0.5 rounded font-mono uppercase">
                          {attachedFile.file_type || "file"}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setAttachedFile(null)}
                        className="p-1 text-slate-400 dark:text-[#8A8F98] hover:text-red-500 dark:hover:text-[#EB5757] transition-colors rounded-md cursor-pointer"
                        title="Remove attachment"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                )}

                {/* Chat Input Form */}
                <form onSubmit={handleSendPrompt} className="relative pt-2.5 border-t border-slate-200 dark:border-[#282A30] shrink-0 flex items-center gap-2 font-mono">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isAgentThinking}
                    className="p-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-[#282A30] transition-colors disabled:opacity-50 shrink-0 cursor-pointer"
                    title="Upload file (text, TeX, code, image)"
                  >
                    <Paperclip className="w-4 h-4 text-emerald-600 dark:text-[#10B981]" />
                  </button>

                  <div className="relative flex-1 font-mono">
                    <textarea
                      id="ai-chat-input"
                      rows={1}
                      placeholder={chatMode === "ask" ? "Ask a question about LaTeX or your document..." : "Ask agent to edit LaTeX..."}
                      value={chatInput}
                      disabled={isAgentThinking}
                      onChange={(e) => {
                        setChatInput(e.target.value);
                        e.target.style.height = "auto";
                        e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          if ((chatInput.trim() || attachedFile) && !isAgentThinking) {
                            handleSendPrompt(e);
                          }
                        }
                      }}
                      className="w-full min-h-[38px] max-h-40 py-2 px-3 rounded-xl border border-slate-200 dark:border-[#282A30] bg-slate-50 focus:bg-white dark:bg-[#1A1C22] dark:focus:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] text-xs outline-none focus:ring-1 focus:ring-emerald-500 dark:focus:ring-[#282A30] transition-all disabled:opacity-50 resize-none overflow-y-auto font-mono"
                    />
                  </div>

                  {isAgentThinking ? (
                    <Button
                      type="button"
                      onClick={handleStopAgentResponse}
                      size="sm"
                      variant="destructive"
                      className="h-9 px-3 rounded-xl bg-[#EB5757] hover:bg-[#D64545] text-white font-mono font-semibold shrink-0 flex items-center gap-1 text-xs shadow-md cursor-pointer border border-[#EB5757]/50"
                    >
                      <Square className="w-3.5 h-3.5 fill-current" />
                      <span>Stop</span>
                    </Button>
                  ) : (
                    <Button
                      type="submit"
                      disabled={(!chatInput.trim() && !attachedFile) || isAgentThinking}
                      size="sm"
                      className="h-9 px-3.5 bg-[#22242C] hover:bg-[#2A2C36] text-[#E2E4E9] font-archivo font-bold rounded-xl border border-[#282A30] shrink-0 flex items-center justify-center text-xs disabled:opacity-40 cursor-pointer"
                    >
                      <Send className="w-3.5 h-3.5 text-[#10B981]" />
                    </Button>
                  )}
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Viewports */}
      <div className="flex md:hidden flex-1 min-h-0 overflow-hidden relative">
        <div className={`flex-1 flex flex-col bg-[#0E0F12] overflow-hidden relative min-h-0 ${activeMobileTab === "files" ? "flex" : "hidden"}`}>
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
          />
        </div>

        <div className={`flex-1 flex flex-col bg-white dark:bg-[#0E0F12] overflow-hidden relative min-h-0 ${activeMobileTab === "code" ? "flex" : "hidden"}`}>
          <div className="flex-1 min-h-0 overflow-hidden relative">
            <EditorErrorBoundary>
              <Editor
                height="100%"
                defaultLanguage={activeFilePath.endsWith(".bib") ? "bibtex" : "latex"}
                theme={monacoTheme}
                value={code}
                beforeMount={(monaco) => setupDefaultLatexSyntaxAndEmeraldTheme(monaco)}
                onMount={(editor, monaco) => handleEditorMount(editor, monaco, false)}
                onChange={handleCodeChange}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  wordWrap: "on",
                  automaticLayout: true,
                  contextmenu: false,
                }}
              />
            </EditorErrorBoundary>
            {diffData && diffEditsList.length > 0 && (
              <div className="absolute top-2 right-2 z-30 max-w-[240px] p-2 rounded-xl bg-[#141519] border border-[#282A30] shadow-2xl font-mono text-xs space-y-1.5">
                <div className="flex items-center justify-between font-archivo font-bold text-[#E2E4E9]">
                  <span className="text-[#10B981]">Pending Edit</span>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleRejectAllEdits}
                    className="flex-1 h-7 rounded-lg bg-[#EB5757]/10 hover:bg-[#EB5757]/20 border border-[#EB5757]/30 text-[#EB5757] text-xs font-semibold flex items-center justify-center gap-1 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Reject</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAcceptAllEdits(diffEditsList)}
                    className="flex-1 h-7 rounded-lg bg-[#10B981] hover:bg-[#059669] text-white text-xs font-archivo font-bold flex items-center justify-center gap-1 transition-colors border border-[#10B981]/30"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Accept</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className={`flex-1 flex flex-col bg-[#0E0F12] overflow-hidden min-h-0 ${activeMobileTab === "pdf" ? "flex" : "hidden"}`}>
          <PDFViewer
            ref={pdfViewerRef}
            pdfBase64={pdfBase64}
            isCompiling={isCompiling}
            onRecompile={() => handleCompile()}
            onAskAiToFix={handleAskAiToFix}
            errorLog={errorLog}
            projectId={projectId}
            onReverseSync={(file, line, col) => {
              setActiveMobileTab("code");
              handleReverseSyncJump(file, line, col);
            }}
            onTextSelected={(text) => {
              handlePdfTextSelected(text);
            }}
            onEnterPresentation={() => setIsPresentationMode(true)}
          />
        </div>

        <div className={`flex-1 flex flex-col bg-[#141519] overflow-hidden relative min-h-0 p-3 space-y-3 text-[#E2E4E9] font-sans ${activeMobileTab === "ai" ? "flex" : "hidden"}`}>
          <div className="border-b border-[#282A30] pb-2.5 shrink-0 space-y-2 select-none">
            <div className="flex items-center justify-between gap-1.5">
              <div className="flex items-center gap-1.5 shrink-0">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      disabled={isAgentThinking}
                      className="p-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] text-emerald-600 dark:text-[#10B981] border border-slate-200 dark:border-[#282A30] transition-all cursor-pointer flex items-center justify-center shrink-0 disabled:opacity-50"
                      title="Chat options"
                    >
                      <Bot className="w-4 h-4 text-emerald-600 dark:text-[#10B981]" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="bg-white dark:bg-[#141519] border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] min-w-[140px] p-1 font-mono z-[99999]">
                    <DropdownMenuItem
                      onClick={handleNewChat}
                      disabled={isAgentThinking}
                      className="flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-slate-100 dark:hover:bg-[#1A1C22] text-slate-700 dark:text-[#E2E4E9] hover:text-slate-900 dark:hover:text-white cursor-pointer rounded-md focus:bg-slate-100 dark:focus:bg-[#1A1C22]"
                    >
                      <PlusCircle className="w-3.5 h-3.5 text-emerald-600 dark:text-[#10B981]" />
                      <span>New Chat</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={handleClearChat}
                      disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                      className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-red-600 dark:text-[#EB5757] hover:bg-red-50 dark:hover:bg-[#EB5757]/10 cursor-pointer rounded-md focus:bg-red-50 dark:focus:bg-[#EB5757]/10"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Clear Chat</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                <ChatModeToggle mode={chatMode} onModeChange={setChatMode} disabled={isAgentThinking} />
              </div>
              <div className="flex items-center gap-1.5 min-w-0">
                <ModelSelector
                  activeModelName={activeModelName}
                  onSelectModel={setActiveModelName}
                  availableModels={availableModels}
                  disabled={isAgentThinking}
                />
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 text-xs font-mono min-h-0 pr-1">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`p-3 rounded-2xl border space-y-1.5 ${m.sender === "user"
                  ? "bg-emerald-50 dark:bg-[#22242C] border-emerald-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] ml-4 font-mono font-semibold"
                  : "bg-slate-100 dark:bg-[#1A1C22] border-slate-200 dark:border-[#282A30] text-slate-800 dark:text-[#E2E4E9] mr-4 font-sans"
                  }`}
              >
                <div className="flex items-center justify-between text-[10px] text-slate-500 dark:text-[#9E9E9E] font-mono">
                  <span className="font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                  <span>{m.time}</span>
                </div>
                {m.sender === "assistant" ? (
                  <ChatMessageContent text={m.text} />
                ) : (
                  <p className="leading-relaxed text-xs whitespace-pre-wrap break-words text-slate-900 dark:text-[#E2E4E9]">{m.text}</p>
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

          <form onSubmit={handleSendPrompt} className="relative pt-2.5 border-t border-slate-200 dark:border-[#282A30] shrink-0 flex items-center gap-2 font-mono">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isAgentThinking}
              className="p-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-[#282A30] shrink-0 cursor-pointer disabled:opacity-50"
              title="Upload file"
            >
              <Paperclip className="w-4 h-4 text-emerald-600 dark:text-[#10B981]" />
            </button>

            <textarea
              id="ai-chat-input-2"
              rows={1}
              placeholder={chatMode === "ask" ? "Ask a question..." : "Ask agent to edit LaTeX..."}
              value={chatInput}
              disabled={isAgentThinking}
              onChange={(e) => {
                setChatInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if ((chatInput.trim() || attachedFile) && !isAgentThinking) {
                    handleSendPrompt(e);
                  }
                }
              }}
              className="flex-1 min-h-[40px] max-h-40 py-2 px-3 rounded-xl border border-[#282A30] bg-[#1A1C22] text-[#E2E4E9] placeholder:text-[#62666D] text-xs outline-none focus:ring-1 focus:ring-[#282A30] transition-all disabled:opacity-50 resize-none overflow-y-auto font-mono"
            />

            {isAgentThinking ? (
              <Button
                type="button"
                onClick={handleStopAgentResponse}
                size="sm"
                variant="destructive"
                className="h-10 px-3 rounded-xl bg-[#EB5757] hover:bg-[#D64545] text-white font-mono font-semibold shrink-0 flex items-center gap-1 text-xs cursor-pointer border border-[#EB5757]/50"
              >
                <Square className="w-4 h-4 fill-current" />
                <span>Stop</span>
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={(!chatInput.trim() && !attachedFile) || isAgentThinking}
                size="sm"
                className="h-10 px-3.5 bg-[#22242C] hover:bg-[#2A2C36] text-[#E2E4E9] font-archivo font-bold rounded-xl border border-[#282A30] shrink-0 flex items-center justify-center disabled:opacity-40 cursor-pointer"
              >
                <Send className="w-4 h-4 text-[#10B981]" />
              </Button>
            )}
          </form>
        </div>
      </div>

      {/* Bottom Navigation for Mobile View */}
      <nav className="md:hidden h-12 border-t border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] shrink-0 z-30 select-none">
        <div className="flex items-center justify-around w-full h-12 font-mono">
          <button
            onClick={() => setActiveMobileTab("files")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "files" ? "text-emerald-600 dark:text-[#10B981] font-bold font-archivo" : "text-slate-500 dark:text-[#9E9E9E]"
              }`}
          >
            <FolderGit2 className="w-4 h-4" />
            <span>Files</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("code")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "code" ? "text-emerald-600 dark:text-[#10B981] font-bold font-archivo" : "text-slate-500 dark:text-[#9E9E9E]"
              }`}
          >
            <FileCode2 className="w-4 h-4" />
            <span>Code</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("pdf")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "pdf" ? "text-emerald-600 dark:text-[#10B981] font-bold font-archivo" : "text-slate-500 dark:text-[#9E9E9E]"
              }`}
          >
            <Eye className="w-4 h-4" />
            <span>PDF</span>
          </button>

          <button
            onClick={() => {
              setActiveMobileTab("ai");
            }}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "ai" ? "text-emerald-600 dark:text-[#10B981] font-bold font-archivo" : "text-slate-500 dark:text-[#9E9E9E]"
              }`}
          >
            <Bot className="w-4 h-4" />
            <span>Agent</span>
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
    </div>
  );
}
