/**
 * lib/pdf-view-state.ts — keeping the reader's place across a recompile.
 *
 * Compiling hands the viewer a new PDF, which opens a new document and remounts
 * the page renderer, so page, zoom and scroll all came back at their defaults:
 * a reader on page 9 was thrown to page 1 on every compile of the document they
 * were reading. The viewer therefore remembers where it was before the swap and
 * restores it after the new document has loaded.
 *
 * The clamp is the part worth testing on its own: an edit that shortens the
 * document can delete the page the reader was on, and the answer is the nearest
 * page that still exists — not page 1.
 */

export type PDFViewState = {
  /** 1-based page the reader was on. */
  page?: number;
  /** The zoom plugin's level: a number, or "automatic" / "fit-page" / "fit-width". */
  zoom?: number | string;
  /** Scroll offset within the page, in page coordinates. */
  scrollOffset?: { x: number; y: number };
};

/**
 * The view to restore in a document of `numPages` pages, or `null` when there
 * is nothing worth restoring (no saved state, or it points at page 1, which is
 * where a fresh document already is).
 */
export function clampRestore(
  saved: PDFViewState | null | undefined,
  numPages: number | null | undefined,
): PDFViewState | null {
  if (!saved) return null;
  const total = Number.isFinite(numPages) && (numPages as number) > 0 ? Math.floor(numPages as number) : 0;

  const rawPage = Number.isFinite(saved.page) ? Math.round(saved.page as number) : 1;
  // A document that shrank below the remembered page: go to its last page, the
  // nearest place that still exists.
  const page = total > 0 ? Math.min(Math.max(1, rawPage), total) : Math.max(1, rawPage);

  const zoom =
    typeof saved.zoom === "number"
      ? saved.zoom > 0
        ? saved.zoom
        : undefined
      : typeof saved.zoom === "string" && saved.zoom
        ? saved.zoom
        : undefined;

  // `undefined` means "no offset recorded"; `{0,0}` is a real place — the
  // viewport top sitting exactly on the page's top edge — and is kept. (Dropping
  // it used to send a reader whose viewport straddled two pages to the wrong
  // page edge.) Only a non-finite offset is discarded.
  const offset =
    saved.scrollOffset &&
    Number.isFinite(saved.scrollOffset.x) &&
    Number.isFinite(saved.scrollOffset.y)
      ? { x: saved.scrollOffset.x, y: saved.scrollOffset.y }
      : undefined;

  // Page 1 with the default zoom and no offset (or the zero offset, which is
  // the same place) is where the viewer already is.
  const offsetMatters = offset !== undefined && (page > 1 || offset.x !== 0 || offset.y !== 0);
  if (page <= 1 && zoom === undefined && !offsetMatters) return null;

  const out: PDFViewState = { page };
  if (zoom !== undefined) out.zoom = zoom;
  if (offset !== undefined && offsetMatters) out.scrollOffset = offset;
  return out;
}

/**
 * The subset of `@embedpdf/plugin-scroll`'s `PageVisibilityMetrics` that the
 * anchor needs — one entry per page intersecting the viewport. `viewportX/Y`
 * is where the visible part of the page starts inside the viewport (screen
 * px); `original.pageX/Y` is the same corner in the page's own coordinates;
 * `scaled.scale` converts between the two.
 */
export type PageVisibility = {
  pageNumber: number;
  viewportX: number;
  viewportY: number;
  original: { pageX: number; pageY: number; visibleWidth: number; visibleHeight: number };
  scaled: { visibleWidth: number; visibleHeight: number; scale: number };
};

/**
 * Where the reader is, read straight from the scroll plugin's visibility
 * metrics: the page with the greatest visible area, and the point of THAT page
 * sitting at the viewport's top-left corner (in page coordinates — what
 * `scrollToPage({ pageCoordinates })` takes back). Returns `null` when nothing
 * is visible: a hidden pane has a zero-sized viewport, and the scroll plugin
 * then reports page 1, which would overwrite the reader's real place.
 *
 * Why not the plugin's own `currentPage` plus `original.pageX/Y`: those
 * coordinates are the corner of the *intersection*, not of the viewport. When
 * the viewport straddles pages 3 and 4, the lower page's intersection starts at
 * its own top edge, so its offset is always `{0,0}` — the restore then landed on
 * the top of page 4 instead of where the reader was. Here the offset is the
 * viewport top relative to the chosen page, so it is exact for either page; for
 * a page whose top edge is below the viewport top it is negative, and that is
 * still the right place to scroll back to.
 *
 * `viewportGap` is the viewport's padding in screen px: the scroll plugin
 * measures pages without it but adds it back when scrolling to a page, so it is
 * taken out here — otherwise every recompile drifts the view down by one gap.
 */
