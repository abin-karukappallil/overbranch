/**
 * lib/inline-diff-monaco.ts — the inline review, drawn in a Monaco editor.
 *
 * A proposed change is shown where it would land: the lines it removes get a
 * red background, the lines it adds appear beneath them in a green block, and
 * each change has its own Accept / Reject.
 *
 * Four things are deliberate:
 *
 * 1. **The document is not touched until a change is accepted.** The removed
 *    lines are the document's own lines, decorated; the added lines live in
 *    view zones, which are not part of the model. Applying the proposal first
 *    and reverting on Reject would push unaccepted AI text through autosave,
 *    the compiler and — in a shared project — the CRDT to every collaborator.
 *
 * 2. **Each change is anchored by a tracked decoration, not a line number.**
 *    The user keeps typing while reviewing, collaborators' edits keep
 *    arriving, and accepting one change moves every change below it. Monaco
 *    moves a decoration with the text it covers, so a change is always applied
 *    where it now is. If the lines a change would replace are edited, it no
 *    longer applies cleanly and is withdrawn from the review instead of being
 *    drawn over text it does not match.
 *
 * 3. **Accepting is an ordinary edit** (`executeEdits`, one undo stop): the
 *    same path as typing, so it is what the Yjs binding turns into CRDT
 *    operations and what Ctrl+Z undoes.
 *
 * 4. **The Accept / Reject controls are plain DOM over the editor**, positioned
 *    from the editor's own geometry — not nodes inside a view zone, whose
 *    pointer events Monaco owns.
 *
 * Pure block logic (what the blocks are, where they sit) is in
 * `lib/inline-diff.ts`.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

import type { PlacedBlock } from "./inline-diff";

export interface InlineDiffState {
  total: number;
  pending: number;
  accepted: number;
  rejected: number;
  /** Changes that cannot be shown inline: the document moved under them. */
  unplaced: number;
  /** 0-based index of the focused change among the pending ones, or -1. */
  current: number;
}

export interface InlineDiffOptions {
  /** Viewers see the proposal but cannot accept it. */
  readOnly?: boolean;
  onState?: (state: InlineDiffState) => void;
  /** Just before accepted changes are written: the last moment the model holds the pre-accept text. */
  onBeforeApply?: () => void;
  /** After an accepted change has been written to the model. */
  onAccepted?: (blockId: string, state: InlineDiffState) => void;
  onRejected?: (blockId: string, state: InlineDiffState) => void;
}

type Status = "pending" | "accepted" | "rejected" | "unplaced";

interface Entry {
  block: PlacedBlock;
  status: Status;
  /** Model decoration that follows the block's lines (or its insertion point). */
  tracker: string | null;
  /** Pure insertion before line 1: there is no line to anchor on. */
  atTop: boolean;
  actions: HTMLElement | null;
}

const STICKY_NEVER_GROWS = 1; // monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges

export class InlineDiffController {
  private readonly editor: any;
  private readonly monaco: any;
  private readonly options: InlineDiffOptions;
  private readonly entries: Entry[];
  private readonly overlay: HTMLElement;
  private readonly disposables: Array<{ dispose(): void }> = [];
  private lineDecorations: string[] = [];
  private zoneIds: string[] = [];
  private zoneNodes: Array<{ node: HTMLElement; id: string; height: number }> = [];
  private signature = "";
  private frame: number | null = null;
  private current = 0;
  private disposed = false;

  constructor(editor: any, monaco: any, blocks: PlacedBlock[], options: InlineDiffOptions = {}) {
    this.editor = editor;
    this.monaco = monaco;
    this.options = options;

    const model = editor.getModel();
    this.entries = blocks.map((block) => ({
      block,
      status: block.liveStart === null ? "unplaced" : "pending",
      tracker: null,
      atTop: false,
      actions: null,
    }));
    for (const entry of this.entries) {
      if (entry.status === "pending") this.track(entry, model);
    }

    this.overlay = document.createElement("div");
    this.overlay.className = "ob-diff-overlay";
    editor.getDomNode()?.appendChild(this.overlay);

    this.disposables.push(
      editor.onDidChangeModelContent(() => this.schedule()),
      editor.onDidLayoutChange(() => {
        this.signature = ""; // widths changed: wrapped zone heights must be re-measured
        this.schedule();
      }),
      editor.onDidScrollChange(() => this.positionActions()),
    );

    this.render();
    this.emit();
  }

