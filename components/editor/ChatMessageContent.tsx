"use client";

import React, { useState } from "react";
import { Check, Copy } from "lucide-react";

interface ChatMessageContentProps {
  text: string;
}

export function ChatMessageContent({ text }: ChatMessageContentProps) {
  if (!text) return null;

  // Simple and robust parser for markdown blocks: code blocks, lists, quotes, inline formatting
  const renderFormatted = () => {
    // Split by code fences ```
    const segments = text.split(/(```[\s\S]*?```)/g);

    return segments.map((segment, segIdx) => {
      if (segment.startsWith("```")) {
        const firstLineEnd = segment.indexOf("\n");
        let language = "";
        let codeBody = "";
        if (firstLineEnd !== -1) {
          language = segment.slice(3, firstLineEnd).trim();
          codeBody = segment.slice(firstLineEnd + 1, -3);
        } else {
          codeBody = segment.slice(3, -3);
        }

        return <CodeBlock key={segIdx} language={language} code={codeBody} />;
      }

      // Normal text: split into paragraphs / lines
      const paragraphs = segment.split(/\n\n+/);
      return (
        <div key={segIdx} className="space-y-2">
          {paragraphs.map((p, pIdx) => {
            const lines = p.split("\n");
            return (
              <div key={pIdx} className="leading-relaxed text-xs">
                {lines.map((line, lIdx) => {
                  const trimmed = line.trim();

                  // Bullet list item
                  if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
                    return (
                      <div key={lIdx} className="flex items-start gap-1.5 ml-2 py-0.5">
                        <span className="text-[#00CC68] select-none shrink-0 mt-0.5">•</span>
                        <span>{renderInlineMarkdown(trimmed.slice(2))}</span>
                      </div>
                    );
                  }

                  // Numbered list item
                  const numMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
                  if (numMatch) {
                    return (
                      <div key={lIdx} className="flex items-start gap-1.5 ml-2 py-0.5">
                        <span className="text-[#00CC68] font-mono text-[11px] select-none shrink-0">{numMatch[1]}.</span>
                        <span>{renderInlineMarkdown(numMatch[2])}</span>
                      </div>
                    );
                  }

                  // Blockquote
                  if (trimmed.startsWith("> ")) {
                    return (
                      <div key={lIdx} className="border-l-2 border-[#00CC68]/60 pl-2.5 py-0.5 text-zinc-300 italic my-1 bg-zinc-950/40 rounded-r">
                        {renderInlineMarkdown(trimmed.slice(2))}
                      </div>
                    );
                  }

                  // Heading
                  if (trimmed.startsWith("### ")) {
                    return <h4 key={lIdx} className="font-bold text-white text-xs mt-2 mb-1">{renderInlineMarkdown(trimmed.slice(4))}</h4>;
                  }
                  if (trimmed.startsWith("## ")) {
                    return <h3 key={lIdx} className="font-bold text-white text-sm mt-2 mb-1">{renderInlineMarkdown(trimmed.slice(3))}</h3>;
                  }
                  if (trimmed.startsWith("# ")) {
                    return <h2 key={lIdx} className="font-bold text-white text-sm mt-2 mb-1">{renderInlineMarkdown(trimmed.slice(2))}</h2>;
                  }

                  return (
                    <span key={lIdx}>
                      {renderInlineMarkdown(line)}
                      {lIdx < lines.length - 1 && <br />}
                    </span>
                  );
                })}
              </div>
            );
          })}
        </div>
      );
    });
  };

  return <div className="space-y-2 text-zinc-100">{renderFormatted()}</div>;
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (_) {}
  };

  return (
    <div className="my-2 rounded-xl bg-zinc-950 border border-zinc-800 overflow-hidden font-mono text-xs">
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-900 border-b border-zinc-800 text-[10px] text-zinc-400 select-none">
        <span className="font-bold uppercase tracking-wider text-[#00CC68]">{language || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-white transition-colors cursor-pointer"
        >
          {copied ? <Check className="w-3 h-3 text-[#00CC68]" /> : <Copy className="w-3 h-3" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-[11px] leading-relaxed text-zinc-200">
        <code>{code.trim()}</code>
      </pre>
    </div>
  );
}

function renderInlineMarkdown(text: string): React.ReactNode[] {
  // Regex to split on `inline code`, **bold**, *italic*
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);

  return parts.map((part, idx) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      return (
        <code key={idx} className="px-1.5 py-0.5 rounded bg-zinc-950 text-[#00CC68] border border-zinc-800 font-mono text-[11px]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
      return (
        <strong key={idx} className="font-bold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length >= 2) {
      return (
        <em key={idx} className="italic text-zinc-300">
          {part.slice(1, -1)}
        </em>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}
