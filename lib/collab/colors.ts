/**
 * lib/collab/colors.ts — Stable per-user collaboration colors
 * ===========================================================
 * A collaborator must get the same color in every session and in every other
 * collaborator's editor, so the color is derived from their user id rather
 * than handed out by the server or picked at random on connect.
 *
 * The palette is the accent family of the "Celestial Obsidian & Luminescent
 * Iris" design system, restricted to hues that stay legible as a 2px caret on
 * both the light (#F3F4F6) and dark (#0E0F12) editor backgrounds.
 */

export interface CollabColor {
  /** Caret, avatar ring and label background. */
  solid: string;
  /** Selection highlight — the same hue at low alpha so text stays readable. */
  translucent: string;
}

const PALETTE: CollabColor[] = [
  { solid: "#6366F1", translucent: "rgba(99, 102, 241, 0.22)" }, // iris
  { solid: "#10B981", translucent: "rgba(16, 185, 129, 0.22)" }, // emerald
  { solid: "#F59E0B", translucent: "rgba(245, 158, 11, 0.22)" }, // amber
  { solid: "#EC4899", translucent: "rgba(236, 72, 153, 0.22)" }, // pink
  { solid: "#06B6D4", translucent: "rgba(6, 182, 212, 0.22)" }, // cyan
  { solid: "#8B5CF6", translucent: "rgba(139, 92, 246, 0.22)" }, // violet
  { solid: "#F43F5E", translucent: "rgba(244, 63, 94, 0.22)" }, // rose
  { solid: "#84CC16", translucent: "rgba(132, 204, 22, 0.22)" }, // lime
];

/** FNV-1a: tiny, stable across runtimes, good enough for bucketing ids. */
function hashString(value: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

export function colorForUser(userId: string): CollabColor {
  if (!userId) return PALETTE[0];
  return PALETTE[hashString(userId) % PALETTE.length];
}

export function initialsForName(name: string | undefined | null): string {
  const clean = (name || "").trim();
  if (!clean) return "?";
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