  // -- public API -----------------------------------------------------------

  getState(): InlineDiffState {
    const count = (s: Status) => this.entries.filter((e) => e.status === s).length;
    const pending = count("pending");
    return {
      total: this.entries.length,
      pending,
      accepted: count("accepted"),
      rejected: count("rejected"),
      unplaced: count("unplaced"),
      current: pending === 0 ? -1 : Math.min(this.current, pending - 1),
    };
  }

  pendingIds(): string[] {
    return this.pending().map((e) => e.block.id);
  }

  accept(blockId: string): boolean {
    const entry = this.entries.find((e) => e.block.id === blockId && e.status === "pending");
    if (!entry || this.options.readOnly) return false;
    const model = this.editor.getModel();
    const where = this.locate(entry, model);
    if (!where) {
      this.withdraw(entry, model);
      this.render();
      this.emit();
      return false;
    }

    const edit = this.editFor(entry, where, model);
    this.options.onBeforeApply?.();
    this.editor.pushUndoStop();
    this.editor.executeEdits("ai-accept-change", [edit]);
    this.editor.pushUndoStop();

    entry.status = "accepted";
    this.untrack(entry, model);
    this.render();
    const state = this.emit();
    this.options.onAccepted?.(blockId, state);
    return true;
  }

  reject(blockId: string): boolean {
    const entry = this.entries.find((e) => e.block.id === blockId && e.status === "pending");
    if (!entry) return false;
    entry.status = "rejected";
    this.untrack(entry, this.editor.getModel());
    this.render();
    const state = this.emit();
    this.options.onRejected?.(blockId, state);
    return true;
  }

  /** Accepts every pending change, bottom-up so no accepted edit moves another. Returns how many. */
  acceptAll(): number {
    if (this.options.readOnly) return 0;
    const model = this.editor.getModel();
    const edits: any[] = [];
    const done: Entry[] = [];
    for (const entry of this.pending()) {
      const where = this.locate(entry, model);
      if (!where) {
        this.withdraw(entry, model);
        continue;
      }
      edits.push(this.editFor(entry, where, model));
      done.push(entry);
    }
    if (edits.length) {
      this.options.onBeforeApply?.();
      this.editor.pushUndoStop();
      this.editor.executeEdits("ai-accept-all", edits);
      this.editor.pushUndoStop();
    }
    for (const entry of done) {
      entry.status = "accepted";
      this.untrack(entry, model);
    }
    this.render();
    const state = this.emit();
    for (const entry of done) this.options.onAccepted?.(entry.block.id, state);
    return done.length;
  }

  rejectAll(): void {
    const model = this.editor.getModel();
    const dropped = this.pending();
    for (const entry of dropped) {
      entry.status = "rejected";
      this.untrack(entry, model);
    }
    this.render();
    const state = this.emit();
    for (const entry of dropped) this.options.onRejected?.(entry.block.id, state);
  }

  /** Scrolls to a pending change (by index among the pending ones). */
  reveal(index: number): void {
    const pending = this.pending();
    if (!pending.length) return;
    this.current = ((index % pending.length) + pending.length) % pending.length;
    const where = this.locate(pending[this.current], this.editor.getModel());
    if (where) this.editor.revealLineInCenterIfOutsideViewport(Math.max(1, where.anchorLine));
    this.positionActions();
    this.emit();
  }

  next(): void {
    this.reveal(this.current + 1);
  }

  previous(): void {
    this.reveal(this.current - 1);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    for (const d of this.disposables) d.dispose();
    const model = this.editor.getModel?.();
    if (model && !model.isDisposed?.()) {
      for (const entry of this.entries) this.untrack(entry, model);
    }
    try {
      this.lineDecorations = this.editor.deltaDecorations(this.lineDecorations, []);
      this.editor.changeViewZones((accessor: any) => {
        for (const id of this.zoneIds) accessor.removeZone(id);
      });
    } catch {
      // the editor itself is being torn down
    }
    this.zoneIds = [];
    this.zoneNodes = [];
    this.overlay.remove();
  }

  // -- tracking -------------------------------------------------------------

  private pending(): Entry[] {
    return this.entries.filter((e) => e.status === "pending");
  }

