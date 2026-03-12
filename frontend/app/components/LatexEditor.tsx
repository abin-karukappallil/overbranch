"use client";

import Editor, { useMonaco } from "@monaco-editor/react";
import { latexTokensProvider, latexThemes } from "./latexTheme";

interface LatexEditorProps {
    value: string;
    onChange: (value: string) => void;
    theme: string;
}

export default function LatexEditor({ value, onChange, theme }: LatexEditorProps) {
    const handleEditorWillMount = (monaco: any) => {
        // Register a new language
        monaco.languages.register({ id: "custom-latex" });
        // Register a tokens provider for the language
        monaco.languages.setMonarchTokensProvider("custom-latex", latexTokensProvider);
        // Define new themes that contain only rules that match this language
        Object.entries(latexThemes).forEach(([themeName, themeData]) => {
            monaco.editor.defineTheme(themeName, themeData);
        });
    };

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
                    quickSuggestions: false,
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
