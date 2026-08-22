"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  FolderGit2,
  Upload,
  Plus,
  FileText,
  BookOpen,
  FileCode,
  Image as ImageIcon,
  FileCheck,
  File,
  Trash2,
  Copy,
  Check,
  X,
  Search,
  ChevronRight,
  Folder,
  Sparkles,
  Eye,
  Loader2,
  Pencil,
  Lock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

export interface ProjectFile {
  path: string;
  name: string;
  size: number;
  type: "document" | "image";
  ext: string;
}

interface ProjectFilesPanelProps {
  projectId: string;
  activeFilePath: string;
  isOpen: boolean;
  onClose: () => void;
  onSelectFile: (filePath: string, fileType: "document" | "image") => void;
  onInsertLatexSnippet?: (snippet: string) => void;
}

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

export function ProjectFilesPanel({
  projectId,
  activeFilePath,
  isOpen,
  onClose,
  onSelectFile,
  onInsertLatexSnippet,
}: ProjectFilesPanelProps) {
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [search, setSearch] = useState("");
  const [newFileModal, setNewFileModal] = useState(false);
  const [newFileName, setNewFileName] = useState("");
  const [renameModalFile, setRenameModalFile] = useState<ProjectFile | null>(null);
  const [newRenamePath, setNewRenamePath] = useState("");
  const [previewImage, setPreviewImage] = useState<ProjectFile | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchFiles = async () => {
    if (!projectId) return;
    setIsLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/projects/list-files?project_id=${projectId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.files && Array.isArray(data.files)) {
          setFiles(data.files);
        }
      }
    } catch (err) {
      console.warn("Failed to fetch project files list:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, [projectId]);

  const handleFileUpload = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0 || !projectId) return;

    setIsUploading(true);
    let successCount = 0;

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      // Store asset with exact name as uploaded file (no figure subfolder prefix)
      const targetPath = file.name;

      const formData = new FormData();
      formData.append("project_id", projectId);
      formData.append("file_path", targetPath);
      formData.append("file", file);

      try {
        const res = await fetch(`${BACKEND_URL}/api/projects/upload-asset`, {
          method: "POST",
          body: formData,
        });

        if (res.ok) {
          successCount++;
        } else {
          toast.error(`Upload failed for ${file.name}`);
        }
      } catch (err) {
        console.error("Upload asset error:", err);
        toast.error(`Network error uploading ${file.name}`);
      }
    }

    setIsUploading(false);
    if (successCount > 0) {
      toast.success(`Successfully uploaded ${successCount} asset(s)!`);
      fetchFiles();
    }
  };

  const handleCreateFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFileName.trim() || !projectId) return;

    let cleanName = newFileName.trim();
    if (!cleanName.includes(".")) cleanName += ".tex";

    try {
      const res = await fetch(`${BACKEND_URL}/api/projects/save-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          file_path: cleanName,
          raw_code: cleanName.endsWith(".tex") ? `% ${cleanName} — TeX document\n` : "",
        }),
      });

      if (res.ok) {
        toast.success(`Created file ${cleanName}`);
        setNewFileName("");
        setNewFileModal(false);
        fetchFiles();
        onSelectFile(cleanName, "document");
      } else {
        toast.error("Failed to create new file.");
      }
    } catch (err) {
      toast.error("Error connecting to server.");
    }
  };

  const handleRenameFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!renameModalFile || !newRenamePath.trim() || !projectId) return;

    const oldPath = renameModalFile.path;
    const newPath = newRenamePath.trim();

    if (oldPath.toLowerCase() === "main.tex") {
      toast.error("Primary main.tex cannot be renamed.");
      return;
    }
    if (newPath.toLowerCase() === "main.tex") {
      toast.error("Cannot rename file to main.tex.");
      return;
    }

    try {
      const res = await fetch(`${BACKEND_URL}/api/projects/rename-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          old_path: oldPath,
          new_path: newPath,
        }),
      });

      if (res.ok) {
        toast.success(`Renamed ${oldPath} to ${newPath}`);
        setRenameModalFile(null);
        setNewRenamePath("");
        fetchFiles();
        if (activeFilePath === oldPath) {
          onSelectFile(newPath, renameModalFile.type);
        }
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "Failed to rename file.");
      }
    } catch (err) {
      toast.error("Error connecting to server for rename.");
    }
  };

  const handleDeleteFile = async (filePath: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (filePath.toLowerCase() === "main.tex") {
      toast.error("Primary main.tex cannot be deleted.");
      return;
    }

    if (!confirm(`Are you sure you want to delete ${filePath}?`)) return;

    try {
      const res = await fetch(
        `${BACKEND_URL}/api/projects/delete-file?project_id=${projectId}&file_path=${encodeURIComponent(
          filePath
        )}`,
        { method: "DELETE" }
      );

      if (res.ok) {
        toast.success(`Deleted ${filePath}`);
        fetchFiles();
        if (activeFilePath === filePath) {
          onSelectFile("main.tex", "document");
        }
      } else {
        toast.error("Failed to delete file.");
      }
    } catch (err) {
      toast.error("Error deleting file.");
    }
  };

  const copyImageLatexCode = (filePath: string, name: string) => {
    const cleanLabel = name.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_");
    const snippet = `\\begin{figure}[htbp]
  \\centering
  \\includegraphics[width=0.8\\textwidth]{${filePath}}
  \\caption{${name.replace(/_/g, " ")}}
  \\label{fig:${cleanLabel}}
\\end{figure}`;

    navigator.clipboard.writeText(snippet);
    setCopiedPath(filePath);
    toast.success("Copied LaTeX code block to clipboard!");
    setTimeout(() => setCopiedPath(null), 2000);
  };

  const getFileIcon = (ext: string, type: "document" | "image") => {
    if (type === "image" || [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"].includes(ext)) {
      return <ImageIcon className="w-4 h-4 text-purple-400 shrink-0" />;
    }
    if (ext === ".tex") return <FileText className="w-4 h-4 text-[#00CC68] shrink-0" />;
    if (ext === ".bib") return <BookOpen className="w-4 h-4 text-amber-400 shrink-0" />;
    if ([".cls", ".sty"].includes(ext)) return <FileCode className="w-4 h-4 text-emerald-400 shrink-0" />;
    if (ext === ".pdf") return <FileCheck className="w-4 h-4 text-rose-400 shrink-0" />;
    return <File className="w-4 h-4 text-zinc-400 shrink-0" />;
  };

  const filteredFiles = files.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()) || f.path.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div
      className={`h-full border-r border-zinc-800 bg-zinc-950 text-zinc-100 transition-all duration-300 ease-in-out overflow-hidden flex flex-col shrink-0 ${isOpen ? "w-full md:w-64 opacity-100" : "w-0 opacity-0 pointer-events-none border-r-0"
        }`}
    >
      <div className="flex flex-col h-full p-3 text-xs w-full min-w-0 md:min-w-[256px] space-y-3">
        {/* Panel Header */}
        <div className="border-b border-zinc-800 pb-2.5 shrink-0 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 font-bold font-archivo uppercase text-white">
              <FolderGit2 className="w-4 h-4 text-[#00CC68]" />
              <span>Project Files</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[#00CC68]/10 text-[#00CC68] font-mono">
                {files.length}
              </span>
            </div>

            <div className="flex items-center gap-1">
              <Button
                size="icon"
                variant="ghost"
                onClick={() => fileInputRef.current?.click()}
                className="h-7 w-7 text-[#00CC68] hover:bg-[#00CC68]/10 rounded-lg"
                title="Upload Asset Files"
              >
                <Upload className="w-3.5 h-3.5" />
              </Button>

              <Button
                size="icon"
                variant="ghost"
                onClick={() => setNewFileModal(true)}
                className="h-7 w-7 text-[#00CC68] hover:bg-[#00CC68]/10 rounded-lg"
                title="Create New TeX File"
              >
                <Plus className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>

          <input
            type="file"
            ref={fileInputRef}
            multiple
            onChange={(e) => handleFileUpload(e.target.files)}
            className="hidden"
            accept=".png,.jpg,.jpeg,.gif,.svg,.webp,.tex,.bib,.cls,.sty,.pdf,.txt"
          />

          {/* Quick Filter Search Input */}
          <div className="relative">
            <Input
              placeholder="Search files & assets..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 pl-7 text-[11px] font-mono bg-zinc-900 border-zinc-800 text-zinc-200"
            />
            <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2 top-1/2 -translate-y-1/2" />
          </div>
        </div>

        {/* Upload Drag & Drop Dropzone area */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleFileUpload(e.dataTransfer.files);
          }}
          onClick={() => fileInputRef.current?.click()}
          className="p-2.5 rounded-xl border border-dashed border-[#00CC68]/30 bg-[#00CC68]/5 hover:bg-[#00CC68]/10 transition-colors text-center cursor-pointer space-y-1 shrink-0 group"
        >
          {isUploading ? (
            <div className="flex items-center justify-center gap-2 text-[#00CC68] font-mono text-[11px] py-1">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Uploading assets...</span>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-center gap-1.5 text-[#00CC68] font-mono font-bold text-[11px]">
                <Upload className="w-3.5 h-3.5" />
                <span>Upload Project Assets</span>
              </div>
              <p className="text-[9px] text-muted-foreground font-mono">Upload images, PDFs, TeX or BIB files directly</p>
            </>
          )}
        </div>

        {/* File Tree List */}
        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {isLoading ? (
            <div className="py-8 text-center text-muted-foreground font-mono flex items-center justify-center gap-2 text-xs">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
              <span>Loading files...</span>
            </div>
          ) : filteredFiles.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground text-xs font-mono">
              No files found.
            </div>
          ) : (
            filteredFiles.map((file) => {
              const isActive = activeFilePath === file.path;
              const isMainTex = file.path.toLowerCase() === "main.tex";
              const isAsset = file.type === "image" || [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"].includes(file.ext.toLowerCase());

              return (
                <div
                  key={file.path}
                  onClick={() => {
                    if (isAsset) {
                      setPreviewImage(file);
                    } else {
                      onSelectFile(file.path, "document");
                    }
                  }}
                  className={`p-2 rounded-xl border flex items-center justify-between text-xs cursor-pointer transition-all gap-2 overflow-hidden ${isActive
                    ? "bg-indigo-500/15 border-indigo-500/40 text-indigo-200 font-semibold"
                    : "bg-muted/30 hover:bg-accent border-border/30 text-foreground"
                    }`}
                >
                  <div className="flex items-center gap-2 truncate min-w-0 flex-1">
                    {getFileIcon(file.ext, file.type)}
                    <span className="truncate text-[11px] font-mono min-w-0" title={file.path}>{file.path}</span>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    {isAsset && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          copyImageLatexCode(file.path, file.name);
                        }}
                        className="p-1 rounded hover:bg-indigo-500/20 text-purple-400 transition-colors"
                        title="Copy TeX Code to Clipboard"
                      >
                        {copiedPath === file.path ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    )}

                    {isMainTex ? (
                      <span className="p-1 text-muted-foreground/60" title="Primary main.tex (Cannot be renamed or deleted)">
                        <Lock className="w-3.5 h-3.5 text-amber-500/70" />
                      </span>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRenameModalFile(file);
                            setNewRenamePath(file.path);
                          }}
                          className="p-1 rounded hover:bg-amber-500/20 text-muted-foreground hover:text-amber-400 transition-colors"
                          title="Rename File"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteFile(file.path, e)}
                          className="p-1 rounded hover:bg-rose-500/20 text-muted-foreground hover:text-rose-400 transition-colors"
                          title="Delete File"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Create New File Modal */}
      {newFileModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="max-w-xs w-full p-4 rounded-2xl border border-border bg-card shadow-2xl space-y-3 font-sans text-xs">
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="font-bold text-foreground">Create New Document</span>
              <button onClick={() => setNewFileModal(false)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleCreateFile} className="space-y-3">
              <div className="space-y-1">
                <label className="text-muted-foreground text-[10px] font-mono">File Name (e.g. intro.tex or refs.bib)</label>
                <Input
                  autoFocus
                  placeholder="sections/intro.tex"
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button size="sm" variant="outline" type="button" onClick={() => setNewFileModal(false)} className="h-8 text-xs">
                  Cancel
                </Button>
                <Button size="sm" type="submit" disabled={!newFileName.trim()} className="h-8 text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
                  Create File
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Rename File Modal */}
      {renameModalFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="max-w-xs w-full p-4 rounded-2xl border border-border bg-card shadow-2xl space-y-3 font-sans text-xs">
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="font-bold text-foreground">Rename File Asset</span>
              <button onClick={() => setRenameModalFile(null)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleRenameFile} className="space-y-3">
              <div className="space-y-1">
                <label className="text-muted-foreground text-[10px] font-mono">New Name for {renameModalFile.name}</label>
                <Input
                  autoFocus
                  value={newRenamePath}
                  onChange={(e) => setNewRenamePath(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button size="sm" variant="outline" type="button" onClick={() => setRenameModalFile(null)} className="h-8 text-xs">
                  Cancel
                </Button>
                <Button size="sm" type="submit" disabled={!newRenamePath.trim() || newRenamePath === renameModalFile.path} className="h-8 text-xs bg-amber-600 hover:bg-amber-500 text-white font-semibold">
                  Rename
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Asset Preview & TeX Code Snippet Modal */}
      {previewImage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in">
          <div className="max-w-md w-full p-5 rounded-2xl border border-border bg-card shadow-2xl space-y-4 font-sans text-xs overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-border/40 pb-2 gap-2">
              <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                <ImageIcon className="w-4 h-4 text-purple-400 shrink-0" />
                <span className="font-bold text-foreground truncate min-w-0 text-xs font-mono" title={previewImage.path}>
                  {previewImage.path}
                </span>
              </div>
              <button
                onClick={() => setPreviewImage(null)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-muted/50 transition-colors shrink-0"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Asset Preview */}
            <div className="p-3 bg-black/40 rounded-xl border border-border/40 flex items-center justify-center max-h-56 overflow-hidden">
              {previewImage.ext.toLowerCase() === ".pdf" ? (
                <iframe
                  src={`${BACKEND_URL}/api/projects/get-file?project_id=${projectId}&file_path=${encodeURIComponent(previewImage.path)}`}
                  title={previewImage.name}
                  className="w-full h-48 rounded border-0"
                />
              ) : (
                <img
                  src={`${BACKEND_URL}/api/projects/get-file?project_id=${projectId}&file_path=${encodeURIComponent(previewImage.path)}`}
                  alt={previewImage.name}
                  className="max-h-48 object-contain rounded"
                />
              )}
            </div>

            {/* Code to implement below */}
            <div className="space-y-1.5 font-mono text-[11px]">
              <span className="text-muted-foreground font-semibold block">Code to implement below:</span>
              <pre className="p-2.5 bg-background rounded-lg border border-border/60 text-emerald-400 overflow-x-auto text-[10px] whitespace-pre">
                {`\\begin{figure}[htbp]
  \\centering
  \\includegraphics[width=0.8\\textwidth]{${previewImage.path}}
  \\caption{${previewImage.name.replace(/_/g, " ")}}
  \\label{fig:${previewImage.name.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_")}}
\\end{figure}`}
              </pre>
            </div>

            {/* Modal Actions (Only Copy and Close buttons) */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPreviewImage(null)}
                className="h-8 text-xs px-4"
              >
                Close
              </Button>

              <Button
                size="sm"
                onClick={() => {
                  copyImageLatexCode(previewImage.path, previewImage.name);
                }}
                className="h-8 text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow-md shadow-indigo-500/20 gap-1.5"
              >
                {copiedPath === previewImage.path ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-300" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Code</span>
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

