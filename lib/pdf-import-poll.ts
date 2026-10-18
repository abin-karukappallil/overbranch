/**
 * Polling policy for the PDF import job (pure, no DOM).
 *
 * The job poll used to treat any non-200 as "the job is gone": a single 5xx while a worker
 * recycled killed a 33-page import in the UI even though the job was still running on the
 * server. Only a definite "unknown job" / "not yours" answer ends the poll; everything else,
 * including a thrown fetch, is transient and retried with backoff.
 */

export const POLL_MS = 1500;
export const POLL_MAX_MS = 10000;
export const POLL_MAX_FAILURES = 20;

export const GONE_MESSAGE = "This import expired or was removed.";
export const FORBIDDEN_MESSAGE = "You no longer have access to this import.";
export const LOST_CONTACT_MESSAGE =
  "Lost contact with the server. Your import may still be running — reopen this project to check.";

/** The message the backend sets on a job it has just relaunched after an interruption. */
export const RESUME_MESSAGE_PREFIX = "Resuming after an interruption";

export type PollOutcome =
  | { kind: "ok"; job: any }
  | { kind: "gone"; message: string }
  | { kind: "forbidden"; message: string }
  | { kind: "transient"; message: string };

/** FastAPI sends {"detail": {"code", "message"}} for the job errors; older routes send a string. */
function detailCode(body: any): string | null {
  const detail = body?.detail;
  if (detail && typeof detail === "object" && typeof detail.code === "string") return detail.code;
  return null;
}

export function classifyPollResponse(status: number, body: any): PollOutcome {
  if (status === 200) return { kind: "ok", job: body };
  const code = detailCode(body);
  if (status === 404) return { kind: "gone", message: GONE_MESSAGE };
  if (status === 403 && code === "job_forbidden") return { kind: "forbidden", message: FORBIDDEN_MESSAGE };
  if (status >= 500) return { kind: "transient", message: `Server error (${status}).` };
  return { kind: "transient", message: `Unexpected response (${status}).` };
}

export function nextPollDelay(consecutiveFailures: number): number {
  if (!(consecutiveFailures > 0)) return POLL_MS;
  return Math.min(POLL_MS * 2 ** consecutiveFailures, POLL_MAX_MS);
}

export function shouldGiveUp(consecutiveFailures: number): boolean {
  return consecutiveFailures >= POLL_MAX_FAILURES;
}

export function isResumeMessage(message: string | null | undefined): boolean {
  return typeof message === "string" && message.startsWith(RESUME_MESSAGE_PREFIX);
}
