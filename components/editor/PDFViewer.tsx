"use client";

import React, { useState, useEffect } from "react";
import {
  RotateCw,
  Play,
  Eye,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { PDFViewer as ExtendPDFViewer } from "@/components/extend/pdf-viewer";

interface PDFViewerProps {
  pdfBase64: string | null;
  isCompiling: boolean;
  onRecompile: () => void;
  errorLog?: string | null;
}

export function PDFViewer({ pdfBase64, isCompiling, onRecompile, errorLog }: PDFViewerProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState<boolean>(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 640);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

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

  return (
    <div className="flex flex-col h-full w-full max-w-full min-w-0 overflow-hidden relative bg-background">
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
        <div className="w-full h-full max-w-full min-w-0 flex-1 flex flex-col items-center bg-zinc-950/60 overflow-hidden">
          <ExtendPDFViewer
            src={blobUrl}
            defaultZoom="automatic"
            showUpload={false}
            showDownload={true}
            showRotateControls={true}
            className="w-full h-full max-w-full min-w-0 overflow-hidden"
          />
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

      {/* Floating Recompile Button for Mobile */}
      <button
        onClick={onRecompile}
        disabled={isCompiling}
        className="md:hidden fixed bottom-[calc(4.5rem+env(safe-area-inset-bottom,0px))] right-4 z-40 w-12 h-12 rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500 text-white flex items-center justify-center shadow-2xl shadow-cyan-500/40 active:scale-95 transition-transform"
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

