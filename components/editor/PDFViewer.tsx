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

  const pdfDataUri = pdfBase64
    ? `data:application/pdf;base64,${pdfBase64}`
    : null;

  const handleZoomIn = () => setZoomLevel(Math.min(200, zoomLevel + 15));
  const handleZoomOut = () => setZoomLevel(Math.max(50, zoomLevel - 15));

  const handleDownload = () => {
    if (!pdfDataUri) return;
    const link = document.createElement("a");
    link.href = pdfDataUri;
    link.download = "main.pdf";
    link.click();
    toast.success("PDF downloaded");
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
    <div className="flex flex-col h-full relative">
      <div className="h-8 px-3 border-b border-border/30 bg-muted/30 flex items-center justify-between text-xs font-mono shrink-0">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Eye className="w-3.5 h-3.5 text-cyan-400" />
          <span>PDF Preview</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleZoomOut} className="p-1 hover:text-foreground text-muted-foreground">
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <span className="text-[10px] text-muted-foreground w-8 text-center">{zoomLevel}%</span>
          <button onClick={handleZoomIn} className="p-1 hover:text-foreground text-muted-foreground">
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          {pdfBase64 && (
            <button onClick={handleDownload} className="p-1 hover:text-foreground text-muted-foreground ml-1">
              <Download className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-zinc-950/40 relative touch-manipulation"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {isCompiling && (
          <div className="absolute inset-0 z-20 bg-background/70 backdrop-blur-sm flex flex-col items-center justify-center gap-3">
            <RotateCw className="w-7 h-7 text-emerald-400 animate-spin" />
            <span className="text-xs font-mono text-emerald-400 font-semibold">Compiling TeX PDF...</span>
          </div>
        )}

        {errorLog && !isCompiling && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-6 gap-3">
            <AlertTriangle className="w-8 h-8 text-amber-400" />
            <span className="text-sm font-bold text-amber-400">Compilation Error</span>
            <pre className="text-[10px] text-muted-foreground font-mono max-w-full overflow-auto bg-card/80 border border-border/40 rounded-lg p-3 max-h-48 whitespace-pre-wrap">
              {errorLog}
            </pre>
            <Button size="sm" onClick={onRecompile} className="bg-amber-600 text-white rounded-lg h-8 text-xs mt-2">
              <RotateCw className="w-3.5 h-3.5 mr-1.5" />
              Retry Compilation
            </Button>
          </div>
        )}

        {pdfDataUri && !errorLog && (
          <div
            className="flex justify-center p-4"
            style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
          >
            <iframe
              src={`${pdfDataUri}#toolbar=0&navpanes=0`}
              className="w-full max-w-2xl bg-white rounded-lg shadow-2xl border border-border/40"
              style={{ height: "calc(100vh - 200px)", minHeight: "500px" }}
              title="LaTeX PDF Preview"
            />
          </div>
        )}

        {!pdfDataUri && !errorLog && !isCompiling && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
            <Eye className="w-10 h-10 opacity-30" />
            <span className="text-xs font-mono">No PDF compiled yet</span>
            <Button size="sm" onClick={onRecompile} className="bg-emerald-600 text-white rounded-lg h-8 text-xs">
              <Play className="w-3.5 h-3.5 mr-1.5 fill-current" />
              Compile Now
            </Button>
          </div>
        )}
      </div>

      <button
        onClick={onRecompile}
        disabled={isCompiling}
        className="md:hidden fixed bottom-20 right-4 z-40 w-12 h-12 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 text-white flex items-center justify-center shadow-2xl shadow-emerald-500/40 active:scale-95 transition-transform"
      >
        {isCompiling ? <RotateCw className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
      </button>
    </div>
  );
}
