# 01/03 — Compile UX: busy vs broken

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: 01/01 · Parallel with: 01/02 (owns `MobileEditorAssist.tsx`, `lib/clipboard.ts`, `lib/collab/monaco-binding.ts`), 01/05, 01/07 (backend). **You own `components/editor/EditorLayout.tsx` from now on.**

## Decisions you need
M8 (429 handling and backoff) — run `grep -E '^\| M8 ' 00-README.md`.
M7 names one deletion inside `EditorLayout.tsx` that belongs to you — run `grep -E '^\| M7 ' 00-README.md`, and read the `### For slice 03` note in `02-touch-callout.md`'s `## Result` if slice 02 has finished; if it has not, follow M7 directly.

## Read first
- `components/editor/EditorLayout.tsx` — `handleCompile` at :1908 (the `authFetch` to `/api/compile` at :1914, the failure branch at :1925-1930), `setErrorLog` state at :341, `isCompiling` at :317, the touch paste listener at :1777-1815, the dead `handleCustomCopy`/`handleCustomPaste` at :1287-1330, and the Ctrl+S binding at :1817 which calls save-then-compile.
- `components/editor/CompileToolbar.tsx` — `CompileSplitButton` at :44 and `CompileToolbar` at :110; the `isCompiling` prop is what drives the button's spinner.
- `backend/main.py:153-197` — `compile_endpoint`, to confirm the 429 body shape `{detail, retry_after_seconds}`; and `backend/compile_queue.py` for `CompileQueueFullError`. **Read only; slice 06 owns both.**

## Scope (files you own)
- `components/editor/EditorLayout.tsx`
- `components/editor/CompileToolbar.tsx`
- `scripts/test_compile_retry.mjs` (new)
- `lib/compile-retry.ts` (new)
- `scripts/run-collab-tests.sh` — **append-only**: add `scripts/test_compile_retry.mjs`.

## Tasks

1. **`lib/compile-retry.ts` (new, pure and DOM-free so it is testable).** Export:
   - `export const COMPILE_RETRY_DELAYS_MS = [1000, 2000, 4000]` — M8's 1s/2s/4s.
   - `export type CompileOutcome = { kind: "ok"; body: any } | { kind: "busy"; retryAfterSeconds: number | null } | { kind: "failed"; errorLog: string } | { kind: "network"; message: string }`
   - `export function classifyCompileResponse(status: number, body: any): CompileOutcome` — `429` → `busy` (reading `retry_after_seconds` when present, else `null`); a `200` with `body.success === true` → `ok`; a `200` with `success === false` → `failed` with `body.error_log ?? "Compilation failed."`; any other status → `failed` with `body?.detail ?? "Compilation failed."`.
     **A 429 must never produce `failed`** — that is the bug: today any non-success body becomes `"Compilation failed."`, so a busy server looks like broken LaTeX.
   - `export function nextRetryDelay(attempt: number): number | null` — `COMPILE_RETRY_DELAYS_MS[attempt] ?? null`, so attempt 3 returns `null` meaning "give up".

2. **Rewire `handleCompile`.** Keep its current signature and all of its existing save/sync behaviour. Replace the failure branch at :1925-1930 with a loop over `classifyCompileResponse`:
   - `ok` → today's success path, unchanged.
   - `busy` → do **not** call `setErrorLog`. Show a single `toast.loading("Server busy — retrying…")` (keep its id so repeated retries update one toast rather than stacking), wait `nextRetryDelay(attempt)` ms, and retry the same request. After the third retry returns `busy`, dismiss the loading toast and `toast.error("Server is busy. Try again in a moment.")`, still without touching `errorLog`.
   - `failed` → `setErrorLog(outcome.errorLog)` and today's `toast.error`.
   - `network` → today's `"Network error or Python backend is not running."` message and toast, unchanged.
   `isCompiling` must stay `true` for the whole retry sequence, so the button keeps spinning and a second click cannot start a parallel compile. Ensure every exit path clears it in a `finally`.

