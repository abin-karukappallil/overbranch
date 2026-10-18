# 01/11 — Manual copy sheet for the chat copy button

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: 01/02 · Parallel with: 01/12 (backend only). Added after acceptance row 7 failed.

## Why this slice exists
Acceptance row 7 FAILED. M6 requires **every** `copyText` call site to act on the boolean and open a
manual copy sheet when the clipboard cannot be reached. `MobileEditorAssist` does this; the chat
message copy button does not:

```
components/editor/CopyButton.tsx:37    if (!ok) return;     // silent failure, no sheet, no toast
```

No slice owned `CopyButton.tsx`, so it was missed. Verify with
`grep -n "copyText\|if (!ok)" components/editor/CopyButton.tsx`.

## Decisions you need
M6 (clipboard write and the manual copy sheet) — run `grep -E '^\| M6 ' 00-README.md`.

## Read first
- `components/editor/CopyButton.tsx` — all 59 lines; `handleCopy` at :34-42 and the `copied` state it drives.
- `components/editor/MobileEditorAssist.tsx` — the `copyFallbackText` state (:88), where it is set (:415) and the read-only textarea sheet it renders. **Read it for the pattern; do not edit it.**
- `lib/clipboard.ts` — `copyText` returns `Promise<boolean>`.

## Scope (files you own)
- `components/editor/CopyButton.tsx`
- `components/editor/CopyFallbackSheet.tsx` (new)
- `components/editor/MobileEditorAssist.tsx` — **only** if you extract the sheet into the shared component; if you do, replace its inline sheet with the shared one and change nothing else in that file. If that turns out to be more than a mechanical swap, leave `MobileEditorAssist` alone and say so in your Result.

## Tasks

1. **`components/editor/CopyFallbackSheet.tsx` (new).** `"use client"`. Props `{ text: string | null; onClose: () => void; label?: string }`. Renders nothing when `text` is null. Otherwise a small centred overlay containing a short line ("Your browser blocked the copy. Select and copy this text:"), a **read-only** `<textarea>` pre-filled with `text`, auto-focused and fully selected on mount (`el.focus(); el.select();` in an effect), and a close button. Give the textarea `aria-label={label ?? "Text to copy"}`. Mirror the visual treatment of the existing sheet in `MobileEditorAssist`.

2. **Wire `CopyButton`.** Replace `if (!ok) return;` at :37 so a `false` result sets a `copyFallbackText` state and renders `<CopyFallbackSheet …>`. A successful copy keeps today's behaviour (the `copied` tick for 1500ms) exactly. The button must still stop event propagation as it does now — it is rendered inside chat message bubbles that have their own click handlers.

3. **Optional shared extraction.** If `MobileEditorAssist`'s inline sheet can be swapped for `CopyFallbackSheet` as a mechanical replacement, do it so there is one implementation. Its two call sites (`handleCopy` ~:428, `handleCut` ~:441) must keep behaving identically, including that **cut only deletes the text when the copy succeeded**. If the swap is not mechanical, skip it and say why.

4. **`scripts/test_copy_fallback.mjs` (new).** The sheet is React, so test the decision logic, not the DOM: export a tiny pure helper from `lib/clipboard.ts` **only if one is genuinely needed** — otherwise assert on `copyText`'s contract as `scripts/test_clipboard.mjs` already does and state in your Result that the sheet itself is MANUAL. Do not add a test that asserts nothing. If you add this file, append it to `scripts/run-collab-tests.sh` (shared, append-only).

## Done when
- `grep -n "if (!ok) return" components/editor/CopyButton.tsx` returns nothing.
- `npx tsc --noEmit` is clean.
- `bash scripts/run-collab-tests.sh` passes.
- `cd backend && .venv/bin/python -m pytest tests/test_collab_sync.py -q` still passes if you touched `MobileEditorAssist`.
- Append `## Result`, stating whether you extracted the shared sheet.

## Result
- `components/editor/CopyFallbackSheet.tsx` (new): portalled fixed overlay, read-only textarea auto-focused and selected on mount, close button, `aria-label={label ?? "Text to copy"}`, renders nothing when `text` is null; stops click propagation (React portals bubble to the host chat bubble).
- `components/editor/CopyButton.tsx`: `if (!ok) return;` replaced by `setCopyFallbackText(text)` plus a rendered `<CopyFallbackSheet>`. The 1500ms `copied` tick and `preventDefault`/`stopPropagation` on the button are untouched.
- `components/editor/MobileEditorAssist.tsx`: NOT changed. Shared sheet NOT extracted: its inline sheet is absolutely positioned inside the assist container, uses touch-specific copy ("Long-press the text, then tap Copy"), and its close handler also refocuses the Monaco editor and shares `copyTargetRef`/`openCopyFallback` timing with cut/copy. Swapping it is a visual and behavioural change, not a mechanical one.
- No new test file: `scripts/test_clipboard.mjs` already asserts `copyText` resolves `false` when writeText rejects and execCommand fails (the contract the call site branches on). The sheet itself is React DOM, so its open/focus/select/close behaviour is MANUAL (block clipboard, click the chat copy button, confirm the sheet opens with text selected, close it; confirm normal copy still shows the check for 1.5s).

Gate output:
```
$ npx tsc --noEmit            -> exit 0, no output
$ bash scripts/run-collab-tests.sh -> ... 10 passed / Client-side checks complete.
$ grep -n "if (!ok) return" components/editor/CopyButton.tsx -> (no output, exit 1)
```
