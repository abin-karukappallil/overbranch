"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ClipboardPaste, Copy, Scissors, Search, TextSelect, X } from "lucide-react";
import { copyText, readClipboard } from "@/lib/clipboard";

interface MobileEditorAssistProps {
  /** The mobile Monaco instance. Null until it mounts. */
  editor: any | null;
  monaco: any | null;
  /** Hides every mutating affordance. */
  readOnly?: boolean;
  /** Only render while this pane is the visible mobile tab. */
  active?: boolean;
  onOpenSearch: () => void;
  /** Called with the new buffer after an edit, so autosave still runs. */
  onDocumentChange?: (value: string) => void;
}

interface VisiblePoint {
  left: number;
  top: number;
  height: number;
}

type HandleKind = "caret" | "start" | "end";

interface DragState {
  kind: HandleKind;
  pointerId: number;
  moved: boolean;
  /** The selection end that stays put while the other is dragged. */
  anchor: { lineNumber: number; column: number } | null;
}

const HANDLE_SIZE = 22;
const DEFAULT_LINE_HEIGHT = 19;
const EDGE_SCROLL_ZONE = 48;

/**
 * Touch editing layer for Monaco on phones.
 *
 * Monaco renders its text into non-editable DOM and keeps the real caret in an
 * off-screen textarea, so a touch device gets no native selection handles and
 * no caret the user can grab — which is why the mobile editor was unusable.
 * This overlay supplies the missing affordances the way iOS does: a draggable
 * caret handle, two selection handles, and a floating action callout. Search
 * itself lives in the editor header, not here.
 *
 * Everything here drives Monaco through its public API (`setPosition`,
 * `setSelection`, `executeEdits`), so it stays correct under word wrap,
 * folding and read-only mode without duplicating any editor state.
 */
