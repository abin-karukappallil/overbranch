/**
 * lib/pdf-sync.ts — choosing WHICH occurrence a PDF selection meant.
 *
 * Selecting text in the PDF used to be resolved by searching the source for
 * those words and taking `matches[0]`, so selecting "This is an example." on
 * page 9 jumped to the first copy of it in the abstract. Identical text appears
 * many times in a real document, and the words alone cannot say which copy the
 * reader pointed at.
 *
 * SyncTeX can: given a page and a point on it, it answers with the source line.
 * Verified against real `pdflatex -synctex=1`: the same sentence on lines 4, 10
 * and 16 resolves to 4, 10 and 16. It returns `Column:-1` though, so the line is
 * all it gives — within a line that holds the text twice, the horizontal
 * position of the selection breaks the tie.
 *
 * These are the pure decisions, kept out of the component so they can be tested
 * under node (the same arrangement as `lib/inline-diff.ts`).
 */

/** The part of a Monaco match this module needs. */
export type OccurrenceMatch = {
  range: {
    startLineNumber: number;
    startColumn: number;
    endLineNumber: number;
    endColumn: number;
  };
};

/**
 * The match the reader meant: the one nearest SyncTeX's line.
 *
 * With no hint this returns the first match, which is exactly what the old code
 * did — so a document compiled without SyncTeX artifacts, or a point SyncTeX has
 * no record for, degrades to the previous behaviour rather than to nothing.
 *
 * Ties go to the earlier match, so the choice is deterministic.
 */
export function pickOccurrence<T extends OccurrenceMatch>(
  matches: readonly T[] | null | undefined,
  hintLine?: number | null,
): T | null {
  if (!matches || matches.length === 0) return null;
  if (!hintLine || hintLine <= 0 || matches.length === 1) return matches[0];

  let best = matches[0];
  let bestDistance = Math.abs(best.range.startLineNumber - hintLine);
  for (let i = 1; i < matches.length; i += 1) {
    const d = Math.abs(matches[i].range.startLineNumber - hintLine);
    if (d < bestDistance) {
      best = matches[i];
      bestDistance = d;
    }
  }
  return best;
}

/**
 * Among the matches that sit on the hinted line, the one the selection's
 * horizontal position points at.
 *
 * `xFraction` is how far across the page the selection starts (0 = left edge,
 * 1 = right edge). A line typeset across the page puts its first occurrence
 * left of its second, so ordering the line's matches by column and indexing by
 * that fraction picks the right one. This only ever refines a choice already
 * made by line, so being approximate costs nothing: with one match on the line
 * it is a no-op.
 */
export function pickWithinLine<T extends OccurrenceMatch>(
  matches: readonly T[] | null | undefined,
  hintLine?: number | null,
  xFraction?: number | null,
): T | null {
  if (!matches || matches.length === 0) return null;
  if (!hintLine || hintLine <= 0) return pickOccurrence(matches, hintLine);

  const onLine = matches
    .filter((m) => m.range.startLineNumber === hintLine)
    .sort((a, b) => a.range.startColumn - b.range.startColumn);
  if (onLine.length === 0) return pickOccurrence(matches, hintLine);
  if (onLine.length === 1 || xFraction == null || !Number.isFinite(xFraction)) return onLine[0];

  const clamped = Math.min(0.999, Math.max(0, xFraction));
  return onLine[Math.min(onLine.length - 1, Math.floor(clamped * onLine.length))];
}

/**
 * The line of a per-line scan that the hint points at.
 *
 * The old substring scan `break`-ed at the first line containing the snippet,
 * which is the same first-occurrence bug one level down. Pass every candidate
 * line and this returns the nearest to the hint (the first, with no hint).
 */
export function pickLine(
  candidates: readonly number[] | null | undefined,
  hintLine?: number | null,
): number | null {
  if (!candidates || candidates.length === 0) return null;
  if (!hintLine || hintLine <= 0) return candidates[0];
  let best = candidates[0];
  for (const line of candidates.slice(1)) {
    if (Math.abs(line - hintLine) < Math.abs(best - hintLine)) best = line;
  }
  return best;
}
