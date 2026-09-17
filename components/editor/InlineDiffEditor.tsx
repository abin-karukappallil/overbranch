"use client";

import React, { useState, useMemo } from "react";
import { Check, X, Sparkles, CheckCheck, XCircle, FileCode2, Code2, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

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
  type: "unchanged" | "deleted" | "added" | "modified";
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
        const propLines = prop ? prop.split("\n") : [];

        // If line counts match and both exist, mark each differing line as modified (yellow)
        const isSameCountReplacement = origLines.length === propLines.length && origLines.length > 0;

        if (isSameCountReplacement) {
          origLines.forEach((ol, lIdx) => {
            const pl = propLines[lIdx];
            if (ol !== pl) {
              // Deleted old version (red)
              linesResult.push({
                type: "deleted",
                text: ol,
                lineNumberOld: oldLineNo++,
                editId: edit.id,
              });
              // Modified new version (yellow)
              linesResult.push({
                type: "modified",
                text: pl,
                lineNumberNew: currentLineNo++,
                editId: edit.id,
              });
            } else {
              linesResult.push({
                type: "unchanged",
                text: ol,
                lineNumberOld: oldLineNo++,
                lineNumberNew: currentLineNo++,
              });
            }
          });
        } else {
          // Standard delete + insert
          origLines.forEach((ol) => {
            linesResult.push({
              type: "deleted",
              text: ol,
              lineNumberOld: oldLineNo++,
              editId: edit.id,
            });
          });

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

  const diffCounts = useMemo(() => {
    let added = 0;
    let deleted = 0;
    let modified = 0;
    computedDiffLines.forEach((l) => {
      if (l.type === "added") added++;
      if (l.type === "deleted") deleted++;
      if (l.type === "modified") modified++;
    });
    return { added, deleted, modified };
  }, [computedDiffLines]);

  const handleCopyPatch = async () => {
    if (!activeEdits || activeEdits.length === 0) {
      return;
    }

    let patchContent = "";
    activeEdits.forEach((edit, idx) => {
      patchContent += `--- a/${edit.id || `chunk-${idx + 1}`}\n`;
      patchContent += `+++ b/${edit.id || `chunk-${idx + 1}`}\n`;
      if (edit.original_chunk) {
        edit.original_chunk.split("\n").forEach((l) => {
          patchContent += `-${l}\n`;
        });
      }
      if (edit.proposed_chunk) {
        edit.proposed_chunk.split("\n").forEach((l) => {
          patchContent += `+${l}\n`;
        });
      }
      patchContent += "\n";
    });

    try {
      await navigator.clipboard.writeText(patchContent.trim());
    } catch (_) {
      toast.error("Failed to copy patch to clipboard.");
    }
  };

  const handleSingleAccept = (editItem: EditItem) => {
    setActiveEdits((prev) => prev.filter((e) => e.id !== editItem.id));
    onAcceptSingle(editItem);
  };

  const handleSingleReject = (editItem: EditItem) => {
    setActiveEdits((prev) => prev.filter((e) => e.id !== editItem.id));
    onRejectSingle(editItem.id);
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#141519] border border-[#282A30] rounded-xl shadow-2xl overflow-hidden font-mono text-xs text-[#E2E4E9]">
      <div className="px-4 py-2.5 border-b border-[#282A30] bg-[#1A1C22] flex items-center justify-between gap-3 shrink-0 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div>
            <h3 className="font-archivo font-bold text-xs text-[#E2E4E9] flex items-center gap-2">
              <span>Inline Diff Review</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#22242C] text-[#10B981] border border-[#282A30]">
                {activeEdits.length} Proposed Change{activeEdits.length !== 1 ? "s" : ""}
              </span>
              {(diffCounts.added > 0 || diffCounts.deleted > 0 || diffCounts.modified > 0) && (
                <span className="text-[10px] font-mono flex items-center gap-1.5 text-[#9E9E9E]">
                  {diffCounts.added > 0 && <span className="text-[#10B981] font-bold">+{diffCounts.added}</span>}
                  {diffCounts.deleted > 0 && <span className="text-[#EB5757] font-bold">-{diffCounts.deleted}</span>}
                  {diffCounts.modified > 0 && <span className="text-[#FF9900] font-bold">~{diffCounts.modified}</span>}
                </span>
              )}
            </h3>
            {explanation && (
              <p className="text-[11px] text-[#9E9E9E] line-clamp-1 mt-0.5 font-sans">{explanation}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={handleCopyPatch}
            className="h-7 bg-[#1A1C22] hover:bg-[#22242C] text-[#9E9E9E] hover:text-[#E2E4E9] border-[#282A30] font-mono text-xs px-2.5 rounded-lg flex items-center gap-1.5 cursor-pointer"
            title="Copy diff patch to clipboard"
          >
            <Copy className="w-3 h-3" />
            <span className="hidden sm:inline">Copy Patch</span>
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={onRejectAll}
            className="h-7 bg-[#1A1C22] hover:bg-[#22242C] text-[#EB5757] hover:text-[#EB5757] border-[#282A30] font-mono text-xs px-2.5 rounded-lg flex items-center gap-1.5 cursor-pointer"
          >
            <XCircle className="w-3 h-3" />
            <span>Reject All</span>
          </Button>

          <Button
            size="sm"
            onClick={() => onAcceptAll(activeEdits)}
            className="h-7 bg-[#10B981] hover:bg-[#059669] text-white font-archivo font-bold px-3 rounded-lg flex items-center gap-1.5 text-xs cursor-pointer shadow-sm"
          >
            <CheckCheck className="w-3 h-3" />
            <span>Accept All ({activeEdits.length})</span>
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[#0E0F12] p-2 leading-relaxed selection:bg-[#22242C]">
        {computedDiffLines.map((line, idx) => {
          const isDeleted = line.type === "deleted";
          const isAdded = line.type === "added";
          const isModified = line.type === "modified";
          const matchedEdit = activeEdits.find((e) => e.id === line.editId);

          return (
            <div
              key={idx}
              className={`group relative flex items-center min-h-[22px] px-2 rounded transition-colors ${
                isDeleted
                  ? "bg-[#EB5757]/10 text-[#FF8585] border-l-2 border-[#EB5757] line-through decoration-[#EB5757]/50"
                  : isAdded
                  ? "bg-[#10B981]/10 text-[#10B981] border-l-2 border-[#10B981] font-medium"
                  : isModified
                  ? "bg-[#FF9900]/10 text-[#FFB84D] border-l-2 border-[#FF9900] font-medium"
                  : "text-[#E2E4E9] hover:bg-[#1A1C22]/40"
              }`}
            >
              <div className="w-16 shrink-0 flex items-center text-[10px] text-[#62666D] select-none gap-2 font-mono">
                <span className="w-6 text-right">{line.lineNumberOld ?? ""}</span>
                <span className="w-6 text-right">{line.lineNumberNew ?? ""}</span>
              </div>

              <div className="w-4 shrink-0 font-bold text-[11px] select-none">
                {isDeleted && <span className="text-[#EB5757]">-</span>}
                {isAdded && <span className="text-[#10B981]">+</span>}
                {isModified && <span className="text-[#FF9900]">~</span>}
              </div>

              <div className="flex-1 whitespace-pre font-mono overflow-x-auto pr-24 text-[11px]">
                {line.text}
              </div>

              {(isDeleted || isAdded || isModified) && matchedEdit && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-[#141519] border border-[#282A30] rounded-lg p-0.5 shadow-xl flex items-center gap-1 z-10">
                  <button
                    onClick={() => handleSingleAccept(matchedEdit)}
                    title="Accept this edit"
                    className="px-2 py-0.5 rounded text-[10px] bg-[#10B981] hover:bg-[#059669] text-white flex items-center gap-1 font-archivo font-bold transition-colors cursor-pointer"
                  >
                    <Check className="w-2.5 h-2.5" />
                    <span>Accept</span>
                  </button>

                  <button
                    onClick={() => handleSingleReject(matchedEdit)}
                    title="Reject this edit"
                    className="px-2 py-0.5 rounded text-[10px] bg-[#1A1C22] hover:bg-[#22242C] text-[#EB5757] border border-[#282A30] flex items-center gap-1 font-mono transition-colors cursor-pointer"
                  >
                    <X className="w-2.5 h-2.5" />
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
