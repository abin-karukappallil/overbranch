"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  CaseSensitive,
  Regex,
  Replace,
  ReplaceAll,
  Search,
  WholeWord,
  X,
} from "lucide-react";

interface EditorSearchBarProps {
  /** The Monaco editor this bar searches. Null until it mounts. */
  editor: any | null;
  monaco: any | null;
  open: boolean;
  onClose: () => void;
  /** Hides replace when the user may not edit. */
  readOnly?: boolean;
  /** Called with the new buffer after a replace, so autosave still runs. */
  onDocumentChange?: (value: string) => void;
  /** Stacked, full-width layout for the mobile pane. */
  compact?: boolean;
  className?: string;
}

interface MatchRange {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
}

/**
 * Find & replace over the active Monaco model.
 *
 * This replaces Monaco's built-in find widget rather than wrapping it: the
 * built-in widget is unreachable on mobile (it needs Ctrl+F and a hardware
 * keyboard), so a single bar driven by our own state is the only way desktop
 * and touch behave the same.
 */
export function EditorSearchBar({
  editor,
  monaco,
  open,
  onClose,
  readOnly = false,
  onDocumentChange,
  compact = false,
  className = "",
}: EditorSearchBarProps) {
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [isRegex, setIsRegex] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [showReplace, setShowReplace] = useState(false);
  const [matches, setMatches] = useState<MatchRange[]>([]);
  const [index, setIndex] = useState(0);
  const [invalidPattern, setInvalidPattern] = useState(false);

  const decorationsRef = useRef<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  // Bumped by the model-content listener so the match list recomputes after an
  // edit (including our own replaces) without re-subscribing on every keystroke.
  const [contentNonce, setContentNonce] = useState(0);

  const clearDecorations = useCallback(() => {
    if (!editor) return;
    try {
      decorationsRef.current = editor.deltaDecorations(decorationsRef.current, []);
    } catch (_) {
      decorationsRef.current = [];
    }
  }, [editor]);

  // --- Match computation -------------------------------------------------
  useEffect(() => {
    if (!open || !editor || !query) {
      setMatches([]);
      setInvalidPattern(false);
      return;
    }
    const model = editor.getModel?.();
    if (!model) {
      setMatches([]);
      return;
    }
    try {
      const found = model.findMatches(
        query,
        false, // search the whole model, not just the editable range
        isRegex,
        matchCase,
        wholeWord ? model.getOptions().wordSeparators : null,
        false, // no capture groups needed
        10000,
      );
      setInvalidPattern(false);
      setMatches(found.map((m: any) => m.range));
    } catch (_) {
      // Only a malformed regex gets here; keep the previous highlights off.
      setInvalidPattern(true);
      setMatches([]);
    }
  }, [open, editor, query, isRegex, matchCase, wholeWord, contentNonce]);

  // Keep the active index inside the (possibly shrunken) match list.
  useEffect(() => {
    setIndex((prev) => (matches.length === 0 ? 0 : Math.min(prev, matches.length - 1)));
  }, [matches]);

  // --- Decorations -------------------------------------------------------
  useEffect(() => {
    if (!editor || !monaco) return;
    if (!open || matches.length === 0) {
      clearDecorations();
      return;
    }
    const next = matches.map((range, i) => ({
      range: new monaco.Range(
        range.startLineNumber,
        range.startColumn,
        range.endLineNumber,
        range.endColumn,
      ),
      options: {
        className: i === index ? "ob-find-match-current" : "ob-find-match",
        stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
        overviewRuler: {
          color: "rgba(16, 185, 129, 0.7)",
          position: monaco.editor.OverviewRulerLane.Center,
        },
      },
    }));
    try {
      decorationsRef.current = editor.deltaDecorations(decorationsRef.current, next);
    } catch (_) {}
  }, [editor, monaco, open, matches, index, clearDecorations]);

  // Drop highlights when the bar closes or the editor goes away.
  useEffect(() => {
    if (!open) clearDecorations();
    return () => clearDecorations();
  }, [open, clearDecorations]);

  // --- Recompute after document edits ------------------------------------
  useEffect(() => {
    if (!editor || !open) return;
    let timer: NodeJS.Timeout | null = null;
    const sub = editor.onDidChangeModelContent(() => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => setContentNonce((n) => n + 1), 120);
    });
    return () => {
      if (timer) clearTimeout(timer);
      sub?.dispose?.();
    };
  }, [editor, open]);

  // --- Open / focus behaviour --------------------------------------------
  useEffect(() => {
    if (!open) return;
    // Seed from the current selection, the way every editor's find does.
    try {
      const sel = editor?.getSelection?.();
      const model = editor?.getModel?.();
      if (sel && model && !sel.isEmpty()) {
        const selected = model.getValueInRange(sel);
        if (selected && !selected.includes("\n")) setQuery(selected);
      }
    } catch (_) {}
    const id = setTimeout(() => {
      const input = inputRef.current;
      if (!input || input.offsetParent === null) return;
      input.focus();
      input.select();
    }, 30);
    return () => clearTimeout(id);
  }, [open, editor]);

  const revealMatch = useCallback(
    (i: number) => {
      if (!editor || !monaco || matches.length === 0) return;
      const range = matches[(i + matches.length) % matches.length];
      if (!range) return;
      const r = new monaco.Range(
        range.startLineNumber,
        range.startColumn,
        range.endLineNumber,
        range.endColumn,
      );
      editor.setSelection(r);
      editor.revealRangeInCenterIfOutsideViewport(r, 0);
    },
    [editor, monaco, matches],
  );

  const goTo = useCallback(
    (delta: number) => {
      if (matches.length === 0) return;
      const next = (index + delta + matches.length) % matches.length;
      setIndex(next);
      revealMatch(next);
    },
    [index, matches.length, revealMatch],
  );

  const pushChange = useCallback(() => {
    if (!editor || !onDocumentChange) return;
    try {
      onDocumentChange(editor.getValue());
    } catch (_) {}
  }, [editor, onDocumentChange]);

  const handleReplaceOne = useCallback(() => {
    if (readOnly || !editor || !monaco || matches.length === 0) return;
    const range = matches[index];
    if (!range) return;
    editor.pushUndoStop();
    editor.executeEdits("ob-find-replace", [
      {
        range: new monaco.Range(
          range.startLineNumber,
          range.startColumn,
          range.endLineNumber,
          range.endColumn,
        ),
        text: replacement,
        forceMoveMarkers: true,
      },
    ]);
    editor.pushUndoStop();
    pushChange();
    setContentNonce((n) => n + 1);
  }, [readOnly, editor, monaco, matches, index, replacement, pushChange]);

  const handleReplaceAll = useCallback(() => {
    if (readOnly || !editor || !monaco || matches.length === 0) return;
    // Descending order so earlier ranges are not invalidated by later splices,
    // and a single undo stop pair so the whole thing is one Ctrl+Z.
    const edits = [...matches]
      .sort((a, b) =>
        b.startLineNumber - a.startLineNumber || b.startColumn - a.startColumn,
      )
      .map((range) => ({
        range: new monaco.Range(
          range.startLineNumber,
          range.startColumn,
          range.endLineNumber,
          range.endColumn,
        ),
        text: replacement,
        forceMoveMarkers: true,
      }));
    editor.pushUndoStop();
    editor.executeEdits("ob-find-replace-all", edits);
    editor.pushUndoStop();
    pushChange();
    setContentNonce((n) => n + 1);
  }, [readOnly, editor, monaco, matches, replacement, pushChange]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      editor?.focus?.();
    } else if (e.key === "Enter") {
      e.preventDefault();
      goTo(e.shiftKey ? -1 : 1);
    }
  };

  const counter = useMemo(() => {
    if (invalidPattern) return "Bad pattern";
    if (!query) return "";
    if (matches.length === 0) return "0 results";
    return `${index + 1}/${matches.length}`;
  }, [invalidPattern, query, matches.length, index]);

  if (!open) return null;

  const toggleClass = (active: boolean) =>
    `size-6 flex items-center justify-center rounded-md border text-[10px] transition-colors cursor-pointer shrink-0 ${
      active
        ? "border-ob-text/20 bg-ob-raised text-ob-text"
        : "border-ob-line bg-ob-card text-ob-muted hover:bg-ob-raised hover:text-ob-text"
    }`;

  const inputClass =
    "h-7 min-w-0 flex-1 px-2 rounded-md bg-ob-raised border border-ob-line text-[11px] font-mono text-ob-text placeholder:text-ob-muted outline-none transition-colors focus:border-ob-text/20";

  const iconBtnClass =
    "size-6 flex items-center justify-center rounded-md bg-ob-card hover:bg-ob-raised text-ob-muted hover:text-ob-text border border-ob-line transition-colors cursor-pointer shrink-0 disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <div
      className={`absolute z-40 rounded-xl border border-ob-line bg-ob-card/95 backdrop-blur-md shadow-[0_12px_36px_rgba(0,0,0,0.24)] p-2 space-y-1.5 font-mono text-ob-text ${
        compact ? "top-1 left-1 right-1" : "top-2 right-3 w-[22rem] max-w-[calc(100%-1.5rem)]"
      } ${className}`}
      onKeyDown={handleKeyDown}
    >
      <div className="flex items-center gap-1.5">
        <Search className="size-3.5 text-ob-muted shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find in document"
          spellCheck={false}
          autoCapitalize="none"
          autoCorrect="off"
          className={inputClass}
        />
        <span
          className={`text-[10px] tabular-nums shrink-0 min-w-[3.25rem] text-right font-mono ${
            invalidPattern
              ? "text-ob-negative"
              : "text-ob-muted"
          }`}
        >
          {counter}
        </span>
        <button
          type="button"
          onClick={() => goTo(-1)}
          disabled={matches.length === 0}
          className={iconBtnClass}
          title="Previous match (Shift+Enter)"
        >
          <ArrowUp className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={() => goTo(1)}
          disabled={matches.length === 0}
          className={iconBtnClass}
          title="Next match (Enter)"
        >
          <ArrowDown className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={() => {
            onClose();
            editor?.focus?.();
          }}
          className={iconBtnClass}
          title="Close (Esc)"
        >
          <X className="w-3 h-3" />
        </button>
      </div>

      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setMatchCase((v) => !v)}
          className={toggleClass(matchCase)}
          title="Match case"
        >
          <CaseSensitive className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={() => setWholeWord((v) => !v)}
          className={toggleClass(wholeWord)}
          title="Whole word"
        >
          <WholeWord className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={() => setIsRegex((v) => !v)}
          className={toggleClass(isRegex)}
          title="Regular expression"
        >
          <Regex className="w-3.5 h-3.5" />
        </button>

        {!readOnly && (
          <button
            type="button"
            onClick={() => setShowReplace((v) => !v)}
            className={`${toggleClass(showReplace)} ml-auto`}
            title={showReplace ? "Hide replace" : "Show replace"}
          >
            <Replace className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {showReplace && !readOnly && (
        <div className="flex items-center gap-1.5">
          <Replace className="size-3.5 text-ob-muted shrink-0" />
          <input
            type="text"
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
            placeholder="Replace with"
            spellCheck={false}
            autoCapitalize="none"
            autoCorrect="off"
            className={inputClass}
          />
          <button
            type="button"
            onClick={handleReplaceOne}
            disabled={matches.length === 0}
            className={iconBtnClass}
            title="Replace this match"
          >
            <Replace className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={handleReplaceAll}
            disabled={matches.length === 0}
            className={iconBtnClass}
            title={`Replace all ${matches.length} match(es)`}
          >
            <ReplaceAll className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}
