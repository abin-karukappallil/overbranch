/**
 * Compile response handling: tell a busy server apart from broken LaTeX.
 *
 * `/api/compile` answers 429 `{detail, retry_after_seconds}` when its queue is
 * full. That means "try again", not "your document is wrong", so it must never
 * become an error log. Pure and DOM-free so it can be tested without a browser.
 */

/** Backoff between retries of a busy compile: 1s, 2s, 4s, then give up. */
export const COMPILE_RETRY_DELAYS_MS = [1000, 2000, 4000];

export type CompileOutcome =
  | { kind: "ok"; body: any }
  | { kind: "busy"; retryAfterSeconds: number | null }
  | { kind: "failed"; errorLog: string }
  | { kind: "network"; message: string };

export function classifyCompileResponse(status: number, body: any): CompileOutcome {
  if (status === 429) {
    const retry = body?.retry_after_seconds;
    return {
      kind: "busy",
      retryAfterSeconds: typeof retry === "number" && Number.isFinite(retry) ? retry : null,
    };
  }
  if (status === 200) {
    if (body?.success === true) return { kind: "ok", body };
    return { kind: "failed", errorLog: body?.error_log ?? "Compilation failed." };
  }
  return { kind: "failed", errorLog: body?.detail ?? "Compilation failed." };
}

/** Delay before retry number `attempt` (0-based), or null to give up. */
export function nextRetryDelay(attempt: number): number | null {
  return COMPILE_RETRY_DELAYS_MS[attempt] ?? null;
}
