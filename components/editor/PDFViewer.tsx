"use client";

import React, {
  useState,
  useEffect,
  useRef,
  useImperativeHandle,
  forwardRef,
  useCallback,
} from "react";
import {
  RotateCw,
  Play,
  Eye,
  AlertTriangle,
  Download,
  Maximize2,
  HelpCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  PDFViewer as ExtendPDFViewer,
  type PDFViewerHandle,
  type PDFViewerPageOverlayProps,
} from "@/components/extend/pdf-viewer";
import type { SyncTeXBackwardResult } from "@/types/sync";

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

export interface PDFViewerRefHandle {
  scrollToDestination: (
    page: number,
    x: number,
    y: number,
    width: number,
    height: number
  ) => void;
  getBlobUrl: () => string | null;
}

interface PDFViewerProps {
  pdfBase64: string | null;
  isCompiling: boolean;
  onRecompile: () => void;
  errorLog?: string | null;
  projectId?: string;
  onReverseSync?: (file: string, line: number, column: number) => void;
  onTextSelected?: (text: string) => void;
  onEnterPresentation?: () => void;
}



export const PDFViewer = forwardRef<PDFViewerRefHandle, PDFViewerProps>(
  function PDFViewer(
    {
      pdfBase64,
      isCompiling,
      onRecompile,
      errorLog,
      projectId,
      onReverseSync,
      onTextSelected,
      onEnterPresentation,
    },
    ref
  ) {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [isMobile, setIsMobile] = useState<boolean>(false);
    const extendViewerRef = useRef<PDFViewerHandle>(null);
    const isUserScrollingRef = useRef(false);
    const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
      const checkMobile = () => {
        setIsMobile(window.innerWidth < 640);
      };
      checkMobile();
      window.addEventListener("resize", checkMobile);
      return () => window.removeEventListener("resize", checkMobile);
    }, []);

    // Convert Base64 string to Blob URL
    useEffect(() => {
      if (!pdfBase64) {
        setBlobUrl(null);
        return;
      }

      try {
        const cleanBase64 = pdfBase64
          .replace(/^data:application\/pdf;base64,/, "")
          .trim();
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

    // Track user manual scrolling to suppress auto-scroll interruption
    useEffect(() => {
      const handleUserScrollInteraction = () => {
        isUserScrollingRef.current = true;
        if (scrollTimeoutRef.current) {
          clearTimeout(scrollTimeoutRef.current);
        }
        scrollTimeoutRef.current = setTimeout(() => {
          isUserScrollingRef.current = false;
        }, 1000);
      };

      const vp = extendViewerRef.current?.getViewportElement();
      if (vp) {
        vp.addEventListener("wheel", handleUserScrollInteraction, {
          passive: true,
        });
        vp.addEventListener("touchmove", handleUserScrollInteraction, {
          passive: true,
        });
        return () => {
          vp.removeEventListener("wheel", handleUserScrollInteraction);
          vp.removeEventListener("touchmove", handleUserScrollInteraction);
        };
      }
    }, [blobUrl]);

    // Forward Sync method exposed via ref
    useImperativeHandle(ref, () => ({
      scrollToDestination: (page, x, y, width, height) => {
        // Do not auto-scroll if user is actively scrolling the PDF
        if (isUserScrollingRef.current) return;

        // Smooth scroll to destination without drawing blocking overlays on the PDF
        try {
          extendViewerRef.current?.scrollToPageArea(
            page,
            {
              top: Math.max(0, y - 60),
              left: Math.max(0, x - 20),
              width: width || 200,
              height: height || 16,
            },
            { behavior: "smooth" }
          );
        } catch (scrollErr) {
          extendViewerRef.current?.scrollToPage(page, { behavior: "smooth" });
        }
      },
      getBlobUrl: () => blobUrl,
    }));

    // Reverse SyncTeX click handler (triggered on Ctrl/Cmd + click or double-click)
    const handlePagePointerDown = useCallback(
      async (
        event: React.PointerEvent<HTMLDivElement>,
        pageNumber: number
      ) => {
        // Only trigger reverse SyncTeX on Ctrl/Cmd + click or double-click (event.detail >= 2)
        const isSyncAction = event.ctrlKey || event.metaKey || event.detail >= 2;
        if (!isSyncAction) return;

        const pageEl = event.currentTarget;
        const rect = pageEl.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const clickY = event.clientY - rect.top;

        // Standard TeX resolution is 72 dpi (big points)
        const attrWidth = parseFloat(pageEl.getAttribute("data-page-width") || "0");
        const attrScale = parseFloat(pageEl.getAttribute("data-page-scale") || "0");

        const scale = attrScale > 0
          ? attrScale
          : attrWidth > 0
            ? rect.width / attrWidth
            : rect.width / 595.28;

        const ptX = clickX / (scale || 1.0);
        const ptY = clickY / (scale || 1.0);

        try {
          let res = await fetch(`${BACKEND_URL}/api/synctex/backward`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              page: pageNumber,
              x: ptX,
              y: ptY,
              project_id: projectId || "",
            }),
          });

          // If direct backend request failed, try local Next.js proxy route
          if (!res.ok) {
            res = await fetch(`/api/synctex/backward`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                page: pageNumber,
                x: ptX,
                y: ptY,
                project_id: projectId || "",
              }),
            });
          }

          if (res.ok) {
            const data: SyncTeXBackwardResult = await res.json();
            if (data && data.line) {
              onReverseSync?.(data.file, data.line, data.column || 1);
            }
          }
        } catch (_) {
          // Graceful handling without intrusive error toast in PDF section
        }
      },
      [projectId, onReverseSync]
    );

    const handleDownloadPDF = () => {
      if (!blobUrl) {
        toast.error("No compiled PDF available to download.");
        return;
      }
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = "document.pdf";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      toast.success("Downloading PDF document...");
    };

    const handlePagePointerUp = useCallback(
      (event: React.PointerEvent<HTMLDivElement>, pageNumber: number) => {
        setTimeout(() => {
          const domText = window.getSelection()?.toString()?.trim();
          if (domText && domText.length >= 2) {
            onTextSelected?.(domText);
          }
        }, 30);
      },
      [onTextSelected]
    );

    return (
      <div className="flex flex-col h-full w-full max-w-full min-w-0 overflow-hidden relative bg-zinc-950 text-zinc-100">
        {/* PDF Header Bar */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-zinc-800 bg-zinc-950 shrink-0 select-none">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold text-white uppercase tracking-wider">
              PDF Preview
            </span>
            <span
              className="hidden lg:flex items-center gap-1 text-[10px] text-zinc-400 font-mono bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded-full"
              title="Ctrl + Click (Cmd + Click on Mac) any text in the PDF to jump directly to its LaTeX line."
            >
              <HelpCircle className="w-3 h-3 text-[#00CC68]" />
              <span>Ctrl+Click to Sync</span>
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Present Button */}
            {blobUrl && (
              <Button
                size="sm"
                variant="outline"
                onClick={onEnterPresentation}
                className="h-7 px-2.5 text-xs font-mono font-bold border-purple-500/40 bg-purple-950/30 hover:bg-purple-900/40 text-purple-300 flex items-center gap-1.5 cursor-pointer shadow-xs"
                title="Fullscreen Presentation Mode (Ctrl+Alt+P)"
              >
                <Maximize2 className="w-3.5 h-3.5 text-purple-400" />
                <span className="hidden sm:inline">Present</span>
              </Button>
            )}

            {/* Recompile Button */}
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
                className="h-7 px-2.5 text-xs font-mono font-bold border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-white flex items-center gap-1.5 cursor-pointer"
                title="Download PDF document"
              >
                <Download className="w-3.5 h-3.5 text-[#00CC68]" />
                <span className="hidden sm:inline">Download</span>
              </Button>
            )}
          </div>
        </div>

        {/* Loading Overlay */}
        {isCompiling && (
          <div className="absolute inset-0 z-20 bg-zinc-950/90 backdrop-blur-sm flex flex-col items-center justify-center gap-3 select-none">
            <RotateCw className="w-8 h-8 text-[#00CC68] animate-spin" />
            <span className="text-xs font-mono text-[#00CC68] font-bold tracking-wider uppercase">
              Compiling TeX PDF with SyncTeX...
            </span>
          </div>
        )}

        {/* Error Overlay */}
        {errorLog && !isCompiling && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-6 gap-3 bg-zinc-950/95">
            <AlertTriangle className="w-10 h-10 text-amber-400" />
            <span className="text-sm font-mono font-bold uppercase text-amber-400">
              Compilation Error
            </span>
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
              ref={extendViewerRef}
              src={blobUrl}
              defaultZoom="automatic"
              showUpload={false}
              showDownload={true}
              showRotateControls={true}
              className="w-full h-full max-w-full min-w-0 overflow-hidden"
              onPagePointerDown={handlePagePointerDown}
              onPagePointerUp={handlePagePointerUp}
              onTextSelected={onTextSelected}
            />
          </div>
        )}

        {/* Empty State */}
        {!blobUrl && !errorLog && !isCompiling && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400 font-mono">
            <Eye className="w-12 h-12 opacity-30 text-[#00CC68]" />
            <span className="text-xs font-bold uppercase tracking-wider">
              No PDF compiled yet
            </span>
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
);
