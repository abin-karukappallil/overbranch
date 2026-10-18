# 01/02 — Touch callout: undo/redo, mention button, clipboard fixes

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: 01/01 · Parallel with: 01/03 (owns `EditorLayout.tsx`, `CompileToolbar.tsx`), 01/06 (backend), 01/07 (backend). **You must not edit `EditorLayout.tsx` — slice 03 owns it.**

## Decisions you need
M5 (mobile undo/redo placement), M6 (clipboard write and the manual copy sheet), M7 (paste interceptor removal and selection stability) — run `grep -E '^\| M(5|6|7) ' 00-README.md`.

M7 asks you to delete a block in `EditorLayout.tsx`, which you do **not** own. See Task 5: you hand that edit to slice 03 instead.

## Read first
- `components/editor/MobileEditorAssist.tsx` — the whole file is yours (606 lines). Pay attention to `MobileEditorAssistProps` (:7-18), `handleCopy` (:394), `handleCut` (:402), `handlePaste` (:414), `consumePastedText` (:429), the callout JSX (:513-565), the paste-fallback textarea (:566-595) and `calloutBtn` (:446).
- `lib/clipboard.ts` — all of it (`copyText`, `readClipboard`, `canReadClipboard`).
- `lib/collab/monaco-binding.ts` — the remote-update path, especially `model.setValue` at :307 and the cursor/selection publish queued from :252.
- `scripts/test_chat_input.mjs` — the frontend test pattern.
- Slice 01's `## Result` section in `01-mention-core.md` — it names the exact props `EditorLayout` now passes you.

## Scope (files you own)
- `components/editor/MobileEditorAssist.tsx`
- `lib/clipboard.ts`
- `lib/collab/monaco-binding.ts`
- `scripts/test_clipboard.mjs` (new)
- `scripts/run-collab-tests.sh` — **append-only**: add `scripts/test_clipboard.mjs` to the `for entry in …` list. Change nothing else.

## Tasks

1. **Accept the new props.** Add to `MobileEditorAssistProps`: `onUndo?: () => void`, `onRedo?: () => void`, `onMention?: () => void`. Slice 01 already passes all three from `EditorLayout`. Destructure them in the component signature.

2. **Undo/Redo in the callout (M5).** Add Undo and Redo buttons at the **left end** of the callout row, before the existing Select/Copy group. Unlike the copy/cut buttons they render whether or not there is a selection — so the callout must open for a bare caret too, which it already does (`calloutAnchor` falls back to `caret` at :438). Use `lucide-react`'s `Undo2` and `Redo2`, matching the existing icon sizing. Each calls its prop and then `editor?.focus?.()`, and leaves the callout **open** (unlike copy, which closes it) so a user can undo several times. When the prop is absent, render the button with `disabled`, `aria-disabled="true"` and 40% opacity. Give them `aria-label="Undo"` / `aria-label="Redo"`.

3. **Mention button (M2/M5).** Add an `@` button to the callout, left of Copy, rendered **only when `hasSelection`** and only when `onMention` is defined. `aria-label="Mention selection to the AI"`. On click: call `onMention()`, close the callout, and call `editor?.focus?.()`.

4. **Clipboard write (M6).** Rewrite `copyText` in `lib/clipboard.ts` so the synchronous fallback is reachable:
   - Extract the existing hidden-textarea `execCommand("copy")` body into `export function copyTextSync(text: string): boolean`.
   - `copyText` becomes: if `navigator.clipboard?.writeText` exists, call it **synchronously** (no `await` before it) and `return true` on resolve; on rejection, immediately `return copyTextSync(text)`. If `writeText` is unavailable, `return copyTextSync(text)` directly. Keep returning `Promise<boolean>`.
   - Keep the existing doc comment's explanation and extend it with *why* the order matters: awaiting `writeText` first consumes the transient user activation, so a later `execCommand` can fail — which is why copy worked only sometimes.
   - In `MobileEditorAssist`, `handleCopy` (:397) and `handleCut` (:406) currently discard the boolean. They must capture it and, when `false`, open a **manual copy sheet**: reuse the existing paste-fallback pattern (`pasteFallbackOpen`, the textarea at :581) to add a `copyFallbackText: string | null` state that renders a read-only textarea pre-filled with the text, focused and fully selected, with a short line telling the user to copy it themselves, and a close button. For `handleCut`, only delete the selected text when the copy succeeded — never destroy text that did not reach the clipboard.

5. **Paste interceptor (M7) — hand off, do not edit.** The listener to remove lives at `EditorLayout.tsx:1777-1815`, which slice 03 owns. Do **not** touch it. Instead, write the exact removal instruction (the line range and what replaces it) into your `## Result` section under a heading `### For slice 03`, so the orchestrator can pass it on. Your own paste path in `MobileEditorAssist` (`handlePaste`, `consumePastedText`) stays, but change `consumePastedText` to insert through the editor's own command rather than a bare `executeEdits` if it currently bypasses the binding — check `insertText` and keep whichever path the collab binding observes.

