# 01/08 — Import dialog: mode picker, resume and errors

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: 01/05, 01/07 · Parallel with: 01/02 (`MobileEditorAssist.tsx`, `lib/clipboard.ts`, `monaco-binding.ts`), 01/03 (`EditorLayout.tsx`, `CompileToolbar.tsx`). **Do not edit `EditorLayout.tsx`** — slice 03 owns it; the dialog is already mounted there (~:4047) and needs no change.

## Decisions you need
M12 (polling, error codes, backoff), M13 (the `mode` field) — run `grep -E '^\| M1(2|3) ' 00-README.md`.
Read slice 05's `## Result` for the exact 404/403 body shape, and slice 07's `### For slice 08` note for the request field name and default.

## Read first
- `components/pdf-import/usePdfConversionJob.ts` — all 335 lines, especially `POLL_MS = 1500` (:14), `poll()` (:169), the GET at :173, **the 404 branch at :186 that sets `"This conversion job no longer exists."`**, the `setTimeout` loop at :190, and the calls `POST /api/convert/pdf` (:218), `/cancel` (:261), `/commit` (:283), `/preview/{page}` (:322), `/api/convert/pdf/config` (:138).
- `components/pdf-import/ImportPdfDialog.tsx` — job state at :59 and the stage/preview UI.
- `scripts/test_chat_input.mjs` — the frontend test pattern.

## Background
The reported failure — a 33-page PDF reporting "this conversion job is no longer exists" partway through — surfaces at `usePdfConversionJob.ts:186`, which stops polling on **any** 404. Slices 05 and 07 fixed the server side (durable job dir, resume, split 404/403). This slice stops the client from giving up.

## Scope (files you own)
- `components/pdf-import/usePdfConversionJob.ts`
- `components/pdf-import/ImportPdfDialog.tsx`
- `lib/pdf-import-poll.ts` (new)
- `scripts/test_pdf_import_poll.mjs` (new)
- `scripts/run-collab-tests.sh` — **append-only**: add `scripts/test_pdf_import_poll.mjs`.

## Tasks

1. **`lib/pdf-import-poll.ts` (new, pure and DOM-free).** Export:
   - `export const POLL_MS = 1500`, `export const POLL_MAX_MS = 10000`, `export const POLL_MAX_FAILURES = 20`
   - `export type PollOutcome = { kind: "ok"; job: any } | { kind: "gone"; message: string } | { kind: "forbidden"; message: string } | { kind: "transient"; message: string }`
   - `export function classifyPollResponse(status: number, body: any): PollOutcome` — `200` → `ok`; `404` with `detail.code === "job_unknown"` (or a bare 404) → `gone` with `"This import expired or was removed."`; `403` with `detail.code === "job_forbidden"` → `forbidden` with `"You no longer have access to this import."`; any `5xx` → `transient`; anything else → `transient`. Handle `detail` arriving as either a dict or a string.
   - `export function nextPollDelay(consecutiveFailures: number): number` — `POLL_MS` when there have been no failures, otherwise `Math.min(POLL_MS * 2 ** failures, POLL_MAX_MS)`.
   - `export function shouldGiveUp(consecutiveFailures: number): boolean` — `failures >= POLL_MAX_FAILURES`.

2. **Rewire `poll()` (M12).** Replace the 404 branch at :186 with `classifyPollResponse`:
   - `ok` → today's behaviour; reset the consecutive-failure counter to 0.
   - `gone` / `forbidden` → stop polling, set that message.
   - `transient` → **keep polling**, increment the counter, schedule the next poll at `nextPollDelay(n)`. Only when `shouldGiveUp(n)` is true, stop with `"Lost contact with the server. Your import may still be running — reopen this project to check."`
   A thrown `fetch` (offline, DNS) is a `transient`, not a stop. Make sure the existing `setTimeout` loop at :190 is cleared on unmount and cannot schedule two chains at once.

