/**
 * latex-edit-apply.ts — the client half of the apply contract.
 *
 * The contract itself is defined and enforced in
 * `backend/opencode/diff_generator.py` (see its module docstring,
 * `apply_contract_version: 2`). In short, for every edit item the backend
 * guarantees a non-empty, unique, structurally-closed, non-overlapping,
 * line-addressed anchor. `backend/tests/test_diff_generator_anchors.py` holds a
 * Python mirror of this file that asserts a full replay reproduces
 * `proposed_code` byte-for-byte; keep the two in step.
 *
 * When this exact/positional pass skips anything, the editor sends the live
 * document and the items to `/api/agent/resolve-edits` (lib/latex-validate.ts),
 * which re-locates them by structural node, normalised text and similarity and
 * applies all of them or none.
 *
 * Two rules matter above all:
 *   1. `proposed_code` is authoritative. Prefer writing it verbatim, but only
 *      when the live document still matches `original_code` — the editor is not
 *      locked while the agent streams, so a blind overwrite would silently
 *      destroy keystrokes typed mid-run.
 *   2. Never drop an edit silently. Every input item ends up in `applied` or
 *      `skipped`; the caller is responsible for surfacing the skips.
 *
 * This module is deliberately pure: no React, no Monaco, no toasts, so it can be
 * unit-tested in isolation.
 */

export type SkipReason =
  | "no-anchor"
  | "not-found"
  | "not-unique"
  | "stale-position"
  | "overlap"
  | "document-changed";

export interface AppliedEditItem {
  id?: string;
  original_chunk: string;
  proposed_chunk: string;
  explanation?: string;
  // Apply-contract v2 fields (absent on older payloads).
  orig_start_line?: number;
  orig_end_line?: number;
  new_start_line?: number;
  new_end_line?: number;
  context_before?: number;
  context_after?: number;
  op?: string;
  anchor_unique?: boolean;
  is_full_document?: boolean;
  // Apply-contract v3: the structural node enclosing the edit in the original,
  // used by the server-side fallback (/api/agent/resolve-edits) to re-locate an
  // edit whose anchor text no longer occurs verbatim.
  node_id?: string;
  node_path?: string[];
}

export interface SkippedEdit {
  item: AppliedEditItem;
  reason: SkipReason;
}

export interface ApplyOutcome {
  code: string;
  strategy: "authoritative" | "chunks";
  applied: AppliedEditItem[];
  skipped: SkippedEdit[];
}

export interface ApplyOptions {
  /** The document text the backend diffed against (`original_code`). */
  originalText?: string;
  /** The backend's full validated buffer (`proposed_code`). */
  authoritativeText?: string;
}

export const normalizeNewlines = (s: string): string => s.replace(/\r\n/g, "\n");

/** What the user sees when an accepted change cannot be placed safely. */
export const SAFE_APPLY_FAILURE = "Couldn't safely apply this change. The document was not modified.";

export const SKIP_REASON_LABELS: Record<SkipReason, string> = {
  "no-anchor": "no anchor in the document",
  "not-found": "target text not found",
  "not-unique": "target text is not unique",
  "stale-position": "the document moved under the edit",
  overlap: "overlaps another edit",
  "document-changed": "the document was modified",
};

/** Human-readable summary of what was skipped, for a single toast. */
export function describeSkipped(skipped: SkippedEdit[]): string {
  const counts = new Map<SkipReason, number>();
  for (const s of skipped) counts.set(s.reason, (counts.get(s.reason) ?? 0) + 1);
  return Array.from(counts.entries())
    .map(([reason, n]) => `${n} ${SKIP_REASON_LABELS[reason]}`)
    .join(", ");
}

interface Resolved {
  start: number;
  end: number;
  item: AppliedEditItem;
}

/** Offset of the start of 1-based `line` in `text`, or -1 if out of range. */
function offsetOfLine(text: string, line: number): number {
  if (line < 1) return -1;
  let offset = 0;
  for (let i = 1; i < line; i++) {
    const nl = text.indexOf("\n", offset);
    if (nl === -1) return -1;
    offset = nl + 1;
  }
  return offset <= text.length ? offset : -1;
}

/**
 * Resolves an item to a character range, preferring a unique substring match and
 * falling back to its line range when the document is provably unchanged.
 */
