/**
 * lib/collab/monaco-binding.ts — Yjs <-> Monaco binding with remote cursors
 * =========================================================================
 * Why this is hand-written instead of `y-monaco`:
 *
 *   `y-monaco` peer-depends on the `monaco-editor` npm package and imports
 *   `Range`/`Selection` from it. OverBranch deliberately does not bundle
 *   monaco — `@monaco-editor/react` loads it from a CDN at runtime — so
 *   pulling it in would ship a second multi-megabyte copy of the editor just
 *   to construct range objects. This binding takes the live `monaco`
 *   namespace that `onMount` already hands us, and in exchange we get direct
 *   control over the remote-cursor decorations and name labels (requirements
 *   that `y-monaco` leaves to the caller anyway).
 *
 * Loop safety — the one thing that must not be got wrong:
 *
 *   local  : model.onDidChangeContent -> Y.Text ops, inside a transaction
 *            whose `origin` is this binding.
 *   remote : ytext.observe -> model.applyEdits, skipped when
 *            `event.transaction.origin === this`.
 *
 *   Filtering on the origin rather than on `transaction.local` matters: an undo
 *   from the Yjs UndoManager *is* a local transaction, and Monaco must be
 *   updated for it. `applyEdits` (not `pushEditOperations`) is used for remote
 *   text so a remote keystroke never lands on this user's native undo stack —
 *   local undo goes through the Yjs UndoManager instead, which is the only way
 *   Ctrl+Z can mean "undo *my* last edit" in a shared document.
 */

import * as Y from "yjs";
import type { Awareness } from "y-protocols/awareness";
import { colorForUser, type CollabColor } from "./colors";
import { collabLog } from "./log";

/* eslint-disable @typescript-eslint/no-explicit-any */

/** How often a moving cursor is published. 20px of mouse travel is not news. */
const CURSOR_THROTTLE_MS = 80;
/** A cursor that has not moved for this long is drawn dimmed, label hidden. */
const CURSOR_IDLE_MS = 12_000;
/** How often idle state is re-evaluated (only while remote peers exist). */
const IDLE_SWEEP_MS = 3_000;

export interface CollabUser {
  id: string;
  name: string;
  email?: string;
  image?: string | null;
}

export interface AwarenessSelection {
  anchor: unknown;
  head: unknown;
}

export interface AwarenessState {
  user?: CollabUser;
  filePath?: string;
  selection?: AwarenessSelection | null;
  lastActive?: number;
}

export interface RemotePeer {
  clientId: number;
  user: CollabUser;
  color: CollabColor;
  filePath?: string;
  /** True when the peer is editing the same file as us. */
  sameFile: boolean;
  lastActive: number;
  idle: boolean;
}

const STYLE_ELEMENT_ID = "ob-collab-remote-cursor-styles";

/** Escapes a display name for use inside a CSS `content: '...'` string. */
function cssContentEscape(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/[\r\n]+/g, " ")
    .slice(0, 48);
}

/**
 * One shared <style> element holds a rule per remote client. Cursor labels are
 * rendered with `::after` + `position: absolute` rather than Monaco injected
 * text, because injected text occupies layout and would shove the local user's
 * own characters sideways every time someone else's caret moved.
 */
class RemoteCursorStyles {
  private rules = new Map<number, string>();
  private element: HTMLStyleElement | null = null;

  private ensureElement(): HTMLStyleElement | null {
    if (typeof document === "undefined") return null;
    if (this.element && this.element.isConnected) return this.element;
    const existing = document.getElementById(STYLE_ELEMENT_ID) as HTMLStyleElement | null;
    if (existing) {
      this.element = existing;
      return existing;
    }
    const style = document.createElement("style");
    style.id = STYLE_ELEMENT_ID;
    document.head.appendChild(style);
    this.element = style;
    return style;
  }

