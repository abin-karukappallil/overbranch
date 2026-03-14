"use client";

import Editor, { DiffEditor } from "@monaco-editor/react";
import { latexTokensProvider, latexThemes } from "./latexTheme";
import { getLatexCompletionProvider } from "./latexSuggestions";

interface LatexEditorProps {
    value: string;
    onChange: (value: string) => void;
    theme: string;
    diffMode?: boolean;
    diffOriginal?: string;
    diffModified?: string;
}

export default function LatexEditor({
    value,
    onChange,
    theme,
    diffMode,
    diffOriginal,
    diffModified,
}: LatexEditorProps) {
    const handleEditorWillMount = (monaco: any) => {
        // Register a new language
        monaco.languages.register({ id: "custom-latex" });
        // Register a tokens provider for the language
        monaco.languages.setMonarchTokensProvider("custom-latex", latexTokensProvider);
        // Define new themes that contain only rules that match this language
        Object.entries(latexThemes).forEach(([themeName, themeData]) => {
            monaco.editor.defineTheme(themeName, themeData);
        });

        // Register code suggestions provider
        monaco.languages.registerCompletionItemProvider("custom-latex", getLatexCompletionProvider(monaco));
    };

    if (diffMode && diffOriginal !== undefined && diffModified !== undefined) {
        return (
            <div className="h-full w-full overflow-hidden rounded-lg border border-accent/30 bg-surface">
                <div className="ai-diff-header">
                    <svg className="h-3.5 w-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                    </svg>
                    <span className="text-xs font-medium text-accent">AI Suggested Changes — Review Diff</span>
                </div>
                <DiffEditor
                    height="calc(100% - 32px)"
                    language="custom-latex"
                    theme={theme}
                    original={diffOriginal}
                    modified={diffModified}
                    beforeMount={handleEditorWillMount}
                    options={{
                        fontSize: 14,
                        fontFamily: "var(--font-geist-mono), 'Fira Code', 'Cascadia Code', monospace",
                        readOnly: true,
                        renderSideBySide: true,
                        scrollBeyondLastLine: false,
                        padding: { top: 12, bottom: 12 },
                        smoothScrolling: true,
                        automaticLayout: true,
                        minimap: { enabled: false },
                    }}
                    loading={
                        <div className="flex h-full items-center justify-center text-muted">
                            Loading diff…
                        </div>
                    }
                />
            </div>
        );
    }

    return (
        <div className="h-full w-full overflow-hidden rounded-lg border border-border bg-surface">
            <Editor
                height="100%"
                defaultLanguage="custom-latex"
                theme={theme}
                beforeMount={handleEditorWillMount}
                value={value}
                onChange={(val) => onChange(val ?? "")}
                options={{
                    fontSize: 14,
                    fontFamily: "var(--font-geist-mono), 'Fira Code', 'Cascadia Code', monospace",
                    fontLigatures: true,
                    lineNumbers: "on",
                    minimap: { enabled: true, scale: 1 },
                    wordWrap: "on",
                    scrollBeyondLastLine: false,
                    padding: { top: 16, bottom: 16 },
                    smoothScrolling: true,
                    cursorBlinking: "smooth",
                    cursorSmoothCaretAnimation: "on",
                    renderLineHighlight: "gutter",
                    bracketPairColorization: { enabled: true },
                    automaticLayout: true,
                    tabSize: 2,
                    suggestOnTriggerCharacters: true,
                    quickSuggestions: true,
                }}
                loading={
                    <div className="flex h-full items-center justify-center text-muted">
                        <svg
                            className="spinner mr-2 h-5 w-5"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                        >
                            <circle cx="12" cy="12" r="10" opacity="0.25" />
                            <path d="M12 2a10 10 0 0 1 10 10" opacity="0.75" />
                        </svg>
                        Loading editor…
                    </div>
                }
            />
        </div>
    );
}
