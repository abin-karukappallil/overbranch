"use client";

interface ToolbarProps {
    onCompile: () => void;
    onDownload: () => void;
    isCompiling: boolean;
    hasPdf: boolean;
}

export default function Toolbar({
    onCompile,
    onDownload,
    isCompiling,
    hasPdf,
}: ToolbarProps) {
    return (
        <div className="flex items-center gap-3">
            {/* Compile button */}
            <button
                id="compile-btn"
                onClick={onCompile}
                disabled={isCompiling}
                className={`
          flex items-center gap-2 rounded-lg px-5 py-2.5
          text-sm font-semibold transition-all duration-200
          ${isCompiling
                        ? "cursor-not-allowed bg-accent/40 text-white/60"
                        : "bg-accent text-white shadow-lg shadow-accent/20 hover:bg-accent-hover hover:shadow-accent/30 active:scale-[0.97] pulse-glow"
                    }
        `}
            >
                {isCompiling ? (
                    <>
                        <svg
                            className="spinner h-4 w-4"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.5"
                        >
                            <circle cx="12" cy="12" r="10" opacity="0.25" />
                            <path d="M12 2a10 10 0 0 1 10 10" opacity="0.75" />
                        </svg>
                        Compiling…
                    </>
                ) : (
                    <>
                        <svg
                            className="h-4 w-4"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.5"
                        >
                            <polygon points="5,3 19,12 5,21" />
                        </svg>
                        Compile
                    </>
                )}
            </button>

            {/* Download PDF button */}
            <button
                id="download-btn"
                onClick={onDownload}
                disabled={!hasPdf || isCompiling}
                className={`
          flex items-center gap-2 rounded-lg border px-4 py-2.5
          text-sm font-medium transition-all duration-200
          ${hasPdf && !isCompiling
                        ? "border-border bg-surface text-foreground hover:border-accent/40 hover:bg-surface-hover active:scale-[0.97]"
                        : "cursor-not-allowed border-border/50 bg-surface/50 text-muted/40"
                    }
        `}
            >
                <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7,10 12,15 17,10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download PDF
            </button>
        </div>
    );
}