  set(clientId: number, name: string, color: CollabColor): void {
    const rule = `
.ob-remote-selection-${clientId} { background-color: ${color.translucent}; }
.ob-remote-head-${clientId} {
  position: relative;
  border-left: 2px solid ${color.solid};
  box-sizing: border-box;
}
.ob-remote-head-${clientId}::after {
  content: '${cssContentEscape(name)}';
  position: absolute;
  left: -2px;
  top: -1.25em;
  padding: 0 4px;
  border-radius: 4px 4px 4px 0;
  background-color: ${color.solid};
  color: #fff;
  font-size: 10px;
  line-height: 1.25em;
  font-family: var(--font-space-mono), ui-monospace, monospace;
  white-space: nowrap;
  pointer-events: none;
  z-index: 30;
  opacity: 1;
  transition: opacity 180ms ease-out;
}
.ob-remote-head-${clientId}.ob-remote-idle::after { opacity: 0; }
.ob-remote-head-${clientId}.ob-remote-idle { opacity: 0.45; }
`.trim();
    if (this.rules.get(clientId) === rule) return;
    this.rules.set(clientId, rule);
    this.flush();
  }

  remove(clientId: number): void {
    if (this.rules.delete(clientId)) this.flush();
  }

  private flush(): void {
    const element = this.ensureElement();
    if (!element) return;
    element.textContent = Array.from(this.rules.values()).join("\n");
  }

  clear(): void {
    this.rules.clear();
    this.flush();
  }
}

const sharedStyles = new RemoteCursorStyles();

export interface MonacoYBindingOptions {
  monaco: any;
  model: any;
  ytext: Y.Text;
  awareness: Awareness;
  filePath: string;
  localUser: CollabUser;
  /** Read-only peers still see cursors but publish no selection of their own. */
  readOnly?: boolean;
  onPeersChange?: (peers: RemotePeer[]) => void;
  /** Fired after a remote change lands, so the host can mirror the text. */
  onRemoteChange?: (value: string) => void;
}

export class MonacoYBinding {
  private readonly monaco: any;
  private readonly model: any;
  private readonly ytext: Y.Text;
  private readonly awareness: Awareness;
  private readonly doc: Y.Doc;
  private readonly filePath: string;
  private readonly localUser: CollabUser;
  private readonly onPeersChange?: (peers: RemotePeer[]) => void;
  private readonly onRemoteChange?: (value: string) => void;

  private readOnly: boolean;
  private destroyed = false;
  private applyingRemote = false;

  private readonly editors = new Map<any, any>(); // editor -> decorations collection
  private readonly editorDisposables = new Map<any, any[]>();
  /**
   * Editors that currently hold the caret. A remote caret and its name label
   * are published only while this is non-empty: Monaco fires
   * `onDidChangeCursorSelection` whenever *remote* text shifts positions, so
   * without this a user who never clicked into the editor would broadcast a
   * caret at line 1 and appear to be sitting there in everyone else's window.
   */
  private readonly focusedEditors = new Set<any>();
  private modelDisposable: any = null;

  private cursorTimer: ReturnType<typeof setTimeout> | null = null;
  private pendingSelection: AwarenessSelection | null | undefined;
  private idleSweep: ReturnType<typeof setInterval> | null = null;
  private knownClients = new Set<number>();

  readonly undoManager: Y.UndoManager;

  constructor(options: MonacoYBindingOptions) {
    this.monaco = options.monaco;
    this.model = options.model;
    this.ytext = options.ytext;
    this.awareness = options.awareness;
    this.doc = options.ytext.doc as Y.Doc;
    this.filePath = options.filePath;
    this.localUser = options.localUser;
    this.readOnly = !!options.readOnly;
    this.onPeersChange = options.onPeersChange;
    this.onRemoteChange = options.onRemoteChange;

    // Track only this binding's own transactions so Ctrl+Z undoes *this user's*
    // edits and never reaches into a collaborator's work.
    this.undoManager = new Y.UndoManager(this.ytext, {
      trackedOrigins: new Set([this]),
      captureTimeout: 400,
    });

    // The model is the authority on initial content: whatever the synced Y.Text
    // holds wins, because the room seeded it from durable storage.
    this.resetModelToYText();

    this.modelDisposable = this.model.onDidChangeContent(this.handleModelChange);
    this.ytext.observe(this.handleYTextChange);
    this.awareness.on("change", this.handleAwarenessChange);

    collabLog("COLLAB_BIND", { filePath: this.filePath, chars: this.ytext.length });
  }

  /* ── Editors ───────────────────────────────────────────────────────────── */

