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
  Bot,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  PDFViewer as ExtendPDFViewer,
  type PDFViewerHandle,
  type PDFViewerPageOverlayProps,
} from "@/components/extend/pdf-viewer";
import { trpcClient } from "@/trpc/client";

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
  onAskAiToFix?: (errorLog: string) => void;
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
      onAskAiToFix,
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
          const data = await trpcClient.synctex.backward.mutate({
            projectId: projectId || undefined,
            page: pageNumber,
            x: ptX,
            y: ptY,
          });

          if (data && data.file && data.line) {
            onReverseSync?.(data.file, data.line, data.column || 1);
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
    };

    const handlePagePointerUp = useCallback(
      (event: React.PointerEvent<HTMLDivElement>, pageNumber: number) => {
        const pageEl = event.currentTarget;
        setTimeout(() => {
          const sel = window.getSelection();
          if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;
          const anchorNode = sel.anchorNode;
          const focusNode = sel.focusNode;
          const isInsidePage = Boolean(
            (anchorNode && pageEl.contains(anchorNode)) ||
            (focusNode && pageEl.contains(focusNode))
          );
          if (!isInsidePage) return;

          const domText = sel.toString().trim();
          if (domText && domText.length >= 2) {
            onTextSelected?.(domText);
          }
        }, 30);
      },
      [onTextSelected]
    );

    return (
      <div className="flex flex-col h-full w-full max-w-full min-w-0 overflow-hidden relative bg-slate-100 dark:bg-[#0E0F12] text-slate-900 dark:text-[#E2E4E9] transition-colors">
        {/* PDF Header Bar */}
        <div className="h-9 flex items-center justify-between px-3 border-b border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#141519] shrink-0 select-none">
          <div className="flex items-center gap-2">
            <span className="text-xs font-archivo font-bold text-slate-900 dark:text-[#E2E4E9] uppercase tracking-wider">
              PDF Preview
            </span>
            <span
              className="hidden lg:flex items-center gap-1 text-[10px] text-slate-600 dark:text-[#9E9E9E] font-mono bg-white dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] px-2 py-0.5 rounded-full"
              title="Ctrl + Click (Cmd + Click on Mac) any text in the PDF to jump directly to its LaTeX line."
            >
              <HelpCircle className="w-3 h-3 text-[#10B981]" />
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
                className="h-7 px-2.5 text-xs font-mono font-medium border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-700 dark:text-[#E2E4E9] flex items-center gap-1.5 cursor-pointer shadow-xs"
                title="Fullscreen Presentation Mode (Ctrl+Alt+P)"
              >
                <Maximize2 className="w-3.5 h-3.5 text-[#10B981]" />
                <span className="hidden sm:inline">Present</span>
              </Button>
            )}


            {blobUrl && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleDownloadPDF}
                className="h-7 px-2.5 text-xs font-mono font-medium border-slate-200 dark:border-[#282A30] bg-white dark:bg-[#1A1C22] hover:bg-slate-100 dark:hover:bg-[#22242C] text-slate-700 dark:text-[#E2E4E9] flex items-center gap-1.5 cursor-pointer shadow-xs"
                title="Download PDF document"
              >
                <Download className="w-3.5 h-3.5 text-[#10B981]" />
                <span className="hidden sm:inline">Download</span>
              </Button>
            )}
          </div>
        </div>

        {/* Loading Overlay */}
        {isCompiling && (
          <div className="absolute inset-0 z-20 bg-white/90 dark:bg-[#0E0F12]/90 flex flex-col items-center justify-center gap-3 select-none">
            <RotateCw className="w-7 h-7 text-[#10B981] animate-spin" />
            <span className="text-xs font-mono text-[#10B981] font-semibold tracking-wider uppercase">
              Compiling LaTeX document...
            </span>
          </div>
        )}

        {/* Error Overlay */}
        {errorLog && !isCompiling && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-6 gap-3 bg-white/95 dark:bg-[#0E0F12]/95">
            <AlertTriangle className="w-9 h-9 text-amber-500" />
            <span className="text-sm font-mono font-semibold uppercase text-amber-500">
              Compilation Error
            </span>
            <pre className="text-[11px] text-slate-900 dark:text-[#E2E4E9] font-mono max-w-full overflow-auto bg-slate-50 dark:bg-[#1A1C22] border border-slate-200 dark:border-[#282A30] rounded-xl p-3.5 max-h-56 whitespace-pre-wrap select-all">
              {errorLog}
            </pre>
            <div className="flex items-center gap-2 mt-2">
              {onAskAiToFix && (
                <Button
                  size="sm"
                  onClick={() => onAskAiToFix(errorLog)}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white font-archivo font-bold rounded-xl h-8 text-xs border border-emerald-600 shadow-sm cursor-pointer flex items-center gap-1.5"
                  title="Ask AI to fix this LaTeX error"
                >
                  <Bot className="w-3.5 h-3.5 text-white" />
                  <span>Ask AI to Fix</span>
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={onRecompile}
                className="bg-white hover:bg-slate-100 dark:bg-[#22242C] dark:hover:bg-[#2A2C36] text-slate-700 dark:text-[#E2E4E9] font-archivo font-bold rounded-xl h-8 text-xs border border-slate-200 dark:border-[#282A30] cursor-pointer flex items-center gap-1.5"
              >
                <RotateCw className="w-3.5 h-3.5 text-slate-500 dark:text-[#10B981]" />
                <span>Retry Compilation</span>
              </Button>
            </div>
          </div>
        )}

        {/* PDF Render Block */}
        {blobUrl && !errorLog && (
          <div className="w-full h-full max-w-full min-w-0 flex-1 flex flex-col items-center bg-slate-100 dark:bg-[#0E0F12] overflow-hidden">
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
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-500 dark:text-[#9E9E9E] font-mono">
            <Eye className="w-10 h-10 opacity-40 text-emerald-600 dark:text-[#10B981]" />
            <span className="text-xs font-archivo font-bold uppercase tracking-wider text-slate-700 dark:text-[#E2E4E9]">
              No PDF compiled yet
            </span>
            <Button
              size="sm"
              onClick={onRecompile}
              className="bg-emerald-600 hover:bg-emerald-700 text-white font-archivo font-bold uppercase tracking-wider rounded-xl h-8 text-xs border border-emerald-600/30 shadow-sm cursor-pointer"
            >
              <Play className="w-3.5 h-3.5 mr-1.5 fill-current text-white" />
              Compile PDF Now
            </Button>
          </div>
        )}

        {/* Floating Recompile Button for Mobile */}
        <button
          onClick={onRecompile}
          disabled={isCompiling}
          className="md:hidden fixed bottom-[calc(4.5rem+env(safe-area-inset-bottom,0px))] right-4 z-40 w-12 h-12 rounded-full bg-[#10B981] text-white flex items-center justify-center shadow-2xl border border-[#10B981]/40 active:scale-95 transition-transform"
          title="Recompile TeX"
        >
          {isCompiling ? (
            <RotateCw className="w-5 h-5 animate-spin text-white" />
          ) : (
            <Play className="w-5 h-5 fill-current ml-0.5 text-white" />
          )}
        </button>
      </div>
    );
  }
);

