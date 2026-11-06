"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Upload,
  Download,
  Archive,
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
  Loader2,
  Pencil,
  Lock,
  FileInput,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";
import { useProjectFiles, type ProjectFile } from "@/components/editor/useProjectFiles";

export type { ProjectFile };

interface ProjectFilesPanelProps {
  projectId: string;
  activeFilePath: string;
  isOpen: boolean;
  onClose: () => void;
  onSelectFile: (filePath: string, fileType: "document" | "image") => void;
  onInsertLatexSnippet?: (snippet: string) => void;
  refreshTrigger?: any;
  /** Opens the PDF → LaTeX importer for this project */
  onImportPdf?: () => void;
}

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
const DIALOG_OVERLAY = "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4";
const DIALOG_PANEL =
  "flex w-full max-w-sm flex-col gap-4 rounded-xl border border-ob-line bg-ob-card p-6 text-ob-text shadow-[0_16px_48px_rgba(0,0,0,0.32)]";
const DIALOG_TITLE = "text-[15px] leading-6 font-medium text-ob-text";
const DIALOG_BODY = "text-[13px] leading-5 text-ob-text-2";
const DIALOG_FOOTER = "flex justify-end gap-2 pt-2";

export function ProjectFilesPanel({
  projectId,
  activeFilePath,
  isOpen,
  onClose,
  onSelectFile,
  refreshTrigger,
  onImportPdf,
}: ProjectFilesPanelProps) {
  const { files, loading: isLoading, refetch } = useProjectFiles(projectId, refreshTrigger);
  const [search, setSearch] = useState("");
  const [newFileModal, setNewFileModal] = useState(false);
  const [newFileName, setNewFileName] = useState("");
  const [renameModalFile, setRenameModalFile] = useState<ProjectFile | null>(null);
  const [newRenamePath, setNewRenamePath] = useState("");
  const [previewImage, setPreviewImage] = useState<ProjectFile | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [downloadingPath, setDownloadingPath] = useState<string | null>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!previewImage || !projectId) {
      setPreviewBlobUrl(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return;
    }

    let active = true;
    let url: string | null = null;
    setPreviewLoading(true);
    setPreviewError(null);

    fetch(
      `/api/projects/get-file?project_id=${encodeURIComponent(projectId)}&file_path=${encodeURIComponent(
        previewImage.path
      )}`
    )
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        if (!active) return;
        url = URL.createObjectURL(blob);
        setPreviewBlobUrl(url);
      })
      .catch((err) => {
        if (!active) return;
        setPreviewError(err?.message || "Failed to load asset");
      })
      .finally(() => {
        if (active) setPreviewLoading(false);
      });

    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [previewImage, projectId]);

  const handleFileUpload = async (uploadedFiles: FileList | null) => {
    if (!uploadedFiles || uploadedFiles.length === 0) return;

    for (let i = 0; i < uploadedFiles.length; i++) {
      const file = uploadedFiles[i];
      const formData = new FormData();
      formData.append("project_id", projectId);
      formData.append("file", file);

      try {
        const res = await authFetch(`${BACKEND_URL}/api/projects/upload-asset`, {
          method: "POST",
          body: formData,
        });

        if (res.ok) {
          toast.success(`Uploaded ${file.name}`);
        } else {
          toast.error(`Failed to upload ${file.name}`);
        }
      } catch (err) {
        toast.error(`Error uploading ${file.name}`);
      }
    }

    refetch();
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleCreateFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFileName.trim()) return;

    let path = newFileName.trim();
    if (!path.includes(".")) path += ".tex";

    try {
      const res = await authFetch(`${BACKEND_URL}/api/projects/save-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          file_path: path,
          raw_code: path.endsWith(".bib") ? "% Bibliography entries\n" : "% LaTeX source file\n",
        }),
      });

      if (res.ok) {
        toast.success(`Created ${path}`);
        setNewFileName("");
        setNewFileModal(false);
        refetch();
        onSelectFile(path, "document");
      } else {
        toast.error("Failed to create file.");
      }
    } catch (err) {
      toast.error("Error creating file.");
    }
  };

  const handleRenameFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!renameModalFile || !newRenamePath.trim() || newRenamePath === renameModalFile.path) return;

    try {
      const res = await authFetch(`${BACKEND_URL}/api/projects/rename-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          old_path: renameModalFile.path,
          new_path: newRenamePath.trim(),
        }),
      });

      if (res.ok) {
        toast.success(`Renamed to ${newRenamePath.trim()}`);
        const oldP = renameModalFile.path;
        const newP = newRenamePath.trim();
        setRenameModalFile(null);
        refetch();
        if (activeFilePath === oldP) {
          onSelectFile(newP, renameModalFile.type);
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
        refetch();
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
    if (!projectId) return;

    const fileName = filePath.split("/").pop() || filePath;
    const href = `/api/projects/get-file?project_id=${encodeURIComponent(projectId)}&file_path=${encodeURIComponent(filePath)}&download=1`;
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = fileName;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  const handleDownloadProject = () => {
    if (!projectId) return;
    const anchor = document.createElement("a");
    anchor.href = `/api/projects/export?project_id=${encodeURIComponent(projectId)}`;
    anchor.download = "project.zip";
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  const getFileIcon = (ext: string, type: "document" | "image") => {
    if (type === "image" || [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"].includes(ext)) {
      return <ImageIcon className="size-4 shrink-0 text-ob-muted" />;
    }
    if (ext === ".tex") return <FileText className="size-4 shrink-0 text-ob-accent" />;
    if (ext === ".bib") return <BookOpen className="size-4 shrink-0 text-ob-muted" />;
    if ([".cls", ".sty"].includes(ext)) return <FileCode className="size-4 shrink-0 text-ob-muted" />;
    if (ext === ".pdf") return <FileCheck className="size-4 shrink-0 text-ob-muted" />;
    return <File className="size-4 shrink-0 text-ob-muted" />;
  };

  const filteredFiles = files.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()) || f.path.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div
      className={`flex h-full shrink-0 flex-col overflow-hidden border-r border-ob-line bg-ob-deep text-ob-text transition-all duration-200 ${
        isOpen ? "w-full opacity-100 md:w-52 lg:w-60 xl:w-64" : "pointer-events-none w-0 border-r-0 opacity-0"
      }`}
    >
      {/* Panel Header */}
      <div className="flex h-10 shrink-0 select-none items-center justify-between border-b border-ob-line bg-ob-deep px-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-ob-text">Files</span>
          <span className="font-mono text-xs text-ob-muted tabular-nums">
            {files.length}
          </span>
        </div>

        <div className="flex items-center gap-0.5">
          {onImportPdf && (
            <button
              onClick={onImportPdf}
              className="flex size-7 cursor-pointer items-center justify-center rounded-md text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
              title="Import PDF as LaTeX"
              aria-label="Import PDF as LaTeX"
            >
              <FileInput className="size-3.5" />
            </button>
          )}
          <button
            onClick={handleDownloadProject}
            className="flex size-7 cursor-pointer items-center justify-center rounded-md text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
            title="Download project (.zip)"
            aria-label="Download project (.zip)"
          >
            <Archive className="size-3.5" />
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex size-7 cursor-pointer items-center justify-center rounded-md text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
            title="Upload asset"
            aria-label="Upload asset"
          >
            <Upload className="size-3.5" />
          </button>

          <button
            onClick={() => setNewFileModal(true)}
            className="flex size-7 cursor-pointer items-center justify-center rounded-md text-ob-muted transition-colors hover:bg-ob-raised hover:text-ob-text"
            title="New file"
            aria-label="New file"
          >
            <Plus className="size-3.5" />
          </button>
        </div>
      </div>

      <div
        className="flex flex-1 flex-col gap-2 overflow-hidden p-2 text-xs"
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

        {/* Search */}
        <div className="relative shrink-0">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ob-muted" />
          <Input
            placeholder="Search files"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-7 rounded-md border-ob-line bg-ob-raised pr-2 pl-7 font-mono text-xs text-ob-text shadow-none placeholder:text-ob-muted"
          />
        </div>

        {/* File Tree List */}
        <div className="flex-1 space-y-0.5 overflow-y-auto pr-0.5 font-mono">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-xs text-ob-muted">
              <Loader2 className="size-3.5 animate-spin" />
              <span>Loading files</span>
            </div>
          ) : filteredFiles.length === 0 ? (
            <div className="py-8 text-center text-xs text-ob-muted">
              No files found
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
                  className={`group flex cursor-pointer items-center justify-between gap-2 overflow-hidden rounded-md px-2 py-1.5 text-xs transition-colors ${
                    isActive
                      ? "bg-ob-raised font-medium text-ob-text"
                      : "text-ob-text-2 hover:bg-ob-raised hover:text-ob-text"
                  }`}
                >
                  <div className="flex min-w-0 flex-1 items-center gap-2 truncate">
                    {getFileIcon(file.ext, file.type)}
                    <span className="min-w-0 truncate font-mono text-[11px]" title={file.path}>
                      {file.path}
                    </span>
                  </div>

                  <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={(e) => handleDownloadFile(file.path, e)}
                      disabled={downloadingPath === file.path}
                      className="flex size-5 items-center justify-center rounded text-ob-muted transition-colors hover:text-ob-text disabled:opacity-50"
                      title="Download"
                    >
                      {downloadingPath === file.path ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <Download className="size-3" />
                      )}
                    </button>

                    {isAsset && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          copyImageLatexCode(file.path, file.name);
                        }}
                        className="flex size-5 items-center justify-center rounded text-ob-muted transition-colors hover:text-ob-text"
                        title="Copy figure snippet"
                      >
                        {copiedPath === file.path ? <Check className="size-3 text-ob-positive" /> : <Copy className="size-3" />}
                      </button>
                    )}

                    {isMainTex ? (
                      <span className="flex size-5 items-center justify-center text-ob-muted" title="Primary main.tex">
                        <Lock className="size-3" />
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
                          className="flex size-5 items-center justify-center rounded text-ob-muted transition-colors hover:text-ob-text"
                          title="Rename"
                        >
                          <Pencil className="size-3" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteFile(file.path, e)}
                          className="flex size-5 items-center justify-center rounded text-ob-muted transition-colors hover:text-ob-negative"
                          title="Delete"
                        >
                          <Trash2 className="size-3" />
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
        <div className={DIALOG_OVERLAY} onClick={() => setNewFileModal(false)}>
          <div className={DIALOG_PANEL} onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-col gap-1">
              <h3 className={DIALOG_TITLE}>Create new file</h3>
              <p className={DIALOG_BODY}>Enter file path (e.g. sections/intro.tex or refs.bib)</p>
            </div>
            <form onSubmit={handleCreateFile} className="flex flex-col gap-4">
              <Input
                autoFocus
                placeholder="sections/intro.tex"
                value={newFileName}
                onChange={(e) => setNewFileName(e.target.value)}
                className="h-9 rounded-lg border-ob-line bg-ob-raised px-3 font-mono text-sm text-ob-text shadow-none placeholder:text-ob-muted"
              />
              <div className={DIALOG_FOOTER}>
                <Button
                  size="sm"
                  variant="ob-quiet"
                  type="button"
                  onClick={() => setNewFileModal(false)}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="ob-primary"
                  type="submit"
                  disabled={!newFileName.trim()}
                >
                  Create file
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Rename File Modal */}
      {renameModalFile && (
        <div className={DIALOG_OVERLAY} onClick={() => setRenameModalFile(null)}>
          <div className={DIALOG_PANEL} onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-col gap-1">
              <h3 className={DIALOG_TITLE}>Rename file</h3>
              <p className={DIALOG_BODY}>New path for {renameModalFile.name}</p>
            </div>
            <form onSubmit={handleRenameFile} className="flex flex-col gap-4">
              <Input
                autoFocus
                value={newRenamePath}
                onChange={(e) => setNewRenamePath(e.target.value)}
                className="h-9 rounded-lg border-ob-line bg-ob-raised px-3 font-mono text-sm text-ob-text shadow-none placeholder:text-ob-muted"
              />
              <div className={DIALOG_FOOTER}>
                <Button
                  size="sm"
                  variant="ob-quiet"
                  type="button"
                  onClick={() => setRenameModalFile(null)}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="ob-primary"
                  type="submit"
                  disabled={!newRenamePath.trim() || newRenamePath === renameModalFile.path}
                >
                  Rename
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Asset Preview & TeX Snippet Modal */}
      {previewImage && (
        <div className={DIALOG_OVERLAY} onClick={() => setPreviewImage(null)}>
          <div className="flex w-full max-w-lg flex-col gap-4 rounded-xl border border-ob-line bg-ob-card p-6 text-ob-text shadow-[0_16px_48px_rgba(0,0,0,0.32)]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className={DIALOG_TITLE}>{previewImage.path}</h3>
              <button
                onClick={() => setPreviewImage(null)}
                className="text-ob-muted hover:text-ob-text"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex min-h-[12rem] max-h-64 items-center justify-center overflow-hidden rounded-lg border border-ob-line bg-ob-deep p-3">
              {previewLoading ? (
                <div className="flex items-center gap-2 text-xs text-ob-muted">
                  <Loader2 className="size-4 animate-spin" />
                  <span>Loading asset</span>
                </div>
              ) : previewError ? (
                <div className="text-xs text-ob-muted">{previewError}</div>
              ) : previewBlobUrl ? (
                previewImage.ext.toLowerCase() === ".pdf" ? (
                  <iframe src={previewBlobUrl} title={previewImage.name} className="h-56 w-full rounded border-0" />
                ) : (
                  <img src={previewBlobUrl} alt={previewImage.name} className="max-h-56 rounded object-contain" />
                )
              ) : null}
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-xs text-ob-text-2">LaTeX figure snippet</span>
              <pre className="overflow-x-auto rounded-lg border border-ob-line bg-ob-raised p-3 font-mono text-[11px] text-ob-text leading-relaxed">
{`\\begin{figure}[htbp]
  \\centering
  \\includegraphics[width=0.8\\textwidth]{${previewImage.path}}
  \\caption{${previewImage.name.replace(/_/g, " ")}}
  \\label{fig:${previewImage.name.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_")}}
\\end{figure}`}
              </pre>
            </div>

            <div className={DIALOG_FOOTER}>
              <Button
                variant="ob-quiet"
                size="sm"
                onClick={() => setPreviewImage(null)}
              >
                Close
              </Button>
              <Button
                variant="ob-secondary"
                size="sm"
                onClick={() => handleDownloadFile(previewImage.path)}
                disabled={downloadingPath === previewImage.path}
              >
                <Download className="size-3.5" />
                <span>Download</span>
              </Button>
              <Button
                variant="ob-primary"
                size="sm"
                onClick={() => copyImageLatexCode(previewImage.path, previewImage.name)}
              >
                {copiedPath === previewImage.path ? (
                  <>
                    <Check className="size-3.5" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="size-3.5" />
                    <span>Copy snippet</span>
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