  /**
   * Both of EditorLayout's Monaco instances (desktop + mobile) share one model,
   * so each needs its own decorations collection to show remote cursors.
   */
  addEditor(editor: any): void {
    if (this.destroyed || !editor || this.editors.has(editor)) return;
    this.editors.set(editor, editor.createDecorationsCollection([]));

    const disposables: any[] = [];
    disposables.push(
      editor.onDidChangeCursorSelection(() => this.queueSelectionPublish(editor)),
    );
    disposables.push(
      editor.onDidFocusEditorText(() => {
        this.focusedEditors.add(editor);
        this.queueSelectionPublish(editor);
      }),
    );
    disposables.push(
      editor.onDidBlurEditorText(() => {
        this.focusedEditors.delete(editor);
        // Both instances of the desktop/mobile pair must be unfocused before
        // the caret is withdrawn, otherwise switching between them would blink.
        if (this.focusedEditors.size === 0) this.clearPublishedSelection();
      }),
    );
    if (editor.hasTextFocus?.()) this.focusedEditors.add(editor);
    this.editorDisposables.set(editor, disposables);
    this.renderRemoteCursors();
  }

  removeEditor(editor: any): void {
    const collection = this.editors.get(editor);
    if (collection) {
      try {
        collection.clear();
      } catch {
        // The editor may already be disposed; nothing left to clear.
      }
    }
    this.editors.delete(editor);
    this.focusedEditors.delete(editor);
    (this.editorDisposables.get(editor) || []).forEach((d) => {
      try {
        d.dispose();
      } catch {
        /* already disposed */
      }
    });
    this.editorDisposables.delete(editor);
  }

  setReadOnly(readOnly: boolean): void {
    this.readOnly = readOnly;
  }

  /* ── Text synchronization ──────────────────────────────────────────────── */

  private resetModelToYText(): void {
    const target = this.ytext.toString();
    if (this.model.getValue() === target) return;
    this.applyingRemote = true;
    try {
      // A whole-model replace is correct exactly once: at bind time, before any
      // local edit exists to preserve.
      this.model.setValue(target);
    } finally {
      this.applyingRemote = false;
    }
  }

  private handleModelChange = (event: any): void => {
    if (this.destroyed || this.applyingRemote) return;
    if (this.readOnly) return;

    const changes = [...(event.changes || [])].sort(
      (a: any, b: any) => b.rangeOffset - a.rangeOffset,
    );
    if (changes.length === 0) return;

    this.doc.transact(() => {
      for (const change of changes) {
        if (change.rangeLength > 0) {
          this.ytext.delete(change.rangeOffset, change.rangeLength);
        }
        if (change.text && change.text.length > 0) {
          this.ytext.insert(change.rangeOffset, change.text);
        }
      }
    }, this);

    // Our own caret moved with the text; republish so peers follow along.
    // Still gated on focus inside: an AI accept edits the model while the
    // user may be in the chat panel, and that must not plant a caret.
    this.queueSelectionPublish(this.firstEditor());
  };

  private handleYTextChange = (event: Y.YTextEvent, transaction: Y.Transaction): void => {
    if (this.destroyed) return;
    if (transaction.origin === this) return; // echo of our own edit

    this.applyingRemote = true;
    try {
      let index = 0;
      for (const op of event.delta) {
        if (op.retain !== undefined) {
          index += op.retain;
        } else if (op.insert !== undefined) {
          const text = typeof op.insert === "string" ? op.insert : "";
          const position = this.model.getPositionAt(index);
          // Applied one op at a time: each edit shifts the offsets that the
          // remaining ops are expressed against.
          this.model.applyEdits([
            {
              range: new this.monaco.Range(
                position.lineNumber,
                position.column,
                position.lineNumber,
                position.column,
              ),
              text,
              forceMoveMarkers: true,
            },
          ]);
          index += text.length;
        } else if (op.delete !== undefined) {
          const start = this.model.getPositionAt(index);
          const end = this.model.getPositionAt(index + op.delete);
          this.model.applyEdits([
            {
              range: new this.monaco.Range(
                start.lineNumber,
                start.column,
                end.lineNumber,
                end.column,
              ),
              text: "",
              forceMoveMarkers: true,
            },
          ]);
        }
      }
    } catch (error) {
      collabLog("COLLAB_ERROR", { stage: "apply_remote_delta", error: String(error) });
      // Last resort: take the CRDT's word for it. The CRDT is the source of
      // truth, so a desynced model is worse than a lost cursor position.
      this.resetModelToYText();
    } finally {
      this.applyingRemote = false;
    }

    this.onRemoteChange?.(this.model.getValue());
    this.renderRemoteCursors();
  };

