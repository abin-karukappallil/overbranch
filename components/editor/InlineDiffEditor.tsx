"use client";

import React, { useState, useMemo } from "react";
import { Check, X, Sparkles, CheckCheck, XCircle, FileCode2, Code2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface EditItem {
  id: string;
  original_chunk: string;
  proposed_chunk: string;
  explanation?: string;
}

export interface InlineDiffEditorProps {
  currentCode: string;
  edits: EditItem[];
  explanation?: string;
  onAcceptAll: (editsToApply: EditItem[]) => void;
  onRejectAll: () => void;
  onAcceptSingle: (item: EditItem) => void;
  onRejectSingle: (itemId: string) => void;
}

interface LineDiff {
  type: "unchanged" | "deleted" | "added";
  text: string;
  lineNumberOld?: number;
  lineNumberNew?: number;
  editId?: string;
}

export function InlineDiffEditor({
  currentCode,
  edits,
  explanation,
  onAcceptAll,
  onRejectAll,
  onAcceptSingle,
  onRejectSingle,
}: InlineDiffEditorProps) {
  const [activeEdits, setActiveEdits] = useState<EditItem[]>(edits);

  React.useEffect(() => {
    setActiveEdits(edits);
  }, [edits]);

  const computedDiffLines = useMemo<LineDiff[]>(() => {
    const linesResult: LineDiff[] = [];
    let codeText = currentCode;

    if (!activeEdits || activeEdits.length === 0) {
      return codeText.split("\n").map((line, idx): LineDiff => ({
        type: "unchanged",
        text: line,
        lineNumberOld: idx + 1,
        lineNumberNew: idx + 1,
        editId: undefined,
      }));
    }

    let currentLineNo = 1;
    let oldLineNo = 1;

    for (const edit of activeEdits) {
      const orig = edit.original_chunk;
      const prop = edit.proposed_chunk;

      if (orig && codeText.includes(orig)) {
        const parts = codeText.split(orig);
        const prefix = parts[0];
        const suffix = parts.slice(1).join(orig);

        if (prefix) {
          const prefLines = prefix.split("\n");
          prefLines.forEach((pl, i) => {
            if (i < prefLines.length - 1 || pl) {
              linesResult.push({
                type: "unchanged",
                text: pl,
                lineNumberOld: oldLineNo++,
                lineNumberNew: currentLineNo++,
              });
            }
          });
        }

        const origLines = orig.split("\n");
        origLines.forEach((ol) => {
          linesResult.push({
            type: "deleted",
            text: ol,
            lineNumberOld: oldLineNo++,
            editId: edit.id,
          });
        });

        if (prop) {
          const propLines = prop.split("\n");
          propLines.forEach((pl) => {
            linesResult.push({
              type: "added",
              text: pl,
              lineNumberNew: currentLineNo++,
              editId: edit.id,
            });
          });
        }

        codeText = suffix;
      } else if (prop) {
        const endDocIndex = codeText.lastIndexOf("\\end{document}");
        let prefix = codeText;
        let suffix = "";

        if (endDocIndex !== -1) {
          prefix = codeText.slice(0, endDocIndex);
          suffix = codeText.slice(endDocIndex);
        }

        if (prefix) {
          const prefLines = prefix.split("\n");
          prefLines.forEach((pl) => {
            linesResult.push({
              type: "unchanged",
              text: pl,
              lineNumberOld: oldLineNo++,
              lineNumberNew: currentLineNo++,
            });
          });
        }

        const propLines = prop.split("\n");
        propLines.forEach((pl) => {
          linesResult.push({
            type: "added",
            text: pl,
            lineNumberNew: currentLineNo++,
            editId: edit.id,
          });
        });

        codeText = suffix;
      }
    }

    if (codeText) {
      const suffLines = codeText.split("\n");
      suffLines.forEach((sl) => {
        linesResult.push({
          type: "unchanged",
          text: sl,
          lineNumberOld: oldLineNo++,
          lineNumberNew: currentLineNo++,
        });
      });
    }

    return linesResult;
  }, [currentCode, activeEdits]);

  const handleSingleAccept = (editItem: EditItem) => {
    setActiveEdits((prev) => prev.filter((e) => e.id !== editItem.id));
    onAcceptSingle(editItem);
  };

  const handleSingleReject = (editItem: EditItem) => {
    setActiveEdits((prev) => prev.filter((e) => e.id !== editItem.id));
    onRejectSingle(editItem.id);
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#0d1117] border border-border/80 rounded-2xl shadow-2xl overflow-hidden backdrop-blur-2xl font-mono text-xs">
      <div className="px-4 py-3 border-b border-border/60 bg-[#161b22] flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2.5">
          
          <div>
            <h3 className="font-bold text-sm text-slate-100 flex items-center gap-2">
              <span>Inline Editor Diff</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                {activeEdits.length} Proposed Change{activeEdits.length !== 1 ? "s" : ""}
              </span>
            </h3>
            {explanation && (
              <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{explanation}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="destructive"
            onClick={onRejectAll}
            className="h-8 bg-rose-600/90 hover:bg-rose-600 text-white font-medium px-3 rounded-lg shadow-sm active:scale-95 transition-all flex items-center gap-1.5 text-xs"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Reject All</span>
          </Button>

          <Button
            size="sm"
            onClick={() => onAcceptAll(activeEdits)}
            className="h-8 bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-3 rounded-lg shadow-sm active:scale-95 transition-all flex items-center gap-1.5 text-xs"
          >
            <CheckCheck className="w-3.5 h-3.5" />
            <span>Accept All ({activeEdits.length})</span>
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#0d1117] p-2 leading-relaxed selection:bg-indigo-500/30">
        {computedDiffLines.map((line, idx) => {
          const isDeleted = line.type === "deleted";
          const isAdded = line.type === "added";
          const isUnchanged = line.type === "unchanged";
          const matchedEdit = activeEdits.find((e) => e.id === line.editId);

          return (
            <div
              key={idx}
              className={`group relative flex items-center min-h-[22px] px-2 rounded transition-colors ${
                isDeleted
                  ? "bg-rose-950/40 text-rose-300 border-l-2 border-rose-500 line-through decoration-rose-500/50"
                  : isAdded
                  ? "bg-emerald-950/40 text-emerald-300 border-l-2 border-emerald-500 font-medium"
                  : "text-slate-300 hover:bg-slate-800/30"
              }`}
            >
              <div className="w-16 shrink-0 flex items-center text-[10px] text-slate-500 select-none gap-2 font-mono">
                <span className="w-6 text-right">{line.lineNumberOld ?? ""}</span>
                <span className="w-6 text-right">{line.lineNumberNew ?? ""}</span>
              </div>

              <div className="w-4 shrink-0 font-bold text-[11px] select-none">
                {isDeleted && <span className="text-rose-400">-</span>}
                {isAdded && <span className="text-emerald-400">+</span>}
              </div>

              <div className="flex-1 whitespace-pre font-mono overflow-x-auto pr-24">
                {line.text}
              </div>

              {(isDeleted || isAdded) && matchedEdit && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-[#161b22]/90 border border-slate-700/80 rounded-md p-0.5 shadow-xl flex items-center gap-1 backdrop-blur-md z-10">
                  <button
                    onClick={() => handleSingleAccept(matchedEdit)}
                    title="Accept this edit"
                    className="px-2 py-0.5 rounded text-[10px] bg-emerald-600/30 hover:bg-emerald-600 text-emerald-200 hover:text-white border border-emerald-500/40 flex items-center gap-1 font-sans font-semibold transition-colors"
                  >
                    <Check className="w-3 h-3" />
                    <span>Accept</span>
                  </button>

                  <button
                    onClick={() => handleSingleReject(matchedEdit)}
                    title="Reject this edit"
                    className="px-2 py-0.5 rounded text-[10px] bg-rose-600/30 hover:bg-rose-600 text-rose-200 hover:text-white border border-rose-500/40 flex items-center gap-1 font-sans font-semibold transition-colors"
                  >
                    <X className="w-3 h-3" />
                    <span>Reject</span>
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
