"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCw,
  Play,
  Eye,
  AlertTriangle,
  Download,
  ExternalLink,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface PDFViewerProps {
  pdfBase64: string | null;
  isCompiling: boolean;
  onRecompile: () => void;
  errorLog?: string | null;
}

export function PDFViewer({ pdfBase64, isCompiling, onRecompile, errorLog }: PDFViewerProps) {
  const [zoomLevel, setZoomLevel] = useState(100);
  const containerRef = useRef<HTMLDivElement>(null);
  const [touchStartDist, setTouchStartDist] = useState<number | null>(null);
  const [initialZoom, setInitialZoom] = useState(100);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  // Convert Base64 string to Blob URL for native cross-browser & mobile rendering
  useEffect(() => {
    if (!pdfBase64) {
      setBlobUrl(null);
      return;
    }

    try {
      const cleanBase64 = pdfBase64.replace(/^data:application\/pdf;base64,/, "").trim();
      const binaryString = atob(cleanBase64);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      setBlobUrl(url);

      return () => {
        URL.revokeObjectURL(url);
      };
    } catch (err) {
      console.error("PDF Blob creation error:", err);
      toast.error("Failed to render PDF preview.");
    }
  }, [pdfBase64]);

  const handleZoomIn = () => setZoomLevel(Math.min(200, zoomLevel + 15));
  const handleZoomOut = () => setZoomLevel(Math.max(50, zoomLevel - 15));

  const handleDownload = () => {
    if (!blobUrl) return;
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = "main.pdf";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("PDF downloading...");
  };

  const handleOpenNewTab = () => {
    if (!blobUrl) return;
    const newWindow = window.open(blobUrl, "_blank");
    if (!newWindow) {
      toast.error("Pop-up blocked. Please allow pop-ups to open the PDF in a new tab.");
    }
  };

  const getTouchDistance = (touches: React.TouchList) => {
    if (touches.length < 2) return 0;
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      setTouchStartDist(getTouchDistance(e.touches));
      setInitialZoom(zoomLevel);
    }
  }, [zoomLevel]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2 && touchStartDist) {
      const currentDist = getTouchDistance(e.touches);
      const scale = currentDist / touchStartDist;
      const newZoom = Math.max(50, Math.min(200, Math.round(initialZoom * scale)));
      setZoomLevel(newZoom);
    }
  }, [touchStartDist, initialZoom]);

  const handleTouchEnd = useCallback(() => {
    setTouchStartDist(null);
  }, []);

  return (
    <div className="flex flex-col h-full relative bg-background">
      {/* Top Toolbar Header */}
      <div className="h-9 px-3 border-b border-border/40 bg-muted/40 backdrop-blur-md flex items-center justify-between text-xs font-mono shrink-0 z-10">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Eye className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-semibold hidden sm:inline">PDF Preview</span>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Zoom Controls */}
          <div className="flex items-center gap-1 bg-card/60 px-1.5 py-0.5 rounded-md border border-border/30">
            <button
              onClick={handleZoomOut}
              className="p-1 hover:text-foreground text-muted-foreground transition-colors"
              title="Zoom Out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] text-muted-foreground w-8 text-center select-none">
              {zoomLevel}%
            </span>
            <button
              onClick={handleZoomIn}
              className="p-1 hover:text-foreground text-muted-foreground transition-colors"
              title="Zoom In"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>

          {blobUrl && (
            <>
              {/* Open in New Tab Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleOpenNewTab}
                className="h-7 px-2 text-[11px] font-mono gap-1 text-muted-foreground hover:text-foreground hover:bg-card border border-border/30"
                title="Open PDF in New Tab"
              >
                <ExternalLink className="w-3.5 h-3.5 text-indigo-400" />
                <span className="hidden md:inline">Open</span>
              </Button>

              {/* Download PDF Button */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="h-7 px-2 text-[11px] font-mono gap-1 bg-cyan-500/10 border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/20"
                title="Download Compiled PDF"
              >
                <Download className="w-3.5 h-3.5" />
                <span className="hidden sm:inline font-semibold">Download</span>
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Main Preview Container */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-zinc-950/60 relative touch-manipulation flex flex-col items-center"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Loading Overlay */}
        {isCompiling && (
          <div className="absolute inset-0 z-20 bg-background/80 backdrop-blur-sm flex flex-col items-center justify-center gap-3">
            <RotateCw className="w-8 h-8 text-cyan-400 animate-spin" />
            <span className="text-xs font-mono text-cyan-400 font-semibold tracking-wide">
              Compiling TeX PDF...
            </span>
          </div>
        )}

        {/* Error Overlay */}
        {errorLog && !isCompiling && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-6 gap-3 bg-background/90">
            <AlertTriangle className="w-10 h-10 text-amber-400" />
            <span className="text-sm font-bold text-amber-400">Compilation Error</span>
            <pre className="text-[11px] text-muted-foreground font-mono max-w-full overflow-auto bg-card border border-border/50 rounded-xl p-3 max-h-56 whitespace-pre-wrap select-all">
              {errorLog}
            </pre>
            <Button
              size="sm"
              onClick={onRecompile}
              className="bg-amber-600 hover:bg-amber-500 text-white rounded-xl h-8 text-xs mt-2"
            >
              <RotateCw className="w-3.5 h-3.5 mr-1.5" />
              Retry Compilation
            </Button>
          </div>
        )}

        {/* PDF Render Block */}
        {blobUrl && !errorLog && (
          <div className="w-full flex-1 flex flex-col items-center p-2 sm:p-4">
            {/* Mobile Quick Action Card */}
            <div className="sm:hidden w-full mb-3 p-2.5 bg-card/60 border border-border/40 rounded-xl flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2 text-cyan-400 font-medium">
                <FileText className="w-4 h-4" />
                <span>main.pdf</span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={handleOpenNewTab}
                  className="h-7 px-2.5 text-[11px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/40"
                >
                  <ExternalLink className="w-3 h-3 mr-1" />
                  Open
                </Button>
                <Button
                  size="sm"
                  onClick={handleDownload}
                  className="h-7 px-2.5 text-[11px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                >
                  <Download className="w-3 h-3 mr-1" />
                  Save
                </Button>
              </div>
            </div>

            {/* Embedded Native Object/Iframe Viewer */}
            <div
              className="w-full flex-1 flex justify-center transition-transform duration-150 ease-out"
              style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
            >
              <object
                data={`${blobUrl}#toolbar=1&navpanes=0`}
                type="application/pdf"
                className="w-full h-full min-h-[550px] max-w-4xl bg-white rounded-xl shadow-2xl border border-border/30"
              >
                <iframe
                  src={`${blobUrl}#toolbar=1&navpanes=0`}
                  className="w-full h-full min-h-[550px] bg-white rounded-xl border-0"
                  title="LaTeX PDF Preview"
                />
              </object>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!blobUrl && !errorLog && !isCompiling && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
            <Eye className="w-12 h-12 opacity-25 text-cyan-400" />
            <span className="text-xs font-mono">No PDF compiled yet</span>
            <Button
              size="sm"
              onClick={onRecompile}
              className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl h-8 text-xs shadow-lg shadow-emerald-600/20"
            >
              <Play className="w-3.5 h-3.5 mr-1.5 fill-current" />
              Compile PDF Now
            </Button>
          </div>
        )}
      </div>

      {/* Floating Recompile Button for Mobile */}
      <button
        onClick={onRecompile}
        disabled={isCompiling}
        className="md:hidden fixed bottom-20 right-4 z-40 w-12 h-12 rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500 text-white flex items-center justify-center shadow-2xl shadow-cyan-500/40 active:scale-95 transition-transform"
        title="Recompile TeX"
      >
        {isCompiling ? (
          <RotateCw className="w-5 h-5 animate-spin" />
        ) : (
          <Play className="w-5 h-5 fill-current ml-0.5" />
        )}
      </button>
    </div>
  );
}