  private track(entry: Entry, model: any): void {
    const start = entry.block.liveStart as number;
    const n = entry.block.oldLines.length;
    const lineCount = model.getLineCount();
    let range: any;
    if (n > 0) {
      const end = Math.min(start + n - 1, lineCount);
      range = new this.monaco.Range(start, 1, end, model.getLineMaxColumn(end));
    } else if (start <= 1) {
      entry.atTop = true;
      return;
    } else {
      // An insertion is anchored at the end of the line it follows.
      const after = Math.min(start - 1, lineCount);
      const col = model.getLineMaxColumn(after);
      range = new this.monaco.Range(after, col, after, col);
    }
    [entry.tracker] = model.deltaDecorations([], [{
      range,
      options: { stickiness: STICKY_NEVER_GROWS, description: "ob-inline-diff-anchor" },
    }]);
  }

  private untrack(entry: Entry, model: any): void {
    if (entry.tracker) {
      try {
        model.deltaDecorations([entry.tracker], []);
      } catch {
        // model already disposed
      }
      entry.tracker = null;
    }
    entry.actions?.remove();
    entry.actions = null;
  }

  private withdraw(entry: Entry, model: any): void {
    entry.status = "unplaced";
    this.untrack(entry, model);
  }

  /**
   * Where a pending block is now: its first and last line (`first > last` for
   * an insertion, which then goes after `anchorLine`). `null` when the lines it
   * would replace no longer hold the text it was computed against.
   */
  private locate(entry: Entry, model: any): { first: number; last: number; anchorLine: number } | null {
    const n = entry.block.oldLines.length;
    if (entry.atTop) return { first: 1, last: 0, anchorLine: 0 };
    if (!entry.tracker) return null;
    const range = model.getDecorationRange(entry.tracker);
    if (!range) return null;
    if (n === 0) {
      return { first: range.startLineNumber + 1, last: range.startLineNumber, anchorLine: range.startLineNumber };
    }
    const first = range.startLineNumber;
    const last = range.endLineNumber;
    if (last - first + 1 !== n) return null;
    for (let i = 0; i < n; i += 1) {
      if (model.getLineContent(first + i) !== entry.block.oldLines[i]) return null;
    }
    return { first, last, anchorLine: first };
  }

  private editFor(entry: Entry, where: { first: number; last: number; anchorLine: number }, model: any): any {
    const { Range } = this.monaco;
    const text = entry.block.newLines.join("\n");
    const lineCount = model.getLineCount();

    if (entry.block.oldLines.length === 0) {
      if (model.getValue() === "") {
        return { range: model.getFullModelRange(), text, forceMoveMarkers: true };
      }
      if (where.anchorLine <= 0) {
        return { range: new Range(1, 1, 1, 1), text: `${text}\n`, forceMoveMarkers: true };
      }
      const col = model.getLineMaxColumn(where.anchorLine);
      return { range: new Range(where.anchorLine, col, where.anchorLine, col), text: `\n${text}`, forceMoveMarkers: true };
    }

    if (entry.block.newLines.length === 0) {
      // Deleting whole lines takes one line break with them.
      if (where.last < lineCount) {
        return { range: new Range(where.first, 1, where.last + 1, 1), text: "", forceMoveMarkers: true };
      }
      if (where.first > 1) {
        const prev = where.first - 1;
        return {
          range: new Range(prev, model.getLineMaxColumn(prev), where.last, model.getLineMaxColumn(where.last)),
          text: "",
          forceMoveMarkers: true,
        };
      }
      return { range: model.getFullModelRange(), text: "", forceMoveMarkers: true };
    }

    return {
      range: new Range(where.first, 1, where.last, model.getLineMaxColumn(where.last)),
      text,
      forceMoveMarkers: true,
    };
  }

  // -- rendering ------------------------------------------------------------