3. **Dead code and the paste interceptor (M7).** Delete `handleCustomCopy` and `handleCustomPaste` (:1287-1330) — the survey confirmed they are wired to nothing. Remove the touch-only native `paste` listener at :1777-1815: it calls `preventDefault()`, `executeEdits("safe-mobile-paste", …)` and then `handleCodeChange(activeEd.getValue())`, which bypasses the Yjs binding and desyncs the room. Removing it lets Monaco's own paste run, which the binding observes. Leave the rest of `handleEditorMount` alone — slice 01 added a keybinding and a content widget there.

4. **`CompileToolbar.tsx`.** Add an optional `busy?: boolean` prop to `CompileSplitButton` and render a distinct hint (tooltip text or a subdued label) when the compile is in its retry backoff rather than actually compiling, so the user can tell "queued behind other work" from "compiling". Keep the existing props and both export signatures working — `CompileToolbar` is also used by `LatexEditorView.tsx`, which you do not own.

5. **`scripts/test_compile_retry.mjs`.** Import from `../lib/compile-retry.ts` and assert:
   - `classifyCompileResponse(429, { detail: "busy", retry_after_seconds: 3 })` → `{ kind: "busy", retryAfterSeconds: 3 }`;
   - `classifyCompileResponse(429, {})` → `busy` with `retryAfterSeconds: null`;
   - `classifyCompileResponse(200, { success: false, error_log: "! Undefined control sequence" })` → `failed` carrying that log;
   - `classifyCompileResponse(200, { success: true, pdf: "…" })` → `ok`;
   - `classifyCompileResponse(500, { detail: "boom" })` → `failed` with `"boom"`;
   - **a 429 never yields `kind: "failed"`** — assert this explicitly, it is the regression guard;
   - `nextRetryDelay(0|1|2)` are 1000/2000/4000 and `nextRetryDelay(3)` is `null`.

## Done when
- `tools/verify-slice.sh scripts/test_compile_retry.mjs` passes.
- `npx tsc --noEmit` is clean, including `LatexEditorView.tsx`, which consumes `CompileToolbar`.
- `bash scripts/run-collab-tests.sh` passes.
- Grepping `EditorLayout.tsx` for `handleCustomCopy`, `handleCustomPaste` and `safe-mobile-paste` returns nothing.
- Root typecheck passes. Append `## Result`.

## Result
- `lib/compile-retry.ts` (new): `COMPILE_RETRY_DELAYS_MS`, `CompileOutcome`, `classifyCompileResponse` (429 -> busy, never failed), `nextRetryDelay`.
- `components/editor/EditorLayout.tsx`: `handleCompile` loops over `classifyCompileResponse` (busy -> one `toast.loading` with id `compile-busy`, 1s/2s/4s backoff, then `toast.error("Server is busy. Try again in a moment.")`, `errorLog` untouched; failed/network keep today's behaviour); `isCompiling` held for the whole sequence and cleared in `finally`; new `compileBusy` state passed as `busy` to both `CompileSplitButton`s; deleted `handleCustomCopy`/`handleCustomPaste` and the touch `safe-mobile-paste` listener (M7).
- `components/editor/CompileToolbar.tsx`: optional `busy` prop on `CompileSplitButton` (label "Queued…" and a "Server busy" tooltip while backing off); `CompileToolbar` signature unchanged.
- `scripts/test_compile_retry.mjs` (new, 7 checks); `scripts/run-collab-tests.sh`: one entry appended.

Gate (`tools/verify-slice.sh scripts/test_compile_retry.mjs`):
```
PASS  typecheck
PASS  scripts/test_compile_retry.mjs
```
`bash scripts/run-collab-tests.sh` passes ("Client-side checks complete."); grep for `handleCustomCopy|handleCustomPaste|safe-mobile-paste` in EditorLayout.tsx is empty.

Skipped / notes: not browser-tested; the now-unused `lib/clipboard` import in EditorLayout was removed. The Ctrl+S binding still calls save then compile and therefore gets the retry behaviour too.
