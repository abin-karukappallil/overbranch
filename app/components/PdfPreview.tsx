"use client";

interface PdfPreviewProps {
    pdfUrl: string | null;
    isCompiling: boolean;
    error: string | null;
}

export default function PdfPreview({
    pdfUrl,
    isCompiling,
    error,
}: PdfPreviewProps) {
    return (
        <div className="relative flex h-full w-full flex-col overflow-hidden rounded-lg border border-border bg-surface">
            {/* Header */}
            <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                <svg
                    className="h-4 w-4 text-error"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM6 20V4h7v5h5v11H6z" />
                    <path d="M8 12h3v2H8v3h3v2H8v-2H6v-2h2v-3H6v-2h2V8h2v2h3V8h2v2h-2v3h2v2h-2v3h-2v-3h-3v3z" opacity="0" />
                </svg>
                <span className="text-sm font-medium text-muted">PDF Preview</span>
                {pdfUrl && (
                    <span className="ml-auto rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success">
                        Compiled
                    </span>
                )}
            </div>

            {/* Content area */}
            <div className="relative flex-1">
                {/* Loading overlay */}
                {isCompiling && (
                    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-surface/90 backdrop-blur-sm fade-in">
                        <div className="relative">
                            <svg
                                className="spinner h-10 w-10 text-accent"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                            >
                                <circle cx="12" cy="12" r="10" opacity="0.2" />
                                <path d="M12 2a10 10 0 0 1 10 10" />
                            </svg>
                        </div>
                        <p className="mt-4 text-sm font-medium text-muted">
                            Compiling LaTeX…
                        </p>
                        <p className="mt-1 text-xs text-muted/60">
                            This may take a few seconds
                        </p>
                    </div>
                )}

                {/* Error state */}
                {error && !isCompiling && (
                    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-8 fade-in">
                        <div className="rounded-xl border border-error/20 bg-error/5 p-6 text-center">
                            <svg
                                className="mx-auto mb-3 h-8 w-8 text-error"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                            >
                                <circle cx="12" cy="12" r="10" />
                                <line x1="15" y1="9" x2="9" y2="15" />
                                <line x1="9" y1="9" x2="15" y2="15" />
                            </svg>
                            <p className="text-sm font-medium text-error">
                                Compilation Failed
                            </p>
                            <p className="mt-2 max-w-sm text-xs leading-relaxed text-muted">
                                {error}
                            </p>
                        </div>
                    </div>
                )}

                {/* PDF iframe */}
                {pdfUrl && !error ? (
                    <iframe
                        src={pdfUrl}
                        className="h-full w-full border-0 bg-white"
                        title="PDF Preview"
                    />
                ) : (
                    !isCompiling &&
                    !error && (
                        <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center fade-in">
                            <div className="rounded-2xl bg-accent/5 p-6">
                                <svg
                                    className="h-12 w-12 text-accent/40"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="1.5"
                                >
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                                    <polyline points="14,2 14,8 20,8" />
                                    <line x1="16" y1="13" x2="8" y2="13" />
                                    <line x1="16" y1="17" x2="8" y2="17" />
                                    <polyline points="10,9 9,9 8,9" />
                                </svg>
                            </div>
                            <div>
                                <p className="text-sm font-medium text-foreground/70">
                                    No PDF generated yet
                                </p>
                                <p className="mt-1 text-xs text-muted">
                                    Click <strong>Compile</strong> to generate your PDF
                                </p>
                            </div>
                        </div>
                    )
                )}
            </div>
        </div>
    );
}
