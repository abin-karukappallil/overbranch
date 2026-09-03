"use client";

import React, { useState, useRef, useEffect } from "react";

import Editor, { OnMount } from "@monaco-editor/react";
import { Drawer } from "vaul";
import Link from "next/link";
import {
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
} from "lucide-react";
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
import { FolderGit2 } from "lucide-react";
import { ChatModeToggle, type ChatMode } from "@/components/editor/ChatModeToggle";
import { EditHistoryStore, type EditHistory } from "@/lib/EditHistoryStore";
import { ChatMessageContent } from "@/components/editor/ChatMessageContent";
import { computeContentHash, getCachedDocumentChunks, setCachedDocumentChunks } from "@/lib/IndexedDBEmbeddingCache";

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

  // AI Agent Assistant & Editor Refs
  const abortControllerRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastSelectionRef = useRef<any>(null);
  const lastPositionRef = useRef<any>(null);
  const [attachedFile, setAttachedFile] = useState<{ filename: string; content: string; file_type: string } | null>(null);
  const [isFileAnalyzerOpen, setIsFileAnalyzerOpen] = useState<boolean>(false);
  const [activeModelName, setActiveModelName] = useState<string>("gemini-3.7-flash");
  const [fallbackModelNotice, setFallbackModelNotice] = useState<string | null>(null);
  const [agentProgressSteps, setAgentProgressSteps] = useState<{ step: string; message: string; icon: string }[]>([]);
  const [filesRefreshTrigger, setFilesRefreshTrigger] = useState<number>(0);
  const [chatMode, setChatMode] = useState<ChatMode>("edit");
  const editHistoryStoreRef = useRef<EditHistoryStore | null>(null);

  useEffect(() => {
    editHistoryStoreRef.current = new EditHistoryStore(projectId || "default");
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
            } catch (_) {}
          }, 1200);
        }
      } catch (_) {}
    }

    // Auto-release browser selection in the PDF so user doesn't have to click away
    setTimeout(() => {
      try {
        window.getSelection()?.removeAllRanges();
      } catch (_) {}
    }, 250);

    // Mobile jump guarantee: layout and reveal once tab is active
    setTimeout(() => {
      if (mobileEditorRef.current) {
        try {
          mobileEditorRef.current.layout();
          mobileEditorRef.current.revealLineInCenter(line, 0);
          mobileEditorRef.current.setPosition({ lineNumber: line, column: targetCol });
          mobileEditorRef.current.focus();
        } catch (_) {}
      }
    }, 80);
    setTimeout(() => {
      if (mobileEditorRef.current) {
        try {
          mobileEditorRef.current.layout();
          mobileEditorRef.current.revealLineInCenter(line, 0);
          mobileEditorRef.current.setPosition({ lineNumber: line, column: targetCol });
          mobileEditorRef.current.focus();
        } catch (_) {}
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
              } catch (_) {}
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
            } catch (_) {}
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
              } catch (_) {}
            }, 1200);
          }
        }
      } catch (_) {}
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
        } catch (_) {}
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
        } catch (_) {}
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
        const sizeMB = (selectedFile.size / (1024 * 1024)).toFixed(1);
        const label = fileType.includes("pdf") || lowerName.endsWith(".pdf") ? "PDF document" : "file";
        toast.success(`Attached ${label} ${filename} (${sizeMB}MB)`);
      };
    } else {
      reader.readAsText(selectedFile);
      reader.onload = () => {
        setAttachedFile({
          filename,
          content: reader.result as string,
          file_type: fileType,
        });
        toast.success(`Attached file ${filename}`);
      };
    }

    if (e.target) e.target.value = "";
  };

  const handleStopAgentResponse = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsAgentThinking(false);
    toast.info("AI response generation stopped.");
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
    toast.success("Started a new chat session.");
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
      toast.info("Chat history and document context deleted.");
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

  // Auto-scroll chat window to bottom when new messages, thinking state, or diffs update
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    mobileChatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isAgentThinking, diffData]);

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
        toast.info("Nothing to copy.");
        return;
      }

      // 1. Try modern Async Clipboard API
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(textToCopy);
          toast.success(selectedText ? "Copied selected text!" : "Copied full document code!");
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
          toast.success(selectedText ? "Copied selected text!" : "Copied full document code!");
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
        toast.success("Copied code to clipboard!");
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
          toast.success("Pasted text at cursor!");
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
    toast.info("Use Ctrl+V or Cmd+V to paste directly into the editor at your cursor.");
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
        toast.info("Selected entire document code.");
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
        toast.info(`Selected line ${pos.lineNumber}`);
      }
    }
  };

  const handleUndo = () => {
    if (editorRef.current) {
      editorRef.current.focus();
      editorRef.current.trigger("toolbar", "undo", null);
      toast.info("Undo");
    }
  };

  const handleRedo = () => {
    if (editorRef.current) {
      editorRef.current.focus();
      editorRef.current.trigger("toolbar", "redo", null);
      toast.info("Redo");
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

  // 1. Load saved code from backend API (Supabase DB + Disk) or LocalStorage when activeFilePath or projectId changes
  useEffect(() => {
    const loadSavedDocument = async () => {
      try {
        const activeProj = projectId || "proj-1";
        const res = await fetch(`${BACKEND_URL}/api/projects/get-file?project_id=${activeProj}&file_path=${encodeURIComponent(activeFilePath)}`);
        if (res.ok) {
          const data = await res.json();
          if (data.raw_code !== undefined) {
            setCode(data.raw_code);
            setSaveStatus("saved");
            localStorage.setItem(storageKey, data.raw_code);
            return;
          }
        }
      } catch (err) {
        console.warn("Backend load failed, falling back to LocalStorage:", err);
      }

      // Fallback to LocalStorage
      try {
        const savedCode = localStorage.getItem(storageKey);
        if (savedCode !== null) {
          setCode(savedCode);
          setSaveStatus("saved");
        }
      } catch (e) { }
    };

    loadSavedDocument();
  }, [projectId, activeFilePath, storageKey]);

  // 2. Save Document function (Saves to Supabase latex_documents DB, Local Disk, and syncs Qdrant vectors)
  const saveDocument = async (newCode: string, showToast = true) => {
    setSaveStatus("saving");
    const activeProj = projectId || "proj-1";

    try {
      // Always save to LocalStorage immediately for crash protection
      localStorage.setItem(storageKey, newCode);

      // Save to Supabase latex_documents DB + Local Disk + Qdrant Vector Sync
      const res = await fetch(`${BACKEND_URL}/api/projects/save-file`, {
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
        if (showToast) {
          toast.success(`Saved ${activeFilePath}!`);
        }
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

  const setupDefaultLatexSyntaxAndEmeraldTheme = (monaco: any, editor: any) => {
    if (!monaco || !editor) return;

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

      // Define default Kinetic Emerald Theme with high contrast & crisp comments
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
          "editor.background": "#121b17", // Kinetic emerald slightly lighter dark background
          "editor.foreground": "#ffffff",
          "editor.lineHighlightBackground": "#1c2b25",
          "editorCursor.foreground": "#00CC68",
          "editorLineNumber.foreground": "#71717a",
          "editorLineNumber.activeForeground": "#00CC68",
          "editorIndentGuide.background": "#273e35",
          "editorIndentGuide.activeBackground": "#00CC68",
        },
      });

      monaco.editor.setTheme("kinetic-emerald");
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
      const res = await fetch(`${BACKEND_URL}/api/compile`, {
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
        toast.success("LaTeX PDF compiled successfully.");
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

  const handleSendPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!chatInput.trim() && !attachedFile) || isAgentThinking) return;

    const userText = chatInput.trim() || (attachedFile ? `[Uploaded file: ${attachedFile.filename}]` : "");
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        sender: "user",
        text: attachedFile
          ? `${userText}\n\n📎 Attached File: ${attachedFile.filename}`
          : userText,
        time: now,
      },
    ]);

    const currentFilePayload = attachedFile;
    setChatInput("");
    if (typeof document !== "undefined") {
      document.querySelectorAll<HTMLTextAreaElement>("textarea[id*='chat-input']").forEach((el) => {
        el.style.height = "auto";
      });
    }
    setAttachedFile(null);
    setIsAgentThinking(true);
    setFallbackModelNotice(null);
    setAgentProgressSteps([]);

    abortControllerRef.current = new AbortController();
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

      const response = await fetch(`${BACKEND_URL}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          project_id: projectId || "proj-default",
          file_path: activeFilePath || "main.tex",
          user_prompt: userText,
          current_code: code,
          model: activeModelName || "auto:smart",
          attached_file: filePayload,
          mode: chatMode,
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

                if (currentEventType === "progress") {
                  setAgentProgressSteps((prev) => [...prev, parsed]);
                } else if (currentEventType === "result") {
                  finalData = parsed;
                } else if (currentEventType === "error") {
                  sseError = new Error(parsed.message || "AI Agent error");
                }
              } catch (parseErr: any) {
                if (parseErr.message && !parseErr.message.includes("JSON")) {
                  sseError = parseErr;
                }
              }
              currentEventType = "";
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
        toast.info(`Generated ${editsList.length} edit proposal(s). Review inline diff.`, { icon: "✨" });
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
    }
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
    const endDocIndex = text.lastIndexOf("\\end{document}");
    if (endDocIndex !== -1) {
      return text.slice(0, endDocIndex) + "\n\n" + snippet + "\n\n" + text.slice(endDocIndex);
    }
    return text + "\n\n" + snippet;
  };

  const applySingleEditInPlace = (currentText: string, orig: string, prop: string): string => {
    if (!prop) return currentText;

    // 1. Full document replacement
    if (prop.includes("\\documentclass") && prop.includes("\\begin{document}")) {
      return prop;
    }

    // 2. Direct exact verbatim match
    if (orig && currentText.includes(orig)) {
      return currentText.replace(orig, prop);
    }

    // 3. Whitespace-tolerant regex match
    if (orig && orig.trim()) {
      const escaped = orig.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
      try {
        const regex = new RegExp(escaped, 'i');
        if (regex.test(currentText)) {
          return currentText.replace(regex, prop);
        }
      } catch {
        // continue to next strategy
      }
    }

    // 4. In-place Beamer frame replacement (prevents duplicate slides at bottom of document)
    if (prop.includes("\\begin{frame}") && prop.includes("\\end{frame}")) {
      const titleMatch = prop.match(/\\begin\{frame\}(?:\[[^\]]*\])?\s*\{([^}]+)\}/);
      const fracMatch = prop.match(/\(?(\d+\/\d+)\)?/);
      const numMatch = prop.match(/\b(?:survey|paper|slide|frame)\s*#?\s*(\d+)\b/i);

      const frameRegex = /\\begin\{frame\}[\s\S]*?\\end\{frame\}/g;
      let m: RegExpExecArray | null;
      let bestMatch: { index: number; length: number } | null = null;

      while ((m = frameRegex.exec(currentText)) !== null) {
        const existingFrame = m[0];
        // Match by fraction like (7/7)
        if (fracMatch && existingFrame.includes(fracMatch[1])) {
          bestMatch = { index: m.index, length: existingFrame.length };
          break;
        }
        // Match by title
        if (titleMatch && existingFrame.toLowerCase().includes(titleMatch[1].toLowerCase().trim())) {
          bestMatch = { index: m.index, length: existingFrame.length };
          break;
        }
        // Match by survey/slide number
        if (numMatch && (existingFrame.includes(`(${numMatch[1]}/`) || existingFrame.includes(` ${numMatch[1]}/`))) {
          bestMatch = { index: m.index, length: existingFrame.length };
          break;
        }
      }

      if (bestMatch) {
        return currentText.slice(0, bestMatch.index) + prop + currentText.slice(bestMatch.index + bestMatch.length);
      }
    }

    // 5. In-place Section replacement
    if (prop.includes("\\section{")) {
      const secMatch = prop.match(/\\section\{([^}]+)\}/);
      if (secMatch) {
        const secTitle = secMatch[1].trim();
        const escapedSec = secTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        try {
          const nextSecRegex = new RegExp(`\\\\section\\{${escapedSec}\\}[\\s\\S]*?(?=\\\\section\\{|\\\\end\\{document\\}|$)`, 'i');
          if (nextSecRegex.test(currentText)) {
            return currentText.replace(nextSecRegex, prop + "\n\n");
          }
        } catch {
          // continue
        }
      }
    }

    // 6. Append safely before \end{document}
    return insertSnippetSafely(currentText, prop);
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
    toast.success("Applied changes into the LaTeX editor!");

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

    toast.success(`Accepted ${itemsToApply.length} AI edit(s) into editor!`);

    saveDocument(updatedCode, true);
    handleCompile(updatedCode);
  };

  const handleRejectAllEdits = () => {
    setDiffData(null);
    setDiffEditsList([]);
    toast.info("Rejected all AI proposed edits.");
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
    toast.success("Accepted single edit!");

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

    toast.success("Reverted AI edit to previous state.");
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

    toast.success("Reapplied AI edit.");
  };

  const handleRejectSingleEdit = (itemId: string) => {
    const remaining = diffEditsList.filter((e) => e.id !== itemId);
    setDiffEditsList(remaining);
    toast.info("Rejected single edit.");
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
        <div className="flex items-center justify-between font-bold text-[#00CC68]">
          <div className="flex items-center gap-1.5 text-xs">
            <span>Proposed TeX Edit ({m.edits.length})</span>
          </div>
          {m.isApplied ? (
            <span className="text-[10px] px-2 py-0.5 rounded bg-[#00CC68]/20 text-[#00CC68] border border-[#00CC68]/30 font-bold flex items-center gap-1">
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
              <div className="text-[#00CC68] bg-[#00CC68]/10 px-1.5 py-0.5 rounded border-l-2 border-[#00CC68] truncate">
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
              className="flex-1 h-7 rounded-lg bg-[#00CC68] hover:bg-[#00E676] text-black text-xs font-mono font-bold flex items-center justify-center gap-1 transition-colors border border-black shadow-[2px_2px_0px_0px_#000000] cursor-pointer"
            >
              <Check className="w-3.5 h-3.5 text-black stroke-[3]" />
              <span>Accept Edit</span>
            </button>
          </div>
        ) : (
          <div className="pt-1.5 border-t border-zinc-800/80 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1 text-[11px] font-mono font-bold text-[#00CC68]">
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
                      className={`px-2 py-1 rounded-md border text-[10px] font-mono font-bold flex items-center gap-1 transition-all shadow-xs ${
                        hasHistory
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
                      className={`px-2 py-1 rounded-md border text-[10px] font-mono font-bold flex items-center gap-1 transition-all shadow-xs ${
                        hasHistory
                          ? "bg-[#00CC68]/20 hover:bg-[#00CC68]/30 text-[#00CC68] border-[#00CC68]/40 cursor-pointer active:scale-95"
                          : "bg-zinc-900 border-zinc-800 opacity-35 text-zinc-500 cursor-not-allowed"
                      }`}
                      title={hasHistory ? "Reapply this AI edit" : "Edit history unavailable"}
                    >
                      <Redo2 className="w-3 h-3 text-[#00CC68]" />
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
    <div className="fixed inset-0 h-[100dvh] w-full max-w-full bg-zinc-950 text-zinc-100 overflow-hidden selection:bg-[#00CC68]/30 selection:text-[#00CC68] flex flex-col relative z-0">
      {/* Guest Session Notification Banner */}
      {isGuestMode && (
        <div className="bg-gradient-to-r from-amber-950/80 via-zinc-900 to-amber-950/80 border-b border-amber-500/40 px-3 sm:px-4 py-2 flex flex-wrap items-center justify-between gap-2.5 text-xs z-30 shrink-0 select-none shadow-md">
          <div className="flex items-center gap-2.5">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
            </span>
            <span className="font-mono font-bold text-amber-400 uppercase tracking-wider text-[10px] sm:text-[11px] bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30">
              Guest Session
            </span>
            <span className="text-zinc-200 text-xs font-mono">
              Expires in: <strong className="text-amber-300 font-bold">{guestTimeLeft || "24:00:00"}</strong>
            </span>
            <span className="text-zinc-400 text-xs hidden md:inline">
              · Read-only preview. Sign up to save this project permanently and unlock full editing.
            </span>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href={`/register?redirect=${encodeURIComponent(`/editor/${projectId || ""}`)}`}
              className="px-3 py-1 rounded-lg bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold text-xs shadow-[2px_2px_0px_0px_#000000] border border-black transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <span>Save Permanently</span>
              <span>→</span>
            </Link>
            <Link
              href={`/login?redirect=${encodeURIComponent(`/editor/${projectId || ""}`)}`}
              className="px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-mono text-xs border border-zinc-700 transition-colors"
            >
              Sign In
            </Link>
          </div>
        </div>
      )}

      <header className="h-14 border-b border-zinc-800 bg-zinc-950 px-3 sm:px-4 flex items-center justify-between gap-2 shrink-0 z-10 select-none">
        <div className="flex items-center gap-2 overflow-hidden">
          <Link href="/dashboard" className="shrink-0 hover:opacity-90 transition-opacity flex items-center gap-1.5" title="OverBranch (Beta) — Return to Dashboard">
            <OverBranchLogo size="sm" variant="icon" colored />
            <span className="text-[9px] font-mono font-black uppercase px-1.5 py-0.5 rounded bg-zinc-900 text-[#00CC68] border border-zinc-800 tracking-wider">
              BETA
            </span>
          </Link>
          <div className="w-[1px] h-4 bg-zinc-800 mx-0.5 shrink-0 hidden sm:block" />
          <div className="truncate">
            <h1 className="font-archivo font-bold text-xs sm:text-sm text-white tracking-tight truncate">
              {projectDetail?.name || (projectId ? `${projectId}.tex` : "main.tex")}
            </h1>
            <p className="text-[10px] text-zinc-400 font-mono truncate">{projectDetail?.template || "LaTeX"} · main.tex</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Save Status Badge & Manual Save Button */}
          <div className="flex items-center gap-2">
            <span className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-900 border border-zinc-800 text-[11px] font-mono">
              {saveStatus === "saved" && (
                <>
                  <CheckCheck className="w-3.5 h-3.5 text-[#00CC68]" />
                  <span className="text-[#00CC68] font-bold">Saved</span>
                </>
              )}
              {saveStatus === "saving" && (
                <>
                  <RotateCw className="w-3.5 h-3.5 text-amber-400 animate-spin" />
                  <span className="text-amber-400 font-bold">Saving...</span>
                </>
              )}
              {saveStatus === "unsaved" && (
                <>
                  <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  <span className="text-zinc-400 font-bold">Unsaved</span>
                </>
              )}
            </span>

            {/* Files Panel Toggle Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFilesOpen(!filesOpen)}
              className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 transition-colors ${filesOpen
                ? "bg-[#00CC68]/10 hover:bg-[#00CC68]/20 border-[#00CC68]/30 text-[#00CC68] font-bold"
                : "bg-zinc-900 hover:bg-zinc-800 border-zinc-800 text-zinc-300"
                }`}
              title={filesOpen ? "Hide Project Files" : "Show Project Files"}
            >
              <FolderGit2 className="w-3.5 h-3.5 text-[#00CC68]" />
              <span>Files</span>
            </Button>

            {/* AI Assistant Toggle Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={toggleAi}
              className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 transition-colors ${aiOpen
                ? "bg-[#00CC68]/10 hover:bg-[#00CC68]/20 border-[#00CC68]/30 text-[#00CC68] font-bold"
                : "bg-zinc-900 hover:bg-zinc-800 border-zinc-800 text-zinc-300"
                }`}
              title={aiOpen ? "Hide AI Assistant (Cmd+L)" : "Show AI Assistant (Cmd+L)"}
            >
              <Bot className="w-3.5 h-3.5 text-[#00CC68]" />
              <span>Agent <span className="text-[9px] opacity-60 ml-0.5">(Cmd+L)</span></span>
            </Button>

            {/* PDF Preview Toggle Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={togglePdf}
              className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 transition-colors ${pdfOpen
                ? "bg-[#00CC68]/10 hover:bg-[#00CC68]/20 border-[#00CC68]/30 text-[#00CC68] font-bold"
                : "bg-zinc-900 hover:bg-zinc-800 border-zinc-800 text-zinc-300"
                }`}
              title={pdfOpen ? "Hide PDF Preview" : "Show PDF Preview"}
            >
              <Eye className="w-3.5 h-3.5 text-cyan-400" />
              <span>Preview</span>
            </Button>

            {/* Fullscreen Presentation Mode Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsPresentationMode(true)}
              className="h-8 px-2.5 text-xs font-mono hidden lg:flex items-center gap-1.5 transition-colors bg-zinc-900 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white cursor-pointer"
              title="Fullscreen Presentation Mode (Ctrl+Alt+P)"
            >
              <Maximize2 className="w-3.5 h-3.5 text-purple-400" />
              <span>Present</span>
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleUndo}
              className="h-8 px-2 bg-zinc-900 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white text-xs font-mono flex items-center gap-1 cursor-pointer"
              title="Undo (Ctrl+Z / Cmd+Z)"
            >
              <Undo2 className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden lg:inline">Undo</span>
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleRedo}
              className="h-8 px-2 bg-zinc-900 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white text-xs font-mono flex items-center gap-1 cursor-pointer"
              title="Redo (Ctrl+Y / Cmd+Shift+Z)"
            >
              <Redo2 className="w-3.5 h-3.5 text-orange-400" />
              <span className="hidden lg:inline">Redo</span>
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={() => saveDocument(code, true)}
              className="h-8 px-2.5 bg-zinc-900 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white text-xs font-mono flex items-center gap-1.5 cursor-pointer"
              title="Save Document (Ctrl+S)"
            >
              <Save className="w-3.5 h-3.5 text-[#00CC68]" />
              <span className="hidden sm:inline">Save</span>
            </Button>
          </div>

          <a
            href="https://github.com/abin-karukappallil/overbranch/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="hidden xl:flex items-center gap-1.5 px-2 py-1 rounded-md border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-[11px] text-zinc-400 hover:text-amber-300 font-mono transition-colors"
            title="OverBranch is in active Beta — Report any bugs on GitHub Issues"
          >
            <span className="text-[9px] font-mono font-bold text-amber-300 bg-amber-400/10 border border-amber-400/20 px-1 py-0.5 rounded">BETA</span>
            <span>Report Bug</span>
          </a>

          <CollaboratorAvatars projectId={projectId} />
        </div>
      </header>

      {/* Desktop Main Split View */}
      <div className="hidden md:flex flex-1 overflow-hidden relative">
        <div className="w-full h-full flex overflow-hidden">
          {/* Panel 1 (Far Left): Project Files & Image Uploads */}
          <ProjectFilesPanel
            projectId={projectId || "proj-1"}
            activeFilePath={activeFilePath}
            isOpen={filesOpen}
            onClose={() => setFilesOpen(false)}
            onSelectFile={(filePath) => setActiveFilePath(filePath)}
            onInsertLatexSnippet={(snippet) => insertSymbol(snippet)}
            refreshTrigger={filesRefreshTrigger}
          />

          {/* Panel 2 (Middle Left): Monaco Code Editor */}
          <div className="flex-1 min-w-[320px] bg-background flex flex-col h-full border-r border-border/40 relative">
            <div className="px-3 py-1 border-b border-border/30 bg-card/40 flex items-center justify-between font-mono text-[11px] shrink-0 overflow-hidden">
              <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none py-0.5 shrink-0 flex-nowrap">

                <button
                  type="button"
                  onClick={handleSelectAll}
                  className="px-2 py-0.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 shrink-0 font-semibold flex items-center gap-1 transition-colors"
                  title="Select All document code (Ctrl+A / Cmd+A)"
                >
                  <CheckSquare className="w-3 h-3 text-cyan-400" />
                  <span>Select All</span>
                </button>
                <button
                  type="button"
                  onClick={handleSelectLine}
                  className="px-2 py-0.5 rounded bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 shrink-0 font-semibold flex items-center gap-1 transition-colors"
                  title="Select current cursor line"
                >
                  <MousePointerClick className="w-3 h-3 text-sky-400" />
                  <span>Select Line</span>
                </button>
                <button
                  type="button"
                  onClick={handleCustomCopy}
                  className="px-2 py-0.5 rounded bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/40 shrink-0 font-semibold flex items-center gap-1 transition-colors"
                  title="Copy selected text or full document code"
                >
                  <Copy className="w-3 h-3 text-indigo-400" />
                  <span>Copy</span>
                </button>
                <button
                  type="button"
                  onClick={handleCustomPaste}
                  className="px-2 py-0.5 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 shrink-0 font-semibold flex items-center gap-1 transition-colors"
                  title="Paste clipboard text at cursor position"
                >
                  <ClipboardPaste className="w-3 h-3 text-emerald-400" />
                  <span>Paste</span>
                </button>
                <button
                  type="button"
                  onClick={handleUndo}
                  className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 shrink-0 font-semibold flex items-center gap-1 transition-colors"
                  title="Undo last change (Ctrl+Z / Cmd+Z)"
                >
                  <Undo2 className="w-3 h-3 text-amber-400" />
                  <span>Undo</span>
                </button>
                <button
                  type="button"
                  onClick={handleRedo}
                  className="px-2 py-0.5 rounded bg-orange-500/20 hover:bg-orange-500/30 text-orange-300 border border-orange-500/40 shrink-0 font-semibold flex items-center gap-1 transition-colors"
                  title="Redo change (Ctrl+Y / Cmd+Shift+Z)"
                >
                  <Redo2 className="w-3 h-3 text-orange-400" />
                  <span>Redo</span>
                </button>
                <span className="text-[10px] text-muted-foreground uppercase font-semibold shrink-0">Quick TeX:</span>
                {quickSymbols.map((sym) => (
                  <button
                    key={sym.label}
                    onClick={() => insertSymbol(sym.insert)}
                    className="px-2 py-0.5 rounded bg-muted/60 hover:bg-accent text-indigo-300 hover:text-white border border-border/40 shrink-0 transition-colors"
                  >
                    {sym.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-hidden relative">
              <Editor
                height="100%"
                defaultLanguage={activeFilePath.endsWith(".bib") ? "bibtex" : "latex"}
                theme="vs-dark"
                value={code}
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

              {/* Floating Non-Overlapping In-Editor Accept/Reject Action Bar */}
              {diffData && diffEditsList.length > 0 && (
                <div className="absolute top-3 right-4 z-20 max-w-sm p-3 rounded-xl bg-[#161b22]/95 border border-indigo-500/40 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 font-mono text-xs space-y-2">
                  <div className="flex items-center justify-between font-bold text-slate-100">
                    <div className="flex items-center gap-1.5 text-indigo-400">
                      <span>In-Editor Code Edit</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-200 border border-indigo-500/30 font-bold font-mono">
                      {getEditLineRange(diffEditsList[0].original_chunk, diffEditsList[0].proposed_chunk)}
                    </span>
                  </div>

                  {/* Red / Green Line Preview */}
                  <div className="max-h-24 overflow-y-auto bg-black/60 p-2 rounded-lg text-[10px] space-y-1 border border-border/40 font-mono">
                    {diffEditsList[0].original_chunk && (
                      <div className="text-rose-300 bg-rose-950/40 px-1.5 py-0.5 rounded line-through border-l-2 border-rose-500 truncate">
                        - {diffEditsList[0].original_chunk.split("\n")[0]}
                      </div>
                    )}
                    {diffEditsList[0].proposed_chunk && (
                      <div className="text-emerald-300 bg-emerald-950/40 px-1.5 py-0.5 rounded border-l-2 border-emerald-500 truncate">
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
                        toast.success("Copied patch to clipboard!");
                      }}
                      className="h-7 px-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-semibold flex items-center justify-center gap-1 transition-colors cursor-pointer"
                      title="Copy diff patch to clipboard"
                    >
                      <Copy className="w-3 h-3 text-zinc-300" />
                      <span>Copy</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleRejectAllEdits}
                      className="flex-1 h-7 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 text-xs font-semibold flex items-center justify-center gap-1 transition-colors cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleAcceptAllEdits(diffEditsList)}
                      className="flex-1 h-7 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center justify-center gap-1 transition-colors shadow-md shadow-emerald-600/20 cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Accept</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Panel 3 (Middle Right): PDF Viewer / Compiled Output */}
          <div
            className={`h-full bg-muted/20 transition-all duration-300 ease-in-out overflow-hidden flex flex-col min-w-0 max-w-full ${pdfOpen ? "flex-1 min-w-[280px] border-r border-border/40" : "w-0 opacity-0 pointer-events-none border-r-0"
              }`}
          >
            <div className="flex-1 h-full min-w-0 max-w-full w-full flex flex-col overflow-hidden">
              <PDFViewer
                ref={pdfViewerRef}
                pdfBase64={pdfBase64}
                isCompiling={isCompiling}
                onRecompile={() => handleCompile()}
                errorLog={errorLog}
                projectId={projectId}
                onReverseSync={handleReverseSyncJump}
                onTextSelected={handlePdfTextSelected}
                onEnterPresentation={() => setIsPresentationMode(true)}
              />
            </div>
          </div>

          {/* Panel 4 (Far Right): Agent Experience */}
          <div
            className={`h-full border-l border-zinc-800 bg-zinc-950 transition-all duration-300 ease-in-out overflow-hidden flex flex-col shrink-0 text-zinc-100 ${aiOpen ? "w-[340px] opacity-100" : "w-0 opacity-0 pointer-events-none border-l-0"
              }`}
          >
            <div className="flex flex-col h-full justify-between p-3 text-xs min-w-[340px]">
              <div className="space-y-3 flex-1 flex flex-col overflow-hidden">
                <div className="border-b border-zinc-800 pb-2.5 shrink-0 space-y-2 select-none">
                  <div className="flex items-center justify-between gap-1.5">
                    <div className="flex items-center gap-1.5 shrink-0">
                      {/* Bot Icon Dropdown for New Chat & Delete Chat */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            disabled={isAgentThinking}
                            className="p-1 rounded-lg bg-[#00CC68]/10 hover:bg-[#00CC68]/20 text-[#00CC68] border border-[#00CC68]/25 hover:border-[#00CC68]/40 transition-all cursor-pointer flex items-center justify-center shrink-0 disabled:opacity-50"
                            title="Chat options (New Chat, Delete Chat)"
                          >
                            <Bot className="w-4 h-4 text-[#00CC68]" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="bg-zinc-950 border-zinc-800 text-zinc-200 min-w-[140px] p-1 font-mono z-[99999]">
                          <DropdownMenuItem
                            onClick={handleNewChat}
                            disabled={isAgentThinking}
                            className="flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-zinc-900 hover:text-[#00CC68] cursor-pointer rounded-md focus:bg-zinc-900 focus:text-[#00CC68]"
                          >
                            <PlusCircle className="w-3.5 h-3.5 text-[#00CC68]" />
                            <span>New Chat</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={handleClearChat}
                            disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                            className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-rose-400 hover:bg-rose-950/40 hover:text-rose-300 cursor-pointer rounded-md focus:bg-rose-950/40 focus:text-rose-300"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>Delete Chat</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>

                      <ChatModeToggle mode={chatMode} onModeChange={setChatMode} disabled={isAgentThinking} />
                    </div>

                    <div className="flex items-center gap-1.5 min-w-0">
                      {/* Model Selector */}
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

                <div className="flex-1 overflow-y-auto space-y-3 pr-1 font-mono">
                  {messages.map((m) => (
                    <div
                      key={m.id}
                      className={`p-3 rounded-2xl border space-y-1.5 ${m.sender === "user"
                        ? "bg-[#00CC68]/10 border-[#00CC68]/20 text-[#00CC68] ml-4 font-mono font-bold"
                        : "bg-zinc-900 border-zinc-800 text-zinc-100 mr-4 font-sans"
                        }`}
                    >
                      <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-white">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                          {m.mode && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded font-mono uppercase text-zinc-400 bg-zinc-800/80 border border-zinc-700">
                              {m.mode}
                            </span>
                          )}
                        </div>
                        <span>{m.time}</span>
                      </div>
                      {m.sender === "assistant" ? (
                        <ChatMessageContent text={m.text} />
                      ) : (
                        <p className="leading-relaxed whitespace-pre-wrap break-words text-xs">{m.text}</p>
                      )}
                      {renderMessageEditsCard(m)}
                    </div>
                  ))}
                  {isAgentThinking && (
                    <div className="p-3 rounded-2xl bg-zinc-900 border border-[#00CC68]/30 text-zinc-100 font-mono text-[11px] space-y-2 shadow-xl animate-in fade-in slide-in-from-bottom-1">
                      <div className="flex items-center justify-between font-bold border-b border-zinc-800 pb-2 text-[#00CC68]">
                        <div className="flex items-center gap-1.5">
                          <span>AI Agent Reasoning...</span>
                        </div>
                        <button
                          type="button"
                          onClick={handleStopAgentResponse}
                          className="px-2 py-0.5 rounded bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 border border-rose-500/40 text-[10px] font-mono font-bold flex items-center gap-1 transition-colors shrink-0"
                        >
                          <Square className="w-2.5 h-2.5 fill-current text-rose-300" />
                          <span>Stop</span>
                        </button>
                      </div>

                      <div className="space-y-1 max-h-24 overflow-y-auto pr-1">
                        {agentProgressSteps.length === 0 ? (
                          <div className="flex items-center gap-2 text-[#00CC68]/80 animate-pulse py-0.5 font-mono text-[10px]">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#00CC68] animate-ping" />
                            <span>Initializing TeX intelligence engine...</span>
                          </div>
                        ) : (
                          agentProgressSteps.map((s, idx) => {
                            const isLatest = idx === agentProgressSteps.length - 1;
                            return (
                              <div
                                key={idx}
                                className={`flex items-center gap-2 transition-all font-mono text-[10px] ${isLatest
                                  ? "text-[#00CC68] font-bold animate-pulse"
                                  : "text-zinc-400 font-normal"
                                  }`}
                              >
                                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isLatest ? "bg-[#00CC68] animate-ping" : "bg-zinc-600"}`} />
                                <span className="truncate">{s.message}</span>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* Sleek Diff Control Card directly above Chat Input */}
                {diffData && diffEditsList.length > 0 && (
                  <div className="mb-2 p-3 rounded-2xl bg-zinc-900 border border-[#00CC68]/40 shadow-xl space-y-2 font-mono text-[11px] animate-in fade-in slide-in-from-bottom-2">
                    <div className="flex items-center justify-between font-bold text-[#00CC68]">
                      <div className="flex items-center gap-1.5">
                        <span>Proposed TeX Edit</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-[#00CC68]/20 text-[#00CC68] border border-[#00CC68]/30 font-bold">
                        {getEditLineRange(diffEditsList[0].original_chunk, diffEditsList[0].proposed_chunk)}
                      </span>
                    </div>

                    {/* Compact Line-by-line Preview */}
                    <div className="max-h-28 overflow-y-auto bg-black/80 p-2 rounded-xl text-[10px] space-y-1 font-mono border border-zinc-800">
                      {diffEditsList[0].original_chunk && (
                        <div className="text-rose-300 bg-rose-950/40 px-1.5 py-0.5 rounded line-through border-l-2 border-rose-500 truncate">
                          - {diffEditsList[0].original_chunk.split("\n")[0]}
                        </div>
                      )}
                      {diffEditsList[0].proposed_chunk && (
                        <div className="text-[#00CC68] bg-[#00CC68]/10 px-1.5 py-0.5 rounded border-l-2 border-[#00CC68] truncate font-bold">
                          + {diffEditsList[0].proposed_chunk.split("\n")[0]}
                        </div>
                      )}
                    </div>

                    {/* Action Buttons Directly Above Chat Input */}
                    <div className="flex items-center gap-1.5 pt-1 font-bold">
                      <button
                        type="button"
                        onClick={() => {
                          let patch = "";
                          diffEditsList.forEach((e) => {
                            if (e.original_chunk) patch += e.original_chunk.split("\n").map((l) => `-${l}`).join("\n") + "\n";
                            if (e.proposed_chunk) patch += e.proposed_chunk.split("\n").map((l) => `+${l}`).join("\n") + "\n";
                          });
                          navigator.clipboard.writeText(patch.trim());
                          toast.success("Copied patch to clipboard!");
                        }}
                        className="h-8 px-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-mono font-semibold flex items-center justify-center gap-1 transition-colors cursor-pointer"
                        title="Copy diff patch to clipboard"
                      >
                        <Copy className="w-3.5 h-3.5 text-zinc-300" />
                        <span>Copy</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleRejectAllEdits}
                        className="flex-1 h-8 rounded-xl bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                      >
                        <X className="w-3.5 h-3.5" />
                        <span>Reject</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleAcceptAllEdits(diffEditsList)}
                        className="flex-1 h-8 rounded-xl bg-[#00CC68] hover:bg-[#00E676] text-black text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-colors border border-black shadow-[2px_2px_0px_0px_#000000] cursor-pointer"
                      >
                        <Check className="w-3.5 h-3.5 text-black stroke-[3]" />
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
                    <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-[#00CC68]/10 border border-[#00CC68]/30 text-[#00CC68] text-[11px] font-mono animate-in fade-in font-bold">
                      <div className="flex items-center gap-2 truncate">
                        <Paperclip className="w-3.5 h-3.5 text-[#00CC68] shrink-0" />
                        <span className="truncate">{attachedFile.filename}</span>
                        <span className="text-[9px] text-black bg-[#00CC68] px-1.5 py-0.5 rounded font-mono font-bold uppercase">
                          {attachedFile.file_type || "file"}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setAttachedFile(null)}
                        className="p-1 text-zinc-400 hover:text-rose-400 transition-colors rounded-md cursor-pointer"
                        title="Remove attachment"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {(attachedFile.filename.toLowerCase().endsWith(".pdf") || (attachedFile.file_type && attachedFile.file_type.includes("pdf"))) && (
                      <button
                        type="button"
                        onClick={() => setChatInput("Recreate this PDF exactly as editable LaTeX.")}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#00CC68]/20 hover:bg-[#00CC68]/30 border border-[#00CC68]/40 text-[#00CC68] text-[11px] font-mono font-bold transition-all cursor-pointer shadow-sm"
                      >
                        <FileText className="w-3 h-3 text-[#00CC68]" />
                        <span> Recreate this PDF as Editable LaTeX</span>
                      </button>
                    )}
                  </div>
                )}

                <form onSubmit={handleSendPrompt} className="relative pt-3 border-t border-zinc-800 shrink-0 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isAgentThinking}
                    className="p-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-800 transition-colors disabled:opacity-50 shrink-0 cursor-pointer"
                    title="Upload file (text, TeX, code, image)"
                  >
                    <Paperclip className="w-4 h-4 text-[#00CC68]" />
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
                      className="w-full min-h-[38px] max-h-40 py-2 px-3 rounded-xl border border-zinc-800 bg-zinc-950 text-white placeholder:text-zinc-500 text-xs outline-none focus:ring-2 focus:ring-[#00CC68] transition-all disabled:opacity-50 resize-none overflow-y-auto font-mono"
                    />
                  </div>

                  {isAgentThinking ? (
                    <Button
                      type="button"
                      onClick={handleStopAgentResponse}
                      size="sm"
                      variant="destructive"
                      className="h-9 px-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-mono font-bold shrink-0 flex items-center gap-1.5 text-xs shadow-md cursor-pointer"
                    >
                      <Square className="w-3.5 h-3.5 fill-current" />
                      <span>Stop</span>
                    </Button>
                  ) : (
                    <Button
                      type="submit"
                      disabled={(!chatInput.trim() && !attachedFile) || isAgentThinking}
                      size="sm"
                      className="h-9 px-3.5 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold rounded-xl border border-black shadow-[2px_2px_0px_0px_#000000] shrink-0 flex items-center justify-center gap-1 text-xs disabled:opacity-40 cursor-pointer"
                    >
                      <Send className="w-3.5 h-3.5 text-black stroke-[3]" />
                    </Button>
                  )}
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Viewports - Keep components mounted with CSS toggle so editor state & sync are never lost */}
      <div className="flex md:hidden flex-1 min-h-0 overflow-hidden relative">
        <div className={`flex-1 flex flex-col bg-background overflow-hidden relative min-h-0 ${activeMobileTab === "files" ? "flex" : "hidden"}`}>
          <ProjectFilesPanel
            projectId={projectId || "proj-1"}
            activeFilePath={activeFilePath}
            isOpen={true}
            onClose={() => setActiveMobileTab("code")}
            onSelectFile={(filePath) => {
              setActiveFilePath(filePath);
              setActiveMobileTab("code");
            }}
            onInsertLatexSnippet={(snippet) => insertSymbol(snippet)}
            refreshTrigger={filesRefreshTrigger}
          />
        </div>

        <div className={`flex-1 flex flex-col bg-background overflow-hidden relative min-h-0 ${activeMobileTab === "code" ? "flex" : "hidden"}`}>
          <div className="px-2 py-1 border-b border-border/30 bg-card/40 flex items-center justify-between font-mono text-[11px] shrink-0 overflow-hidden">
            <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none py-0.5 shrink-0 flex-nowrap">
              <button
                type="button"
                onClick={handleSelectAll}
                className="px-2 py-1 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shrink-0 text-xs font-semibold flex items-center gap-1"
              >
                <CheckSquare className="w-3.5 h-3.5 text-cyan-400" />
                <span>Select All</span>
              </button>
              <button
                type="button"
                onClick={handleSelectLine}
                className="px-2 py-1 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40 shrink-0 text-xs font-semibold flex items-center gap-1"
              >
                <MousePointerClick className="w-3.5 h-3.5 text-sky-400" />
                <span>Select Line</span>
              </button>
              <button
                type="button"
                onClick={handleCustomCopy}
                className="px-2 py-1 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shrink-0 text-xs font-semibold flex items-center gap-1"
              >
                <Copy className="w-3.5 h-3.5 text-indigo-400" />
                <span>Copy</span>
              </button>
              <button
                type="button"
                onClick={handleCustomPaste}
                className="px-2 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shrink-0 text-xs font-semibold flex items-center gap-1"
              >
                <ClipboardPaste className="w-3.5 h-3.5 text-emerald-400" />
                <span>Paste</span>
              </button>
              <button
                type="button"
                onClick={handleUndo}
                className="px-2 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 shrink-0 text-xs font-semibold flex items-center gap-1"
                title="Undo (Ctrl+Z)"
              >
                <Undo2 className="w-3.5 h-3.5 text-amber-400" />
                <span>Undo</span>
              </button>
              <button
                type="button"
                onClick={handleRedo}
                className="px-2 py-1 rounded bg-orange-500/20 text-orange-300 border border-orange-500/40 shrink-0 text-xs font-semibold flex items-center gap-1"
                title="Redo (Ctrl+Y)"
              >
                <Redo2 className="w-3.5 h-3.5 text-orange-400" />
                <span>Redo</span>
              </button>
              {quickSymbols.map((sym) => (
                <button
                  key={sym.label}
                  onClick={() => insertSymbol(sym.insert)}
                  className="px-2 py-1 rounded bg-muted/60 text-indigo-300 border border-border/40 shrink-0 text-xs"
                >
                  {sym.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden relative">
            <EditorErrorBoundary>
              <Editor
                height="100%"
                defaultLanguage={activeFilePath.endsWith(".bib") ? "bibtex" : "latex"}
                theme="vs-dark"
                value={code}
                onMount={(editor, monaco) => handleEditorMount(editor, monaco, false)}
                onChange={handleCodeChange}
                options={{
                  minimap: { enabled: false },
                  fontSize: 14,
                  wordWrap: "on",
                  automaticLayout: true,
                  contextmenu: false,
                }}
              />
            </EditorErrorBoundary>
            {diffData && diffEditsList.length > 0 && (
              <div className="absolute top-2 right-2 z-30 max-w-[240px] p-2 rounded-xl bg-[#161b22]/95 border border-indigo-500/40 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 font-mono text-xs space-y-1.5">
                <div className="flex items-center justify-between font-bold text-slate-100">
                  <div className="flex items-center gap-1.5 text-indigo-400">
                    <span>Pending Edit</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleRejectAllEdits}
                    className="flex-1 h-7 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 text-xs font-semibold flex items-center justify-center gap-1 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Reject</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAcceptAllEdits(diffEditsList)}
                    className="flex-1 h-7 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center justify-center gap-1 transition-colors shadow-md shadow-emerald-600/20"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Accept</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className={`flex-1 flex flex-col bg-zinc-950 overflow-hidden min-h-0 ${activeMobileTab === "pdf" ? "flex" : "hidden"}`}>
          <PDFViewer
            ref={pdfViewerRef}
            pdfBase64={pdfBase64}
            isCompiling={isCompiling}
            onRecompile={() => handleCompile()}
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

        <div className={`flex-1 flex flex-col bg-zinc-950 overflow-hidden relative min-h-0 p-3 space-y-3 text-zinc-100 font-sans ${activeMobileTab === "ai" ? "flex" : "hidden"}`}>
          <div className="border-b border-zinc-800 pb-2.5 shrink-0 space-y-2 select-none">
              <div className="flex items-center justify-between gap-1.5">
                <div className="flex items-center gap-1.5 shrink-0">
                  {/* Bot Icon Dropdown for New Chat & Delete Chat */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        disabled={isAgentThinking}
                        className="p-1 rounded-lg bg-[#00CC68]/10 hover:bg-[#00CC68]/20 text-[#00CC68] border border-[#00CC68]/25 hover:border-[#00CC68]/40 transition-all cursor-pointer flex items-center justify-center shrink-0 disabled:opacity-50"
                        title="Chat options (New Chat, Delete Chat)"
                      >
                        <Bot className="w-4 h-4 text-[#00CC68]" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="bg-zinc-950 border-zinc-800 text-zinc-200 min-w-[140px] p-1 font-mono z-[99999]">
                      <DropdownMenuItem
                        onClick={handleNewChat}
                        disabled={isAgentThinking}
                        className="flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-zinc-900 hover:text-[#00CC68] cursor-pointer rounded-md focus:bg-zinc-900 focus:text-[#00CC68]"
                      >
                        <PlusCircle className="w-3.5 h-3.5 text-[#00CC68]" />
                        <span>New Chat</span>
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={handleClearChat}
                        disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                        className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-rose-400 hover:bg-rose-950/40 hover:text-rose-300 cursor-pointer rounded-md focus:bg-rose-950/40 focus:text-rose-300"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete Chat</span>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <ChatModeToggle mode={chatMode} onModeChange={setChatMode} disabled={isAgentThinking} />
                </div>
                <div className="flex items-center gap-1.5 min-w-0">
                  {/* Model Selector */}
                  <ModelSelector
                    activeModelName={activeModelName}
                    onSelectModel={setActiveModelName}
                    availableModels={availableModels}
                    disabled={isAgentThinking}
                  />
                </div>
              </div>

              {fallbackModelNotice && (
                <div className="px-2.5 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-center justify-between gap-2 shrink-0">
                  <div className="flex items-center gap-1.5 truncate">
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                    <span className="truncate">{fallbackModelNotice}</span>
                  </div>
                  <button onClick={() => setFallbackModelNotice(null)} className="text-amber-400 hover:text-white p-0.5 cursor-pointer">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 text-xs font-mono min-h-0 pr-1">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`p-3 rounded-2xl border space-y-1.5 ${m.sender === "user"
                    ? "bg-[#00CC68]/10 border-[#00CC68]/20 text-[#00CC68] ml-4 font-mono font-bold"
                    : "bg-zinc-900 border-zinc-800 text-zinc-100 mr-4 font-sans"
                    }`}
                >
                  <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-white">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                      {m.mode && (
                        <span className="text-[9px] px-1.5 py-0.2 rounded font-mono uppercase text-zinc-400 bg-zinc-800/80 border border-zinc-700">
                          {m.mode}
                        </span>
                      )}
                    </div>
                    <span>{m.time}</span>
                  </div>
                  {m.sender === "assistant" ? (
                    <ChatMessageContent text={m.text} />
                  ) : (
                    <p className="leading-relaxed text-xs whitespace-pre-wrap break-words">{m.text}</p>
                  )}
                  {renderMessageEditsCard(m)}
                </div>
              ))}
              {isAgentThinking && (
                <div className="p-3 rounded-2xl bg-zinc-900 border border-[#00CC68]/30 text-zinc-100 font-mono text-xs space-y-2 shadow-xl animate-in fade-in slide-in-from-bottom-1">
                  <div className="flex items-center justify-between font-bold border-b border-zinc-800 pb-2 text-[#00CC68]">
                    <div className="flex items-center gap-1.5">
                      <Zap className="w-4 h-4 text-[#00CC68] animate-pulse shrink-0" />
                      <span>AI Agent Reasoning...</span>
                    </div>
                    <button
                      type="button"
                      onClick={handleStopAgentResponse}
                      className="px-2 py-0.5 rounded bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 border border-rose-500/40 text-xs font-mono font-bold flex items-center gap-1 transition-colors shrink-0 cursor-pointer"
                    >
                      <Square className="w-3 h-3 fill-current text-rose-300" />
                      <span>Stop</span>
                    </button>
                  </div>

                  <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                    {agentProgressSteps.length === 0 ? (
                      <div className="flex items-center gap-2 text-[#00CC68]/80 animate-pulse py-0.5 font-mono text-xs">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#00CC68] animate-ping" />
                        <span>Initializing TeX intelligence engine...</span>
                      </div>
                    ) : (
                      agentProgressSteps.map((s, idx) => {
                        const isLatest = idx === agentProgressSteps.length - 1;
                        return (
                          <div
                            key={idx}
                            className={`flex items-center gap-2 transition-all font-mono text-xs ${isLatest
                              ? "text-[#00CC68] font-bold animate-pulse"
                              : "text-zinc-400 font-normal"
                              }`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isLatest ? "bg-[#00CC68] animate-ping" : "bg-zinc-600"}`} />
                            <span className="truncate">{s.message}</span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
              <div ref={mobileChatEndRef} />
            </div>

            {diffData && diffEditsList.length > 0 && (
              <div className="mb-2 p-3 rounded-2xl bg-zinc-900 border border-[#00CC68]/40 shadow-xl space-y-2 font-mono text-xs shrink-0 animate-in fade-in slide-in-from-bottom-2">
                <div className="flex items-center justify-between font-bold text-[#00CC68]">
                  <div className="flex items-center gap-1.5">
                    <Zap className="w-3.5 h-3.5 text-[#00CC68]" />
                    <span>Proposed TeX Edit</span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-[#00CC68]/20 text-[#00CC68] border border-[#00CC68]/30 font-bold">
                    {getEditLineRange(diffEditsList[0].original_chunk, diffEditsList[0].proposed_chunk)}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 pt-1 font-bold">
                  <button
                    type="button"
                    onClick={() => {
                      let patch = "";
                      diffEditsList.forEach((e) => {
                        if (e.original_chunk) patch += e.original_chunk.split("\n").map((l) => `-${l}`).join("\n") + "\n";
                        if (e.proposed_chunk) patch += e.proposed_chunk.split("\n").map((l) => `+${l}`).join("\n") + "\n";
                      });
                      navigator.clipboard.writeText(patch.trim());
                      toast.success("Copied patch to clipboard!");
                    }}
                    className="h-8 px-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-mono flex items-center justify-center gap-1 transition-colors cursor-pointer"
                    title="Copy diff patch"
                  >
                    <Copy className="w-3.5 h-3.5 text-zinc-300" />
                    <span>Copy</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleRejectAllEdits}
                    className="flex-1 h-8 rounded-xl bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Reject</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAcceptAllEdits(diffEditsList)}
                    className="flex-1 h-8 rounded-xl bg-[#00CC68] hover:bg-[#00E676] text-black text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-colors border border-black shadow-[2px_2px_0px_0px_#000000] cursor-pointer"
                  >
                    <Check className="w-3.5 h-3.5 text-black stroke-[3]" />
                    <span>Accept All</span>
                  </button>
                </div>
              </div>
            )}

            {attachedFile && (
              <div className="space-y-1.5 mb-2">
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-[#00CC68]/10 border border-[#00CC68]/30 text-[#00CC68] text-xs font-mono animate-in fade-in font-bold">
                  <div className="flex items-center gap-2 truncate">
                    <Paperclip className="w-3.5 h-3.5 text-[#00CC68] shrink-0" />
                    <span className="truncate">{attachedFile.filename}</span>
                    <span className="text-[9px] text-black bg-[#00CC68] px-1.5 py-0.5 rounded font-mono font-bold uppercase">
                      {attachedFile.file_type || "file"}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setAttachedFile(null)}
                    className="p-1 text-zinc-400 hover:text-rose-400 transition-colors rounded-md cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                {(attachedFile.filename.toLowerCase().endsWith(".pdf") || (attachedFile.file_type && attachedFile.file_type.includes("pdf"))) && (
                  <button
                    type="button"
                    onClick={() => setChatInput("Recreate this PDF exactly as editable LaTeX.")}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#00CC68]/20 hover:bg-[#00CC68]/30 border border-[#00CC68]/40 text-[#00CC68] text-[11px] font-mono font-bold transition-all cursor-pointer shadow-sm"
                  >
                    <FileText className="w-3 h-3 text-[#00CC68]" />
                    <span>✨ Recreate this PDF as Editable LaTeX</span>
                  </button>
                )}
              </div>
            )}

            <form onSubmit={handleSendPrompt} className="relative pt-3 border-t border-zinc-800 shrink-0 flex items-center gap-2 font-mono">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isAgentThinking}
                className="p-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-800 shrink-0 cursor-pointer disabled:opacity-50"
                title="Upload file"
              >
                <Paperclip className="w-4 h-4 text-[#00CC68]" />
              </button>

              <textarea
                id="ai-chat-input-2"
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
                className="flex-1 min-h-[42px] max-h-40 py-2.5 px-3 rounded-xl border border-zinc-800 bg-zinc-950 text-white placeholder:text-zinc-500 text-xs outline-none focus:ring-2 focus:ring-[#00CC68] transition-all disabled:opacity-50 resize-none overflow-y-auto font-mono"
              />

              {isAgentThinking ? (
                <Button
                  type="button"
                  onClick={handleStopAgentResponse}
                  size="sm"
                  variant="destructive"
                  className="h-11 px-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-mono font-bold shrink-0 flex items-center gap-1 text-xs cursor-pointer"
                >
                  <Square className="w-4 h-4 fill-current" />
                  <span>Stop</span>
                </Button>
              ) : (
                <Button
                  type="submit"
                  disabled={(!chatInput.trim() && !attachedFile) || isAgentThinking}
                  size="sm"
                  className="h-11 px-4 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold rounded-xl border border-black shadow-[2px_2px_0px_0px_#000000] shrink-0 flex items-center justify-center disabled:opacity-40 cursor-pointer"
                >
                  <Send className="w-4 h-4 text-black stroke-[3]" />
                </Button>
              )}
            </form>
          </div>
        </div>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden border-t border-zinc-800 bg-zinc-950/95 backdrop-blur-xl shrink-0 z-40 pb-[env(safe-area-inset-bottom,0px)]">
        <div className="flex items-center justify-around w-full h-14 font-mono">
          <button
            onClick={() => setActiveMobileTab("files")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "files" ? "text-[#00CC68] font-bold" : "text-zinc-400"
              }`}
          >
            <FolderGit2 className="w-4 h-4" />
            <span>Files</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("code")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "code" ? "text-[#00CC68] font-bold" : "text-zinc-400"
              }`}
          >
            <FileCode2 className="w-4 h-4" />
            <span>Code</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("pdf")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "pdf" ? "text-cyan-400 font-bold" : "text-zinc-400"
              }`}
          >
            <Eye className="w-4 h-4" />
            <span>PDF</span>
          </button>

          <button
            onClick={() => {
              setActiveMobileTab("ai");
            }}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${activeMobileTab === "ai" ? "text-[#00CC68] font-bold" : "text-zinc-400"
              }`}
          >
            <Bot className="w-4 h-4" />
            <span>Agent</span>
          </button>
        </div>
      </nav>

      {/* Mobile AI Assistant Drawer */}
      <Drawer.Root open={mobileDrawerOpen} onOpenChange={setMobileDrawerOpen}>
        <Drawer.Portal>
          <Drawer.Overlay className="fixed inset-0 bg-black/60 z-50 backdrop-blur-sm" />
          <Drawer.Content className="fixed inset-0 z-50 bg-zinc-950 flex flex-col p-4 space-y-3 text-zinc-100 font-sans h-[100dvh] max-h-[100dvh]">
            <div className="w-12 h-1.5 rounded-full bg-zinc-800 mx-auto shrink-0" />
            <div className="border-b border-zinc-800 pb-2.5 shrink-0 space-y-2 select-none">
              <div className="flex items-center justify-between gap-1.5">
                <div className="flex items-center gap-1.5 shrink-0">
                  {/* Bot Icon Dropdown for New Chat & Delete Chat */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        disabled={isAgentThinking}
                        className="p-1 rounded-lg bg-[#00CC68]/10 hover:bg-[#00CC68]/20 text-[#00CC68] border border-[#00CC68]/25 hover:border-[#00CC68]/40 transition-all cursor-pointer flex items-center justify-center shrink-0 disabled:opacity-50"
                        title="Chat options (New Chat, Delete Chat)"
                      >
                        <Bot className="w-5 h-5 text-[#00CC68]" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="bg-zinc-950 border-zinc-800 text-zinc-200 min-w-[140px] p-1 font-mono z-[99999]">
                      <DropdownMenuItem
                        onClick={handleNewChat}
                        disabled={isAgentThinking}
                        className="flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-zinc-900 hover:text-[#00CC68] cursor-pointer rounded-md focus:bg-zinc-900 focus:text-[#00CC68]"
                      >
                        <PlusCircle className="w-3.5 h-3.5 text-[#00CC68]" />
                        <span>New Chat</span>
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={handleClearChat}
                        disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                        className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-rose-400 hover:bg-rose-950/40 hover:text-rose-300 cursor-pointer rounded-md focus:bg-rose-950/40 focus:text-rose-300"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete Chat</span>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <ChatModeToggle mode={chatMode} onModeChange={setChatMode} disabled={isAgentThinking} />
                </div>
                <div className="flex items-center gap-1.5 min-w-0">
                  {/* Model Selector */}
                  <ModelSelector
                    activeModelName={activeModelName}
                    onSelectModel={setActiveModelName}
                    availableModels={availableModels}
                    disabled={isAgentThinking}
                  />

                  <button onClick={() => setMobileDrawerOpen(false)} className="text-zinc-400 hover:text-white p-1 cursor-pointer shrink-0">
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {fallbackModelNotice && (
                <div className="px-2.5 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-center justify-between gap-2 shrink-0">
                  <div className="flex items-center gap-1.5 truncate">
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                    <span className="truncate">{fallbackModelNotice}</span>
                  </div>
                  <button onClick={() => setFallbackModelNotice(null)} className="text-amber-400 hover:text-white p-0.5 cursor-pointer">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 text-xs font-mono">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`p-3 rounded-2xl border space-y-1.5 ${m.sender === "user"
                    ? "bg-[#00CC68]/10 border-[#00CC68]/20 text-[#00CC68] ml-4 font-mono font-bold"
                    : "bg-zinc-900 border-zinc-800 text-zinc-100 mr-4 font-sans"
                    }`}
                >
                  <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono">
                    <span className="font-bold text-white">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                    <span>{m.time}</span>
                  </div>
                  <p className="leading-relaxed text-sm whitespace-pre-wrap break-words">{m.text}</p>
                  {renderMessageEditsCard(m)}
                </div>
              ))}
              {isAgentThinking && (
                <div className="p-3 rounded-2xl bg-zinc-900 border border-[#00CC68]/30 text-zinc-100 font-mono text-xs space-y-2 shadow-xl animate-in fade-in slide-in-from-bottom-1">
                  <div className="flex items-center justify-between font-bold border-b border-zinc-800 pb-2 text-[#00CC68]">
                    <div className="flex items-center gap-1.5">
                      <Zap className="w-4 h-4 text-[#00CC68] animate-pulse shrink-0" />
                      <span>AI Agent Reasoning...</span>
                    </div>
                    <button
                      type="button"
                      onClick={handleStopAgentResponse}
                      className="px-2 py-1 rounded bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 border border-rose-500/40 text-xs font-mono font-bold flex items-center gap-1 transition-colors shrink-0 cursor-pointer"
                    >
                      <Square className="w-3 h-3 fill-current text-rose-300" />
                      <span>Stop</span>
                    </button>
                  </div>

                  <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                    {agentProgressSteps.length === 0 ? (
                      <div className="flex items-center gap-2 text-[#00CC68]/80 animate-pulse py-0.5 font-mono text-xs">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#00CC68] animate-ping" />
                        <span>Initializing TeX intelligence engine...</span>
                      </div>
                    ) : (
                      agentProgressSteps.map((s, idx) => {
                        const isLatest = idx === agentProgressSteps.length - 1;
                        return (
                          <div
                            key={idx}
                            className={`flex items-center gap-2 transition-all font-mono text-xs ${isLatest
                              ? "text-[#00CC68] font-bold animate-pulse"
                              : "text-zinc-400 font-normal"
                              }`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isLatest ? "bg-[#00CC68] animate-ping" : "bg-zinc-600"}`} />
                            <span className="truncate">{s.message}</span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
              <div ref={mobileChatEndRef} />
            </div>

            {attachedFile && (
              <div className="space-y-1.5 mb-2">
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-[#00CC68]/10 border border-[#00CC68]/30 text-[#00CC68] text-xs font-mono animate-in fade-in font-bold">
                  <div className="flex items-center gap-2 truncate">
                    <Paperclip className="w-4 h-4 text-[#00CC68] shrink-0" />
                    <span className="truncate">{attachedFile.filename}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setAttachedFile(null)}
                    className="p-1 text-zinc-400 hover:text-rose-400 transition-colors rounded-md cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {(attachedFile.filename.toLowerCase().endsWith(".pdf") || (attachedFile.file_type && attachedFile.file_type.includes("pdf"))) && (
                  <button
                    type="button"
                    onClick={() => setChatInput("Recreate this PDF exactly as editable LaTeX.")}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#00CC68]/20 hover:bg-[#00CC68]/30 border border-[#00CC68]/40 text-[#00CC68] text-[11px] font-mono font-bold transition-all cursor-pointer shadow-sm"
                  >
                    <FileText className="w-3 h-3 text-[#00CC68]" />
                    <span>✨ Recreate this PDF as Editable LaTeX</span>
                  </button>
                )}
              </div>
            )}

            <form onSubmit={handleSendPrompt} className="relative pt-3 border-t border-zinc-800 shrink-0 flex items-center gap-2 font-mono">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isAgentThinking}
                className="p-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-800 shrink-0 cursor-pointer disabled:opacity-50"
                title="Upload file"
              >
                <Paperclip className="w-4 h-4 text-[#00CC68]" />
              </button>

              <textarea
                id="mobile-ai-chat-input"
                rows={1}
                placeholder="Ask agent to edit LaTeX..."
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
                className="flex-1 min-h-[42px] max-h-40 py-2.5 px-3 rounded-xl border border-zinc-800 bg-zinc-950 text-white placeholder:text-zinc-500 text-xs outline-none focus:ring-2 focus:ring-[#00CC68] transition-all disabled:opacity-50 resize-none overflow-y-auto font-mono"
              />

              {isAgentThinking ? (
                <Button
                  type="button"
                  onClick={handleStopAgentResponse}
                  size="sm"
                  variant="destructive"
                  className="h-11 px-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-mono font-bold flex items-center gap-1 text-xs shrink-0 cursor-pointer"
                >
                  <Square className="w-4 h-4 fill-current" />
                  <span>Stop</span>
                </Button>
              ) : (
                <Button
                  type="submit"
                  disabled={(!chatInput.trim() && !attachedFile) || isAgentThinking}
                  size="sm"
                  className="h-11 px-4 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold rounded-xl border border-black shadow-[2px_2px_0px_0px_#000000] shrink-0 flex items-center justify-center disabled:opacity-40 cursor-pointer"
                >
                  <Send className="w-4 h-4 text-black stroke-[3]" />
                </Button>
              )}
            </form>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Fullscreen Presentation Mode View */}
      {isPresentationMode && (
        <PresentationView
          blobUrl={pdfViewerRef.current?.getBlobUrl() || null}
          onExit={() => setIsPresentationMode(false)}
        />
      )}
    </div>
  );
}
