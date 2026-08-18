"use client";

import React, { useState, useEffect } from "react";
import {
  RotateCw,
  Play,
  Eye,
  AlertTriangle,
  Download,
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

  const handleDownloadPDF = () => {
    if (!pdfBase64 && !blobUrl) {
      toast.error("No compiled PDF available to download.");
      return;
    }

    try {
      if (blobUrl) {
        const anchor = document.createElement("a");
        anchor.href = blobUrl;
        anchor.download = "document.pdf";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        toast.success("Downloading PDF document...");
        return;
      }

      const cleanBase64 = (pdfBase64 || "").replace(/^data:application\/pdf;base64,/, "").trim();
      const binaryString = atob(cleanBase64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "document.pdf";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Downloading PDF document...");
    } catch (err) {
      console.error("PDF download error:", err);
      toast.error("Failed to download PDF.");
    }
  };

  return (
    <div className="flex flex-col h-full w-full max-w-full min-w-0 overflow-hidden relative bg-zinc-950 text-zinc-100">
      {/* PDF Header Bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-zinc-800 bg-zinc-950 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-white uppercase">PDF Preview</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={onRecompile}
            disabled={isCompiling}
            className="h-7 px-3 bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold rounded-lg text-xs border border-black shadow-[3px_3px_0px_0px_#000000] flex items-center gap-1.5 cursor-pointer"
            title="Compile TeX PDF"
          >
            {isCompiling ? (
              <RotateCw className="w-3.5 h-3.5 animate-spin text-black" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-current text-black" />
            )}
            <span>Compile</span>
          </Button>

          {blobUrl && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleDownloadPDF}
              className="h-7 px-2.5 text-xs font-mono font-bold border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-white flex items-center gap-1.5"
              title="Download PDF document"
            >
              <Download className="w-3.5 h-3.5 text-[#00CC68]" />
              <span>Download PDF</span>
            </Button>
          )}
        </div>
      </div>

      {/* Loading Overlay */}
      {isCompiling && (
        <div className="absolute inset-0 z-20 bg-zinc-950/90 backdrop-blur-sm flex flex-col items-center justify-center gap-3">
          <RotateCw className="w-8 h-8 text-[#00CC68] animate-spin" />
          <span className="text-xs font-mono text-[#00CC68] font-bold tracking-wider uppercase">
            Compiling TeX PDF...
          </span>
        </div>
      )}

      {/* Error Overlay */}
      {errorLog && !isCompiling && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-6 gap-3 bg-zinc-950/95">
          <AlertTriangle className="w-10 h-10 text-amber-400" />
          <span className="text-sm font-mono font-bold uppercase text-amber-400">Compilation Error</span>
          <pre className="text-[11px] text-zinc-300 font-mono max-w-full overflow-auto bg-zinc-900 border border-zinc-800 rounded-xl p-3 max-h-56 whitespace-pre-wrap select-all">
            {errorLog}
          </pre>
          <Button
            size="sm"
            onClick={onRecompile}
            className="bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold rounded-xl h-8 text-xs mt-2 border border-black shadow-[3px_3px_0px_0px_#000000]"
          >
            <RotateCw className="w-3.5 h-3.5 mr-1.5" />
            Retry Compilation
          </Button>
        </div>
      )}

      {/* PDF Render Block */}
      {blobUrl && !errorLog && (
        <div className="w-full h-full max-w-full min-w-0 flex-1 flex flex-col items-center bg-zinc-950 overflow-hidden">
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
        <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400 font-mono">
          <Eye className="w-12 h-12 opacity-30 text-[#00CC68]" />
          <span className="text-xs font-bold uppercase tracking-wider">No PDF compiled yet</span>
          <Button
            size="sm"
            onClick={onRecompile}
            className="bg-[#00CC68] hover:bg-[#00E676] text-black font-mono font-bold uppercase tracking-wider rounded-xl h-8 text-xs border border-black shadow-[3px_3px_0px_0px_#000000] cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 mr-1.5 fill-current text-black" />
            Compile PDF Now
          </Button>
        </div>
      )}

      {/* Floating Recompile Button for Mobile */}
      <button
        onClick={onRecompile}
        disabled={isCompiling}
        className="md:hidden fixed bottom-[calc(4.5rem+env(safe-area-inset-bottom,0px))] right-4 z-40 w-12 h-12 rounded-full bg-[#00CC68] text-black flex items-center justify-center shadow-2xl border-2 border-black active:scale-95 transition-transform"
        title="Recompile TeX"
      >
        {isCompiling ? (
          <RotateCw className="w-5 h-5 animate-spin text-black" />
        ) : (
          <Play className="w-5 h-5 fill-current ml-0.5 text-black" />
        )}
      </button>
    </div>
  );
}

