export function getLatexCompletionProvider(monaco: any) {
    return {
        provideCompletionItems: (model: any, position: any) => {
            const word = model.getWordUntilPosition(position);
            const range = {
                startLineNumber: position.lineNumber,
                endLineNumber: position.lineNumber,
                startColumn: word.startColumn,
                endColumn: word.endColumn,
            };

            const suggestions = [
                // Document Structure
                {
                    label: "\\documentclass",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Document Class",
                    insertText: "documentclass[${1:options}]{${2:article}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\usepackage",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Use Package",
                    insertText: "usepackage{${1:package}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\begin",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Begin Environment",
                    insertText: "begin{${1:environment}}\n\t$0\n\\end{${1:environment}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\end",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "End Environment",
                    insertText: "end{${1:environment}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },

                // Sections
                {
                    label: "\\section",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Section",
                    insertText: "section{${1:title}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\subsection",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Subsection",
                    insertText: "subsection{${1:title}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },

                // Text Formatting
                {
                    label: "\\textbf",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Bold Text",
                    insertText: "textbf{${1:text}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\textit",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Italic Text",
                    insertText: "textit{${1:text}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\underline",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Underlined Text",
                    insertText: "underline{${1:text}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },

                // Graphics and Math
                {
                    label: "\\includegraphics",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Include Graphics",
                    insertText: "includegraphics[width=${1:1\\textwidth}]{${2:filename.png}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\frac",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Fraction",
                    insertText: "frac{${1:numerator}}{${2:denominator}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
                {
                    label: "\\sum",
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    documentation: "Summation",
                    insertText: "sum_{${1:i=1}}^{${2:n}}",
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    range,
                },
            ];

            return { suggestions };
        },
    };
}
