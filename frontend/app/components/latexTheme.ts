// Monarch language definition for LaTeX
export const latexTokensProvider: any = {
    tokenizer: {
        root: [
            // Comments
            [/%(.*)$/, "comment"],

            // Commands (e.g., \documentclass, \begin, \end, \textbf)
            [/\\[a-zA-Z]+/, "keyword"],
            [/\\[@\w]+/, "keyword.control"],

            // Escaped characters (e.g., \%, \&, \_)
            [/\\[%$&_#\\]/, "constant.escape"],

            // Math modes
            [/\$\$/, "string.math.block", "@mathBlock"],
            [/\$/, "string.math.inline", "@mathInline"],
            [/\\\[/, "string.math.block", "@mathBlockBracket"],
            [/\\\(/, "string.math.inline", "@mathInlineBracket"],

            // Braces and brackets
            [/[{}()\[\]]/, "delimiter"],

            // Environment names inside \begin{} or \end{}
            [/(?<=\\begin\{)[a-zA-Z0-9*]+(?=\})/, "type.environment"],
            [/(?<=\\end\{)[a-zA-Z0-9*]+(?=\})/, "type.environment"],

            // Numbers
            [/\d*\.\d+([eE][\-+]?\d+)?/, "number.float"],
            [/\d+/, "number"],

            // Strings (sometimes used in options)
            [/"([^"\\]|\\.)*$/, "string.invalid"],
            [/"/, "string", "@string"],
        ],

        mathBlock: [
            [/\$\$/, "string.math.block", "@pop"],
            [/\\[a-zA-Z]+/, "keyword.math"], // Math commands get a slightly different color
            [/[{}()\[\]]/, "delimiter.math"],
            [/[_^\-+*/=<>]/, "operator.math"],
            [/%(.*)$/, "comment"],
            [/./, "string.math.block"],
        ],

        mathInline: [
            [/\$/, "string.math.inline", "@pop"],
            [/\\[a-zA-Z]+/, "keyword.math"],
            [/[{}()\[\]]/, "delimiter.math"],
            [/[_^\-+*/=<>]/, "operator.math"],
            [/./, "string.math.inline"],
        ],

        mathBlockBracket: [
            [/\\\]/, "string.math.block", "@pop"],
            [/\\[a-zA-Z]+/, "keyword.math"],
            [/[{}()\[\]]/, "delimiter.math"],
            [/[_^\-+*/=<>]/, "operator.math"],
            [/%(.*)$/, "comment"],
            [/./, "string.math.block"],
        ],

        mathInlineBracket: [
            [/\\\)/, "string.math.inline", "@pop"],
            [/\\[a-zA-Z]+/, "keyword.math"],
            [/[{}()\[\]]/, "delimiter.math"],
            [/[_^\-+*/=<>]/, "operator.math"],
            [/./, "string.math.inline"],
        ],

        string: [
            [/[^\\"]+/, "string"],
            [/\\./, "string.escape"],
            [/"/, "string", "@pop"],
        ],
    },
};

export const latexThemes: Record<string, any> = {
    "latex-dark": {
        base: "vs-dark",
        inherit: true,
        rules: [
            { token: "keyword", foreground: "#c678dd", fontStyle: "bold" },
            { token: "keyword.control", foreground: "#c678dd", fontStyle: "bold" },
            { token: "comment", foreground: "#7f848e", fontStyle: "italic" },
            { token: "string.math.inline", foreground: "#98c379" },
            { token: "string.math.block", foreground: "#98c379" },
            { token: "keyword.math", foreground: "#61afef" },
            { token: "operator.math", foreground: "#d19a66" },
            { token: "delimiter.math", foreground: "#abb2bf" },
            { token: "delimiter", foreground: "#abb2bf" },
            { token: "type.environment", foreground: "#e5c07b" },
            { token: "constant.escape", foreground: "#56b6c2" },
            { token: "number", foreground: "#d19a66" },
            { token: "number.float", foreground: "#d19a66" },
            { token: "string", foreground: "#98c379" },
        ],
        colors: {
            "editor.background": "#1e1e24",
            "editor.foreground": "#abb2bf",
            "editorCursor.foreground": "#528bff",
            "editor.lineHighlightBackground": "#2c313a",
            "editorLineNumber.foreground": "#636d83",
            "editorIndentGuide.background": "#3b4048",
            "editorIndentGuide.activeBackground": "#5c6370",
        },
    },
    "latex-light": {
        base: "vs",
        inherit: true,
        rules: [
            { token: "keyword", foreground: "#a626a4", fontStyle: "bold" },
            { token: "keyword.control", foreground: "#a626a4", fontStyle: "bold" },
            { token: "comment", foreground: "#a0a1a7", fontStyle: "italic" },
            { token: "string.math.inline", foreground: "#50a14f" },
            { token: "string.math.block", foreground: "#50a14f" },
            { token: "keyword.math", foreground: "#0184bc" },
            { token: "operator.math", foreground: "#986801" },
            { token: "delimiter.math", foreground: "#383a42" },
            { token: "delimiter", foreground: "#383a42" },
            { token: "type.environment", foreground: "#c18401" },
            { token: "constant.escape", foreground: "#0184bc" },
            { token: "number", foreground: "#986801" },
            { token: "number.float", foreground: "#986801" },
            { token: "string", foreground: "#50a14f" },
        ],
        colors: {
            "editor.background": "#fafafa",
            "editor.foreground": "#383a42",
            "editorCursor.foreground": "#526fff",
            "editor.lineHighlightBackground": "#e5e5e6",
            "editorLineNumber.foreground": "#9d9d9f",
            "editorIndentGuide.background": "#e4e4e4",
            "editorIndentGuide.activeBackground": "#9d9d9f",
        },
    },
    "monokai": {
        base: "vs-dark",
        inherit: true,
        rules: [
            { token: "keyword", foreground: "#f92672", fontStyle: "bold" },
            { token: "keyword.control", foreground: "#f92672", fontStyle: "bold" },
            { token: "comment", foreground: "#75715e", fontStyle: "italic" },
            { token: "string.math.inline", foreground: "#e6db74" },
            { token: "string.math.block", foreground: "#e6db74" },
            { token: "keyword.math", foreground: "#66d9ef" },
            { token: "operator.math", foreground: "#fd971f" },
            { token: "delimiter.math", foreground: "#f8f8f2" },
            { token: "delimiter", foreground: "#f8f8f2" },
            { token: "type.environment", foreground: "#a6e22e" },
            { token: "constant.escape", foreground: "#ae81ff" },
            { token: "number", foreground: "#ae81ff" },
            { token: "number.float", foreground: "#ae81ff" },
            { token: "string", foreground: "#e6db74" },
        ],
        colors: {
            "editor.background": "#272822",
            "editor.foreground": "#f8f8f2",
            "editorCursor.foreground": "#f8f8f0",
            "editor.lineHighlightBackground": "#3e3d32",
            "editorLineNumber.foreground": "#90908a",
            "editorIndentGuide.background": "#464741",
            "editorIndentGuide.activeBackground": "#767771",
        },
    }
};

export const INCLUDED_THEMES = [
    { id: "latex-dark", name: "LaTeX Dark" },
    { id: "latex-light", name: "LaTeX Light" },
    { id: "monokai", name: "Monokai" },
];
