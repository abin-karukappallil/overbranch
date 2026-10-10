/**
 * lib/collab/text-diff.ts — Minimal line edits between two document versions
 * ==========================================================================
 * The AI apply paths used to hand Monaco a single edit spanning
 * `getFullModelRange()`. That is a correct way to set text in a single-user
 * editor, but under a CRDT it reads as "delete the whole document, then insert
 * a new one": every collaborator's concurrent keystroke in that span is
 * discarded, and every remote cursor collapses to the top of the file. In
 * other words, a whole-document replace *is* last-write-wins, which is exactly
 * what collaborative editing must not do.
 *
 * So AI output is converted into the smallest set of line ranges that differ.
 * Untouched regions are never rewritten, so concurrent edits elsewhere survive
 * and cursors stay where they were. This also helps the single-user case: the
 * undo stack gets one entry per real change instead of one giant one.
 *
 * Algorithm: trim the common prefix/suffix of lines (which removes almost
 * everything for a typical surgical edit), then run an LCS over what is left.
 * The LCS is skipped above `MAX_LCS_LINES` on either side, where the changed
 * region is large enough that one replace is both correct and cheaper.
 */

export interface LineEdit {
  /** 1-based inclusive start line in the original. */
  startLine: number;
  /** 1-based exclusive end line in the original (startLine === endLine = insert). */
  endLine: number;
  /** Replacement lines (may be empty for a pure deletion). */
  lines: string[];
}

const MAX_LCS_LINES = 1500;

/** Splits keeping no trailing empty artifacts beyond what the text implies. */
function splitLines(text: string): string[] {
  return text.split("\n");
}

function lcsEdits(
  original: string[],
  updated: string[],
  offset: number,
): LineEdit[] {
  const n = original.length;
  const m = updated.length;

  // One coarse replace when the changed window is too large to diff cheaply.
  if (n > MAX_LCS_LINES || m > MAX_LCS_LINES) {
    return [{ startLine: offset + 1, endLine: offset + n + 1, lines: updated }];
  }

  // table[i][j] = LCS length of original[i:] and updated[j:]
  const table: Uint32Array[] = Array.from(
    { length: n + 1 },
    () => new Uint32Array(m + 1),
  );
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i][j] =
        original[i] === updated[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const edits: LineEdit[] = [];
  let i = 0;
  let j = 0;
  let pendingStart = -1;
  let pendingLines: string[] = [];

  const flush = (endIndex: number) => {
    if (pendingStart < 0) return;
    edits.push({
      startLine: offset + pendingStart + 1,
      endLine: offset + endIndex + 1,
      lines: pendingLines,
    });
    pendingStart = -1;
    pendingLines = [];
  };

  while (i < n && j < m) {
    if (original[i] === updated[j]) {
      flush(i);
      i += 1;
      j += 1;
      continue;
    }
    if (pendingStart < 0) pendingStart = i;
    if (table[i + 1][j] >= table[i][j + 1]) {
      i += 1; // original line deleted
    } else {
      pendingLines.push(updated[j]); // updated line inserted
      j += 1;
    }
  }

  if (i < n || j < m) {
    if (pendingStart < 0) pendingStart = i;
    while (j < m) {
      pendingLines.push(updated[j]);
      j += 1;
    }
    i = n;
  }
  flush(i);

  return edits;
}

/**
 * Returns the minimal line-range edits that turn `original` into `updated`.
 * An empty array means the two are identical.
 */
export function computeLineEdits(original: string, updated: string): LineEdit[] {
  if (original === updated) return [];

  const originalLines = splitLines(original);
  const updatedLines = splitLines(updated);

  let prefix = 0;
  const maxPrefix = Math.min(originalLines.length, updatedLines.length);
  while (prefix < maxPrefix && originalLines[prefix] === updatedLines[prefix]) {
    prefix += 1;
  }

  let suffix = 0;
  while (
    suffix < maxPrefix - prefix &&
    originalLines[originalLines.length - 1 - suffix] ===
      updatedLines[updatedLines.length - 1 - suffix]
  ) {
    suffix += 1;
  }

  const originalMiddle = originalLines.slice(prefix, originalLines.length - suffix);
  const updatedMiddle = updatedLines.slice(prefix, updatedLines.length - suffix);

  return lcsEdits(originalMiddle, updatedMiddle, prefix);
}

/* eslint-disable @typescript-eslint/no-explicit-any */

/**
 * Applies `updated` to a Monaco editor as surgical range edits.
 *
 * Returns the number of edit operations applied. The edits go through
 * `executeEdits` (one undo stop around the whole set, so the user sees a
 * single undoable action) which is also what the Yjs binding observes — so an
 * AI edit enters the collaborative document the same way a keystroke does, and
 * reaches every other user through the same CRDT updates.
 */
export function applyTextToEditor(
  editor: any,
  monaco: any,
  updated: string,
  source = "ob-apply-text",
): number {
  const model = editor?.getModel?.();
  if (!model || !monaco) return 0;

  const current = model.getValue();
  if (current === updated) return 0;

  const edits = computeLineEdits(current, updated);
  if (edits.length === 0) return 0;

  const lineCount = model.getLineCount();
  const operations = edits.map((edit) => {
    const startLine = Math.min(Math.max(edit.startLine, 1), lineCount + 1);
    const endLine = Math.min(Math.max(edit.endLine, startLine), lineCount + 1);

    // An edit that reaches past the last line has no line to anchor its end on,
    // so it is expressed as "to the end of the last line" plus a leading
    // newline, instead of a range Monaco would clamp silently.
    const atDocumentEnd = endLine > lineCount;
    const range = atDocumentEnd
      ? new monaco.Range(
          Math.max(startLine - 1, 1),
          startLine > 1 ? model.getLineMaxColumn(Math.max(startLine - 1, 1)) : 1,
          lineCount,
          model.getLineMaxColumn(lineCount),
        )
      : new monaco.Range(startLine, 1, endLine, 1);

    let text = edit.lines.length > 0 ? edit.lines.join("\n") : "";
    if (atDocumentEnd) {
      // The range starts at the end of the previous line, so the replacement
      // has to re-supply the newline it consumed. The test is `lines.length`,
      // not `text.length`: appending a single empty line (which is what
      // "add a trailing newline" looks like) joins to "" and must still
      // produce "\n".
      if (startLine > 1) text = edit.lines.length > 0 ? `\n${text}` : "";
    } else if (edit.lines.length > 0) {
      text = `${text}\n`;
    }

    return { range, text, forceMoveMarkers: true };
  });

  editor.pushUndoStop();
  editor.executeEdits(source, operations);
  editor.pushUndoStop();

  return operations.length;
}
