/**
 * lib/inline-diff.ts — an AI proposal as blocks that can be reviewed one by one.
 *
 * The editor shows a proposed change inline: the lines to be removed in red,
 * the lines to be added in green beneath them, and Accept / Reject for each
 * change. This module is the pure half of that — which blocks there are, where
 * they sit, and what accepting a subset produces. The Monaco half is
 * `lib/inline-diff-monaco.ts`.
 *
 * A block is the unit of accept/reject, and it is deliberately *not* a line.
 * The backend's `hunks` (diff_generator.compute_review_hunks, apply contract
 * v4) are structurally closed: a `\begin{itemize}` added on one line and its
 * `\end{itemize}` ten lines below are one block, because accepting the first
 * and rejecting the second leaves a document that does not compile. Inside a
 * block only the lines that really changed are coloured (`segments`), so a
 * block spanning a few unchanged lines does not paint them.
 *
 * Without `hunks` (an older backend, or a payload with no line references) the
 * whole proposal is a single block: all of it can still be reviewed and
 * accepted, but no part can be split off, since nothing here could prove the
 * split safe.
 */

import { computeLineEdits } from "./collab/text-diff";

/** A structurally closed change, as line references into the original / proposed text. */
export interface ReviewHunk {
  id: string;
  /** 1-based first replaced line of the original (the line inserted before, when orig_count is 0). */
  orig_start: number;
  orig_count: number;
  /** 1-based first line of the replacement in the proposal. */
  new_start: number;
  new_count: number;
}

/** A run of really-changed lines inside a block. */
export interface ReviewSegment {
  /** 0-based offset of the first removed line within the block's old lines. */
  offset: number;
  removed: number;
  added: string[];
}

export interface ReviewBlock {
  id: string;
  /** 1-based line of the ORIGINAL document where the block starts. */
  origStart: number;
  oldLines: string[];
  newLines: string[];
  segments: ReviewSegment[];
}

/** A block together with where it sits in the document as it is now. */
export interface PlacedBlock extends ReviewBlock {
  /** 1-based line in the live document, or null when the document changed under the block. */
  liveStart: number | null;
}

export const normalizeEol = (s: string): string => s.replace(/\r\n/g, "\n");

/** Lines as the editor numbers them. An empty document has no lines to replace. */
function linesOf(text: string): string[] {
  return text === "" ? [] : normalizeEol(text).split("\n");
}

function segmentsFor(oldLines: string[], newLines: string[]): ReviewSegment[] {
  if (oldLines.length === 0) {
    return newLines.length ? [{ offset: 0, removed: 0, added: newLines }] : [];
  }
  if (newLines.length === 0) {
    return [{ offset: 0, removed: oldLines.length, added: [] }];
  }
  return computeLineEdits(oldLines.join("\n"), newLines.join("\n")).map((e) => ({
    offset: e.startLine - 1,
    removed: e.endLine - e.startLine,
    added: e.lines,
  }));
}

function validHunks(hunks: ReviewHunk[] | undefined, nOrig: number, nNew: number): ReviewHunk[] | null {
  if (!Array.isArray(hunks) || hunks.length === 0) return null;
  let prevEnd = 1;
  for (const h of hunks) {
    const ok =
      Number.isInteger(h.orig_start) && Number.isInteger(h.orig_count) &&
      Number.isInteger(h.new_start) && Number.isInteger(h.new_count) &&
      h.orig_count >= 0 && h.new_count >= 0 &&
      h.orig_start >= prevEnd && h.orig_start + h.orig_count - 1 <= nOrig &&
      h.new_start >= 1 && h.new_start + h.new_count - 1 <= nNew;
    if (!ok) return null;
    prevEnd = h.orig_start + h.orig_count;
  }
  return hunks;
}

/**
 * The review blocks of a proposal, in document order.
 *
 * `hunks` is trusted only if applying all of them to `original` reproduces
 * `proposed` — otherwise it describes some other pair of texts, and the
 * proposal falls back to a single block.
 */