  /* ── Presence / cursors ────────────────────────────────────────────────── */

  private firstEditor(): any {
    for (const editor of this.editors.keys()) {
      // Prefer whichever instance is actually on screen: the hidden one of the
      // desktop/mobile pair reports a stale selection.
      try {
        if (editor.getDomNode?.()?.offsetParent) return editor;
      } catch {
        /* fall through */
      }
    }
    return this.editors.keys().next().value;
  }

  private queueSelectionPublish(editor: any): void {
    if (this.destroyed || !editor) return;
    // Nobody has the caret here: a position change is Monaco re-anchoring
    // around someone else's edit, not this user placing a cursor.
    if (this.focusedEditors.size === 0) return;
    let selection: any = null;
    try {
      selection = editor.getSelection();
    } catch {
      return;
    }
    if (!selection) return;

    const anchorOffset = this.model.getOffsetAt({
      lineNumber: selection.selectionStartLineNumber,
      column: selection.selectionStartColumn,
    });
    const headOffset = this.model.getOffsetAt({
      lineNumber: selection.positionLineNumber,
      column: selection.positionColumn,
    });

    this.pendingSelection = {
      anchor: Y.relativePositionToJSON(
        Y.createRelativePositionFromTypeIndex(this.ytext, anchorOffset),
      ),
      head: Y.relativePositionToJSON(
        Y.createRelativePositionFromTypeIndex(this.ytext, headOffset),
      ),
    };

    if (this.cursorTimer) return;
    this.cursorTimer = setTimeout(() => {
      this.cursorTimer = null;
      this.publishSelection();
    }, CURSOR_THROTTLE_MS);
  }

  /**
   * Withdraws this user's caret from everyone else's editor, leaving them
   * present in the collaborator list but not drawn in the text. Sent when the
   * editor loses focus — the user is in the chat panel, another file or
   * another window, and a caret parked where they last clicked would be a lie.
   */
  private clearPublishedSelection(): void {
    if (this.destroyed) return;
    if (this.cursorTimer) {
      clearTimeout(this.cursorTimer);
      this.cursorTimer = null;
    }
    this.pendingSelection = null;
    const state = this.awareness.getLocalState() || {};
    if ((state as AwarenessState).selection == null) return;
    this.awareness.setLocalState({ ...state, selection: null, lastActive: Date.now() });
  }

  /** Publishes presence. Called on a throttle, never per keystroke. */
  private publishSelection(): void {
    if (this.destroyed) return;
    const state: AwarenessState = {
      user: this.localUser,
      filePath: this.filePath,
      selection: this.pendingSelection ?? null,
      lastActive: Date.now(),
    };
    this.awareness.setLocalState({ ...this.awareness.getLocalState(), ...state });
  }

  /** Publishes the file we are on without waiting for a cursor move. */
  publishPresence(extra: Partial<AwarenessState> = {}): void {
    if (this.destroyed) return;
    this.awareness.setLocalState({
      ...this.awareness.getLocalState(),
      user: this.localUser,
      filePath: this.filePath,
      lastActive: Date.now(),
      ...extra,
    });
  }

  private handleAwarenessChange = (): void => {
    if (this.destroyed) return;
    this.renderRemoteCursors();
  };

  peers(): RemotePeer[] {
    const now = Date.now();
    const result: RemotePeer[] = [];
    this.awareness.getStates().forEach((raw, clientId) => {
      if (clientId === this.awareness.clientID) return;
      const state = raw as AwarenessState;
      const user = state?.user;
      if (!user?.id) return;
      const lastActive = typeof state.lastActive === "number" ? state.lastActive : 0;
      result.push({
        clientId,
        user,
        color: colorForUser(user.id),
        filePath: state.filePath,
        sameFile: state.filePath === this.filePath,
        lastActive,
        idle: now - lastActive > CURSOR_IDLE_MS,
      });
    });
    return result;
  }

