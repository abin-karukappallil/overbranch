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
} from "lucide-react";
import { CollaboratorAvatars } from "@/components/editor/CollaboratorAvatars";
import { PDFViewer } from "@/components/editor/PDFViewer";
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
import { trpc } from "@/trpc/client";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { FolderGit2 } from "lucide-react";

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

interface EditorLayoutProps {
  projectId?: string;
}

interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  text: string;
  time: string;
  edits?: EditItem[];
  isApplied?: boolean;
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

// ─── Model Selector Types & Config ───────────────────────────────────────────
interface ModelOption {
  id: string;
  label: string;
  default?: boolean;
}

interface ProviderGroup {
  name: string;
  models: ModelOption[];
}

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

export function EditorLayout({ projectId }: EditorLayoutProps) {
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
  const [activeModelName, setActiveModelName] = useState<string>("auto:smart");
  const [fallbackModelNotice, setFallbackModelNotice] = useState<string | null>(null);
  const [agentProgressSteps, setAgentProgressSteps] = useState<{step: string; message: string; icon: string}[]>([]);
  const monacoRef = useRef<any>(null);

  // ─── Model Selector State ────────────────────────────────────────────────
  const [modelSelectorOpen, setModelSelectorOpen] = useState<boolean>(false);
  const [availableModels, setAvailableModels] = useState<ProviderGroup[]>([]);

  // Fetch available models from backend on mount
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/models`);
        if (res.ok) {
          const data: ModelsResponse = await res.json();
          setAvailableModels(data.providers || []);
          if (data.default_model) {
            setActiveModelName(data.default_model);
          }
        }
      } catch (err) {
        console.warn("Failed to fetch models:", err);
        // Fallback: hardcode defaults so selector still works
        setAvailableModels([
          { name: "FreeLLM API", models: [
            { id: "auto:smart", label: "FreeLLM Auto Smart", default: true },
            { id: "auto", label: "FreeLLM Auto Router" },
            { id: "auto:fast", label: "FreeLLM Auto Fast" },
            { id: "openai/gpt-oss-120b", label: "GPT-OSS-120B" },
          ]},
          { name: "Gemini", models: [
            { id: "gemini-3.7-flash", label: "Gemini 3.7 Flash" },
            { id: "gemini-3.6-flash", label: "Gemini 3.6 Flash" },
            { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash" },
            { id: "gemini-3.5-flash-thinking", label: "Gemini 3.5 Flash Thinking" },
            { id: "gemini-3.5-flash-thinking-lite", label: "Gemini 3.5 Flash Thinking Lite" },
          ]},
        ]);
      }
    };
    fetchModels();
  }, []);

  // Helper: get display label for a model ID
  const getModelLabel = (modelId: string): string => {
    for (const provider of availableModels) {
      for (const m of provider.models) {
        if (m.id === modelId) return m.label;
      }
    }
    return modelId;
  };

  const renderModelSelectorModal = () => {
    if (!modelSelectorOpen) return null;
    return (
      <div 
        className="fixed inset-0 z-[99999] bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
        onPointerDown={(e) => { e.stopPropagation(); setModelSelectorOpen(false); }}
        onClick={(e) => { e.stopPropagation(); setModelSelectorOpen(false); }}
      >
        <div 
          className="w-80 max-w-[92vw] bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl overflow-hidden p-3 space-y-3 animate-in zoom-in-95 duration-150 font-sans"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5 select-none">
            <div className="flex items-center gap-2 font-archivo uppercase text-white font-bold text-xs tracking-wide">
              <span>Select AI Model</span>
            </div>
            <button 
              type="button"
              onPointerDown={(e) => { e.stopPropagation(); setModelSelectorOpen(false); }}
              onClick={(e) => { e.stopPropagation(); setModelSelectorOpen(false); }}
              className="p-1 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="max-h-[60vh] overflow-y-auto space-y-3 pr-1">
            {availableModels.map((provider) => (
              <div key={provider.name} className="space-y-1.5">
                <div className="text-[10px] font-archivo uppercase tracking-widest text-[#00CC68] font-bold px-1">
                  {provider.name}
                </div>
                <div className="space-y-1">
                  {provider.models.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        setActiveModelName(m.id);
                        setModelSelectorOpen(false);
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveModelName(m.id);
                        setModelSelectorOpen(false);
                      }}
                      className={`w-full text-left px-3 py-2.5 rounded-xl text-xs font-mono flex items-center justify-between gap-3 transition-all cursor-pointer ${
                        activeModelName === m.id
                          ? "bg-[#00CC68]/20 text-[#00CC68] font-bold border border-[#00CC68]/40"
                          : "bg-zinc-950/60 text-zinc-300 hover:bg-zinc-800 hover:text-white border border-zinc-800/80"
                      }`}
                    >
                      <span className="truncate">
                        {m.label}{m.default ? " (Default)" : ""}
                      </span>
                      {activeModelName === m.id && <Check className="w-3.5 h-3.5 text-[#00CC68] shrink-0 stroke-[3]" />}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

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
    } catch (_) {}
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
      } catch (_) {}
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
      const selectedText = selection && model ? model.getValueInRange(selection) : "";
      const textToCopy = selectedText || editor.getValue();

      if (!textToCopy) {
        toast.info("Nothing to copy.");
        return;
      }

      try {
        await navigator.clipboard.writeText(textToCopy);
        toast.success(selectedText ? "Copied selected code!" : "Copied full document code!");
        return;
      } catch (err) {
        console.warn("Clipboard write API error:", err);
      }
    } else if (code) {
      try {
        await navigator.clipboard.writeText(code);
        toast.success("Copied code to clipboard!");
        return;
      } catch (err) {}
    }
    toast.error("Unable to access clipboard for copy.");
  };

  const handleCustomPaste = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.readText) {
        const text = await navigator.clipboard.readText();
        if (text) {
          insertSymbol(text);
          toast.success("Pasted text into TeX editor at cursor!");
          return;
        }
      }
    } catch (err) {
      console.warn("Direct clipboard read blocked by browser permissions:", err);
    }
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
          setMobileDrawerOpen((prev) => {
            const next = !prev;
            if (next) {
              setTimeout(() => {
                const inputEl = document.getElementById("mobile-ai-chat-input");
                if (inputEl) inputEl.focus();
              }, 150);
            }
            return next;
          });
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

  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    setupDefaultLatexSyntaxAndEmeraldTheme(monaco, editor);

    editor.onDidChangeCursorSelection((e) => {
      if (e.selection) {
        lastSelectionRef.current = e.selection;
      }
    });

    editor.onDidChangeCursorPosition((e) => {
      if (e.position) {
        lastPositionRef.current = e.position;
      }
    });

    // Safely attach paste listener to container DOM node to handle mobile/Gboard clipboard paste operations without crashing Monaco
    try {
      const containerNode = editor.getContainerDomNode();
      if (containerNode) {
        containerNode.addEventListener(
          "paste",
          (e: ClipboardEvent) => {
            try {
              const pastedText = e.clipboardData?.getData("text/plain");
              if (pastedText !== undefined && pastedText !== null && editorRef.current) {
                const activeEd = editorRef.current;
                const selection = activeEd.getSelection();
                if (selection) {
                  e.preventDefault();
                  e.stopPropagation();
                  activeEd.executeEdits("safe-mobile-paste", [
                    {
                      range: selection,
                      text: pastedText,
                      forceMoveMarkers: true,
                    },
                  ]);
                  handleCodeChange(activeEd.getValue());
                }
              }
            } catch (pasteErr) {
              console.warn("Handled mobile paste fallback exception:", pasteErr);
            }
          },
          true
        );
      }
    } catch (err) {
      console.warn("Failed to attach paste event listener:", err);
    }

    try {
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyC, () => {
        handleCustomCopy();
      });
    } catch (e) {}

    // Register Ctrl+S / Cmd+S save shortcut inside Monaco Editor
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      const currentVal = editor.getValue();
      saveDocument(currentVal, true);
      handleCompile(currentVal);
    });
  };

  const syncVectorDatabase = async (updatedCode: string) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/sync-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId || "00000000-0000-0000-0000-000000000000",
          file_path: "main.tex",
          new_code: updatedCode,
        }),
      });
      const data = await response.json();
      if (data.synced) {
        setSaveStatus("saved");
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
          engine: "latexmk",
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
        try { reader.cancel(); } catch (_) {}
        try { reader.releaseLock(); } catch (_) {}
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

      // Build explicit edits list
      let editsList: EditItem[] = (data.edits && Array.isArray(data.edits) && data.edits.length > 0)
        ? data.edits
          .filter((e: any) => e.original_chunk || e.proposed_chunk)
          .map((e: any, idx: number) => ({
            id: `edit-${Date.now()}-${idx}`,
            original_chunk: e.original_chunk || "",
            proposed_chunk: e.proposed_chunk || "",
            explanation: sanitizeChunkReferences(e.explanation || rawExplanation),
          }))
        : (data.original_chunk || data.proposed_chunk)
          ? [{
            id: `edit-${Date.now()}-0`,
            original_chunk: data.original_chunk || "",
            proposed_chunk: data.proposed_chunk || "",
            explanation: sanitizeChunkReferences(data.explanation || "AI Proposed Edit"),
          }]
          : [];

      // Fallback: extract LaTeX from raw explanation
      if (editsList.length === 0) {
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

  const handleAcceptDiff = (originalChunk: string, proposedChunk: string) => {
    let updatedCode = code;
    const model = editorRef.current?.getModel?.();

    if (model) {
      const currentText = model.getValue();

      const escapedSearch = originalChunk
        ? originalChunk.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
        : '';
      const regex = escapedSearch ? new RegExp(escapedSearch, 'gi') : null;

      if (originalChunk && regex && regex.test(currentText)) {
        updatedCode = replaceAllCaseInsensitive(currentText, originalChunk, proposedChunk);
      } else {
        const selection = editorRef.current?.getSelection?.();
        if (selection && !selection.isEmpty()) {
          editorRef.current.executeEdits("ai-agent", [
            { range: selection, text: proposedChunk, forceMoveMarkers: true },
          ]);
          updatedCode = model.getValue();
        } else {
          updatedCode = insertSnippetSafely(currentText, proposedChunk);
        }
      }
      model.setValue(updatedCode);
    } else {
      const escapedSearch = originalChunk
        ? originalChunk.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
        : '';
      const regex = escapedSearch ? new RegExp(escapedSearch, 'gi') : null;

      if (originalChunk && regex && regex.test(code)) {
        updatedCode = replaceAllCaseInsensitive(code, originalChunk, proposedChunk);
      } else {
        updatedCode = insertSnippetSafely(code, proposedChunk);
      }
    }

    setCode(updatedCode);
    setDiffData(null);
    toast.success("Accepted AI changes into LaTeX editor!");

    // Save & Sync
    saveDocument(updatedCode, true);

    // Recompile PDF
    handleCompile(updatedCode);
  };

  const handleAcceptAllEdits = (itemsToApply: EditItem[], msgId?: string) => {
    const model = editorRef.current?.getModel?.();
    let updatedCode = model ? model.getValue() : code;

    itemsToApply.forEach((item) => {
      const orig = item.original_chunk;
      const prop = item.proposed_chunk;

      if (orig && updatedCode.includes(orig)) {
        updatedCode = replaceAllCaseInsensitive(updatedCode, orig, prop);
      } else if (prop) {
        updatedCode = insertSnippetSafely(updatedCode, prop);
      }
    });

    if (model) {
      model.setValue(updatedCode);
    }

    setCode(updatedCode);
    setDiffData(null);
    setDiffEditsList([]);

    if (msgId) {
      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, isApplied: true } : m))
      );
    } else {
      setMessages((prev) =>
        prev.map((m) => (m.edits && m.edits.length > 0 ? { ...m, isApplied: true } : m))
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
    const model = editorRef.current?.getModel?.();
    let updatedCode = model ? model.getValue() : code;
    const orig = item.original_chunk;
    const prop = item.proposed_chunk;

    if (orig && updatedCode.includes(orig)) {
      updatedCode = replaceAllCaseInsensitive(updatedCode, orig, prop);
    } else if (prop) {
      updatedCode = insertSnippetSafely(updatedCode, prop);
    }

    if (model) {
      model.setValue(updatedCode);
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
          <div className="text-[11px] text-[#00CC68] font-mono font-bold flex items-center gap-1 pt-0.5">
            <Check className="w-3.5 h-3.5" />
            <span>Applied changes to TeX editor</span>
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
      <header className="h-14 border-b border-zinc-800 bg-zinc-950 px-3 sm:px-4 flex items-center justify-between gap-2 shrink-0 z-10 select-none">
        <div className="flex items-center gap-2 overflow-hidden">
          <Link href="/dashboard" className="shrink-0 hover:opacity-90 transition-opacity">
            <OverBranchLogo size="sm" variant="icon" colored />
          </Link>
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
                onMount={handleEditorMount}
                onChange={handleCodeChange}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  automaticLayout: true,
                  contextmenu: false,
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

                  {/* Accept / Reject Buttons */}
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      onClick={handleRejectAllEdits}
                      className="flex-1 h-7 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleAcceptAllEdits(diffEditsList)}
                      className="flex-1 h-7 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-md shadow-emerald-600/20"
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
                pdfBase64={pdfBase64}
                isCompiling={isCompiling}
                onRecompile={() => handleCompile()}
                errorLog={errorLog}
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
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-archivo uppercase text-white font-bold text-xs">
                      <Bot className="w-4 h-4 text-[#00CC68]" />
                      <span>Agent</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {/* New Chat Button */}
                      <button
                        type="button"
                        onClick={handleNewChat}
                        disabled={isAgentThinking}
                        className="px-2 py-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-[#00CC68] border border-zinc-800 text-[10px] font-mono font-bold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50"
                        title="Start new chat session"
                      >
                        <PlusCircle className="w-3.5 h-3.5 text-[#00CC68]" />
                        <span>New</span>
                      </button>

                      {/* Clear / Delete Chat Button */}
                      <button
                        type="button"
                        onClick={handleClearChat}
                        disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                        className="p-1.5 rounded-lg bg-zinc-900 hover:bg-rose-950/50 text-zinc-400 hover:text-rose-400 border border-zinc-800 text-[10px] font-mono transition-colors cursor-pointer disabled:opacity-30"
                        title="Delete chat history and document context"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>

                      {/* Model Selector */}
                      <button
                        type="button"
                        onPointerDown={(e) => {
                          if (!isAgentThinking) {
                            e.stopPropagation();
                            setModelSelectorOpen(true);
                          }
                        }}
                        onClick={(e) => {
                          if (!isAgentThinking) {
                            e.stopPropagation();
                            setModelSelectorOpen(true);
                          }
                        }}
                        disabled={isAgentThinking}
                        className={`flex items-center gap-1.5 px-2 py-1 rounded-lg bg-[#00CC68]/10 text-[#00CC68] font-mono text-[10px] border border-[#00CC68]/20 font-bold hover:bg-[#00CC68]/20 transition-colors cursor-pointer shrink-0 ${isAgentThinking ? "opacity-60 cursor-not-allowed" : ""}`}
                        title="Select AI Model"
                      >
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isAgentThinking ? "bg-amber-400 animate-ping" : "bg-[#00CC68]"}`} />
                        <span className="truncate max-w-[95px]">{isAgentThinking ? "Thinking..." : getModelLabel(activeModelName)}</span>
                        {!isAgentThinking && <ChevronDown className="w-3 h-3 text-[#00CC68] shrink-0" />}
                      </button>
                    </div>
                  </div>

                  {fallbackModelNotice && (
                    <div className="px-2.5 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] font-mono flex items-center justify-between gap-2 shrink-0">
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
                        <span className="font-bold text-white">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                        <span>{m.time}</span>
                      </div>
                      <p className="leading-relaxed whitespace-pre-wrap break-words text-xs">{m.text}</p>
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
                                className={`flex items-center gap-2 transition-all font-mono text-[10px] ${
                                  isLatest
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
                    <div className="flex items-center gap-2 pt-1 font-bold">
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
                  <div className="flex items-center justify-between px-3 py-2 mb-1.5 rounded-xl bg-[#00CC68]/10 border border-[#00CC68]/30 text-[#00CC68] text-[11px] font-mono animate-in fade-in font-bold">
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

      {/* Mobile Viewports */}
      <div className="flex md:hidden flex-1 min-h-0 overflow-hidden relative">
        {activeMobileTab === "files" && (
          <div className="flex-1 flex flex-col bg-background overflow-hidden relative min-h-0">
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
            />
          </div>
        )}

        {activeMobileTab === "code" && (
          <div className="flex-1 flex flex-col bg-background overflow-hidden relative min-h-0">
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
                  onMount={handleEditorMount}
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
        )}

        {activeMobileTab === "pdf" && (
          <div className="flex-1 flex flex-col bg-zinc-950 overflow-hidden min-h-0">
            <PDFViewer
              pdfBase64={pdfBase64}
              isCompiling={isCompiling}
              onRecompile={() => handleCompile()}
              errorLog={errorLog}
            />
          </div>
        )}

        {activeMobileTab === "ai" && (
          <div className="flex-1 flex flex-col bg-zinc-950 overflow-hidden relative min-h-0 p-3 space-y-3 text-zinc-100 font-sans">
            <div className="border-b border-zinc-800 pb-2.5 shrink-0 space-y-2 select-none">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-archivo uppercase text-white font-bold">
                  <Bot className="w-4 h-4 text-[#00CC68]" />
                  <span>Agent</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {/* New Chat Button */}
                  <button
                    type="button"
                    onClick={handleNewChat}
                    disabled={isAgentThinking}
                    className="px-2 py-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-[#00CC68] border border-zinc-800 text-[10px] font-mono font-bold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                    title="Start new chat session"
                  >
                    <PlusCircle className="w-3.5 h-3.5 text-[#00CC68]" />
                    <span>New</span>
                  </button>

                  {/* Clear / Delete Chat Button */}
                  <button
                    type="button"
                    onClick={handleClearChat}
                    disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                    className="p-1.5 rounded-lg bg-zinc-900 hover:bg-rose-950/50 text-zinc-400 hover:text-rose-400 border border-zinc-800 text-[10px] font-mono transition-colors cursor-pointer disabled:opacity-30 shrink-0"
                    title="Delete chat history and document context"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>

                  {/* Model Selector */}
                  <button
                    type="button"
                    onPointerDown={(e) => {
                      if (!isAgentThinking) {
                        e.stopPropagation();
                        setModelSelectorOpen(true);
                      }
                    }}
                    onClick={(e) => {
                      if (!isAgentThinking) {
                        e.stopPropagation();
                        setModelSelectorOpen(true);
                      }
                    }}
                    disabled={isAgentThinking}
                    className={`flex items-center gap-1.5 px-2 py-1 rounded-lg bg-[#00CC68]/10 text-[#00CC68] font-mono text-[10px] border border-[#00CC68]/20 font-bold hover:bg-[#00CC68]/20 transition-colors cursor-pointer shrink-0 ${isAgentThinking ? "opacity-60 cursor-not-allowed" : ""}`}
                    title="Select AI Model"
                  >
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isAgentThinking ? "bg-amber-400 animate-ping" : "bg-[#00CC68]"}`} />
                    <span className="truncate max-w-[95px]">{isAgentThinking ? "Thinking..." : getModelLabel(activeModelName)}</span>
                    {!isAgentThinking && <ChevronDown className="w-3 h-3 text-[#00CC68] shrink-0" />}
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

            <div className="flex-1 overflow-y-auto space-y-3 text-xs font-mono min-h-0 pr-1">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`p-3 rounded-2xl border space-y-1.5 ${
                    m.sender === "user"
                      ? "bg-[#00CC68]/10 border-[#00CC68]/20 text-[#00CC68] ml-4 font-mono font-bold"
                      : "bg-zinc-900 border-zinc-800 text-zinc-100 mr-4 font-sans"
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono">
                    <span className="font-bold text-white">{m.sender === "user" ? "You" : "OverBranch AI"}</span>
                    <span>{m.time}</span>
                  </div>
                  <p className="leading-relaxed text-xs whitespace-pre-wrap break-words">{m.text}</p>
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
                            className={`flex items-center gap-2 transition-all font-mono text-xs ${
                              isLatest
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
                <div className="flex items-center gap-2 pt-1 font-bold">
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
              <div className="flex items-center justify-between px-3 py-2 mb-1.5 rounded-xl bg-[#00CC68]/10 border border-[#00CC68]/30 text-[#00CC68] text-xs font-mono animate-in fade-in font-bold">
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
        )}
      </div>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden border-t border-zinc-800 bg-zinc-950/95 backdrop-blur-xl shrink-0 z-40 pb-[env(safe-area-inset-bottom,0px)]">
        <div className="flex items-center justify-around w-full h-14 font-mono">
          <button
            onClick={() => setActiveMobileTab("files")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${
              activeMobileTab === "files" ? "text-[#00CC68] font-bold" : "text-zinc-400"
            }`}
          >
            <FolderGit2 className="w-4 h-4" />
            <span>Files</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("code")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${
              activeMobileTab === "code" ? "text-[#00CC68] font-bold" : "text-zinc-400"
            }`}
          >
            <FileCode2 className="w-4 h-4" />
            <span>Code</span>
          </button>

          <button
            onClick={() => setActiveMobileTab("pdf")}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${
              activeMobileTab === "pdf" ? "text-cyan-400 font-bold" : "text-zinc-400"
            }`}
          >
            <Eye className="w-4 h-4" />
            <span>PDF</span>
          </button>

          <button
            onClick={() => {
              setActiveMobileTab("ai");
              setMobileDrawerOpen(true);
            }}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 text-xs ${
              activeMobileTab === "ai" ? "text-[#00CC68] font-bold" : "text-zinc-400"
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
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-archivo uppercase text-white font-bold">
                  <Bot className="w-5 h-5 text-[#00CC68]" />
                  <span className="font-bold text-sm text-white">OverBranch Agent</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {/* New Chat Button */}
                  <button
                    type="button"
                    onClick={handleNewChat}
                    disabled={isAgentThinking}
                    className="px-2 py-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-[#00CC68] border border-zinc-800 text-[10px] font-mono font-bold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                    title="Start new chat session"
                  >
                    <PlusCircle className="w-3.5 h-3.5 text-[#00CC68]" />
                    <span>New</span>
                  </button>

                  {/* Clear / Delete Chat Button */}
                  <button
                    type="button"
                    onClick={handleClearChat}
                    disabled={isAgentThinking || (messages.length === 0 && !attachedFile)}
                    className="p-1.5 rounded-lg bg-zinc-900 hover:bg-rose-950/50 text-zinc-400 hover:text-rose-400 border border-zinc-800 text-[10px] font-mono transition-colors cursor-pointer disabled:opacity-30 shrink-0"
                    title="Delete chat history and document context"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>

                  {/* Model Selector */}
                  <button
                    type="button"
                    onPointerDown={(e) => {
                      if (!isAgentThinking) {
                        e.stopPropagation();
                        setModelSelectorOpen(true);
                      }
                    }}
                    onClick={(e) => {
                      if (!isAgentThinking) {
                        e.stopPropagation();
                        setModelSelectorOpen(true);
                      }
                    }}
                    disabled={isAgentThinking}
                    className={`flex items-center gap-1.5 px-2 py-1 rounded-lg bg-[#00CC68]/10 text-[#00CC68] font-mono text-[10px] border border-[#00CC68]/20 font-bold hover:bg-[#00CC68]/20 transition-colors cursor-pointer shrink-0 ${isAgentThinking ? "opacity-60 cursor-not-allowed" : ""}`}
                    title="Select AI Model"
                  >
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isAgentThinking ? "bg-amber-400 animate-ping" : "bg-[#00CC68]"}`} />
                    <span className="truncate max-w-[95px]">{isAgentThinking ? "Thinking..." : getModelLabel(activeModelName)}</span>
                    {!isAgentThinking && <ChevronDown className="w-3 h-3 text-[#00CC68] shrink-0" />}
                  </button>
                  <button onClick={() => setMobileDrawerOpen(false)} className="text-zinc-400 hover:text-white p-1 cursor-pointer">
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
                            className={`flex items-center gap-2 transition-all font-mono text-xs ${
                              isLatest
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
              <div className="flex items-center justify-between px-3 py-2 mb-1 rounded-xl bg-[#00CC68]/10 border border-[#00CC68]/30 text-[#00CC68] text-xs font-mono animate-in fade-in font-bold">
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
            {renderModelSelectorModal()}
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>

      {/* Custom AI Model Selection Modal */}
      {renderModelSelectorModal()}
    </div>
  );
}
