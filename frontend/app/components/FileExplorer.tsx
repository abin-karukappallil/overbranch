"use client";

import { useState } from "react";

interface FileItem {
    name: string;
    content: string;
    isBinary?: boolean;
}

interface FileExplorerProps {
    files: FileItem[];
    activeFile: string;
    onSelectFile: (name: string) => void;
    onAddFile: (name: string) => void;
    onUploadFile: (file: File) => void;
    onDeleteFile: (name: string) => void;
}

export default function FileExplorer({
    files,
    activeFile,
    onSelectFile,
    onAddFile,
    onUploadFile,
    onDeleteFile,
}: FileExplorerProps) {
    const [newFileName, setNewFileName] = useState("");
    const [isAdding, setIsAdding] = useState(false);

    const handleAdd = () => {
        if (newFileName.trim()) {
            const name = newFileName.endsWith(".tex") ? newFileName : `${newFileName}.tex`;
            onAddFile(name);
            setNewFileName("");
            setIsAdding(false);
        }
    };

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            onUploadFile(file);
        }
        e.target.value = "";
    };

    return (
        <div className="flex h-full flex-col bg-surface-dark border-r border-border w-64">
            <div className="p-4 border-b border-border flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Project</h2>
                <div className="flex gap-1">
                    <button
                        onClick={() => setIsAdding(true)}
                        className="p-1 hover:bg-white/5 rounded text-muted hover:text-foreground transition-colors"
                        title="New File"
                    >
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 5v14M5 12h14" />
                        </svg>
                    </button>
                    <label className="p-1 hover:bg-white/5 rounded text-muted hover:text-foreground transition-colors cursor-pointer" title="Upload File">
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                            <polyline points="17 8 12 3 7 8" />
                            <line x1="12" y1="3" x2="12" y2="15" />
                        </svg>
                        <input type="file" className="hidden" accept=".tex,image/*" onChange={handleFileUpload} />
                    </label>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto py-2">
                {isAdding && (
                    <div className="px-3 mb-2">
                        <input
                            autoFocus
                            type="text"
                            value={newFileName}
                            onChange={(e) => setNewFileName(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") handleAdd();
                                if (e.key === "Escape") setIsAdding(false);
                            }}
                            onBlur={() => !newFileName && setIsAdding(false)}
                            placeholder="filename.tex"
                            className="w-full bg-background border border-accent/30 rounded px-2 py-1 text-xs outline-none focus:border-accent"
                        />
                    </div>
                )}

                {files.map((file) => (
                    <div
                        key={file.name}
                        onClick={() => onSelectFile(file.name)}
                        className={`
              group flex items-center justify-between cursor-pointer text-sm py-1.5 px-4 transition-colors
              ${activeFile === file.name ? "bg-accent/10 text-accent font-medium" : "text-muted hover:bg-white/5 hover:text-foreground"}
            `}
                    >
                        <div className="flex items-center gap-2 truncate">
                            <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                                <polyline points="14,2 14,8 20,8" />
                            </svg>
                            <span className="truncate">{file.name}</span>
                        </div>

                        {files.length > 1 && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onDeleteFile(file.name);
                                }}
                                className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-error/10 hover:text-error rounded transition-all"
                            >
                                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M18 6L6 18M6 6l12 12" />
                                </svg>
                            </button>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