export function MobileEditorAssist({
  editor,
  monaco,
  readOnly = false,
  active = true,
  onOpenSearch,
  onDocumentChange,
}: MobileEditorAssistProps) {
  const [focused, setFocused] = useState(false);
  const [caret, setCaret] = useState<VisiblePoint | null>(null);
  const [selStart, setSelStart] = useState<VisiblePoint | null>(null);
  const [selEnd, setSelEnd] = useState<VisiblePoint | null>(null);
  const [hasSelection, setHasSelection] = useState(false);
  const [calloutOpen, setCalloutOpen] = useState(false);
  const [typing, setTyping] = useState(false);
  const [pasteFallbackOpen, setPasteFallbackOpen] = useState(false);

  const dragRef = useRef<DragState | null>(null);
  const autoScrollRef = useRef<{ dir: number; timer: NodeJS.Timeout } | null>(null);
  const blurTimerRef = useRef<NodeJS.Timeout | null>(null);
  const typingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pasteTargetRef = useRef<HTMLTextAreaElement>(null);

  const lineHeight = useCallback((): number => {
    try {
      const h = editor?.getOption?.(monaco?.editor?.EditorOption?.lineHeight);
      return typeof h === "number" && h > 0 ? h : DEFAULT_LINE_HEIGHT;
    } catch (_) {
      return DEFAULT_LINE_HEIGHT;
    }
  }, [editor, monaco]);

  /**
   * Vertical distance from a handle's centre to the glyph it points at, so a
   * drag samples the character under the handle's tip rather than under the
   * fingertip (which sits a whole line below it).
   */
  const probeOffset = useCallback(
    () => HANDLE_SIZE / 2 + lineHeight() / 2,
    [lineHeight],
  );

  // --- Keep the handles pinned to the model ------------------------------
  const sync = useCallback(() => {
    if (!editor) return;
    let sel: any;
    try {
      sel = editor.getSelection();
    } catch (_) {
      return;
    }
    if (!sel) return;

    const viewportHeight = (() => {
      try {
        return editor.getLayoutInfo?.()?.height ?? 0;
      } catch (_) {
        return 0;
      }
    })();

    const toPoint = (pos: any): VisiblePoint | null => {
      try {
        // Scroll-adjusted and relative to the editor's DOM node. Monaco
        // documents this as *inaccurate* (rather than null) for positions
        // outside the viewport, so reject out-of-bounds results explicitly —
        // otherwise a stale handle hovers at the pane edge and drags from
        // the wrong place.
        const v = editor.getScrolledVisiblePosition(pos);
        if (!v) return null;
        const height = v.height || lineHeight();
        if (viewportHeight > 0 && (v.top + height < 0 || v.top > viewportHeight)) {
          return null;
        }
        return { left: v.left, top: v.top, height };
      } catch (_) {
        return null;
      }
    };

    if (sel.isEmpty()) {
      setHasSelection(false);
      setCaret(toPoint(sel.getStartPosition()));
      setSelStart(null);
      setSelEnd(null);
    } else {
      setHasSelection(true);
      setCaret(null);
      setSelStart(toPoint(sel.getStartPosition()));
      setSelEnd(toPoint(sel.getEndPosition()));
    }
  }, [editor, lineHeight]);

  const markTyping = useCallback(() => {
    setTyping(true);
    setCalloutOpen(false);
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
    typingTimerRef.current = setTimeout(() => setTyping(false), 400);
  }, []);

  useEffect(() => {
    if (!editor) return;
    const subs = [
      editor.onDidChangeCursorSelection?.(() => {
        if (!dragRef.current) setCalloutOpen(false);
        sync();
      }),
      editor.onDidScrollChange?.(() => sync()),
      editor.onDidLayoutChange?.(() => sync()),
      editor.onDidChangeModelContent?.(() => {
        markTyping();
        sync();
      }),
      editor.onDidFocusEditorText?.(() => {
        if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
        setFocused(true);
        sync();
      }),
      editor.onDidBlurEditorText?.(() => {
        // Debounced: tapping our own buttons blurs the editor for a moment,
        // and tearing the UI down mid-tap would cancel the action.
        if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
        blurTimerRef.current = setTimeout(() => {
          setFocused(false);
          setCalloutOpen(false);
        }, 200);
      }),
    ];
    sync();
    return () => {
      subs.forEach((s) => s?.dispose?.());
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
    };
  }, [editor, sync, markTyping]);

  // The on-screen keyboard shrinks the visual viewport without changing layout
  // height on iOS, so Monaco must be re-laid-out and the handles re-measured
  // whenever it opens or closes.
  useEffect(() => {
    const vv = typeof window !== "undefined" ? window.visualViewport : null;
    if (!vv) return;
    const onViewportChange = () => {
      try {
        editor?.layout?.();
      } catch (_) {}
      sync();
    };
    vv.addEventListener("resize", onViewportChange);
    vv.addEventListener("scroll", onViewportChange);
    onViewportChange();
    return () => {
      vv.removeEventListener("resize", onViewportChange);
      vv.removeEventListener("scroll", onViewportChange);
    };
  }, [editor, sync]);

  // Re-measure when this pane becomes the visible tab (it was display:none).
  useEffect(() => {
    if (!active || !editor) return;
    const id = setTimeout(() => {
      try {
        editor.layout();
      } catch (_) {}
      sync();
    }, 60);
    return () => clearTimeout(id);
  }, [active, editor, sync]);

  // --- Edit primitives ---------------------------------------------------
  const applyEdits = useCallback(
    (edits: any[], source: string) => {
      if (!editor || readOnly) return;
      editor.pushUndoStop();
      editor.executeEdits(source, edits);
      editor.pushUndoStop();
      try {
        onDocumentChange?.(editor.getValue());
      } catch (_) {}
    },
    [editor, readOnly, onDocumentChange],
  );

  const insertText = useCallback(
    (text: string) => {
      if (!editor || !text) return;
      const sel = editor.getSelection();
      if (!sel) return;
      applyEdits([{ range: sel, text, forceMoveMarkers: true }], "mobile-insert");
      editor.focus();
    },
    [editor, applyEdits],
  );

  // --- Handle dragging ---------------------------------------------------
  const stopAutoScroll = useCallback(() => {
    if (autoScrollRef.current) {
      clearInterval(autoScrollRef.current.timer);
      autoScrollRef.current = null;
    }
  }, []);

  const maybeAutoScroll = useCallback(
    (clientY: number) => {
      if (!editor) return;
      const dom = editor.getDomNode?.();
      if (!dom) return;
      const rect = dom.getBoundingClientRect();
      let dir = 0;
      if (clientY < rect.top + EDGE_SCROLL_ZONE) dir = -1;
      else if (clientY > rect.bottom - EDGE_SCROLL_ZONE) dir = 1;

      if (dir === 0) {
        stopAutoScroll();
        return;
      }
      if (autoScrollRef.current?.dir === dir) return;
      stopAutoScroll();
      autoScrollRef.current = {
        dir,
        timer: setInterval(() => {
          try {
            editor.setScrollTop(Math.max(0, editor.getScrollTop() + dir * 14));
          } catch (_) {}
        }, 32),
      };
    },
    [editor, stopAutoScroll],
  );

  const handlePointerDown = (kind: HandleKind) => (e: React.PointerEvent) => {
    if (!editor) return;
    // Keep focus (and therefore the keyboard) on the editor.
    e.preventDefault();
    e.stopPropagation();
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch (_) {}

    const sel = editor.getSelection();
    dragRef.current = {
      kind,
      pointerId: e.pointerId,
      moved: false,
      anchor:
        kind === "start"
          ? sel?.getEndPosition?.() ?? null
          : kind === "end"
            ? sel?.getStartPosition?.() ?? null
            : null,
    };
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId || !editor || !monaco) return;
    e.preventDefault();
    e.stopPropagation();
    drag.moved = true;

    // The start handle hangs above its line, the others below it.
    const probeY =
      drag.kind === "start" ? e.clientY + probeOffset() : e.clientY - probeOffset();

    let pos: any = null;
    try {
      pos = editor.getTargetAtClientPoint(e.clientX, probeY)?.position ?? null;
    } catch (_) {}
    if (!pos) {
      maybeAutoScroll(e.clientY);
      return;
    }

    if (drag.kind === "caret") {
      editor.setPosition(pos);
    } else if (drag.anchor) {
      const a = drag.anchor;
      const aFirst =
        a.lineNumber < pos.lineNumber ||
        (a.lineNumber === pos.lineNumber && a.column <= pos.column);
      const s = aFirst ? a : pos;
      const t = aFirst ? pos : a;
      // Refuse to collapse the selection onto itself mid-drag; the handles
      // would vanish under the finger and the gesture would be unrecoverable.
      if (s.lineNumber === t.lineNumber && s.column === t.column) return;
      editor.setSelection(
        new monaco.Range(s.lineNumber, s.column, t.lineNumber, t.column),
      );
    }
    maybeAutoScroll(e.clientY);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    stopAutoScroll();
    dragRef.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch (_) {}
    if (!drag) return;
    e.preventDefault();
    e.stopPropagation();
    // A tap (no movement) toggles the menu; a drag always reveals it.
    setCalloutOpen((prev) => (drag.moved ? true : !prev));
    editor?.focus?.();
    sync();
  };

  // --- Callout actions ---------------------------------------------------
  const selectWord = () => {
    if (!editor || !monaco) return;
    const model = editor.getModel();
    const pos = editor.getPosition();
    if (!model || !pos) return;
    const word = model.getWordAtPosition(pos);
    const range = word
      ? new monaco.Range(pos.lineNumber, word.startColumn, pos.lineNumber, word.endColumn)
      : new monaco.Range(pos.lineNumber, 1, pos.lineNumber, model.getLineMaxColumn(pos.lineNumber));
    editor.setSelection(range);
    editor.focus();
    setCalloutOpen(true);
  };

  const selectAll = () => {
    if (!editor) return;
    const model = editor.getModel();
    if (!model) return;
    editor.setSelection(model.getFullModelRange());
    editor.focus();
    setCalloutOpen(true);
  };

  const selectedText = (): string => {
    if (!editor) return "";
    const model = editor.getModel();
    const sel = editor.getSelection();
    if (!model || !sel || sel.isEmpty()) return "";
    return model.getValueInRange(sel);
  };

  const handleCopy = async () => {
    const text = selectedText();
    if (!text) return;
    await copyText(text);
    setCalloutOpen(false);
    editor?.focus?.();
  };

  const handleCut = async () => {
    if (readOnly) return;
    const text = selectedText();
    if (!text) return;
    await copyText(text);
    const sel = editor.getSelection();
    applyEdits([{ range: sel, text: "", forceMoveMarkers: true }], "mobile-cut");
    setCalloutOpen(false);
    editor?.focus?.();
  };

  const handlePaste = async () => {
    if (readOnly) return;
    const text = await readClipboard();
    if (text != null && text !== "") {
      insertText(text);
      setCalloutOpen(false);
      return;
    }
    // iOS Safari has no readText at all. The only way to reach the clipboard
    // is a genuine DOM paste into a real field, so hand the user one.
    setCalloutOpen(false);
    setPasteFallbackOpen(true);
    setTimeout(() => pasteTargetRef.current?.focus(), 40);
  };

  const consumePastedText = (text: string) => {
    if (!text) return;
    setPasteFallbackOpen(false);
    if (pasteTargetRef.current) pasteTargetRef.current.value = "";
    insertText(text);
  };

  if (!editor || !monaco || !active) return null;

  const showHandles = focused && !typing;
  const calloutAnchor = hasSelection ? selStart ?? selEnd : caret;

  const handleBase =
    "ob-touch-handle pointer-events-auto absolute flex items-center justify-center";
  const ballClass =
    "rounded-full bg-emerald-600 dark:bg-[#10B981] shadow-[0_1px_4px_rgba(0,0,0,0.45)] ring-2 ring-white/80 dark:ring-[#0E0F12]";
  const stemClass = "absolute w-0.5 bg-emerald-600 dark:bg-[#10B981]";

  const calloutBtn =
    "px-2.5 h-8 flex items-center gap-1 text-[11px] font-mono whitespace-nowrap text-slate-700 dark:text-[#E2E4E9] active:bg-slate-200 dark:active:bg-[#2A2C36] transition-colors first:rounded-l-lg last:rounded-r-lg";

  return (
    // Transparent to taps except on the handles themselves, so Monaco keeps
    // receiving every gesture it already handles.
    <div className="absolute inset-0 z-20 pointer-events-none overflow-hidden">
      {showHandles && !hasSelection && caret && (
        <div
          className={handleBase}
          style={{
            left: caret.left - HANDLE_SIZE / 2,
            top: caret.top + caret.height,
            width: HANDLE_SIZE,
            height: HANDLE_SIZE,
          }}
          onPointerDown={handlePointerDown("caret")}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          aria-hidden="true"
        >
          <span className={stemClass} style={{ height: 6, top: -3 }} />
          <span className={ballClass} style={{ width: 13, height: 13 }} />
        </div>
      )}

      {showHandles && hasSelection && selStart && (
        <div
          className={handleBase}
          style={{
            left: selStart.left - HANDLE_SIZE / 2,
            top: selStart.top - HANDLE_SIZE,
            width: HANDLE_SIZE,
            height: HANDLE_SIZE,
          }}
          onPointerDown={handlePointerDown("start")}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          aria-hidden="true"
        >
          <span className={ballClass} style={{ width: 13, height: 13 }} />
          <span className={stemClass} style={{ height: 6, bottom: -3 }} />
        </div>
      )}

      {showHandles && hasSelection && selEnd && (
        <div
          className={handleBase}
          style={{
            left: selEnd.left - HANDLE_SIZE / 2,
            top: selEnd.top + selEnd.height,
            width: HANDLE_SIZE,
            height: HANDLE_SIZE,
          }}
          onPointerDown={handlePointerDown("end")}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          aria-hidden="true"
        >
          <span className={stemClass} style={{ height: 6, top: -3 }} />
          <span className={ballClass} style={{ width: 13, height: 13 }} />
        </div>
      )}

      {/* Action callout */}
      {showHandles && calloutOpen && calloutAnchor && (
        <div
          className="pointer-events-auto absolute flex items-stretch rounded-lg border border-slate-300 dark:border-[#383B46] bg-white dark:bg-[#22242C] shadow-2xl overflow-x-auto max-w-[94%] divide-x divide-slate-200 dark:divide-[#383B46]"
          style={{
            left: Math.max(6, calloutAnchor.left - 60),
            top: Math.max(4, calloutAnchor.top - 42),
          }}
          onPointerDown={(e) => e.preventDefault()}
        >
          {!hasSelection && (
            <button type="button" className={calloutBtn} onClick={selectWord}>
              <TextSelect className="w-3 h-3" />
              <span>Select</span>
            </button>
          )}
          <button type="button" className={calloutBtn} onClick={selectAll}>
            <span>Select All</span>
          </button>
          {hasSelection && (
            <button type="button" className={calloutBtn} onClick={handleCopy}>
              <Copy className="w-3 h-3" />
              <span>Copy</span>
            </button>
          )}
          {hasSelection && !readOnly && (
            <button type="button" className={calloutBtn} onClick={handleCut}>
              <Scissors className="w-3 h-3" />
              <span>Cut</span>
            </button>
          )}
          {!readOnly && (
            <button type="button" className={calloutBtn} onClick={handlePaste}>
              <ClipboardPaste className="w-3 h-3" />
              <span>Paste</span>
            </button>
          )}
          <button
            type="button"
            className={calloutBtn}
            onClick={() => {
              setCalloutOpen(false);
              onOpenSearch();
            }}
          >
            <Search className="w-3 h-3" />
            <span>Find</span>
          </button>
        </div>
      )}

      {/* iOS paste fallback: readText() is unavailable there, so the only
          route to the clipboard is a real DOM paste the user performs. */}
      {pasteFallbackOpen && (
        <div className="pointer-events-auto absolute inset-x-3 top-3 rounded-xl border border-slate-300 dark:border-[#383B46] bg-white dark:bg-[#141519] shadow-2xl p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono font-semibold text-slate-900 dark:text-[#E2E4E9]">
              Long-press the box, then tap Paste
            </span>
            <button
              type="button"
              onClick={() => setPasteFallbackOpen(false)}
              className="p-1 rounded-md text-slate-500 dark:text-[#9E9E9E] active:bg-slate-200 dark:active:bg-[#22242C]"
              aria-label="Cancel paste"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <textarea
            ref={pasteTargetRef}
            rows={2}
            placeholder="Paste here…"
            spellCheck={false}
            autoCapitalize="none"
            autoCorrect="off"
            onPaste={(e) => {
              const text = e.clipboardData?.getData("text/plain");
              if (text) {
                e.preventDefault();
                consumePastedText(text);
              }
            }}
            onInput={(e) => {
              // Some engines fire no usable `paste` event; take the value.
              const value = (e.currentTarget as HTMLTextAreaElement).value;
              if (value) consumePastedText(value);
            }}
            className="w-full rounded-lg border border-slate-200 dark:border-[#282A30] bg-slate-50 dark:bg-[#1A1C22] p-2 text-[11px] font-mono text-slate-900 dark:text-[#E2E4E9] outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </div>
      )}
    </div>
  );
}
