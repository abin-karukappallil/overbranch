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
  Sparkles,
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
} from "lucide-react";
import { CompileToolbar } from "@/components/editor/CompileToolbar";
import { CollaboratorAvatars } from "@/components/editor/CollaboratorAvatars";
import { PDFViewer } from "@/components/editor/PDFViewer";
import { ProjectFilesPanel } from "@/components/editor/ProjectFilesPanel";
import { InlineDiffEditor, EditItem } from "@/components/editor/InlineDiffEditor";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { trpc } from "@/trpc/client";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";
import { FolderGit2 } from "lucide-react";

interface EditorLayoutProps {
  projectId?: string;
}

interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  text: string;
  time: string;
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

export const GROQ_MODELS = [
  { id: "qwen/qwen3.6-27b", name: "Qwen 3.6 27B" },
  { id: "qwen-qwq-32b", name: "Qwen QWQ 32B" },
  { id: "llama-3.3-70b-versatile", name: "Llama 3.3 70B" },
  { id: "llama-3.1-8b-instant", name: "Llama 3.1 8B Instant" },
  { id: "gemma2-9b-it", name: "Gemma 2 9B" },
  { id: "mixtral-8x7b-32768", name: "Mixtral 8x7B" },
  { id: "deepseek-r1-distill-llama-70b", name: "DeepSeek R1 70B" },
  { id: "openai/gpt-oss-20b", name: "OpenAI GPT OSS 20B" },
  { id: "openai/gpt-oss-120b", name: "OpenAI GPT OSS 120B" },
];
export const DEFAULT_MODEL = "qwen/qwen3.6-27b";

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

  // Groq API & Model Config States
  const [groqApiKey, setGroqApiKey] = useState("");
  const [groqModel, setGroqModel] = useState(DEFAULT_MODEL);
  const [showConfigPanel, setShowConfigPanel] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedKey = localStorage.getItem("groq_api_key");
      const savedModel = localStorage.getItem("groq_model");
      if (savedKey) setGroqApiKey(savedKey);
      if (savedModel) setGroqModel(savedModel);
    }
  }, []);

  const handleSaveGroqConfig = (key: string, model: string) => {
    setGroqApiKey(key);
    setGroqModel(model);
    if (typeof window !== "undefined") {
      if (key && key.trim()) localStorage.setItem("groq_api_key", key.trim());
      else localStorage.removeItem("groq_api_key");
      localStorage.setItem("groq_model", model);
    }
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
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
        const res = await fetch(`${backendUrl}/api/projects/get-file?project_id=${activeProj}&file_path=${encodeURIComponent(activeFilePath)}`);
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
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/projects/save-file`, {
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

  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;

    // Register Ctrl+S / Cmd+S save shortcut inside Monaco Editor
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      const currentVal = editor.getValue();
      saveDocument(currentVal, true);
      handleCompile(currentVal);
    });
  };

  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

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
          engine: "pdflatex",
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
    if (!chatInput.trim() || isAgentThinking) return;

    const userText = chatInput.trim();
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, sender: "user", text: userText, time: now },
    ]);
    setChatInput("");
    setIsAgentThinking(true);

    const userGroqKey = localStorage.getItem("groq_api_key") || groqApiKey;
    const userGroqModel = localStorage.getItem("groq_model") || groqModel;

    try {
      const response = await fetch(`${BACKEND_URL}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId || "proj-default",
          file_path: "main.tex",
          user_prompt: userText,
          current_code: code,
          groq_api_key: userGroqKey,
          groq_model: userGroqModel,
        }),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        const detailMsg = errJson.detail || `AI Agent returned status ${response.status}`;
        throw new Error(detailMsg);
      }

      const data = await response.json();
      const assistantTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

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

      // Fallback: If no edits were parsed in JSON but responseText contains LaTeX code, extract as proposed edit
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
          text: responseText,
          time: assistantTime,
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
      const isUnconfiguredGroq = !userGroqKey;
      const warningMsg = isUnconfiguredGroq
        ? `⚠️ LLM outage / timeout detected on default model. Please configure your own API key using Groq provider in the AI settings panel (🔑 Key icon).`
        : `AI Agent Error: ${err.message || "Failed to reach AI service"}`;

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

    if (editorRef.current) {
      const model = editorRef.current.getModel();
      const currentText = model.getValue();

      const escapedSearch = originalChunk
        ? originalChunk.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
        : '';
      const regex = escapedSearch ? new RegExp(escapedSearch, 'gi') : null;

      if (originalChunk && regex && regex.test(currentText)) {
        updatedCode = replaceAllCaseInsensitive(currentText, originalChunk, proposedChunk);
      } else {
        const selection = editorRef.current.getSelection();
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

  const handleAcceptAllEdits = (itemsToApply: EditItem[]) => {
    let updatedCode = code;

    itemsToApply.forEach((item) => {
      const orig = item.original_chunk;
      const prop = item.proposed_chunk;

      if (orig && updatedCode.includes(orig)) {
        updatedCode = replaceAllCaseInsensitive(updatedCode, orig, prop);
      } else if (prop) {
        updatedCode = insertSnippetSafely(updatedCode, prop);
      }
    });

    if (editorRef.current) {
      editorRef.current.getModel().setValue(updatedCode);
    }

    setCode(updatedCode);
    setDiffData(null);
    setDiffEditsList([]);
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
    let updatedCode = code;
    const orig = item.original_chunk;
    const prop = item.proposed_chunk;

    if (orig && updatedCode.includes(orig)) {
      updatedCode = replaceAllCaseInsensitive(updatedCode, orig, prop);
    } else if (prop) {
      updatedCode = insertSnippetSafely(updatedCode, prop);
    }

    if (editorRef.current) {
      editorRef.current.getModel().setValue(updatedCode);
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

  const insertSymbol = (symbolInsert: string) => {
    if (editorRef.current) {
      const editor = editorRef.current;
      const selection = editor.getSelection();
      const id = { major: 1, minor: 1 };
      const op = {
        identifier: id,
        range: selection,
        text: symbolInsert,
        forceMoveMarkers: true,
      };
      editor.executeEdits("my-source", [op]);
      handleCodeChange(editor.getValue());
    } else {
      const newText = code + "\n" + symbolInsert;
      handleCodeChange(newText);
    }
    toast.info(`Inserted ${symbolInsert.split("{")[0]}`);
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-background overflow-hidden selection:bg-indigo-500/20 relative">
      <header className="h-14 border-b border-border/40 bg-card/60 backdrop-blur-xl px-3 sm:px-4 flex items-center justify-between gap-2 shrink-0 z-10">
        <div className="flex items-center gap-2 overflow-hidden">
          <Link href="/dashboard" className="shrink-0 hover:opacity-90 transition-opacity">
            <OverBranchLogo size="sm" variant="icon" colored />
          </Link>
          <div className="truncate">
            <h1 className="font-bold text-xs sm:text-sm text-foreground tracking-tight truncate">
              {projectDetail?.name || (projectId ? `${projectId}.tex` : "main.tex")}
            </h1>
            <p className="text-[10px] text-muted-foreground font-mono truncate">{projectDetail?.template || "LaTeX"} · main.tex</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Save Status Badge & Manual Save Button */}
          <div className="flex items-center gap-2">
            <span className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card border border-border/40 text-[11px] font-mono">
              {saveStatus === "saved" && (
                <>
                  <CheckCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-400 font-semibold">Saved</span>
                </>
              )}
              {saveStatus === "saving" && (
                <>
                  <RotateCw className="w-3.5 h-3.5 text-amber-400 animate-spin" />
                  <span className="text-amber-400 font-semibold">Saving...</span>
                </>
              )}
              {saveStatus === "unsaved" && (
                <>
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
                  <span className="text-muted-foreground">Unsaved</span>
                </>
              )}
            </span>

            {/* Files Panel Toggle Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFilesOpen(!filesOpen)}
              className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 transition-colors ${filesOpen
                  ? "bg-emerald-500/10 hover:bg-emerald-500/20 border-emerald-500/30 text-emerald-300 font-semibold"
                  : "bg-card/80 hover:bg-card border-border/60 text-muted-foreground"
                }`}
              title={filesOpen ? "Hide Project Files" : "Show Project Files"}
            >
              <FolderGit2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Files</span>
            </Button>

            {/* AI Assistant Toggle Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={toggleAi}
              className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 transition-colors ${aiOpen
                  ? "bg-indigo-500/10 hover:bg-indigo-500/20 border-indigo-500/30 text-indigo-300 font-semibold"
                  : "bg-card/80 hover:bg-card border-border/60 text-muted-foreground"
                }`}
              title={aiOpen ? "Hide AI Assistant (Cmd+L)" : "Show AI Assistant (Cmd+L)"}
            >
              <Bot className="w-3.5 h-3.5 text-indigo-400" />
              <span>Agent <span className="text-[9px] opacity-60 ml-0.5">(Cmd+L)</span></span>
            </Button>

            {/* PDF Preview Toggle Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={togglePdf}
              className={`h-8 px-2.5 text-xs font-mono hidden md:flex items-center gap-1.5 transition-colors ${pdfOpen
                  ? "bg-cyan-500/10 hover:bg-cyan-500/20 border-cyan-500/30 text-cyan-300 font-semibold"
                  : "bg-card/80 hover:bg-card border-border/60 text-muted-foreground"
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
              className="h-8 px-2.5 bg-card/80 hover:bg-card border-border/60 text-xs font-mono flex items-center gap-1.5"
              title="Save Document (Ctrl+S)"
            >
              <Save className="w-3.5 h-3.5 text-indigo-400" />
              <span className="hidden sm:inline">Save</span>
            </Button>
          </div>

          <CollaboratorAvatars projectId={projectId} />
        </div>
      </header>

      <CompileToolbar onCompile={() => handleCompile()} isCompiling={isCompiling} />

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
            <div className="px-3 py-1 border-b border-border/30 bg-card/40 flex items-center justify-between font-mono text-[11px] shrink-0">
              <div className="flex items-center gap-2 overflow-x-auto py-0.5">
                <span className="text-[10px] text-emerald-400 font-semibold px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 truncate">
                  Editing: {activeFilePath}
                </span>
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
                  readOnly: isViewer,
                }}
              />

              {/* Floating Non-Overlapping In-Editor Accept/Reject Action Bar */}
              {diffData && diffEditsList.length > 0 && (
                <div className="absolute top-3 right-4 z-20 max-w-sm p-3 rounded-xl bg-[#161b22]/95 border border-indigo-500/40 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 font-mono text-xs space-y-2">
                  <div className="flex items-center justify-between font-bold text-slate-100">
                    <div className="flex items-center gap-1.5 text-indigo-400">
                      <Sparkles className="w-4 h-4" />
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
            className={`h-full border-l border-border/40 bg-card/40 backdrop-blur-xl transition-all duration-300 ease-in-out overflow-hidden flex flex-col shrink-0 ${aiOpen ? "w-[340px] opacity-100" : "w-0 opacity-0 pointer-events-none border-l-0"
              }`}
          >
            <div className="flex flex-col h-full justify-between p-3 text-xs min-w-[340px]">
              <div className="space-y-3 flex-1 flex flex-col overflow-hidden">
                <div className="border-b border-border/40 pb-2 shrink-0 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Bot className="w-4 h-4 text-indigo-400" />
                      <span className="font-bold text-foreground">Agentic Xperience</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setShowConfigPanel(!showConfigPanel)}
                        className={`p-1 rounded-md border text-[10px] font-mono flex items-center gap-1 transition-colors ${showConfigPanel
                            ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                            : groqApiKey
                              ? "bg-indigo-500/10 text-indigo-300 border-indigo-500/30"
                              : "bg-muted/40 text-muted-foreground border-border/40 hover:bg-accent"
                          }`}
                        title="Configure Groq API Key & Model"
                      >
                        <Key className="w-3 h-3 text-amber-400" />
                        <span className="truncate max-w-[90px]">{groqApiKey ? groqModel : "gpt-oss-120b"}</span>
                        <Settings2 className="w-3 h-3" />
                      </button>
                      <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 font-mono text-[10px]">
                        <span className={`w-1.5 h-1.5 rounded-full ${isAgentThinking ? "bg-amber-400 animate-ping" : "bg-emerald-400"}`} />
                        <span>{isAgentThinking ? "Thinking..." : "Ready"}</span>
                      </div>
                    </div>
                  </div>

                  {/* Groq Settings Collapsible Panel */}
                  {showConfigPanel && (
                    <div className="p-2.5 rounded-xl bg-card border border-border/60 space-y-2 font-mono text-[11px] shadow-lg animate-in fade-in zoom-in-95">
                      <div className="flex items-center justify-between font-bold text-indigo-400">
                        <div className="flex items-center gap-1.5">
                          <Key className="w-3.5 h-3.5 text-amber-400" />
                          <span>Groq AI Settings</span>
                        </div>
                        <span className="text-[10px] text-muted-foreground font-normal">Stored Locally</span>
                      </div>

                      <div className="space-y-1">
                        <label className="text-[10px] text-muted-foreground block font-semibold">Groq API Key:</label>
                        <input
                          type="password"
                          placeholder="gsk_... (Blank = Groq gpt-oss-120b(server))"
                          value={groqApiKey}
                          onChange={(e) => handleSaveGroqConfig(e.target.value, groqModel)}
                          className="w-full h-8 px-2 rounded-lg bg-background border border-border/60 text-xs text-foreground outline-none focus:border-indigo-500 font-mono"
                        />
                      </div>

                      <div className="space-y-1">
                        <label className="text-[10px] text-muted-foreground block font-semibold">Select Model:</label>
                        <select
                          value={groqModel}
                          onChange={(e) => handleSaveGroqConfig(groqApiKey, e.target.value)}
                          className="w-full h-8 px-2 rounded-lg bg-background border border-border/60 text-xs text-foreground outline-none focus:border-indigo-500 font-mono"
                        >
                          {GROQ_MODELS.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  )}

                  {/* Small Warning Banner if Groq key is not configured */}
                  {!groqApiKey && (
                    <div className="px-2.5 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] font-mono flex items-center gap-2 shrink-0">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                      <span className="leading-snug">
                        Groq API key not set. Using default Groq (openai/gpt-oss-120b) model.
                      </span>
                    </div>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                  {messages.map((m) => (
                    <div
                      key={m.id}
                      className={`p-2.5 rounded-xl border space-y-1.5 ${m.sender === "user"
                          ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-200 ml-4"
                          : "bg-muted/40 border-border/40 text-foreground mr-4"
                        }`}
                    >
                      <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                        <span>{m.sender === "user" ? "You" : "Nemotron AI"}</span>
                        <span>{m.time}</span>
                      </div>
                      <p className="leading-relaxed">{m.text}</p>
                    </div>
                  ))}
                  {isAgentThinking && (
                    <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-300 flex items-center gap-2 text-[11px] animate-pulse font-mono">
                      <Sparkles className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                      <span>Generating LaTeX edit proposal via {groqApiKey ? "Groq (" + groqModel + ")" : "Groq (openai/gpt-oss-120b)"}...</span>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* Sleek Diff Control Card directly above Chat Input */}
                {diffData && diffEditsList.length > 0 && (
                  <div className="mb-2 p-2.5 rounded-xl bg-card border border-indigo-500/30 shadow-xl space-y-2 font-mono text-[11px] animate-in fade-in slide-in-from-bottom-2">
                    <div className="flex items-center justify-between font-semibold text-indigo-300">
                      <div className="flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                        <span>Proposed LaTeX Edit</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-200 border border-indigo-500/30 font-bold">
                        {getEditLineRange(diffEditsList[0].original_chunk, diffEditsList[0].proposed_chunk)}
                      </span>
                    </div>

                    {/* Compact Line-by-line Preview */}
                    <div className="max-h-28 overflow-y-auto bg-black/40 p-2 rounded-lg text-[10px] space-y-0.5 font-mono border border-border/40">
                      {diffEditsList[0].original_chunk && (
                        <div className="text-rose-400 bg-rose-950/30 px-1 py-0.5 rounded line-through truncate font-mono">
                          - {diffEditsList[0].original_chunk.split("\n")[0]}
                        </div>
                      )}
                      {diffEditsList[0].proposed_chunk && (
                        <div className="text-emerald-400 bg-emerald-950/30 px-1 py-0.5 rounded truncate font-mono">
                          + {diffEditsList[0].proposed_chunk.split("\n")[0]}
                        </div>
                      )}
                    </div>

                    {/* Action Buttons Directly Above Chat Input */}
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
                        <span>Accept All</span>
                      </button>
                    </div>
                  </div>
                )}

                <form onSubmit={handleSendPrompt} className="relative pt-2 border-t border-border/40 shrink-0">
                  <input
                    id="ai-chat-input"
                    type="text"
                    placeholder="Ask assistant to edit TeX... (Cmd+L)"
                    value={chatInput}
                    disabled={isAgentThinking}
                    onChange={(e) => setChatInput(e.target.value)}
                    className="w-full h-9 pl-3 pr-8 rounded-xl border border-border/60 bg-background text-foreground text-xs outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={isAgentThinking || !chatInput.trim()}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 hover:text-indigo-300 disabled:opacity-40"
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Viewports */}
      <div className="flex md:hidden flex-1 overflow-hidden relative">
        {activeMobileTab === "files" && (
          <div className="flex-1 flex flex-col bg-background overflow-hidden relative">
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
          <div className="flex-1 flex flex-col bg-background overflow-hidden relative">
            <div className="px-2 py-1 border-b border-border/30 bg-card/40 flex items-center justify-between font-mono text-[11px]">
              <span className="text-[10px] text-emerald-400 font-semibold px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 truncate">
                {activeFilePath}
              </span>
              <div className="flex items-center gap-1.5 overflow-x-auto">
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
                  fontSize: 14,
                  wordWrap: "on",
                  automaticLayout: true,
                }}
              />
              {diffData && diffEditsList.length > 0 && (
                <div className="absolute top-3 right-4 z-20 max-w-xs p-2.5 rounded-xl bg-[#161b22]/95 border border-indigo-500/40 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 font-mono text-xs space-y-2">
                  <div className="flex items-center justify-between font-bold text-slate-100">
                    <div className="flex items-center gap-1.5 text-indigo-400">
                      <Sparkles className="w-3.5 h-3.5" />
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
          <div className="flex-1 flex flex-col bg-zinc-950 overflow-hidden">
            <PDFViewer
              pdfBase64={pdfBase64}
              isCompiling={isCompiling}
              onRecompile={() => handleCompile()}
              errorLog={errorLog}
            />
          </div>
        )}
      </div>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden h-14 border-t border-border/40 bg-card/95 backdrop-blur-xl flex items-center justify-around shrink-0 z-30">
        <button
          onClick={() => setActiveMobileTab("files")}
          className={`flex-1 h-full flex flex-col items-center justify-center gap-1 text-xs min-h-[48px] ${activeMobileTab === "files" ? "text-emerald-400 font-bold" : "text-muted-foreground"
            }`}
        >
          <FolderGit2 className="w-5 h-5" />
          <span>Files</span>
        </button>

        <button
          onClick={() => setActiveMobileTab("code")}
          className={`flex-1 h-full flex flex-col items-center justify-center gap-1 text-xs min-h-[48px] ${activeMobileTab === "code" ? "text-indigo-400 font-bold" : "text-muted-foreground"
            }`}
        >
          <FileCode2 className="w-5 h-5" />
          <span>Code</span>
        </button>

        <button
          onClick={() => setActiveMobileTab("pdf")}
          className={`flex-1 h-full flex flex-col items-center justify-center gap-1 text-xs min-h-[48px] ${activeMobileTab === "pdf" ? "text-cyan-400 font-bold" : "text-muted-foreground"
            }`}
        >
          <Eye className="w-5 h-5" />
          <span>PDF</span>
        </button>

        <button
          onClick={() => setMobileDrawerOpen(true)}
          className="flex-1 h-full flex flex-col items-center justify-center gap-1 text-xs text-purple-400 min-h-[48px]"
        >
          <Bot className="w-5 h-5" />
          <span>AI Assistant</span>
        </button>
      </nav>

      {/* Mobile AI Assistant Drawer */}
      <Drawer.Root open={mobileDrawerOpen} onOpenChange={setMobileDrawerOpen}>
        <Drawer.Portal>
          <Drawer.Overlay className="fixed inset-0 bg-black/60 z-50 backdrop-blur-sm" />
          <Drawer.Content className="fixed bottom-0 left-0 right-0 max-h-[85vh] h-[80vh] z-50 bg-card border-t border-border/80 rounded-t-3xl flex flex-col p-4 space-y-3">
            <div className="w-12 h-1.5 rounded-full bg-border/60 mx-auto shrink-0" />
            <div className="border-b border-border/40 pb-2 shrink-0 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bot className="w-5 h-5 text-indigo-400" />
                  <span className="font-bold text-sm text-foreground">Agentic Xperience</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowConfigPanel(!showConfigPanel)}
                    className="px-2 py-1 rounded-lg border border-border/60 bg-card text-xs font-mono flex items-center gap-1.5 text-indigo-300"
                    title="Configure Groq API Key & Model"
                  >
                    <Key className="w-3.5 h-3.5 text-amber-400" />
                    <span className="truncate max-w-[90px]">{groqApiKey ? groqModel : "gpt-oss-120b"}</span>
                    <Settings2 className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => setMobileDrawerOpen(false)} className="text-muted-foreground p-1">
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {showConfigPanel && (
                <div className="p-3 rounded-xl bg-background border border-border/60 space-y-2 font-mono text-xs shadow-lg">
                  <div className="flex items-center justify-between font-bold text-indigo-400">
                    <div className="flex items-center gap-1.5">
                      <Key className="w-4 h-4 text-amber-400" />
                      <span>Groq AI Settings</span>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground block font-semibold">Groq API Key:</label>
                    <input
                      type="password"
                      placeholder="gsk_... (Blank = Groq gpt-oss-120b)"
                      value={groqApiKey}
                      onChange={(e) => handleSaveGroqConfig(e.target.value, groqModel)}
                      className="w-full h-9 px-2.5 rounded-lg bg-card border border-border/60 text-xs text-foreground outline-none focus:border-indigo-500 font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground block font-semibold">Select Model:</label>
                    <select
                      value={groqModel}
                      onChange={(e) => handleSaveGroqConfig(groqApiKey, e.target.value)}
                      className="w-full h-9 px-2.5 rounded-lg bg-card border border-border/60 text-xs text-foreground outline-none focus:border-indigo-500 font-mono"
                    >
                      {GROQ_MODELS.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  {/* Small Warning Banner if Groq key is not configured */}
                  {!groqApiKey && (
                    <div className="px-2.5 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] font-mono flex items-center gap-2 shrink-0">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                      <span className="leading-snug">
                        Groq API key not set. Using default Groq (openai/gpt-oss-120b) model.
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 text-xs">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`p-3 rounded-xl border space-y-1.5 ${m.sender === "user"
                      ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-200 ml-4"
                      : "bg-muted/40 border-border/40 text-foreground mr-4"
                    }`}
                >
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                    <span>{m.sender === "user" ? "You" : "Nemotron AI"}</span>
                    <span>{m.time}</span>
                  </div>
                  <p className="leading-relaxed text-sm">{m.text}</p>
                </div>
              ))}
              {isAgentThinking && (
                <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-300 flex items-center gap-2 text-xs animate-pulse font-mono">
                  <Sparkles className="w-4 h-4 text-purple-400 shrink-0" />
                  <span>Generating LaTeX edit proposal via {groqApiKey ? "Groq (" + groqModel + ")" : "Groq (openai/gpt-oss-120b)"}...</span>
                </div>
              )}
              <div ref={mobileChatEndRef} />
            </div>

            <form onSubmit={handleSendPrompt} className="relative pt-2 border-t border-border/40 shrink-0">
              <input
                id="mobile-ai-chat-input"
                type="text"
                placeholder="Ask assistant to edit TeX..."
                value={chatInput}
                disabled={isAgentThinking}
                onChange={(e) => setChatInput(e.target.value)}
                className="w-full h-11 pl-3 pr-10 rounded-xl border border-border/60 bg-background text-foreground text-base outline-none focus:border-indigo-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isAgentThinking || !chatInput.trim()}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-indigo-400 p-1 disabled:opacity-40"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    </div>
  );
}
