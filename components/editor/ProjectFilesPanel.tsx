"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  FolderGit2,
  Upload,
  Download,
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
import { authFetch } from "@/lib/api-client";

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
  refreshTrigger?: any;
}

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

// In-memory SWR cache for instant file tree display across views and re-renders
const fileListCache = new Map<string, { files: ProjectFile[]; timestamp: number }>();

export function ProjectFilesPanel({
  projectId,
  activeFilePath,
  isOpen,
  onClose,
  onSelectFile,
  onInsertLatexSnippet,
  refreshTrigger,
}: ProjectFilesPanelProps) {
  const [files, setFiles] = useState<ProjectFile[]>(() => fileListCache.get(projectId)?.files || []);
  const [isLoading, setIsLoading] = useState(() => !fileListCache.has(projectId));
  const [isUploading, setIsUploading] = useState(false);
  const [search, setSearch] = useState("");
  const [newFileModal, setNewFileModal] = useState(false);
  const [newFileName, setNewFileName] = useState("");
  const [renameModalFile, setRenameModalFile] = useState<ProjectFile | null>(null);
  const [newRenamePath, setNewRenamePath] = useState("");
  const [previewImage, setPreviewImage] = useState<ProjectFile | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchFiles = async (forceSpinner = false) => {
    if (!projectId) return;
    const cached = fileListCache.get(projectId);
    const hasCache = !!cached && cached.files.length > 0;
    if (!hasCache || forceSpinner) {
      setIsLoading(true);
    }
    try {
      const res = await authFetch(`${BACKEND_URL}/api/projects/list-files?project_id=${projectId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.files && Array.isArray(data.files)) {
          setFiles(data.files);
          fileListCache.set(projectId, { files: data.files, timestamp: Date.now() });
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
  }, [projectId, refreshTrigger]);

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
        const res = await authFetch(`${BACKEND_URL}/api/projects/upload-asset`, {
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
      fileListCache.delete(projectId);
      fetchFiles(true);
    }
  };

  const handleCreateFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFileName.trim() || !projectId) return;

    let cleanName = newFileName.trim();
    if (!cleanName.includes(".")) cleanName += ".tex";

    try {
      const res = await authFetch(`${BACKEND_URL}/api/projects/save-file`, {
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
        fileListCache.delete(projectId);
        fetchFiles(true);
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
      const res = await authFetch(`${BACKEND_URL}/api/projects/rename-file`, {
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
        fileListCache.delete(projectId);
        fetchFiles(true);
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
      const res = await authFetch(
        `${BACKEND_URL}/api/projects/delete-file?project_id=${projectId}&file_path=${encodeURIComponent(
          filePath
        )}`,
        { method: "DELETE" }
      );

      if (res.ok) {
        toast.success(`Deleted ${filePath}`);
        fileListCache.delete(projectId);
        fetchFiles(true);
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
    setTimeout(() => setCopiedPath(null), 2000);
  };

  const handleDownloadFile = (filePath: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      const downloadUrl = `${BACKEND_URL}/api/projects/get-file?project_id=${projectId}&file_path=${encodeURIComponent(filePath)}`;
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = filePath.split("/").pop() || filePath;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      toast.success(`Downloading ${filePath}...`);
    } catch (err) {
      toast.error(`Failed to download ${filePath}`);
    }
  };

  const getFileIcon = (ext: string, type: "document" | "image") => {
    if (type === "image" || [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"].includes(ext)) {
      return <ImageIcon className="w-4 h-4 text-purple-400 shrink-0" />;
    }
    if (ext === ".tex") return <FileText className="w-4 h-4 text-indigo-400 shrink-0" />;
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
      className={`h-full border-r border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] text-slate-900 dark:text-[#E2E4E9] transition-all duration-300 ease-in-out overflow-hidden flex flex-col shrink-0 ${isOpen ? "w-full md:w-64 opacity-100" : "w-0 opacity-0 pointer-events-none border-r-0"
        }`}
    >
      {/* Panel Header */}
      <div className="h-9 px-3 border-b border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#141519] flex items-center justify-between shrink-0 select-none">
        <div className="flex items-center gap-1.5 font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">
          <FolderGit2 className="w-4 h-4 text-[#10B981]" />
          <span>Project Files</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-[#22242C] border border-slate-200 dark:border-[#282A30] text-slate-600 dark:text-[#9E9E9E] font-mono">
            {files.length}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            className="h-6 w-6 text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] hover:bg-slate-200 dark:hover:bg-[#22242C] rounded-md cursor-pointer"
            title="Upload Asset Files"
          >
            <Upload className="w-3.5 h-3.5" />
          </Button>

          <Button
            size="icon"
            variant="ghost"
            onClick={() => setNewFileModal(true)}
            className="h-6 w-6 text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] hover:bg-slate-200 dark:hover:bg-[#22242C] rounded-md cursor-pointer"
            title="Create New TeX File"
          >
            <Plus className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex flex-col flex-1 p-3 text-xs w-full min-w-0 space-y-3 overflow-hidden"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFileUpload(e.dataTransfer.files);
        }}
      >
        <input
          type="file"
          ref={fileInputRef}
          multiple
          onChange={(e) => handleFileUpload(e.target.files)}
          className="hidden"
          accept=".png,.jpg,.jpeg,.gif,.svg,.webp,.tex,.bib,.cls,.sty,.pdf,.txt"
        />

        {/* Quick Filter Search Input */}
        <div className="relative shrink-0">
          <Input
            placeholder="Search files..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-7 text-[11px] font-mono bg-slate-50 dark:bg-[#1A1C22] border-slate-200 dark:border-[#282A30] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-lg focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#282A30]"
          />
          <Search className="w-3.5 h-3.5 text-slate-400 dark:text-[#62666D] absolute left-2.5 top-1/2 -translate-y-1/2" />
        </div>

        {/* File Tree List */}
        <div className="flex-1 overflow-y-auto space-y-1 pr-0.5 font-mono">
          {isLoading ? (
            <div className="py-8 text-center text-slate-500 dark:text-[#9E9E9E] font-mono flex items-center justify-center gap-2 text-xs">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-[#10B981]" />
              <span>Loading files...</span>
            </div>
          ) : filteredFiles.length === 0 ? (
            <div className="py-8 text-center text-slate-400 dark:text-[#62666D] text-xs font-mono">
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
                  className={`group px-2.5 py-1.5 rounded-lg flex items-center justify-between text-xs cursor-pointer transition-colors gap-2 overflow-hidden ${
                    isActive
                      ? "bg-slate-100 dark:bg-[#22242C] text-slate-900 dark:text-[#E2E4E9] font-medium border border-slate-200 dark:border-[#282A30]"
                      : "text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] hover:bg-slate-100 dark:hover:bg-[#1E2026]"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate min-w-0 flex-1">
                    {getFileIcon(file.ext, file.type)}
                    <span className="truncate text-[11px] font-mono min-w-0" title={file.path}>
                      {file.path}
                    </span>
                  </div>

                  <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={(e) => handleDownloadFile(file.path, e)}
                      className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#2A2C36] text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] transition-colors"
                      title="Download File"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>

                    {isAsset && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          copyImageLatexCode(file.path, file.name);
                        }}
                        className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#2A2C36] text-slate-500 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-[#E2E4E9] transition-colors"
                        title="Copy TeX Code to Clipboard"
                      >
                        {copiedPath === file.path ? <Check className="w-3.5 h-3.5 text-[#10B981]" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    )}

                    {isMainTex ? (
                      <span className="p-1 text-slate-400 dark:text-[#62666D]" title="Primary main.tex">
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
                          className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#2A2C36] text-slate-400 dark:text-[#62666D] hover:text-amber-500 transition-colors"
                          title="Rename File"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteFile(file.path, e)}
                          className="p-1 rounded hover:bg-slate-200 dark:hover:bg-[#2A2C36] text-slate-400 dark:text-[#62666D] hover:text-red-500 dark:hover:text-[#EB5757] transition-colors"
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

        {/* Powered By UPZARE Technologies Footer */}
        <div className="pt-2 border-t border-slate-200 dark:border-[#282A30] shrink-0">
          <a
            href="https://upzare.com"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between p-2 rounded-lg bg-slate-50 hover:bg-slate-100 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] border border-slate-200 dark:border-[#282A30] text-[10px] font-mono transition-colors group"
            title="Powered By UPZARE Technologies Private Limited"
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-slate-500 dark:text-[#9E9E9E]">Powered By</span>
              <img
                src="https://cdn.upzare.com/assets/logo.png"
                alt="UPZARE Technologies Private Limited"
                className="h-3.5 w-auto object-contain"
              />
            </div>
            <span className="font-bold text-slate-800 dark:text-[#E2E4E9] group-hover:text-emerald-600 dark:group-hover:text-emerald-400">
              UPZARE
            </span>
          </a>
        </div>
      </div>

      {/* Create New File Modal */}
      {newFileModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 animate-in fade-in backdrop-blur-xs">
          <div className="max-w-xs w-full p-5 rounded-2xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] text-slate-900 dark:text-[#E2E4E9] shadow-2xl space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#282A30] pb-2">
              <span className="font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">Create New File</span>
              <button onClick={() => setNewFileModal(false)} className="text-slate-400 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleCreateFile} className="space-y-3">
              <div className="space-y-1">
                <label className="text-slate-500 dark:text-[#9E9E9E] text-[10px] uppercase">File Name (e.g. intro.tex or refs.bib)</label>
                <Input
                  autoFocus
                  placeholder="sections/intro.tex"
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  className="h-9 text-xs font-mono border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-xl focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#282A30]"
                />
              </div>
              <div className="flex justify-end gap-2 pt-1 font-mono">
                <Button size="sm" variant="outline" type="button" onClick={() => setNewFileModal(false)} className="h-8 text-xs rounded-xl border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] text-slate-600 dark:text-[#9E9E9E]">
                  Cancel
                </Button>
                <Button size="sm" type="submit" disabled={!newFileName.trim()} className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold rounded-xl border border-emerald-600 dark:border-[#282A30]">
                  Create File
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Rename File Modal */}
      {renameModalFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 animate-in fade-in backdrop-blur-xs">
          <div className="max-w-xs w-full p-5 rounded-2xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] text-slate-900 dark:text-[#E2E4E9] shadow-2xl space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#282A30] pb-2">
              <span className="font-archivo font-bold text-slate-900 dark:text-[#E2E4E9]">Rename File Asset</span>
              <button onClick={() => setRenameModalFile(null)} className="text-slate-400 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleRenameFile} className="space-y-3">
              <div className="space-y-1">
                <label className="text-slate-500 dark:text-[#9E9E9E] text-[10px] uppercase">New Name for {renameModalFile.name}</label>
                <Input
                  autoFocus
                  value={newRenamePath}
                  onChange={(e) => setNewRenamePath(e.target.value)}
                  className="h-9 text-xs font-mono border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] text-slate-900 dark:text-[#E2E4E9] placeholder:text-slate-400 dark:placeholder:text-[#62666D] rounded-xl focus-visible:ring-1 focus-visible:ring-emerald-500 dark:focus-visible:ring-[#282A30]"
                />
              </div>
              <div className="flex justify-end gap-2 pt-1 font-mono">
                <Button size="sm" variant="outline" type="button" onClick={() => setRenameModalFile(null)} className="h-8 text-xs rounded-xl border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] text-slate-600 dark:text-[#9E9E9E]">
                  Cancel
                </Button>
                <Button size="sm" type="submit" disabled={!newRenamePath.trim() || newRenamePath === renameModalFile.path} className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold rounded-xl border border-emerald-600 dark:border-[#282A30]">
                  Rename
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Asset Preview & TeX Code Snippet Modal */}
      {previewImage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 animate-in fade-in backdrop-blur-xs">
          <div className="max-w-md w-full p-5 rounded-2xl border border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#141519] text-slate-900 dark:text-[#E2E4E9] shadow-2xl space-y-4 font-mono text-xs overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#282A30] pb-2 gap-2">
              <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                <ImageIcon className="w-4 h-4 text-emerald-600 dark:text-[#10B981] shrink-0" />
                <span className="font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] truncate min-w-0 text-xs" title={previewImage.path}>
                  {previewImage.path}
                </span>
              </div>
              <button
                onClick={() => setPreviewImage(null)}
                className="text-slate-400 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-[#22242C] transition-colors shrink-0"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Asset Preview */}
            <div className="p-3 bg-slate-50 dark:bg-[#0E0F12] rounded-xl border border-slate-200 dark:border-[#282A30] flex items-center justify-center max-h-56 overflow-hidden">
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
              <span className="text-slate-600 dark:text-[#9E9E9E] font-medium block">LaTeX Include Snippet:</span>
              <pre className="p-2.5 bg-slate-50 dark:bg-[#0E0F12] rounded-lg border border-slate-200 dark:border-[#282A30] text-emerald-700 dark:text-[#10B981] overflow-x-auto text-[10px] whitespace-pre font-mono">
                {`\\begin{figure}[htbp]
  \\centering
  \\includegraphics[width=0.8\\textwidth]{${previewImage.path}}
  \\caption{${previewImage.name.replace(/_/g, " ")}}
  \\label{fig:${previewImage.name.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_")}}
\\end{figure}`}
              </pre>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200 dark:border-[#282A30] font-mono">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPreviewImage(null)}
                className="h-8 text-xs px-4 rounded-xl border-slate-200 dark:border-[#282A30] bg-slate-100 dark:bg-[#1A1C22] text-slate-600 dark:text-[#9E9E9E] hover:text-slate-900 dark:hover:text-white cursor-pointer"
              >
                Close
              </Button>

              <Button
                size="sm"
                onClick={() => handleDownloadFile(previewImage.path)}
                className="h-8 text-xs bg-slate-100 hover:bg-slate-200 dark:bg-[#1A1C22] dark:hover:bg-[#22242C] text-slate-800 dark:text-[#E2E4E9] font-archivo font-bold rounded-xl border border-slate-200 dark:border-[#282A30] flex items-center gap-1.5 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5 text-emerald-600 dark:text-[#10B981]" />
                <span>Download File</span>
              </Button>

              <Button
                size="sm"
                onClick={() => {
                  copyImageLatexCode(previewImage.path, previewImage.name);
                }}
                className="h-8 text-xs bg-emerald-600 hover:bg-emerald-700 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-white dark:text-[#E2E4E9] font-archivo font-bold rounded-xl border border-emerald-600 dark:border-[#282A30] flex items-center gap-1.5 cursor-pointer"
              >
                {copiedPath === previewImage.path ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-white dark:text-[#10B981]" />
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