  private renderRemoteCursors(): void {
    if (this.destroyed) return;
    const peers = this.peers();
    const seen = new Set<number>();
    const decorations: any[] = [];

    for (const peer of peers) {
      seen.add(peer.clientId);
      sharedStyles.set(peer.clientId, peer.user.name || "Collaborator", peer.color);
      if (!peer.sameFile) continue;

      const state = this.awareness.getStates().get(peer.clientId) as AwarenessState | undefined;
      const selection = state?.selection;
      if (!selection?.anchor || !selection?.head) continue;

      const anchor = Y.createAbsolutePositionFromRelativePosition(
        Y.createRelativePositionFromJSON(selection.anchor),
        this.doc,
      );
      const head = Y.createAbsolutePositionFromRelativePosition(
        Y.createRelativePositionFromJSON(selection.head),
        this.doc,
      );
      // A relative position resolves against the type it was created on; a
      // peer who has switched files produces a position in another Y.Text.
      if (!anchor || !head || anchor.type !== this.ytext || head.type !== this.ytext) continue;

      const idleClass = peer.idle ? " ob-remote-idle" : "";
      const anchorPosition = this.model.getPositionAt(anchor.index);
      const headPosition = this.model.getPositionAt(head.index);

      if (anchor.index !== head.index) {
        const start = anchor.index < head.index ? anchorPosition : headPosition;
        const end = anchor.index < head.index ? headPosition : anchorPosition;
        decorations.push({
          range: new this.monaco.Range(
            start.lineNumber,
            start.column,
            end.lineNumber,
            end.column,
          ),
          options: {
            className: `ob-remote-selection ob-remote-selection-${peer.clientId}`,
            stickiness: this.monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
          },
        });
      }

      // On line 1 the label has nothing above it and the viewport would clip
      // it, so it is flipped below the caret.
      const belowClass = headPosition.lineNumber === 1 ? " ob-remote-head-below" : "";
      decorations.push({
        range: new this.monaco.Range(
          headPosition.lineNumber,
          headPosition.column,
          headPosition.lineNumber,
          headPosition.column,
        ),
        options: {
          className: `ob-remote-head ob-remote-head-${peer.clientId}${idleClass}${belowClass}`,
          stickiness: this.monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
        },
      });
    }

    for (const clientId of this.knownClients) {
      if (!seen.has(clientId)) sharedStyles.remove(clientId);
    }
    this.knownClients = seen;

    this.editors.forEach((collection) => {
      try {
        collection.set(decorations);
      } catch {
        // Editor disposed between render and set; the next render recovers.
      }
    });

    this.onPeersChange?.(peers);
    this.ensureIdleSweep(peers.length > 0);
  }

  /**
   * Idle state is time-based, so it needs a tick — but only while someone else
   * is actually present. A solo editor runs no timer at all.
   */
  private ensureIdleSweep(needed: boolean): void {
    if (needed && !this.idleSweep) {
      this.idleSweep = setInterval(() => this.renderRemoteCursors(), IDLE_SWEEP_MS);
    } else if (!needed && this.idleSweep) {
      clearInterval(this.idleSweep);
      this.idleSweep = null;
    }
  }

  /* ── Teardown ──────────────────────────────────────────────────────────── */

  destroy(): void {
    if (this.destroyed) return;
    // Withdraw the caret before the destroyed flag short-circuits it: on a
    // file switch this binding's relative positions point into a Y.Text the
    // peers are no longer looking at.
    this.clearPublishedSelection();
    this.destroyed = true;

    if (this.cursorTimer) clearTimeout(this.cursorTimer);
    if (this.idleSweep) clearInterval(this.idleSweep);
    this.cursorTimer = null;
    this.idleSweep = null;

    try {
      this.ytext.unobserve(this.handleYTextChange);
    } catch {
      /* doc may already be destroyed */
    }
    this.awareness.off("change", this.handleAwarenessChange);
    try {
      this.modelDisposable?.dispose();
    } catch {
      /* model may already be disposed */
    }
    this.modelDisposable = null;

    Array.from(this.editors.keys()).forEach((editor) => this.removeEditor(editor));
    this.focusedEditors.clear();
    this.knownClients.forEach((clientId) => sharedStyles.remove(clientId));
    this.knownClients.clear();

    try {
      this.undoManager.destroy();
    } catch {
      /* already destroyed */
    }

    collabLog("COLLAB_UNBIND", { filePath: this.filePath });
  }
}

export function clearRemoteCursorStyles(): void {
  sharedStyles.clear();
}
