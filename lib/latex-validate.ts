/**
 * latex-validate.ts — client for POST /api/agent/validate-latex.
 *
 * Used after a *partial* apply. The authoritative whole-document path is already
 * validated on the backend, and a complete chunk replay reproduces that same
 * document byte-for-byte — but accepting only some edits can leave an orphaned
 * \end{...} that nothing else would catch.
 *
 * `heal` is off by default on purpose: auto-healing hoists \usepackage, injects
 * \usetikzlibrary and theme colours and rewrites \\[len] spacing, so it must
 * never be applied without showing the user `fixes_applied`.
 */

import { authFetch } from "@/lib/api-client";

const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

export interface LatexValidationResult {
  valid: boolean;
  errors: string[];
  fixes_applied: string[];
  healed_code: string | null;
  changed: boolean;
  file_path?: string;
  /** True when the check could not be performed (network/server failure). */
  unavailable?: boolean;
}

export async function healAndValidateLatex(
  code: string,
  projectId?: string,
  filePath?: string,
  heal = false,
): Promise<LatexValidationResult> {
  try {
    const res = await authFetch(`${BACKEND_URL}/api/agent/validate-latex`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latex_code: code,
        project_id: projectId,
        file_path: filePath || "main.tex",
        heal,
      }),
    });

    if (!res.ok) {
      return {
        valid: true,
        errors: [],
        fixes_applied: [],
        healed_code: null,
        changed: false,
        unavailable: true,
      };
    }

    return (await res.json()) as LatexValidationResult;
  } catch {
    // Fail open: refusing a user's edit because the backend hiccuped is worse
    // than one failed compile. The caller skips auto-compile and warns instead.
    return {
      valid: true,
      errors: [],
      fixes_applied: [],
      healed_code: null,
      changed: false,
      unavailable: true,
    };
  }
}

export interface ResolveEditsFailure {
  id: string | null;
  op: string;
  target: string | null;
  reason: string;
  attempts: { method: string; outcome: string }[];
}

export interface ResolveEditsResult {
  success: boolean;
  code: string;
  applied: { id: string; method: string; confidence?: number }[];
  failed: ResolveEditsFailure[];
  document_unchanged: boolean;
  /** True when the server could not be reached; nothing was resolved. */
  unavailable?: boolean;
}

/**
 * Asks the backend to place edits the exact-text pass could not, using the same
 * target locator as the agent (node → exact → normalised → fuzzy). All or
 * nothing: on any failure `code` is the unchanged input.
 */
export async function resolveEditsOnServer(
  currentCode: string,
  items: unknown[],
  originalCode?: string,
  projectId?: string,
  filePath?: string,
): Promise<ResolveEditsResult> {
  const unchanged = (unavailable: boolean): ResolveEditsResult => ({
    success: false,
    code: currentCode,
    applied: [],
    failed: [],
    document_unchanged: true,
    unavailable,
  });
  try {
    const res = await authFetch(`${BACKEND_URL}/api/agent/resolve-edits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_code: currentCode,
        items,
        original_code: originalCode,
        project_id: projectId,
        file_path: filePath || "main.tex",
      }),
    });
    if (!res.ok) return unchanged(true);
    return (await res.json()) as ResolveEditsResult;
  } catch {
    return unchanged(true);
  }
}
