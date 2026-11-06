/**
 * Two letters for an avatar, from a display name: first and last word, so "Alex Rivers" is "AR".
 * Parenthesised notes such as "(you)" and an email's domain are not part of the name.
 */
export function initialsOf(name: string | null | undefined): string {
  const clean = (name || "")
    .replace(/\([^)]*\)/g, " ")
    .replace(/@.*$/, "")
    .trim();
  const parts = clean.split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