  private schedule(): void {
    if (this.disposed || this.frame !== null) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      if (this.disposed) return;
      const before = this.getState();
      this.render();
      const after = this.getState();
      if (before.pending !== after.pending || before.unplaced !== after.unplaced) this.emit();
    });
  }

  private emit(): InlineDiffState {
    const state = this.getState();
    this.options.onState?.(state);
    return state;
  }

  private render(): void {
    if (this.disposed) return;
    const model = this.editor.getModel();
    if (!model) return;

    const decorations: any[] = [];
    const zones: Array<{ afterLine: number; lines: string[]; key: string }> = [];
    const parts: string[] = [];

    for (const entry of this.pending()) {
      const where = this.locate(entry, model);
      if (!where) {
        this.withdraw(entry, model);
        continue;
      }
      const base = entry.block.oldLines.length === 0 ? where.anchorLine + 1 : where.first;
      for (const seg of entry.block.segments) {
        const firstRemoved = base + seg.offset;
        if (seg.removed > 0) {
          const lastRemoved = firstRemoved + seg.removed - 1;
          decorations.push({
            range: new this.monaco.Range(firstRemoved, 1, lastRemoved, model.getLineMaxColumn(lastRemoved)),
            options: {
              isWholeLine: true,
              className: "ob-diff-removed",
              linesDecorationsClassName: "ob-diff-removed-gutter",
              marginClassName: "ob-diff-removed-margin",
              overviewRuler: { color: "rgba(239, 68, 68, 0.75)", position: 7 },
              description: "ob-inline-diff-removed",
            },
          });
          parts.push(`r${firstRemoved}-${lastRemoved}`);
        }
        if (seg.added.length > 0) {
          const afterLine = seg.removed > 0 ? firstRemoved + seg.removed - 1 : firstRemoved - 1;
          zones.push({ afterLine, lines: seg.added, key: `${entry.block.id}:${seg.offset}` });
          parts.push(`z${afterLine}:${entry.block.id}:${seg.offset}:${seg.added.length}`);
        }
      }
    }

    const layout = this.editor.getLayoutInfo();
    const signature = `${layout.contentWidth}|${parts.join(",")}`;
    if (signature !== this.signature) {
      this.signature = signature;
      this.lineDecorations = this.editor.deltaDecorations(this.lineDecorations, decorations);
      this.renderZones(zones, model);
    }
    this.renderActions(model);
  }

  private renderZones(zones: Array<{ afterLine: number; lines: string[]; key: string }>, model: any): void {
    const lineHeight = this.lineHeight();
    const wraps = this.wraps();
    const width = this.wrapWidth();
    const built: Array<{ node: HTMLElement; margin: HTMLElement; afterLine: number; height: number }> = [];

    for (const zone of zones) {
      const node = document.createElement("div");
      node.className = `ob-diff-zone${wraps ? " ob-diff-zone-wrap" : ""}`;
      this.editor.applyFontInfo?.(node);
      // Wrap where the editor wraps its own lines, not at the edge of the zone
      // (which runs on under the scrollbar).
      if (wraps) node.style.paddingRight = `calc(100% - ${width}px)`;
      for (const text of zone.lines) {
        const line = document.createElement("div");
        line.className = "ob-diff-added-line";
        line.style.minHeight = `${lineHeight}px`;
        line.textContent = text === "" ? "​" : text;
        node.appendChild(line);
        this.colorize(line, text, model);
      }
      const margin = document.createElement("div");
      margin.className = "ob-diff-added-margin";
      built.push({
        node,
        margin,
        afterLine: zone.afterLine,
        height: wraps ? this.measure(node, width, zone.lines.length * lineHeight) : zone.lines.length * lineHeight,
      });
    }

    this.zoneNodes = [];
    this.editor.changeViewZones((accessor: any) => {
      for (const id of this.zoneIds) accessor.removeZone(id);
      this.zoneIds = [];
      for (const z of built) {
        const id = accessor.addZone({
          afterLineNumber: Math.max(0, z.afterLine),
          heightInPx: z.height,
          domNode: z.node,
          marginDomNode: z.margin,
          suppressMouseDown: true,
        });
        this.zoneIds.push(id);
        this.zoneNodes.push({ node: z.node, id, height: z.height });
      }
    });
  }

  /** Height of a wrapped zone at the editor's content width. */
  private measure(node: HTMLElement, width: number, minimum: number): number {
    const host = this.editor.getDomNode();
    if (!host) return minimum;
    const probe = node.cloneNode(true) as HTMLElement;
    probe.style.cssText += `;position:absolute;visibility:hidden;left:-99999px;top:0;width:${width}px;height:auto;padding-right:0;`;
    host.appendChild(probe);
    const height = Math.ceil(probe.getBoundingClientRect().height);
    probe.remove();
    return Math.max(minimum, height);
  }

  private colorize(line: HTMLElement, text: string, model: any): void {
    if (!text.trim() || !this.monaco.editor?.colorize) return;
    const language = model.getLanguageId?.() || "plaintext";
    Promise.resolve(this.monaco.editor.colorize(text, language, { tabSize: model.getOptions?.().tabSize ?? 2 }))
      .then((html: string) => {
        if (this.disposed || !line.isConnected) return;
        // Monaco's own tokenizer output (escaped spans), minus the line break it appends.
        line.innerHTML = String(html).replace(/<br\s*\/?>\s*$/i, "");
      })
      .catch(() => {
        /* plain text is already shown */
      });
  }

  private lineHeight(): number {
    try {
      return this.editor.getOption(this.monaco.editor.EditorOption.lineHeight) || 19;
    } catch {
      return 19;
    }
  }

  /** The pixel width the editor wraps its own lines at. */
  private wrapWidth(): number {
    const layout = this.editor.getLayoutInfo();
    const fallback = Math.max(40, layout.contentWidth - (layout.verticalScrollbarWidth || 0) - 4);
    try {
      const { EditorOption } = this.monaco.editor;
      const column = this.editor.getOption(EditorOption.wrappingInfo)?.wrappingColumn;
      const char = this.editor.getOption(EditorOption.fontInfo)?.typicalHalfwidthCharacterWidth;
      return column > 0 && char > 0 ? Math.min(fallback, Math.floor(column * char)) : fallback;
    } catch {
      return fallback;
    }
  }

  private wraps(): boolean {
    try {
      const info = this.editor.getOption(this.monaco.editor.EditorOption.wrappingInfo);
      return !!info && info.wrappingColumn !== -1;
    } catch {
      return false;
    }
  }

  // -- accept / reject controls ---------------------------------------------

  private renderActions(model: any): void {
    for (const entry of this.entries) {
      if (entry.status !== "pending") {
        entry.actions?.remove();
        entry.actions = null;
        continue;
      }
      if (!entry.actions) entry.actions = this.buildActions(entry);
    }
    void model;
    this.positionActions();
  }

  private buildActions(entry: Entry): HTMLElement {
    const bar = document.createElement("div");
    bar.className = "ob-diff-actions";
    bar.dataset.block = entry.block.id;

    const button = (label: string, title: string, cls: string, run: () => void) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `ob-diff-btn ${cls}`;
      b.title = title;
      b.textContent = label;
      // Keep the caret where it is: the editor must not lose focus to a review click.
      b.addEventListener("mousedown", (e) => e.preventDefault());
      b.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        run();
      });
      return b;
    };

    if (!this.options.readOnly) {
      bar.appendChild(button("✓ Accept", "Accept this change", "ob-diff-btn-accept", () => this.accept(entry.block.id)));
    }
    bar.appendChild(button("✕ Reject", "Reject this change", "ob-diff-btn-reject", () => this.reject(entry.block.id)));
    this.overlay.appendChild(bar);
    return bar;
  }

  private positionActions(): void {
    if (this.disposed) return;
    const model = this.editor.getModel();
    if (!model) return;
    const layout = this.editor.getLayoutInfo();
    const scrollTop = this.editor.getScrollTop();
    const right = (layout.verticalScrollbarWidth || 0) + (layout.minimap?.minimapWidth || 0) + 10;
    const pending = this.pending();

    pending.forEach((entry, index) => {
      const bar = entry.actions;
      if (!bar) return;
      const where = this.locate(entry, model);
      if (!where) {
        bar.style.display = "none";
        return;
      }
      const first = entry.block.segments[0];
      const base = entry.block.oldLines.length === 0 ? where.anchorLine + 1 : where.first;
      let top: number;
      if (first && first.removed === 0) {
        // The change starts with added lines: sit on the top edge of their green block.
        const afterLine = base + first.offset - 1;
        top = afterLine <= 0 ? 0 : this.bottomOf(afterLine);
      } else {
        top = this.editor.getTopForLineNumber(base + (first ? first.offset : 0));
      }
      const y = top - scrollTop;
      const visible = y > -4 && y < layout.height - 22;
      bar.style.display = visible ? "flex" : "none";
      bar.style.top = `${Math.max(0, y)}px`;
      bar.style.right = `${right}px`;
      bar.classList.toggle("ob-diff-actions-current", index === Math.min(this.current, pending.length - 1));
    });
  }

  private bottomOf(line: number): number {
    if (typeof this.editor.getBottomForLineNumber === "function") {
      return this.editor.getBottomForLineNumber(line);
    }
    return this.editor.getTopForLineNumber(line) + this.lineHeight();
  }
}
