/**
 * Ranking for the @file mention popover. Pure and DOM-free so
 * scripts/test_mention_match.mjs can run it under plain node.
 *
 * Each file is scored on its basename (weighted 1.5x) and on its full path;
 * the better of the two wins. A hit scores `100 - index` (a prefix beats a
 * substring that starts later), a miss scores 0 and is dropped.
 */

export interface MentionCandidate {
  path: string;
}

export interface ScoredMatch {
  path: string;
  score: number;
}

export const DEFAULT_MENTION_LIMIT = 8;

function hitScore(haystack: string, needle: string): number {
  const at = haystack.indexOf(needle);
  return at < 0 ? 0 : Math.max(100 - at, 1);
}

function baseName(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

export function scoreMatches(
  files: ReadonlyArray<MentionCandidate>,
  query: string,
  limit = DEFAULT_MENTION_LIMIT,
): ScoredMatch[] {
  const q = query.trim().toLowerCase();
  const scored: Array<ScoredMatch & { base: string }> = [];

  for (const file of files) {
    const path = file.path;
    const lowerPath = path.toLowerCase();
    const base = baseName(lowerPath);
    // An empty query matches everything at the same score: the list then falls
    // back to "shorter name, then alphabetical".
    const score = q
      ? Math.max(hitScore(base, q) * 1.5, hitScore(lowerPath, q))
      : 100;
    if (score > 0) scored.push({ path, score, base });
  }

  scored.sort(
    (a, b) =>
      b.score - a.score ||
      a.base.length - b.base.length ||
      (a.path < b.path ? -1 : a.path > b.path ? 1 : 0),
  );

  return scored.slice(0, Math.max(0, limit)).map(({ path, score }) => ({ path, score }));
}
