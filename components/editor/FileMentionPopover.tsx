"use client";

import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { BookOpen, File, FileCheck, FileCode, FileText, Image as ImageIcon } from "lucide-react";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { scoreMatches } from "@/lib/mention-match";
import { getCaretCoords } from "@/lib/textarea-caret";
import { useProjectFiles, type ProjectFile } from "@/components/editor/useProjectFiles";

interface FileMentionPopoverProps {
  /** The chat textarea this popover belongs to. Must sit inside a `relative` wrapper. */
  textarea: HTMLTextAreaElement | null;
  projectId: string;
  /** The controlled value of the textarea; a change re-evaluates the trigger. */
  chatInput: string;
  /** The user picked `file`; `@` is at `triggerIndex` and the typed query is `queryLength` long. */
  onInsertMention: (file: string, triggerIndex: number, queryLength: number) => void;
  /** Reports whether the list is showing, so the chat's Enter-to-send can stand down. */
  onOpenChange?: (open: boolean) => void;
}

interface Trigger {
  index: number;
  query: string;
}

/**
 * The `@query` token the caret is in: an `@` at the start of the text or after
 * whitespace, followed by no whitespace (and no second `@`) up to the caret.
 */
function detectTrigger(value: string, caret: number): Trigger | null {
  let i = caret - 1;
  while (i >= 0 && value[i] !== "@") {
    if (/\s/.test(value[i])) return null;
    i--;
  }
  if (i < 0) return null;
  if (i > 0 && !/\s/.test(value[i - 1])) return null;
  return { index: i, query: value.slice(i + 1, caret) };
}

