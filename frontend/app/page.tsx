"use client";

import { useState, useCallback, useMemo } from "react";
import { trpc } from "@/trpc/client";
import LatexEditor from "@/app/components/LatexEditor";
import PdfPreview from "@/app/components/PdfPreview";
import Toolbar from "@/app/components/Toolbar";
import FileExplorer from "@/app/components/FileExplorer";

const DEFAULT_FILENAME = "main.tex";
const DEFAULT_LATEX = `\\documentclass{article}
\\begin{document}
Hello World
\\end{document}`;

interface FileItem {
  name: string;
  content: string;
  isBinary?: boolean;
}

export default function Home() {
  const [files, setFiles] = useState<FileItem[]>([
    { name: DEFAULT_FILENAME, content: DEFAULT_LATEX },
  ]);
  const [activeFileName, setActiveFileName] = useState(DEFAULT_FILENAME);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string | null>(null);
  const [theme, setTheme] = useState("latex-dark");

  const activeFile = useMemo(
    () => files.find((f) => f.name === activeFileName) || files[0],
    [files, activeFileName]
  );

  const updateActiveContent = useCallback((content: string) => {
    setFiles((prev) =>
      prev.map((f) => (f.name === activeFileName ? { ...f, content } : f))
    );
  }, [activeFileName]);

  const handleAddFile = useCallback((name: string, content: string = "", isBinary: boolean = false) => {
    if (files.some((f) => f.name === name)) return;
    setFiles((prev) => [...prev, { name, content, isBinary }]);
    setActiveFileName(name);
  }, [files]);

  const handleUploadFile = useCallback((file: File) => {
    const isTex = file.name.endsWith(".tex");
    const reader = new FileReader();

    reader.onload = (e) => {
      let content = e.target?.result as string;

      if (!isTex && content.includes(",")) {
        // Extract base64 part from data URL
        content = content.split(",")[1];
      }

      // If the file already exists, overwrite it. Otherwise, add it.
      setFiles((prev) => {
        if (prev.some(f => f.name === file.name)) {
          return prev.map(f => f.name === file.name ? { ...f, content, isBinary: !isTex } : f);
        }
        return [...prev, { name: file.name, content, isBinary: !isTex }];
      });
      setActiveFileName(file.name);
    };

    if (isTex) {
      reader.readAsText(file);
    } else {
      reader.readAsDataURL(file);
    }
  }, []);

  const handleDeleteFile = useCallback((name: string) => {
    if (files.length <= 1) return;
    setFiles((prev) => prev.filter((f) => f.name !== name));
    if (activeFileName === name) {
      setActiveFileName(files.find((f) => f.name !== name)?.name || "");
    }
  }, [files, activeFileName]);

  const compileMutation = trpc.latex.compileLatex.useMutation({
    onSuccess: async (data) => {
      if (data.success && data.pdf) {
        try {
          const res = await fetch(`data:application/pdf;base64,${data.pdf}`);
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);

          if (pdfUrl) URL.revokeObjectURL(pdfUrl);

          setPdfUrl(url);
          setError(null);
          setLogs(null);
        } catch (e) {
          setError("Failed to render PDF format");
          setLogs(data.logs || "No logs available");
          setPdfUrl(null);
        }
      } else {
        setError("Compilation failed");
        setLogs(data.logs || "No logs available");
        setPdfUrl(null);
      }
    },
    onError: (err) => {
      setError(err.message || "An unexpected error occurred during compilation");
      setLogs(null);
    },
  });

  const handleCompile = useCallback(() => {
    setError(null);
    setLogs(null);

    const mainFileContent = files.find(f => f.name === activeFileName)?.content || "";
    const sideFiles = files.filter(f => f.name !== activeFileName);

    const images = sideFiles
      .filter(f => f.isBinary)
      .map(f => ({ filename: f.name, data: f.content }));

    const textFiles = sideFiles
      .filter(f => !f.isBinary)
      .map(f => ({
        filename: f.name,
        // Backend expects base64 data for all extra files
        data: btoa(unescape(encodeURIComponent(f.content))) // Base64 encode string
      }));

    compileMutation.mutate({
      tex: mainFileContent,
      images,
      files: textFiles
    });
  }, [activeFileName, files, compileMutation]);

  const handleDownload = useCallback(() => {
    if (!pdfUrl) return;
    try {
      const link = document.createElement("a");
      link.href = pdfUrl;
      link.setAttribute("download", `${activeFileName.replace(".tex", "")}.pdf`);
      link.setAttribute("target", "_blank");
      document.body.appendChild(link);
      link.click();
      setTimeout(() => document.body.removeChild(link), 100);
    } catch (err) {
      window.open(pdfUrl, "_blank");
    }
  }, [pdfUrl, activeFileName]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border bg-toolbar-bg px-4 py-3 md:px-6 z-10">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10">
            <svg
              className="h-4.5 w-4.5 text-accent"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
              <polyline points="14,2 14,8 20,8" />
              <line x1="9" y1="13" x2="15" y2="13" />
              <line x1="9" y1="17" x2="15" y2="17" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight text-foreground">
              OverBranch
            </h1>
            <p className="text-[11px] text-muted">LaTeX Editor</p>
          </div>
        </div>

        <Toolbar
          activeFileName={activeFileName}
          onCompile={handleCompile}
          onDownload={handleDownload}
          isCompiling={compileMutation.isPending}
          hasPdf={!!pdfUrl}
          pdfUrl={pdfUrl}
          theme={theme}
          onThemeChange={setTheme}
        />
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar: File Explorer */}
        <FileExplorer
          files={files}
          activeFile={activeFileName}
          onSelectFile={setActiveFileName}
          onAddFile={handleAddFile}
          onUploadFile={handleUploadFile}
          onDeleteFile={handleDeleteFile}
        />

        {/* Split-screen editor area */}
        <main className="flex flex-1 flex-col overflow-hidden md:flex-row">
          {/* Left: Code editor */}
          <div className="flex h-1/2 flex-col border-b border-border p-2 md:h-full md:w-1/2 md:border-b-0 md:border-r md:p-3">
            {activeFile.isBinary ? (
              <div className="flex h-full w-full flex-col items-center justify-center overflow-hidden rounded-lg border border-border bg-surface">
                <svg className="h-12 w-12 text-muted mb-4 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <p className="text-sm font-medium text-foreground">Image File Selected</p>
                <p className="text-xs text-muted mt-1">{activeFile.name}</p>
                <p className="text-xs text-muted/60 mt-4 text-center max-w-[250px]">
                  This file will be included in the compilation bundle.
                </p>
              </div>
            ) : (
              <LatexEditor
                filename={activeFileName}
                value={activeFile.content}
                onChange={updateActiveContent}
                theme={theme}
              />
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
