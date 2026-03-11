"use client";

import { useState, useCallback } from "react";
import { trpc } from "@/trpc/client";
import LatexEditor from "@/app/components/LatexEditor";
import PdfPreview from "@/app/components/PdfPreview";
import Toolbar from "@/app/components/Toolbar";

const DEFAULT_LATEX = `\\documentclass{article}
\\begin{document}
Hello World
\\end{document}`;

export default function Home() {
  const [latexContent, setLatexContent] = useState(DEFAULT_LATEX);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string | null>(null);

  const compileMutation = trpc.latex.compileLatex.useMutation({
    onSuccess: (data) => {
      if (data.success && data.pdf) {
        // Convert base64 PDF to blob URL
        const byteCharacters = atob(data.pdf);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: "application/pdf" });
        const url = URL.createObjectURL(blob);

        // Revoke the previous URL to prevent memory leaks
        if (pdfUrl) {
          URL.revokeObjectURL(pdfUrl);
        }

        setPdfUrl(url);
        setError(null);
        setLogs(null);
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
    compileMutation.mutate({ tex: latexContent });
  }, [latexContent, compileMutation]);

  const handleDownload = useCallback(() => {
    if (!pdfUrl) return;

    const link = document.createElement("a");
    link.href = pdfUrl;
    link.download = "document.pdf";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [pdfUrl]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border bg-toolbar-bg px-4 py-3 md:px-6">
        <div className="flex items-center gap-3">
          {/* Logo */}
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
          onCompile={handleCompile}
          onDownload={handleDownload}
          isCompiling={compileMutation.isPending}
          hasPdf={!!pdfUrl}
        />
      </header>

      {/* Split-screen editor area */}
      <main className="flex flex-1 flex-col overflow-hidden md:flex-row">
        {/* Left: Code editor */}
        <div className="flex h-1/2 flex-col border-b border-border p-2 md:h-full md:w-1/2 md:border-b-0 md:border-r md:p-3">
          <LatexEditor value={latexContent} onChange={setLatexContent} />
        </div>

        {/* Right: PDF preview */}
        <div className="flex h-1/2 flex-col p-2 md:h-full md:w-1/2 md:p-3">
          <PdfPreview
            pdfUrl={pdfUrl}
            isCompiling={compileMutation.isPending}
            error={error}
          />
          {logs && (
            <div className="mt-2 flex-1 overflow-auto rounded-lg border border-error/20 bg-error/5 p-4 font-mono text-xs text-error/80">
              <h3 className="mb-2 font-bold uppercase tracking-wider text-error">Compilation Logs</h3>
              <pre className="whitespace-pre-wrap">{logs}</pre>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
