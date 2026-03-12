"use client";

import { useState, useCallback, useMemo, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { trpc } from "@/trpc/client";
import LatexEditor from "@/app/components/LatexEditor";
import PdfPreview from "@/app/components/PdfPreview";
import Toolbar from "@/app/components/Toolbar";
import Link from "next/link";

interface FileData {
    id: string;
    projectId: string;
    fileName: string;
    fileType: string;
    content: string | null;
    createdAt: Date;
    updatedAt: Date;
}

interface AssetData {
    id: string;
    projectId: string;
    assetName: string;
    assetType: string;
    assetUrl: string;
    createdAt: Date;
}

interface EditorWorkspaceProps {
    projectId: string;
    projectName: string;
    initialFiles: FileData[];
    initialAssets: AssetData[];
}

export default function EditorWorkspace({
    projectId,
    projectName,
    initialFiles,
    initialAssets,
}: EditorWorkspaceProps) {
    const router = useRouter();

    const [files, setFiles] = useState<FileData[]>(initialFiles);
    const [assets, setAssets] = useState<AssetData[]>(initialAssets);
    const [activeFileId, setActiveFileId] = useState<string>(
        initialFiles.find((f) => f.fileName === "main.tex")?.id || initialFiles[0]?.id || ""
    );
    const [pdfUrl, setPdfUrl] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [logs, setLogs] = useState<string | null>(null);
    const [theme, setTheme] = useState("latex-dark");
    const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
    const [showNewFileInput, setShowNewFileInput] = useState(false);
    const [newFileName, setNewFileName] = useState("");
    const [renamingFileId, setRenamingFileId] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState("");
    const [showAssetPanel, setShowAssetPanel] = useState(false);

    const saveTimerRef = useRef<NodeJS.Timeout | null>(null);

    const activeFile = useMemo(
        () => files.find((f) => f.id === activeFileId),
        [files, activeFileId]
    );

    // tRPC mutations
    const updateFileMutation = trpc.projectFile.update.useMutation({
        onSuccess: () => {
            setSaveStatus("saved");
            setTimeout(() => setSaveStatus("idle"), 2000);
        },
    });

    const createFileMutation = trpc.projectFile.create.useMutation({
        onSuccess: (newFile) => {
            setFiles((prev) => [...prev, newFile]);
            setActiveFileId(newFile.id);
            setShowNewFileInput(false);
            setNewFileName("");
        },
    });

    const deleteFileMutation = trpc.projectFile.delete.useMutation({
        onSuccess: (_, variables) => {
            setFiles((prev) => prev.filter((f) => f.id !== variables.id));
            if (activeFileId === variables.id) {
                const remaining = files.filter((f) => f.id !== variables.id);
                setActiveFileId(remaining[0]?.id || "");
            }
        },
    });

    const renameFileMutation = trpc.projectFile.rename.useMutation({
        onSuccess: (updated) => {
            setFiles((prev) =>
                prev.map((f) => (f.id === updated.id ? { ...f, fileName: updated.fileName } : f))
            );
            setRenamingFileId(null);
            setRenameValue("");
        },
    });

    const uploadAssetMutation = trpc.projectAsset.upload.useMutation({
        onSuccess: (asset) => {
            setAssets((prev) => [...prev, asset]);
        },
    });

    const deleteAssetMutation = trpc.projectAsset.delete.useMutation({
        onSuccess: (_, variables) => {
            setAssets((prev) => prev.filter((a) => a.id !== variables.id));
        },
    });

    // Autosave handler
    const handleContentChange = useCallback(
        (content: string) => {
            // Update local state immediately
            setFiles((prev) =>
                prev.map((f) => (f.id === activeFileId ? { ...f, content } : f))
            );

            // Debounced save
            if (saveTimerRef.current) {
                clearTimeout(saveTimerRef.current);
            }
            setSaveStatus("idle");
            saveTimerRef.current = setTimeout(() => {
                if (activeFileId) {
                    setSaveStatus("saving");
                    updateFileMutation.mutate({
                        id: activeFileId,
                        content,
                    });
                }
            }, 2000);
        },
        [activeFileId, updateFileMutation]
    );

    // Cleanup timer
    useEffect(() => {
        return () => {
            if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        };
    }, []);

    // File CRUD handlers
    const handleCreateFile = useCallback(() => {
        if (!newFileName.trim()) return;
        createFileMutation.mutate({
            projectId,
            fileName: newFileName.trim(),
            fileType: newFileName.endsWith(".tex") ? "tex" : newFileName.split(".").pop() || "txt",
        });
    }, [newFileName, projectId, createFileMutation]);

    const handleDeleteFile = useCallback(
        (fileId: string) => {
            if (files.length <= 1) return;
            deleteFileMutation.mutate({ id: fileId });
        },
        [files, deleteFileMutation]
    );

    const handleStartRename = useCallback(
        (fileId: string, currentName: string) => {
            setRenamingFileId(fileId);
            setRenameValue(currentName);
        },
        []
    );

    const handleRename = useCallback(() => {
        if (!renamingFileId || !renameValue.trim()) return;
        renameFileMutation.mutate({
            id: renamingFileId,
            fileName: renameValue.trim(),
        });
    }, [renamingFileId, renameValue, renameFileMutation]);

    // Image upload
    const handleUploadImage = useCallback(
        (file: File) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                let data = e.target?.result as string;
                // Extract base64 from data URL
                if (data.includes(",")) {
                    data = data.split(",")[1];
                }
                const isImage = file.type.startsWith("image/");
                uploadAssetMutation.mutate({
                    projectId,
                    assetName: file.name,
                    assetType: isImage ? "image" : "file",
                    base64Data: data,
                });
            };
            reader.readAsDataURL(file);
        },
        [projectId, uploadAssetMutation]
    );

    // Compile handler
    const compileMutation = trpc.latex.compile.useMutation({
        onSuccess: async (data) => {
            if (data.pdf) {
                try {
                    const res = await fetch(`data:application/pdf;base64,${data.pdf}`);
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
                    setPdfUrl(url);
                    setError(null);
                    setLogs(null);
                } catch {
                    setError("Failed to render PDF");
                    setPdfUrl(null);
                }
            }
        },
        onError: (err) => {
            setError(err.message || "Compilation failed");
            setLogs(null);
        },
    });

    const handleCompile = useCallback(() => {
        setError(null);
        setLogs(null);
        if (!activeFile) return;
        compileMutation.mutate({
            projectId,
            activeFileId: activeFile.id,
            latex: activeFile.content || ""
        });
    }, [projectId, activeFile, compileMutation]);

    // Download PDF
    const handleDownload = useCallback(() => {
        if (!pdfUrl) return;
        const link = document.createElement("a");
        link.href = pdfUrl;
        link.download = `${activeFile?.fileName.replace(".tex", "") || "document"}.pdf`;
        document.body.appendChild(link);
        link.click();
        setTimeout(() => document.body.removeChild(link), 100);
    }, [pdfUrl, activeFile]);

    return (
        <div className="editor-page">
            {/* Header */}
            <header className="flex items-center justify-between border-b border-border bg-toolbar-bg px-4 py-3 md:px-6 z-10">
                <div className="flex items-center gap-3">
                    <Link href="/dashboard" className="editor-header-back">
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="15,18 9,12 15,6" />
                        </svg>
                        Projects
                    </Link>
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10">
                        <svg className="h-4.5 w-4.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                            <polyline points="14,2 14,8 20,8" />
                            <line x1="9" y1="13" x2="15" y2="13" />
                            <line x1="9" y1="17" x2="15" y2="17" />
                        </svg>
                    </div>
                    <div>
                        <h1 className="text-sm font-semibold tracking-tight text-foreground">{projectName}</h1>
                        <div className={`autosave-indicator ${saveStatus}`}>
                            {saveStatus === "saving" && "Saving..."}
                            {saveStatus === "saved" && "✓ Saved"}
                            {saveStatus === "idle" && ""}
                        </div>
                    </div>
                </div>

                <Toolbar
                    onCompile={handleCompile}
                    onDownload={handleDownload}
                    isCompiling={compileMutation.isPending}
                    hasPdf={!!pdfUrl}
                    theme={theme}
                    onThemeChange={setTheme}
                />
            </header>

            <div className="flex flex-1 overflow-hidden">
                {/* Sidebar: File Explorer */}
                <aside className="flex w-56 flex-col border-r border-border bg-surface">
                    {/* Files section */}
                    <div className="flex items-center justify-between border-b border-border px-3 py-2">
                        <span className="text-xs font-semibold uppercase tracking-wider text-muted">Files</span>
                        <div className="flex gap-1">
                            <button
                                onClick={() => setShowAssetPanel(!showAssetPanel)}
                                className="rounded p-1 text-muted hover:text-foreground hover:bg-surface-hover"
                                title="Toggle assets panel"
                            >
                                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                                    <circle cx="8.5" cy="8.5" r="1.5" />
                                    <polyline points="21 15 16 10 5 21" />
                                </svg>
                            </button>
                            <button
                                onClick={() => setShowNewFileInput(true)}
                                className="rounded p-1 text-muted hover:text-foreground hover:bg-surface-hover"
                                title="New file"
                            >
                                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <line x1="12" y1="5" x2="12" y2="19" />
                                    <line x1="5" y1="12" x2="19" y2="12" />
                                </svg>
                            </button>
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto py-1">
                        {/* New file input */}
                        {showNewFileInput && (
                            <div className="px-2 py-1">
                                <input
                                    type="text"
                                    value={newFileName}
                                    onChange={(e) => setNewFileName(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") handleCreateFile();
                                        if (e.key === "Escape") {
                                            setShowNewFileInput(false);
                                            setNewFileName("");
                                        }
                                    }}
                                    onBlur={() => {
                                        if (newFileName.trim()) handleCreateFile();
                                        else {
                                            setShowNewFileInput(false);
                                            setNewFileName("");
                                        }
                                    }}
                                    placeholder="filename.tex"
                                    autoFocus
                                    className="w-full rounded border border-accent bg-background px-2 py-1 text-xs text-foreground outline-none"
                                />
                            </div>
                        )}

                        {/* File list */}
                        {files.map((file) => (
                            <div
                                key={file.id}
                                className={`group flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer transition-colors ${file.id === activeFileId
                                    ? "bg-accent/10 text-accent"
                                    : "text-muted hover:bg-surface-hover hover:text-foreground"
                                    }`}
                                onClick={() => setActiveFileId(file.id)}
                            >
                                <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                                    <polyline points="14,2 14,8 20,8" />
                                </svg>

                                {renamingFileId === file.id ? (
                                    <input
                                        type="text"
                                        value={renameValue}
                                        onChange={(e) => setRenameValue(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") handleRename();
                                            if (e.key === "Escape") {
                                                setRenamingFileId(null);
                                                setRenameValue("");
                                            }
                                        }}
                                        onBlur={handleRename}
                                        autoFocus
                                        className="flex-1 rounded border border-accent bg-background px-1 py-0.5 text-xs text-foreground outline-none"
                                        onClick={(e) => e.stopPropagation()}
                                    />
                                ) : (
                                    <span className="flex-1 truncate">{file.fileName}</span>
                                )}

                                <div className="hidden group-hover:flex items-center gap-0.5">
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            handleStartRename(file.id, file.fileName);
                                        }}
                                        className="rounded p-0.5 text-muted hover:text-foreground"
                                        title="Rename"
                                    >
                                        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                                        </svg>
                                    </button>
                                    {files.length > 1 && (
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleDeleteFile(file.id);
                                            }}
                                            className="rounded p-0.5 text-muted hover:text-error"
                                            title="Delete"
                                        >
                                            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <polyline points="3 6 5 6 21 6" />
                                                <path d="M19 6l-2 14H7L5 6" />
                                                <path d="M10 11v6M14 11v6M9 6V4h6v2" />
                                            </svg>
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}

                        {/* Assets section in sidebar */}
                        {showAssetPanel && (
                            <>
                                <div className="flex items-center justify-between border-t border-border px-3 py-2 mt-2">
                                    <span className="text-xs font-semibold uppercase tracking-wider text-muted">Assets</span>
                                    <label className="rounded p-1 text-muted hover:text-foreground hover:bg-surface-hover cursor-pointer" title="Upload asset">
                                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                            <polyline points="17 8 12 3 7 8" />
                                            <line x1="12" y1="3" x2="12" y2="15" />
                                        </svg>
                                        <input
                                            type="file"
                                            className="hidden"
                                            accept="image/*,.pdf,.bib,.cls,.sty"
                                            onChange={(e) => {
                                                const file = e.target.files?.[0];
                                                if (file) handleUploadImage(file);
                                                e.target.value = "";
                                            }}
                                        />
                                    </label>
                                </div>

                                {assets.length > 0 ? (
                                    assets.map((asset) => (
                                        <div
                                            key={asset.id}
                                            className="group flex items-center gap-2 px-3 py-1.5 text-xs text-muted hover:bg-surface-hover"
                                        >
                                            <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                {asset.assetType === "image" ? (
                                                    <>
                                                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                                                        <circle cx="8.5" cy="8.5" r="1.5" />
                                                        <polyline points="21 15 16 10 5 21" />
                                                    </>
                                                ) : (
                                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                                                )}
                                            </svg>
                                            <span className="flex-1 truncate">{asset.assetName}</span>
                                            <button
                                                onClick={() => deleteAssetMutation.mutate({ id: asset.id })}
                                                className="hidden group-hover:block rounded p-0.5 text-muted hover:text-error"
                                                title="Delete asset"
                                            >
                                                <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                    <line x1="18" y1="6" x2="6" y2="18" />
                                                    <line x1="6" y1="6" x2="18" y2="18" />
                                                </svg>
                                            </button>
                                        </div>
                                    ))
                                ) : (
                                    <p className="px-3 py-2 text-xs text-muted/60">No assets uploaded</p>
                                )}
                            </>
                        )}
                    </div>
                </aside>

                {/* Editor + Preview */}
                <main className="flex flex-1 flex-col overflow-hidden md:flex-row">
                    {/* Left: Code editor */}
                    <div className="flex h-1/2 flex-col border-b border-border p-2 md:h-full md:w-1/2 md:border-b-0 md:border-r md:p-3">
                        {activeFile ? (
                            <LatexEditor
                                value={activeFile.content || ""}
                                onChange={handleContentChange}
                                theme={theme}
                            />
                        ) : (
                            <div className="flex h-full items-center justify-center text-muted text-sm">
                                Select a file to edit
                            </div>
                        )}
                    </div>

                    {/* Right: PDF preview */}
                    <div className="flex h-1/2 flex-col p-2 md:h-full md:w-1/2 md:p-3">
                        <PdfPreview
                            pdfUrl={pdfUrl}
                            isCompiling={compileMutation.isPending}
                            error={error}
                        />
                        {logs && (
                            <div className="mt-2 h-40 overflow-auto rounded-lg border border-error/20 bg-error/5 p-4 font-mono text-xs text-error/80">
                                <h3 className="mb-2 font-bold uppercase tracking-wider text-error">Compilation Logs</h3>
                                <pre className="whitespace-pre-wrap">{logs}</pre>
                            </div>
                        )}
                    </div>
                </main>
            </div>
        </div>
    );
}