export function buildReviewBlocks(
  original: string,
  proposed: string,
  hunks?: ReviewHunk[],
): ReviewBlock[] {
  const orig = linesOf(original);
  const next = linesOf(proposed);
  if (orig.join("\n") === next.join("\n") && orig.length === next.length) return [];

  const usable = validHunks(hunks, orig.length, next.length);
  if (usable) {
    const blocks: ReviewBlock[] = usable.map((h) => {
      const oldLines = orig.slice(h.orig_start - 1, h.orig_start - 1 + h.orig_count);
      const newLines = next.slice(h.new_start - 1, h.new_start - 1 + h.new_count);
      return {
        id: h.id,
        origStart: h.orig_start,
        oldLines,
        newLines,
        segments: segmentsFor(oldLines, newLines),
      };
    });
    const replay = applyBlocks(original, blocks, new Set(blocks.map((b) => b.id)));
    if (replay === linesToText(next, proposed)) return blocks;
  }

  // One block covering the changed span: trim what the two versions share.
  let prefix = 0;
  const max = Math.min(orig.length, next.length);
  while (prefix < max && orig[prefix] === next[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < max - prefix &&
    orig[orig.length - 1 - suffix] === next[next.length - 1 - suffix]
  ) {
    suffix += 1;
  }
  const oldLines = orig.slice(prefix, orig.length - suffix);
  const newLines = next.slice(prefix, next.length - suffix);
  return [{
    id: "all",
    origStart: prefix + 1,
    oldLines,
    newLines,
    segments: segmentsFor(oldLines, newLines),
  }];
}

function linesToText(lines: string[], like: string): string {
  return like === "" && lines.length === 0 ? "" : lines.join("\n");
}

/** `original` with the blocks in `accepted` applied and the others left as they are. */
export function applyBlocks(original: string, blocks: ReviewBlock[], accepted: Set<string>): string {
  const orig = linesOf(original);
  const out: string[] = [];
  let pos = 0;
  for (const b of [...blocks].sort((x, y) => x.origStart - y.origStart)) {
    const start = b.origStart - 1;
    out.push(...orig.slice(pos, start));
    out.push(...(accepted.has(b.id) ? b.newLines : b.oldLines));
    pos = start + b.oldLines.length;
  }
  out.push(...orig.slice(pos));
  return out.join("\n");
}

/**
 * Where each block sits in `live`, the document as it is now.
 *
 * The editor is not locked while the agent works, so `live` may differ from
 * the `original` the blocks were computed against. A block whose own lines are
 * untouched has simply moved by however many lines were added or removed above
 * it; a block whose lines the user edited cannot be placed, and is reported
 * with `liveStart: null` rather than drawn over text it no longer matches.
 */
export function placeBlocks(original: string, live: string, blocks: ReviewBlock[]): PlacedBlock[] {
  const a = normalizeEol(original);
  const b = normalizeEol(live);
  if (a === b) return blocks.map((blk) => ({ ...blk, liveStart: blk.origStart }));

  const userEdits = a === "" ? [] : computeLineEdits(a, b);
  return blocks.map((blk) => {
    const start = blk.origStart;
    const end = blk.origStart + blk.oldLines.length; // exclusive
    let delta = 0;
    for (const e of userEdits) {
      const growth = e.lines.length - (e.endLine - e.startLine);
      if (e.endLine <= start) {
        delta += growth; // entirely above the block (an insertion at its first line included)
      } else if (e.startLine >= end && !(e.startLine === start && blk.oldLines.length === 0)) {
        // entirely below
      } else {
        return { ...blk, liveStart: null };
      }
    }
    return { ...blk, liveStart: start + delta };
  });
}

export interface ReviewStats {
  added: number;
  removed: number;
}

export function blockStats(blocks: ReviewBlock[]): ReviewStats {
  let added = 0;
  let removed = 0;
  for (const b of blocks) {
    for (const s of b.segments) {
      added += s.added.length;
      removed += s.removed;
    }
  }
  return { added, removed };
}