function fileIcon(file: ProjectFile | undefined, path: string) {
  const ext = (file?.ext || path.slice(path.lastIndexOf(".")) || "").toLowerCase();
  if (file?.type === "image" || [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"].includes(ext)) {
    return <ImageIcon className="w-4 h-4 text-purple-400 shrink-0" />;
  }
  if (ext === ".tex") return <FileText className="w-4 h-4 text-indigo-400 shrink-0" />;
  if (ext === ".bib") return <BookOpen className="w-4 h-4 text-amber-400 shrink-0" />;
  if (ext === ".cls" || ext === ".sty") return <FileCode className="w-4 h-4 text-emerald-400 shrink-0" />;
  if (ext === ".pdf") return <FileCheck className="w-4 h-4 text-rose-400 shrink-0" />;
  return <File className="w-4 h-4 text-zinc-400 shrink-0" />;
}

export function FileMentionPopover({
  textarea,
  projectId,
  chatInput,
  onInsertMention,
  onOpenChange,
}: FileMentionPopoverProps) {
  const { files } = useProjectFiles(projectId);
  const [caret, setCaret] = useState(0);
  const [focused, setFocused] = useState(false);
  const [dismissedAt, setDismissedAt] = useState<number | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [anchor, setAnchor] = useState<{ left: number; top: number; height: number }>({ left: 0, top: 0, height: 0 });
  const listRef = useRef<HTMLDivElement>(null);

  // Track caret and focus of the textarea. Arrow keys and clicks move the caret
  // without changing the text, so `chatInput` alone is not enough.
  useEffect(() => {
    if (!textarea) return;
    const sync = () => setCaret(textarea.selectionStart ?? 0);
    const onFocus = () => {
      setFocused(true);
      sync();
    };
    const onBlur = () => setFocused(false);
    const onSelectionChange = () => {
      if (document.activeElement === textarea) sync();
    };
    setFocused(document.activeElement === textarea);
    sync();
    textarea.addEventListener("input", sync);
    textarea.addEventListener("keyup", sync);
    textarea.addEventListener("click", sync);
    textarea.addEventListener("select", sync);
    textarea.addEventListener("focus", onFocus);
    textarea.addEventListener("blur", onBlur);
    document.addEventListener("selectionchange", onSelectionChange);
    return () => {
      textarea.removeEventListener("input", sync);
      textarea.removeEventListener("keyup", sync);
      textarea.removeEventListener("click", sync);
      textarea.removeEventListener("select", sync);
      textarea.removeEventListener("focus", onFocus);
      textarea.removeEventListener("blur", onBlur);
      document.removeEventListener("selectionchange", onSelectionChange);
    };
  }, [textarea]);

  // Controlled text can change under a still caret (e.g. after an insertion).
  useEffect(() => {
    if (textarea && document.activeElement === textarea) setCaret(textarea.selectionStart ?? 0);
  }, [chatInput, textarea]);

  const trigger = useMemo(() => detectTrigger(chatInput, Math.min(caret, chatInput.length)), [chatInput, caret]);
  const query = trigger?.query ?? "";
  const results = useMemo(() => (trigger ? scoreMatches(files, query, 8) : []), [files, query, trigger]);
  const filesByPath = useMemo(() => new Map(files.map((f) => [f.path, f])), [files]);

  useEffect(() => {
    if (!trigger) setDismissedAt(null);
  }, [trigger]);
  useEffect(() => {
    setActiveIndex(0);
  }, [query, trigger?.index]);

  const open =
    !!textarea && !!trigger && focused && !textarea.disabled && results.length > 0 && dismissedAt !== trigger.index;

  const onOpenChangeRef = useRef(onOpenChange);
  onOpenChangeRef.current = onOpenChange;
  useEffect(() => {
    onOpenChangeRef.current?.(open);
    return () => onOpenChangeRef.current?.(false);
  }, [open]);

  // Pin the popover to the `@`, not the caret, so it does not slide while typing.
  const triggerIndex = trigger?.index ?? -1;
  useLayoutEffect(() => {
    if (!open || !textarea || triggerIndex < 0) return;
    const c = getCaretCoords(textarea, triggerIndex);
    setAnchor({
      left: textarea.offsetLeft + Math.min(Math.max(c.left, 0), Math.max(textarea.clientWidth - 1, 0)),
      top: textarea.offsetTop + Math.min(Math.max(c.top, 0), Math.max(textarea.clientHeight - c.height, 0)),
      height: c.height,
    });
  }, [open, textarea, triggerIndex, chatInput]);

  // Keyboard: captured on window so it runs before the textarea's own handlers,
  // and swallowed so Enter does not also send the message.
  const stateRef = useRef({ results, activeIndex, trigger });
  stateRef.current = { results, activeIndex, trigger };
  const insertRef = useRef(onInsertMention);
  insertRef.current = onInsertMention;
  useEffect(() => {
    if (!open || !textarea) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (document.activeElement !== textarea || e.isComposing) return;
      const { results: list, activeIndex: active, trigger: t } = stateRef.current;
      if (!t || list.length === 0) return;
      const swallow = () => {
        e.preventDefault();
        e.stopPropagation();
      };
      switch (e.key) {
        case "ArrowDown":
          swallow();
          setActiveIndex((active + 1) % list.length);
          break;
        case "ArrowUp":
          swallow();
          setActiveIndex((active - 1 + list.length) % list.length);
          break;
        case "Enter":
        case "Tab": {
          swallow();
          const pick = list[Math.min(active, list.length - 1)];
          insertRef.current(pick.path, t.index, t.query.length);
          break;
        }
        case "Escape":
          swallow();
          setDismissedAt(t.index);
          break;
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, textarea]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [open, activeIndex]);

  if (!textarea) return null;

  return (
    <Popover open={open}>
      <PopoverAnchor asChild>
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            left: anchor.left,
            top: anchor.top,
            width: 1,
            height: anchor.height,
            pointerEvents: "none",
          }}
        />
      </PopoverAnchor>
      <PopoverContent
        side="top"
        align="start"
        sideOffset={6}
        className="w-72 max-w-[calc(100vw-1.5rem)] p-1 font-mono"
        // The textarea keeps focus the whole time; the list is driven by its keys.
        onOpenAutoFocus={(e) => e.preventDefault()}
        onCloseAutoFocus={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
        onMouseDown={(e) => e.preventDefault()}
      >
        <div ref={listRef} role="listbox" aria-label="Mention a file" className="max-h-60 overflow-y-auto">
          {results.map((r, i) => {
            const base = r.path.slice(r.path.lastIndexOf("/") + 1);
            const dir = r.path.slice(0, r.path.length - base.length);
            return (
              <div
                key={r.path}
                role="option"
                aria-selected={i === activeIndex}
                data-index={i}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => {
                  if (trigger) onInsertMention(r.path, trigger.index, trigger.query.length);
                }}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-[11px] cursor-pointer ${
                  i === activeIndex
                    ? "bg-slate-100 dark:bg-[#22242C] text-slate-900 dark:text-[#E2E4E9]"
                    : "text-slate-600 dark:text-[#9E9E9E]"
                }`}
              >
                {fileIcon(filesByPath.get(r.path), r.path)}
                <span className="truncate font-medium">{base}</span>
                {dir && <span className="truncate text-[10px] text-slate-400 dark:text-[#62666D]">{dir}</span>}
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