3. **Mode picker (M13).** In `ImportPdfDialog.tsx`, before the upload starts, offer two choices, defaulting to **Exact copy**:
   - **Exact copy** — "Reproduces the PDF as closely as possible."
   - **Editable template** — "Keeps the fonts, sizes, colours and margins, but as styles you can change. Best for a report template from a lecturer."
   Pass the chosen value as the `mode` field on `POST /api/convert/pdf` (:218), using the exact field name and default from slice 07's Result. Disable the picker once a job is running.

4. **Template rules in the preview (M14).** When the job's `report.template_rules` exists and `is_template` is true, show a short "Template rules detected" panel in the preview stage listing the stated rules (font, size, spacing, margins) and the `evidence` strings. Absent or false → render nothing. Treat every field as optional; this data comes from an LLM and may be partial.

5. **Resume feedback (M11).** When a polled job's `message` is the resume message slice 05 sets, show it in the dialog's stage line rather than leaving the old stage text, so an interrupted 33-page import visibly recovers instead of looking stuck.

6. **`scripts/test_pdf_import_poll.mjs`.** Import from `../lib/pdf-import-poll.ts` and assert:
   - `classifyPollResponse(200, {...})` → `ok`;
   - `404` with `detail: {code: "job_unknown"}` → `gone`, and a bare `404` with a string detail also → `gone`;
   - `403` with `detail: {code: "job_forbidden"}` → `forbidden`;
   - `500` and `502` → `transient`, **not** `gone` — this is the regression guard for the reported bug;
   - `nextPollDelay(0) === 1500`, `nextPollDelay(3) === 10000` (capped), and the delay never exceeds `POLL_MAX_MS`;
   - `shouldGiveUp(19) === false` and `shouldGiveUp(20) === true`.

## Done when
- `tools/verify-slice.sh scripts/test_pdf_import_poll.mjs` passes.
- `npx tsc --noEmit` is clean for your files.
- `bash scripts/run-collab-tests.sh` passes with your appended entry.
- `grep -n "no longer exists" components/pdf-import/usePdfConversionJob.ts` returns nothing.
- Root typecheck passes. Append `## Result`.

## Result

- `lib/pdf-import-poll.ts` (new) — `POLL_MS/POLL_MAX_MS/POLL_MAX_FAILURES`, `classifyPollResponse` (reads `detail.code`, tolerates string/absent detail), `nextPollDelay`, `shouldGiveUp`, message constants and `isResumeMessage`.
- `components/pdf-import/usePdfConversionJob.ts` — `poll()` now uses the classifier: 5xx, non-JSON bodies and thrown fetches keep polling with backoff and give up only after 20 consecutive failures; `gone`/`forbidden` stop. A generation counter (bumped by `stopPolling`, also on unmount) stops an in-flight poll from starting a second timer chain. `start()` sends `mode` ("exact" default / "template"). Added `ConversionMode`, `TemplateRules` types and optional `template_rules`/`style_profile` on `ConversionReport`.
- `components/pdf-import/ImportPdfDialog.tsx` — Exact copy / Editable template picker (default exact, disabled while starting/running, passed as `mode`), "Template rules detected" panel in the report (renders nothing unless `is_template === true`; every field optional), stage line turns amber when `job.message` is the resume message.
- `scripts/test_pdf_import_poll.mjs` (new) and `scripts/run-collab-tests.sh` (appended entry) — both gitignored here, as expected.

Gate (`tools/verify-slice.sh scripts/test_pdf_import_poll.mjs`):
```
PASS  typecheck
PASS  scripts/test_pdf_import_poll.mjs
```
`bash scripts/run-collab-tests.sh` ends "Client-side checks complete."; `grep -n "no longer exists" components/pdf-import/` returns nothing.

Skipped: no UI for "reconnecting" during transient failures (the brief did not ask); no backend or `EditorLayout.tsx` changes. A 403 without `detail.code === "job_forbidden"` is treated as transient (keeps polling), per the brief's "anything else".