6. **Selection stability in the collab binding (M7).** In `lib/collab/monaco-binding.ts`, the remote-update path calls `model.setValue` at :307, which resets the selection and the undo stack — a plausible cause of a Ctrl+C that copies nothing when a collaborator types during the selection. Change it so that when the local selection is **non-empty**, the remote update is applied with `model.applyEdits(...)` (a minimal diff) instead of `setValue`, and the prior selection is restored afterwards with `editor.setSelection(...)`, offset by any edit that landed before it. Keep `setValue` for the case where there is no local selection or the diff is not computable. Do not change the decoration or cursor-publish logic.

7. **`scripts/test_clipboard.mjs`.** Import from `../lib/clipboard.ts` and assert, with a stubbed global `navigator` and `document`:
   - when `navigator.clipboard.writeText` resolves, `copyText` resolves `true` and `execCommand` was **not** called;
   - when `writeText` rejects, `copyText` still resolves `true` because `copyTextSync` ran, and `execCommand("copy")` was called **exactly once**;
   - when `writeText` rejects **and** `execCommand` returns `false`, `copyText` resolves `false`;
   - when `navigator.clipboard` is absent entirely, `copyText` goes straight to `copyTextSync`;
   - `copyText("")` resolves `false` without touching either path.

## Done when
- `tools/verify-slice.sh scripts/test_clipboard.mjs` passes.
- `bash scripts/run-collab-tests.sh` passes, including the existing `test_collab_binding.mjs` — your change to `monaco-binding.ts` must not regress it.
- `cd backend && pytest tests/test_collab_sync.py -v` still passes.
- `npx tsc --noEmit` is clean for your files.
- Root typecheck passes. Append `## Result`, including the `### For slice 03` handoff from Task 5.

## Result
- `components/editor/MobileEditorAssist.tsx`: destructured `onUndo`/`onRedo`/`onMention`; Undo/Redo buttons at the left of the callout (always rendered, disabled + 40% opacity + `aria-disabled` when prop absent, callout stays open); `@` mention button (only `hasSelection && onMention`, closes callout); `handleCopy`/`handleCut` act on the `copyText` boolean and open a new manual copy sheet (`copyFallbackText` state, read-only focused+selected textarea, close button); cut deletes only after a successful copy.
- `lib/clipboard.ts`: new exported `copyTextSync`; `copyText` calls `writeText` synchronously and falls back to `copyTextSync` on rejection (or when `writeText` is absent); doc comment extended with the user-activation rationale.
- `lib/collab/monaco-binding.ts`: `resetModelToYText` now patches with one prefix/suffix `applyEdits` and restores every non-empty editor selection (offset-shifted) when any editor has a selection; otherwise (or on error) it keeps `setValue`.
- `scripts/test_clipboard.mjs` (new, 6 checks, includes a synchronous-call assertion); `scripts/run-collab-tests.sh`: one entry appended.

Gate summary (`tools/verify-slice.sh scripts/test_clipboard.mjs`):
```
PASS  typecheck
PASS  scripts/test_clipboard.mjs
```
`bash scripts/run-collab-tests.sh` passes ("Client-side checks complete."); `pytest tests/test_collab_sync.py` 23 passed.

Skipped / notes:
- Task 5 `consumePastedText` left unchanged: `insertText` already goes through `editor.executeEdits`, which fires `model.onDidChangeContent`, the path the collab binding observes, plus `onDocumentChange`. No bare model write exists.
- Task 6 premise differs from the brief: the remote Y.Text path (`handleYTextChange`) already uses per-op `applyEdits`; `model.setValue` is only reached via `resetModelToYText` (bind time and the error fallback in `handleYTextChange`). The selection-preserving patch was put there, so the fallback no longer wipes a selection. Not covered by an existing test; verified by typecheck, the unchanged binding test, and reading.
- Not browser-tested.

### For slice 03
In `components/editor/EditorLayout.tsx` (line numbers have drifted from the plan's :1777-1815), delete the whole block starting at the comment `// Attach touch/mobile fallback paste listener only on touch-enabled devices` (currently line 1902) through the closing `} catch (err) { console.warn("Failed to attach touch paste event listener:", err); }` (currently line 1939). That is the `try { const isTouchDevice = ...; containerNode.addEventListener("paste", ...) }` block, which calls `preventDefault()` + `executeEdits("safe-mobile-paste")` + `handleCodeChange(getValue())`. Replace it with nothing; Monaco's native paste then runs and the collab binding observes it. Check afterwards that `isDesktop` and `handleCodeChange` are still used elsewhere (tsc will flag unused only if configured). Also per M7, delete the dead `handleCustomCopy`/`handleCustomPaste` (grep for them; they were at ~:1287-1330).