function resolveItem(
  currentText: string,
  item: AppliedEditItem,
  documentUnchanged: boolean,
): { start: number; end: number } | SkipReason {
  const anchor = normalizeNewlines(item.proposed_chunk === undefined ? "" : item.original_chunk ?? "");

  if (anchor) {
    const first = currentText.indexOf(anchor);
    if (first !== -1) {
      if (currentText.indexOf(anchor, first + 1) === -1) {
        return { start: first, end: first + anchor.length };
      }
      // Ambiguous by text. Line numbers can still disambiguate it, but only if
      // nothing else has moved.
      if (documentUnchanged && item.orig_start_line && item.orig_end_line !== undefined) {
        const positional = resolvePositional(currentText, item, anchor);
        if (positional) return positional;
      }
      return "not-unique";
    }
    if (documentUnchanged && item.orig_start_line && item.orig_end_line !== undefined) {
      const positional = resolvePositional(currentText, item, anchor);
      if (positional) return positional;
    }
    return "not-found";
  }

  // Empty anchor: only legitimate for a whole-document write.
  if (item.is_full_document) return { start: 0, end: currentText.length };
  return "no-anchor";
}

/** Line-range resolution, validated against the anchor text so it cannot drift. */
function resolvePositional(
  currentText: string,
  item: AppliedEditItem,
  anchor: string,
): { start: number; end: number } | null {
  const startLine = item.orig_start_line!;
  const endLine = item.orig_end_line!;
  const start = offsetOfLine(currentText, startLine);
  if (start === -1) return null;
  // orig_end_line is inclusive; the range ends where the line after it begins.
  let end = offsetOfLine(currentText, endLine + 1);
  if (end === -1) end = currentText.length;

  const slice = currentText.slice(start, end);
  // The backend strips at most one trailing newline from the anchor.
  if (slice === anchor || slice === `${anchor}\n`) {
    return { start, end: start + anchor.length };
  }
  return null;
}

/**
 * Applies edit items to `currentText`.
 *
 * Returns the resulting code plus a full account of what was applied and what
 * was skipped. Resolution happens up front, overlaps are rejected, and splices
 * run in descending order so earlier offsets stay valid.
 */
export function applyEditItems(
  currentText: string,
  items: AppliedEditItem[],
  opts: ApplyOptions = {},
): ApplyOutcome {
  const current = normalizeNewlines(currentText);
  const original =
    opts.originalText !== undefined ? normalizeNewlines(opts.originalText) : undefined;
  const authoritative =
    opts.authoritativeText !== undefined
      ? normalizeNewlines(opts.authoritativeText)
      : undefined;

  // Fast path: the backend's own validated buffer, used only when the live
  // document is still exactly what the backend diffed against.
  if (authoritative !== undefined && original !== undefined && current === original) {
    return {
      code: authoritative,
      strategy: "authoritative",
      applied: [...items],
      skipped: [],
    };
  }

  // A single whole-document item is equivalent to the authoritative path — and
  // so is held to rule 1: only when the live document is still the one the
  // backend diffed. Writing it unconditionally replaced text typed during the
  // run, or (after switching files) wrote main.tex's proposal into another file.
  if (items.length === 1 && items[0]?.is_full_document) {
    const base =
      original ??
      (items[0].original_chunk !== undefined ? normalizeNewlines(items[0].original_chunk) : undefined);
    if (base !== undefined && (current === base || current.trim() === base.trim())) {
      return {
        code: normalizeNewlines(items[0].proposed_chunk ?? current),
        strategy: "authoritative",
        applied: [items[0]],
        skipped: [],
      };
    }
    return {
      code: current,
      strategy: "chunks",
      applied: [],
      skipped: [{ item: items[0], reason: "document-changed" }],
    };
  }

  const documentUnchanged = original !== undefined && current === original;

  const resolved: Resolved[] = [];
  const skipped: SkippedEdit[] = [];

  for (const item of items) {
    const outcome = resolveItem(current, item, documentUnchanged);
    if (typeof outcome === "string") {
      skipped.push({ item, reason: outcome });
    } else {
      resolved.push({ start: outcome.start, end: outcome.end, item });
    }
  }

  // Descending by start offset, so splicing never invalidates an earlier range.
  resolved.sort((a, b) => b.start - a.start);

  const accepted: Resolved[] = [];
  for (const r of resolved) {
    const clashes = accepted.some((a) => !(r.end <= a.start || r.start >= a.end));
    if (clashes) {
      skipped.push({ item: r.item, reason: "overlap" });
      continue;
    }
    accepted.push(r);
  }

  let code = current;
  for (const r of accepted) {
    code =
      code.slice(0, r.start) +
      normalizeNewlines(r.item.proposed_chunk ?? "") +
      code.slice(r.end);
  }

  return {
    code,
    strategy: "chunks",
    applied: accepted.map((r) => r.item),
    skipped,
  };
}