export function anchorFromVisibility(
  metrics: readonly PageVisibility[] | null | undefined,
  options: { viewportGap?: number } = {},
): { page: number; scrollOffset: { x: number; y: number } } | null {
  if (!metrics || metrics.length === 0) return null;
  const gap = Number.isFinite(options.viewportGap) ? (options.viewportGap as number) : 0;

  let best: PageVisibility | null = null;
  let bestArea = 0;
  for (const m of metrics) {
    if (!m || !Number.isFinite(m.pageNumber) || m.pageNumber < 1) continue;
    const w = m.scaled?.visibleWidth;
    const h = m.scaled?.visibleHeight;
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) continue;
    const area = w * h;
    // Strictly greater: an exact tie keeps the earlier (upper) page.
    if (area > bestArea) {
      best = m;
      bestArea = area;
    }
  }
  if (!best) return null;

  const scale = best.scaled.scale;
  if (!Number.isFinite(scale) || scale <= 0) return null;
  const x = best.original.pageX - (best.viewportX + gap) / scale;
  const y = best.original.pageY - (best.viewportY + gap) / scale;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { page: Math.round(best.pageNumber), scrollOffset: { x, y } };
}

/* ────────────────────────────────────────────────────────────────────────────
 * Surviving a page reload, not just a recompile.
 *
 * The in-memory anchor dies with the tab, so reopening a project dropped the
 * reader on page 1 of a document they had read half of. The anchor is small and
 * per-project, so it lives in `localStorage` under one key per project — the
 * same thing Overleaf does with its PDF position.
 *
 * Storage is treated as a cache that may be absent, blocked (private windows,
 * blocked site data), or hand-edited: every path is wrapped, and anything that
 * does not parse into a usable anchor reads back as `null`.
 * ──────────────────────────────────────────────────────────────────────────── */

/** `localStorage` key holding the remembered view of one project's PDF. */
export function storedViewKey(projectId: string): string {
  return `ob:pdf-view:${projectId}`;
}

/** Older than this and the remembered place is not worth honouring. */
export const STORED_VIEW_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

type StoredView = PDFViewState & { savedAt?: number };

/**
 * The zoom plugin's mode names. A stored zoom has to be a positive number or
 * one of these; anything else came from a hand-edited entry or a future
 * version of this code, and the viewer's default is the safer answer.
 */
const ZOOM_MODES = new Set(["automatic", "fit-page", "fit-width"]);

/**
 * `localStorage`, or `null` where there is none (SSR) or reaching it throws
 * (a private window, blocked site data). Accessing the property itself can
 * throw, which is why even that is inside the `try`.
 */
function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/**
 * The remembered view for a project, or `null` when there is none, it cannot be
 * read, it does not parse, or it has gone stale. The page is NOT clamped here —
 * the page count of the document being opened is not known yet; `clampRestore`
 * does that once it is.
 */
export function readStoredView(
  projectId: string | null | undefined,
  now: number = Date.now(),
): PDFViewState | null {
  if (!projectId) return null;
  const store = storage();
  if (!store) return null;

  let raw: string | null = null;
  try {
    raw = store.getItem(storedViewKey(projectId));
  } catch {
    return null;
  }
  if (!raw) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const saved = parsed as StoredView;

  if (Number.isFinite(saved.savedAt) && now - (saved.savedAt as number) > STORED_VIEW_MAX_AGE_MS) {
    return null;
  }

  // Stricter than `clampRestore`, which is fed by the viewer itself and so
  // only has to cope with rounding. This is fed by whatever is in the
  // browser's storage, so a page that is not a page, or a zoom that is neither
  // a scale nor a mode the plugin knows, discards the whole entry rather than
  // moving the reader somewhere arbitrary.
  if (!Number.isFinite(saved.page) || (saved.page as number) < 1) return null;
  if (
    saved.zoom !== undefined &&
    saved.zoom !== null &&
    !(typeof saved.zoom === "number" && Number.isFinite(saved.zoom) && saved.zoom > 0) &&
    !(typeof saved.zoom === "string" && ZOOM_MODES.has(saved.zoom))
  ) {
    return null;
  }

  // Then the clamp, with no page count: it normalises the offset and answers
  // `null` for an entry that only says "page 1".
  return clampRestore({ page: saved.page, zoom: saved.zoom, scrollOffset: saved.scrollOffset }, 0);
}

/**
 * Remember where the reader is in a project's PDF. Callers should debounce this
 * — the viewer reports on every scroll frame. A failure is ignored: losing the
 * reader's place on the next reload is not worth an error in their face.
 */
export function writeStoredView(
  projectId: string | null | undefined,
  view: PDFViewState | null | undefined,
  now: number = Date.now(),
): void {
  if (!projectId) return;
  const store = storage();
  if (!store) return;

  const key = storedViewKey(projectId);
  // Nothing worth remembering (page 1, default zoom): drop the entry rather
  // than leave a stale one behind to restore to.
  const keep = clampRestore(view, 0);
  try {
    if (!keep) store.removeItem(key);
    else store.setItem(key, JSON.stringify({ ...keep, savedAt: now } satisfies StoredView));
  } catch {
    /* storage full or blocked: the in-memory anchor still covers recompiles */
  }
}
