"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { trpc } from "@/trpc/client";
import {
    AI_SYSTEM_PROMPT,
    PARALLEL_AI_SYSTEM_PROMPT,
    GROQ_MODELS,
    DEFAULT_MODEL,
    extractLatexFromResponse,
    extractChunkLatex,
    extractChunkId,
    extractChangesSummary,
} from "./aiSystemPrompt";
import { getStoredApiKey } from "./AiSettingsModal";
import { estimateTokenCount, splitLatexDocument } from "@/lib/latexSplitter";

const PARALLEL_TOKEN_THRESHOLD = 6000;

export interface ChatMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    timestamp: Date;
    latexCode?: string | null;
    status?: "pending" | "done" | "error" | "applied" | "rejected";
}

interface AiChatPanelProps {
    isOpen: boolean;
    onClose: () => void;
    currentFileContent: string;
    onApplyChange: (newContent: string) => void;
    onShowDiff: (original: string, modified: string) => void;
    onClearDiff: () => void;
    onOpenSettings: () => void;
}

export default function AiChatPanel({
    isOpen,
    onClose,
    currentFileContent,
    onApplyChange,
    onShowDiff,
    onClearDiff,
    onOpenSettings,
}: AiChatPanelProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [model, setModel] = useState(() => {
        if (typeof window !== "undefined") {
            return localStorage.getItem("overbranch_ai_model") || DEFAULT_MODEL;
        }
        return DEFAULT_MODEL;
    });
    const [isStreaming, setIsStreaming] = useState(false);
    const [pendingDiffMessageId, setPendingDiffMessageId] = useState<string | null>(null);
    const chatEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const chatMutation = trpc.ai.chat.useMutation();

    const apiKey = typeof window !== "undefined" ? getStoredApiKey() : null;

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, isStreaming]);

    useEffect(() => {
        localStorage.setItem("overbranch_ai_model", model);
    }, [model]);

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + "px";
        }
    }, [input]);

    // Helper to update the pending message content progressively
    const updatePendingMessage = useCallback((pendingId: string, content: string, extra?: Partial<ChatMessage>) => {
        setMessages((prev) =>
            prev.map((m) =>
                m.id === pendingId ? { ...m, content, ...extra } : m
            )
        );
    }, []);

    // ─────────────────────────────────────────────
    //  SINGLE-CALL PIPELINE (small documents)
    // ─────────────────────────────────────────────
    const handleSingleCall = useCallback(async (
        pendingId: string,
        userRequest: string,
        processedContent: string,
        conversationHistory: { role: "user" | "assistant"; content: string }[]
    ) => {
        updatePendingMessage(pendingId, "🔍 Analyzing LaTeX code...");

        const apiMessages = [
            { role: "system" as const, content: AI_SYSTEM_PROMPT },
            ...conversationHistory,
            {
                role: "user" as const,
                content: `Here is the current LaTeX document:\n\n\`\`\`latex\n${processedContent}\n\`\`\`\n\nUser request: ${userRequest}`,
            },
        ];

        const result = await chatMutation.mutateAsync({
            apiKey: apiKey!,
            model,
            messages: apiMessages,
        });

        const extractedCode = extractLatexFromResponse(result.content);

        updatePendingMessage(pendingId, result.content, {
            latexCode: extractedCode,
            status: "done",
        });

        return extractedCode;
    }, [apiKey, model, chatMutation, updatePendingMessage]);

    // ─────────────────────────────────────────────
    //  PARALLEL PIPELINE (large documents)
    // ─────────────────────────────────────────────
    const handleParallelCall = useCallback(async (
        pendingId: string,
        userRequest: string,
        processedContent: string,
    ) => {
        // Step 1: Analyzing
        updatePendingMessage(pendingId, "🔍 Analyzing LaTeX code...");
        await delay(400);

        // Step 2: Token detection
        const tokenCount = estimateTokenCount(processedContent);
        updatePendingMessage(pendingId, `📊 Token count: ~${tokenCount} — Activating parallel processing...`);
        await delay(400);

        // Step 3: Splitting
        updatePendingMessage(pendingId, "✂️ Splitting document into semantic chunks...");
        const { preamble, chunks } = splitLatexDocument(processedContent, 6);
        await delay(300);

        updatePendingMessage(pendingId, `📦 Split into ${chunks.length} chunks. Dispatching parallel AI agents...`);
        await delay(300);

        // Step 4: Dispatch parallel agents
        // Main agent uses openai/gpt-oss-120b (single call path)
        // Parallel agents use diverse Groq models with low input token rate limits
        const AGENT_MODELS = [
            "llama-3.1-8b-instant",
            "moonshotai/kimi-k2-instruct-0905",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "gemma2-9b-it",
            "mixtral-8x7b-32768",
        ];

        // Track state of each agent for live UI updates
        const agentStates = Array.from({ length: chunks.length }, (_, i) => ({
            id: i + 1,
            model: AGENT_MODELS[i % AGENT_MODELS.length],
            status: "dispatching..."
        }));

        const refreshAgentUI = () => {
            const statusLines = agentStates.map(a =>
                `${a.status === "completed" ? "✅" : "⏳"} Agent ${a.id} (${a.model}): ${a.status}`
            ).join('\n');
            updatePendingMessage(pendingId, `🚀 Parallel agents working:\n\n${statusLines}`);
        };

        const agentPromises = chunks.map(async (chunk, idx) => {
            const chunkId = idx + 1;
            const totalChunks = chunks.length;
            const agentModel = AGENT_MODELS[idx % AGENT_MODELS.length];

            const agentMessages = [
                { role: "system" as const, content: PARALLEL_AI_SYSTEM_PROMPT },
                {
                    role: "user" as const,
                    content: `CHUNK_ID: ${chunkId}\nTOTAL_CHUNKS: ${totalChunks}\n\nHere is body chunk ${chunkId} of ${totalChunks}:\n\n\`\`\`latex\n${chunk}\n\`\`\`\n\nUser editing instruction: ${userRequest}`,
                },
            ];

            // Mark processing
            agentStates[idx].status = "processing edit...";
            refreshAgentUI();

            try {
                const result = await chatMutation.mutateAsync({
                    apiKey: apiKey!,
                    model: agentModel,
                    messages: agentMessages,
                });

                // Mark completed
                agentStates[idx].status = "completed";
                refreshAgentUI();

                return { chunkId, response: result.content };
            } catch (error) {
                // Mark error but don't break others
                agentStates[idx].status = `error: ${error instanceof Error ? error.message : "failed"}`;
                refreshAgentUI();
                return { chunkId, response: chunk }; // fallback to original chunk on error
            }
        });

        // Wait for all agents
        const agentResults = await Promise.all(agentPromises);

        // Step 5: Collecting results
        updatePendingMessage(pendingId, "📥 All agents finished. Collecting results...");
        await delay(300);

        // Step 6: Merging
        updatePendingMessage(pendingId, "🔗 Merging document chunks...");
        await delay(200);

        // Sort responses by chunk ID
        agentResults.sort((a, b) => {
            const idA = extractChunkId(a.response) ?? a.chunkId;
            const idB = extractChunkId(b.response) ?? b.chunkId;
            return idA - idB;
        });

        // Extract the updated LaTeX from each agent response
        const mergedChunks = agentResults.map((r) => {
            const originalChunk = chunks[r.chunkId - 1] || "";
            const summary = extractChangesSummary(r.response) || "";

            // Safety 1: If the agent explicitly says no changes are needed,
            // strictly use the original chunk to prevent any accidental truncation.
            if (summary.toLowerCase().includes("no changes needed") || summary.toLowerCase().includes("no change")) {
                console.log(`[AI] Agent ${r.chunkId} reported no changes. Using original chunk.`);
                return originalChunk;
            }

            let extracted = extractChunkLatex(r.response);
            if (!extracted) {
                extracted = extractLatexFromResponse(r.response);
            }

            if (extracted) {
                // Safety 2: Length check to catch lazy models returning placeholders
                // e.g., "```latex\n% rest of code\n```"
                // If the extracted code is massively smaller than the original, it's likely truncated.
                if (extracted.length < originalChunk.length * 0.5 && originalChunk.length > 500) {
                    console.warn(`[AI] WARNING: Agent ${r.chunkId} returned suspiciously short chunk (${extracted.length} vs ${originalChunk.length}). Falling back to original.`);
                    return originalChunk;
                }
                return extracted;
            }

            // Last resort: use original chunk
            console.warn(`[AI] WARNING: Agent ${r.chunkId} failed extraction. Falling back to original.`);
            return originalChunk;
        });

        // Collect changes summaries
        const changesSummaries = agentResults
            .map((r) => {
                const summary = extractChangesSummary(r.response);
                return summary ? `**Agent ${r.chunkId}:** ${summary}` : null;
            })
            .filter(Boolean);

        // Build the final merged document
        let finalLatex = "";
        if (preamble) {
            finalLatex += preamble + "\n";
        }
        finalLatex += mergedChunks.join("\n");

        // Ensure document ends properly
        if (!finalLatex.includes("\\end{document}") && preamble.includes("\\begin{document}")) {
            finalLatex += "\n\\end{document}\n";
        }

        // Build the summary content for display
        const summaryContent = [
            "✅ **Parallel editing complete!**",
            "",
            `📊 Document: ~${tokenCount} tokens → ${chunks.length} chunks`,
            `🤖 ${agentResults.length} agents completed successfully`,
            "",
            "**Changes Summary:**",
            ...changesSummaries,
        ].join("\n");

        updatePendingMessage(pendingId, summaryContent, {
            latexCode: finalLatex,
            status: "done",
        });

        return finalLatex;
    }, [apiKey, model, chatMutation, updatePendingMessage]);

    // ─────────────────────────────────────────────
    //  MAIN SUBMIT HANDLER
    // ─────────────────────────────────────────────
    const handleSubmit = useCallback(async () => {
        if (!input.trim() || isStreaming || !apiKey) return;

        const userMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: "user",
            content: input.trim(),
            timestamp: new Date(),
        };

        const pendingId = crypto.randomUUID();
        const pendingMessage: ChatMessage = {
            id: pendingId,
            role: "assistant",
            content: "",
            timestamp: new Date(),
            status: "pending",
        };

        setMessages((prev) => [...prev, userMessage, pendingMessage]);
        setInput("");
        setIsStreaming(true);

        // Build conversation history
        const conversationHistory = messages
            .filter((m) => m.status !== "error")
            .slice(-10)
            .map((m) => {
                let content = m.content;
                if (m.role === "assistant" && m.latexCode) {
                    content = content.replace(/```latex[\s\S]*?```/g, "[CODE BLOCK TRUNCATED FOR CONTEXT]");
                }
                content = content.replace(/Here is the current LaTeX document:[\s\S]*?User request:/g, "User request:");
                return {
                    role: m.role as "user" | "assistant",
                    content,
                };
            });

        // Pre-process content
        const processedContent = currentFileContent
            .replace(/%.*$/gm, '')
            .replace(/[ \t]+/g, ' ')
            .replace(/\n\s*\n/g, '\n\n')
            .trim();

        try {
            const tokenCount = estimateTokenCount(processedContent);
            let extractedCode: string | null = null;

            if (tokenCount <= PARALLEL_TOKEN_THRESHOLD) {
                // ─── Single call path ───
                extractedCode = await handleSingleCall(
                    pendingId,
                    userMessage.content,
                    processedContent,
                    conversationHistory
                );
            } else {
                // ─── Parallel pipeline path ───
                extractedCode = await handleParallelCall(
                    pendingId,
                    userMessage.content,
                    processedContent,
                );
            }

            // Show diff if we extracted code
            if (extractedCode) {
                onShowDiff(currentFileContent, extractedCode);
                setPendingDiffMessageId(pendingId);
            }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : "AI request failed";
            updatePendingMessage(pendingId, errorMsg, { status: "error" });
        } finally {
            setIsStreaming(false);
        }
    }, [input, isStreaming, apiKey, messages, currentFileContent, model, chatMutation, onShowDiff, handleSingleCall, handleParallelCall, updatePendingMessage]);

    const handleAccept = useCallback(() => {
        if (!pendingDiffMessageId) return;
        const msg = messages.find((m) => m.id === pendingDiffMessageId);
        if (msg?.latexCode) {
            onApplyChange(msg.latexCode);
            setMessages((prev) =>
                prev.map((m) =>
                    m.id === pendingDiffMessageId ? { ...m, status: "applied" as const } : m
                )
            );
        }
        onClearDiff();
        setPendingDiffMessageId(null);
    }, [pendingDiffMessageId, messages, onApplyChange, onClearDiff]);

    const handleReject = useCallback(() => {
        if (!pendingDiffMessageId) return;
        setMessages((prev) =>
            prev.map((m) =>
                m.id === pendingDiffMessageId ? { ...m, status: "rejected" as const } : m
            )
        );
        onClearDiff();
        setPendingDiffMessageId(null);
    }, [pendingDiffMessageId, onClearDiff]);

    const handleClearChat = () => {
        setMessages([]);
        onClearDiff();
        setPendingDiffMessageId(null);
    };

    if (!isOpen) return null;

    return (
        <div className="ai-panel">
            {/* Header */}
            <div className="ai-panel-header">
                <div className="ai-panel-header-left">
                    <svg className="h-4 w-4 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 2a8 8 0 0 0-8 8c0 3.36 2.07 6.24 5 7.42V20a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-2.58c2.93-1.18 5-4.06 5-7.42a8 8 0 0 0-8-8z" />
                        <line x1="9" y1="22" x2="15" y2="22" />
                    </svg>
                    <span className="ai-panel-title">AI Assistant</span>
                </div>
                <div className="ai-panel-header-right">
                    <button onClick={handleClearChat} className="ai-panel-btn" title="Clear chat">
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6l-2 14H7L5 6" />
                            <path d="M10 11v6M14 11v6M9 6V4h6v2" />
                        </svg>
                    </button>
                    <button onClick={onOpenSettings} className="ai-panel-btn" title="AI Settings">
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="3" />
                            <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                        </svg>
                    </button>
                    <button onClick={onClose} className="ai-panel-btn" title="Close panel">
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    </button>
                </div>
            </div>

            {/* Model selector */}
            <div className="ai-model-selector">
                <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="ai-model-select"
                >
                    {GROQ_MODELS.map((m) => (
                        <option key={m.id} value={m.id}>
                            {m.name}
                        </option>
                    ))}
                </select>
            </div>

            {/* API key warning */}
            {!apiKey && (
                <div className="ai-api-key-banner">
                    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 2a4 4 0 0 0-4 4v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2h-2V6a4 4 0 0 0-4-4z" />
                        <circle cx="12" cy="15" r="1.5" />
                    </svg>
                    <div>
                        <p className="ai-banner-text">Add your Groq API key to enable AI editing.</p>
                        <button onClick={onOpenSettings} className="ai-banner-link">
                            Open Settings →
                        </button>
                    </div>
                </div>
            )}

            {/* Chat messages */}
            <div className="ai-chat-messages">
                {messages.length === 0 && apiKey && (
                    <div className="ai-empty-state">
                        <svg className="h-8 w-8 text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M12 2a8 8 0 0 0-8 8c0 3.36 2.07 6.24 5 7.42V20a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-2.58c2.93-1.18 5-4.06 5-7.42a8 8 0 0 0-8-8z" />
                            <line x1="9" y1="22" x2="15" y2="22" />
                        </svg>
                        <p>Ask the AI to edit or improve your LaTeX code</p>
                        <span className="text-xs text-muted/40">e.g. &quot;Add a table of contents&quot; or &quot;Fix the bibliography format&quot;</span>
                    </div>
                )}

                {messages.map((msg) => (
                    <div key={msg.id} className={`ai-chat-message ai-chat-${msg.role}`}>
                        <div className="ai-chat-message-header">
                            <span className="ai-chat-role">
                                {msg.role === "user" ? "You" : "AI"}
                            </span>
                            {msg.status && msg.status !== "done" && (
                                <span className={`ai-chat-status ai-status-${msg.status}`}>
                                    {msg.status === "pending" && (
                                        <>
                                            <svg className="spinner h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <circle cx="12" cy="12" r="10" opacity="0.25" />
                                                <path d="M12 2a10 10 0 0 1 10 10" opacity="0.75" />
                                            </svg>
                                            Processing…
                                        </>
                                    )}
                                    {msg.status === "error" && "Error"}
                                    {msg.status === "applied" && "✓ Applied"}
                                    {msg.status === "rejected" && "✗ Rejected"}
                                </span>
                            )}
                        </div>
                        <div className="ai-chat-message-body">
                            {msg.status === "pending" && !msg.content ? (
                                <div className="ai-thinking-dots">
                                    <span></span><span></span><span></span>
                                </div>
                            ) : (
                                <pre className="ai-chat-content">{msg.content}</pre>
                            )}
                        </div>
                    </div>
                ))}

                {/* Accept/Reject controls */}
                {pendingDiffMessageId && !isStreaming && (
                    <div className="ai-diff-controls">
                        <span className="ai-diff-label">AI suggested changes — review the diff in the editor</span>
                        <div className="ai-diff-buttons">
                            <button onClick={handleAccept} className="ai-diff-accept">
                                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                    <polyline points="20 6 9 17 4 12" />
                                </svg>
                                Accept
                            </button>
                            <button onClick={handleReject} className="ai-diff-reject">
                                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                    <line x1="18" y1="6" x2="6" y2="18" />
                                    <line x1="6" y1="6" x2="18" y2="18" />
                                </svg>
                                Reject
                            </button>
                        </div>
                    </div>
                )}

                <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="ai-input-container">
                <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            handleSubmit();
                        }
                    }}
                    placeholder={apiKey ? "Ask AI to edit your LaTeX…" : "Set your API key first…"}
                    disabled={!apiKey || isStreaming}
                    className="ai-input"
                    rows={1}
                />
                <button
                    onClick={handleSubmit}
                    disabled={!apiKey || isStreaming || !input.trim()}
                    className="ai-send-btn"
                    title="Send"
                >
                    {isStreaming ? (
                        <svg className="spinner h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" opacity="0.25" />
                            <path d="M12 2a10 10 0 0 1 10 10" opacity="0.75" />
                        </svg>
                    ) : (
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="22" y1="2" x2="11" y2="13" />
                            <polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                    )}
                </button>
            </div>
        </div>
    );
}

// Simple delay utility for progress animation
function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
