"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  X,
  Radio,
  Flame,
  Maximize2,
  Minimize2,
  RotateCcw,
} from "lucide-react";
import { renderPdfSlide, getPdfPageCount } from "@/lib/pdf-thumbnail-utils";

interface PresentationViewProps {
  blobUrl: string | null;
  onExit: () => void;
  initialPage?: number;
}

export function PresentationView({
  blobUrl,
  onExit,
  initialPage = 1,
}: PresentationViewProps) {
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [totalPages, setTotalPages] = useState(1);
  const [slideUrl, setSlideUrl] = useState<string | null>(null);
  const [isLoadingSlide, setIsLoadingSlide] = useState(true);
  const [zoomScale, setZoomScale] = useState(1.0);
  const [laserActive, setLaserActive] = useState(false);
  const [laserPos, setLaserPos] = useState<{ x: number; y: number }>({
    x: -100,
    y: -100,
  });
  const [controlsVisible, setControlsVisible] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const hideControlsTimerRef = useRef<NodeJS.Timeout | null>(null);
  const slideCacheRef = useRef<Map<number, string>>(new Map());

  // Auto-request browser fullscreen on mount
  useEffect(() => {
    try {
      if (
        document.documentElement.requestFullscreen &&
        !document.fullscreenElement
      ) {
        document.documentElement.requestFullscreen().catch(() => {});
      }
    } catch (_) {}

    const handleFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      try {
        if (document.fullscreenElement && document.exitFullscreen) {
          document.exitFullscreen().catch(() => {});
        }
      } catch (_) {}
    };
  }, []);

  // Fetch total page count on mount
  useEffect(() => {
    if (!blobUrl) return;
    let cancelled = false;

    getPdfPageCount(blobUrl)
      .then((count) => {
        if (!cancelled && count > 0) {
          setTotalPages(count);
        }
      })
      .catch((err) => {
        console.warn("Could not determine page count:", err);
      });

    return () => {
      cancelled = true;
    };
  }, [blobUrl]);

  // Render current slide
  useEffect(() => {
    if (!blobUrl) return;
    let cancelled = false;

    const pageIndex = Math.max(0, currentPage - 1);

    // Check memory cache first - 0ms instant display!
    const cached = slideCacheRef.current.get(pageIndex);
    if (cached) {
      setSlideUrl(cached);
      setIsLoadingSlide(false);
    } else {
      setIsLoadingSlide(true);
    }

    renderPdfSlide({
      url: blobUrl,
      pageIndex,
      targetWidth: 1920,
      targetHeight: 1080,
    })
      .then((res) => {
        if (cancelled || !res) return;
        slideCacheRef.current.set(pageIndex, res.url);
        setSlideUrl(res.url);
        if (res.pageCount > 0) {
          setTotalPages(res.pageCount);
        }
        setIsLoadingSlide(false);

        // Pre-fetch adjacent slides
        if (pageIndex + 1 < res.pageCount && !slideCacheRef.current.has(pageIndex + 1)) {
          renderPdfSlide({
            url: blobUrl,
            pageIndex: pageIndex + 1,
            targetWidth: 1920,
            targetHeight: 1080,
          }).then((nextRes) => {
            if (nextRes) slideCacheRef.current.set(pageIndex + 1, nextRes.url);
          });
        }
        if (pageIndex - 1 >= 0 && !slideCacheRef.current.has(pageIndex - 1)) {
          renderPdfSlide({
            url: blobUrl,
            pageIndex: pageIndex - 1,
            targetWidth: 1920,
            targetHeight: 1080,
          }).then((prevRes) => {
            if (prevRes) slideCacheRef.current.set(pageIndex - 1, prevRes.url);
          });
        }
      })
      .catch((err) => {
        console.warn("Failed to render slide image:", err);
        if (!cancelled) setIsLoadingSlide(false);
      });

    return () => {
      cancelled = true;
    };
  }, [blobUrl, currentPage]);

  // Background pre-cache all remaining slides for 0ms instantaneous flipping
  useEffect(() => {
    if (!blobUrl || totalPages <= 1) return;
    let isCancelled = false;

    const preloadAll = async () => {
      for (let p = 0; p < totalPages; p++) {
        if (isCancelled) break;
        if (!slideCacheRef.current.has(p)) {
          const res = await renderPdfSlide({
            url: blobUrl,
            pageIndex: p,
            targetWidth: 1920,
            targetHeight: 1080,
          });
          if (res && !isCancelled) {
            slideCacheRef.current.set(p, res.url);
          }
        }
      }
    };

    preloadAll();
    return () => {
      isCancelled = true;
    };
  }, [blobUrl, totalPages]);

  // Show floating controls on mouse move and auto-hide after 3s
  const showControlsTemporarily = useCallback(() => {
    setControlsVisible(true);
    if (hideControlsTimerRef.current) {
      clearTimeout(hideControlsTimerRef.current);
    }
    hideControlsTimerRef.current = setTimeout(() => {
      setControlsVisible(false);
    }, 3000);
  }, []);

  // Initialize 3s auto-hide timer immediately on mount
  useEffect(() => {
    showControlsTemporarily();
    return () => {
      if (hideControlsTimerRef.current) {
        clearTimeout(hideControlsTimerRef.current);
      }
    };
  }, [showControlsTemporarily]);

  const goToPage = useCallback(
    (pageNum: number) => {
      const clamped = Math.max(1, Math.min(pageNum, totalPages));
      setCurrentPage(clamped);
      setZoomScale(1.0);
    },
    [totalPages]
  );

  const handleNextPage = useCallback(() => {
    goToPage(currentPage + 1);
  }, [currentPage, goToPage]);

  const handlePrevPage = useCallback(() => {
    goToPage(currentPage - 1);
  }, [currentPage, goToPage]);

  // Keyboard navigation: right, up, down, left can control slides
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Hold 'L' for laser pointer
      if (e.key === "l" || e.key === "L") {
        setLaserActive(true);
        return;
      }

      // Next slide: Right arrow, Down arrow, Space, PageDown, Enter
      if (
        e.key === "ArrowRight" ||
        e.key === "ArrowDown" ||
        e.key === " " ||
        e.key === "PageDown" ||
        e.key === "Enter"
      ) {
        e.preventDefault();
        handleNextPage();
      }
      // Previous slide: Left arrow, Up arrow, Backspace, PageUp
      else if (
        e.key === "ArrowLeft" ||
        e.key === "ArrowUp" ||
        e.key === "Backspace" ||
        e.key === "PageUp"
      ) {
        e.preventDefault();
        handlePrevPage();
      } else if (e.key === "Home") {
        e.preventDefault();
        goToPage(1);
      } else if (e.key === "End") {
        e.preventDefault();
        goToPage(totalPages);
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setZoomScale((z) => Math.min(z + 0.25, 3.0));
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        setZoomScale((z) => Math.max(z - 0.25, 0.5));
      } else if (e.key === "0") {
        e.preventDefault();
        setZoomScale(1.0);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onExit();
      } else if (e.key === "f" || e.key === "F") {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen().catch(() => {});
        } else {
          document.exitFullscreen().catch(() => {});
        }
      }
      showControlsTemporarily();
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === "l" || e.key === "L") {
        setLaserActive(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [handleNextPage, handlePrevPage, goToPage, totalPages, onExit, showControlsTemporarily]);

  // Track mouse coordinates for laser pointer
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      setLaserPos({ x: e.clientX, y: e.clientY });
      showControlsTemporarily();
    },
    [showControlsTemporarily]
  );

  // Click on slide sides to advance or go back
  const handleSlideAreaClick = (e: React.MouseEvent<HTMLDivElement>) => {
    // If laser is active or controls were clicked, don't trigger slide advance
    if (laserActive) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const xFraction = (e.clientX - rect.left) / rect.width;
    if (xFraction > 0.55) {
      handleNextPage();
    } else if (xFraction < 0.45) {
      handlePrevPage();
    }
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  };

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      className="fixed inset-0 z-[99999] bg-black flex flex-col items-center justify-center select-none overflow-hidden cursor-default"
    >
      {/* Slide Display Area */}
      <div
        onClick={handleSlideAreaClick}
        className="w-full h-full flex items-center justify-center relative p-2 sm:p-4 overflow-hidden"
      >
        {slideUrl ? (
          <img
            key={`slide-${currentPage}`}
            src={slideUrl}
            alt={`Slide ${currentPage}`}
            className="max-w-full max-h-full object-contain shadow-[0_0_40px_rgba(0,0,0,0.9)] rounded-xs pointer-events-none transition-transform duration-150 ease-out"
            style={{
              transform: `scale(${zoomScale})`,
              transformOrigin: "center center",
            }}
          />
        ) : (
          /* Fallback native object / iframe viewer if engine is compiling */
          blobUrl && (
            <object
              data={`${blobUrl}#page=${currentPage}&toolbar=0&navpanes=0&scrollbar=0&view=Fit`}
              type="application/pdf"
              className="w-full h-full max-w-full max-h-full pointer-events-auto border-none"
            >
              <div className="text-white text-sm font-mono text-center">
                Loading presentation slide...
              </div>
            </object>
          )
        )}

        {/* Loading Indicator */}
        {isLoadingSlide && !slideUrl && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60 backdrop-blur-xs z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 rounded-full border-2 border-[#00CC68] border-t-transparent animate-spin" />
              <span className="text-xs font-mono text-[#00CC68] font-bold uppercase tracking-wider">
                Loading Slide {currentPage}...
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Laser Pointer Dot */}
      {laserActive && (
        <div
          className="fixed pointer-events-none z-[100001] w-6 h-6 rounded-full bg-red-500/90 shadow-[0_0_24px_8px_rgba(239,68,68,0.95)] animate-pulse -translate-x-1/2 -translate-y-1/2 transition-transform duration-75"
          style={{
            left: `${laserPos.x}px`,
            top: `${laserPos.y}px`,
          }}
        >
          <div className="w-2 h-2 rounded-full bg-white absolute inset-0 m-auto" />
        </div>
      )}

      {/* Laser Active Status Indicator */}
      {laserActive && (
        <div className="fixed top-4 left-4 z-[100000] px-3 py-1 rounded-full bg-red-600/30 border border-red-500 text-red-300 text-xs font-mono font-bold flex items-center gap-1.5 shadow-lg animate-pulse pointer-events-none">
          <Flame className="w-3.5 h-3.5 text-red-400" />
          <span>Laser Active (Release L to hide)</span>
        </div>
      )}

      {/* Floating HUD Controls */}
      <div
        className={`fixed bottom-6 z-[100000] flex items-center gap-2 px-3.5 py-2 rounded-2xl bg-zinc-950/90 backdrop-blur-md border border-zinc-800 text-zinc-100 shadow-2xl transition-all duration-300 select-none ${
          controlsVisible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-4 pointer-events-none"
        }`}
      >
        {/* Page Navigation */}
        <div className="flex items-center gap-1 font-mono text-xs text-zinc-300">
          <button
            type="button"
            onClick={handlePrevPage}
            disabled={currentPage <= 1}
            className="p-1.5 rounded-lg hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-white cursor-pointer"
            title="Previous Slide (← or Backspace)"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="px-2 font-bold min-w-[80px] text-center text-xs">
            Slide {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            onClick={handleNextPage}
            disabled={currentPage >= totalPages}
            className="p-1.5 rounded-lg hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-white cursor-pointer"
            title="Next Slide (→, Space or Click)"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        <div className="w-px h-5 bg-zinc-800 mx-1" />

        {/* Zoom Controls */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setZoomScale((z) => Math.max(z - 0.25, 0.5))}
            className="p-1.5 rounded-lg hover:bg-zinc-800 transition-colors text-zinc-300 hover:text-white cursor-pointer"
            title="Zoom Out (-)"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoomScale(1.0)}
            className="px-2 py-1 rounded-lg hover:bg-zinc-800 text-[11px] font-mono font-bold text-zinc-300 hover:text-[#00CC68] transition-colors cursor-pointer"
            title="Reset Zoom (0)"
          >
            {Math.round(zoomScale * 100)}%
          </button>
          <button
            type="button"
            onClick={() => setZoomScale((z) => Math.min(z + 0.25, 3.0))}
            className="p-1.5 rounded-lg hover:bg-zinc-800 transition-colors text-zinc-300 hover:text-white cursor-pointer"
            title="Zoom In (+)"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
        </div>

        <div className="w-px h-5 bg-zinc-800 mx-1" />

        {/* Laser Pointer Toggle */}
        <button
          type="button"
          onMouseDown={() => setLaserActive(true)}
          onMouseUp={() => setLaserActive(false)}
          onClick={() => setLaserActive((prev) => !prev)}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer ${
            laserActive
              ? "bg-red-600 text-white shadow-md"
              : "bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-red-400 border border-zinc-800"
          }`}
          title="Hold L key or click to toggle Laser Pointer"
        >
          <Radio className="w-3.5 h-3.5 text-red-500" />
          <span className="hidden sm:inline">Laser</span>
        </button>

        <div className="w-px h-5 bg-zinc-800 mx-1" />

        {/* Toggle Fullscreen */}
        <button
          type="button"
          onClick={toggleFullscreen}
          className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-300 hover:text-white transition-colors cursor-pointer"
          title={isFullscreen ? "Exit Fullscreen (F)" : "Enter Fullscreen (F)"}
        >
          {isFullscreen ? (
            <Minimize2 className="w-4 h-4" />
          ) : (
            <Maximize2 className="w-4 h-4" />
          )}
        </button>

        <div className="w-px h-5 bg-zinc-800 mx-1" />

        {/* Exit Presentation */}
        <button
          type="button"
          onClick={onExit}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 border border-rose-500/40 text-xs font-mono font-bold transition-colors cursor-pointer"
          title="Exit Presentation Mode (Esc)"
        >
          <X className="w-3.5 h-3.5" />
          <span>Exit</span>
        </button>
      </div>
    </div>
  );
}
