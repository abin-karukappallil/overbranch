# 01/01 — Mention model, desktop trigger, chips and payload

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: none · Parallel with: 04 (backend agent), 05 (backend pdf2latex), 06 (backend compile) — all backend-only, no file overlap.

## Decisions you need
M1 (data model), M2 (triggers and chip UI), M3 (wire format) — run `grep -E '^\| M(1|2|3) ' 00-README.md`.

You also set up slice 02's contract: M5 says `MobileEditorAssist` gets `onUndo`/`onRedo` props that you wire here, even though slice 02 implements the buttons. Run `grep -E '^\| M5 ' 00-README.md`.

## Read first
- `components/editor/EditorLayout.tsx` — `activeSelection()` at :1148-1166 (the existing selection payload), `getActiveEditor()` at :1182, `handleEditorMount` ~:1700-1860 (the Ctrl+S `addCommand` at :1817 is where your keybinding goes), the agent fetch body at :2008-2025, the desktop chat form at :3654 and the mobile chat form at :3925, the `<MobileEditorAssist …>` call site ~:3765.
- `components/editor/ChatAttachments.tsx` — the chip row directly above the chat input; match its markup and Tailwind classes so mention chips look native.
- `scripts/test_chat_input.mjs` — the pattern for a frontend test (plain node asserts, no framework).

## Scope (files you own)
- `lib/mentions.ts` (new)
- `components/editor/MentionChips.tsx` (new)
- `components/editor/EditorLayout.tsx`
- `scripts/test_mentions.mjs` (new)
- `scripts/run-collab-tests.sh` — **append-only**: add `scripts/test_mentions.mjs` to the `for entry in …` list at lines 19-20. Change nothing else in that file.

## Tasks

1. **`lib/mentions.ts`.** Pure, DOM-free so it is testable under node. Export:
   - `export interface MentionRef { id: string; file: string; start_line: number; end_line: number; text: string; label: string }`
   - `export const MAX_MENTIONS = 8` and `export const MAX_MENTION_CHARS = 4000`
   - `export function mentionLabel(file: string, startLine: number, endLine: number): string` — basename of `file`, then `` `L${start}` `` when `start === end`, else `` `L${start}–L${end}` `` (en dash U+2013). Basename is the segment after the last `/`.
   - `export function makeMention(file, startLine, endLine, text): MentionRef` — builds `id` as `` `${file}:${start}:${end}` ``, truncates `text` to `MAX_MENTION_CHARS` appending `"\n…"` when it was longer, and sets `label` from `mentionLabel`.
   - `export function addMention(list: MentionRef[], next: MentionRef): { list: MentionRef[]; error: string | null }` — replaces in place when `next.id` already exists (keeping its position); otherwise appends. When the id is new and `list.length >= MAX_MENTIONS`, returns the list unchanged with `error: "You can mention up to 8 selections."`. Otherwise `error: null`.
   - `export function removeMention(list: MentionRef[], id: string): MentionRef[]`

2. **`components/editor/MentionChips.tsx`.** `"use client"`. Props `{ mentions: MentionRef[]; onRemove: (id: string) => void; disabled?: boolean }`. Renders nothing when `mentions` is empty. Otherwise a wrapping flex row of chips, each showing an `@` glyph, `mention.label`, and an `×` button (`aria-label={`Remove mention ${mention.label}`}`) calling `onRemove(mention.id)`. Give each chip `title={mention.text.slice(0, 200)}`. Mirror `ChatAttachments.tsx` for the chip shape, spacing and colours. When `disabled`, the `×` buttons are disabled.

3. **Mention state in `EditorLayout`.** Add `const [mentions, setMentions] = useState<MentionRef[]>([])` near the other chat state. Add a `useCallback` named `addMentionFromSelection()` that:
   - reads the active editor via the existing `getActiveEditor()`;
   - returns silently when there is no editor, no model, or the selection is empty;
   - builds the mention with `makeMention(activeFilePath || "main.tex", sel.startLineNumber, sel.endLineNumber, model.getValueInRange(sel))`;
   - calls `addMention(...)` and, when it returns an `error`, shows `toast.error(error)` and does not change state.
   Also add `removeMentionById(id)`. Reset `mentions` to `[]` on project change (the effect that already resets chat state) and after a successful send.

4. **Keybinding.** In `handleEditorMount`, beside the existing Ctrl+S binding at :1817, register
   `editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyM, () => addMentionFromSelection())`.
   It must be registered on **both** the desktop and mobile editor instances (the hook runs for both). Keep the callback in a ref if needed so the command does not capture a stale closure — the existing bindings in that function show the pattern used here.

5. **Desktop floating trigger (Monaco content widget).** In `handleEditorMount`, for the desktop instance only (`isDesktop === true`), create a content widget that renders a single small button labelled `@ Mention`:
   - `getId()` returns `"overbranch.mention.widget"`.
   - `getPosition()` returns `{ position: { lineNumber: sel.startLineNumber, column: sel.startColumn }, preference: [monaco.editor.ContentWidgetPositionPreference.ABOVE, monaco.editor.ContentWidgetPositionPreference.BELOW] }`.
   - Its DOM node is a `<button>` built with `document.createElement`; style it to match the editor chrome and give it `aria-label="Mention selection to the AI"`. Attach the click with `addEventListener("mousedown", e => { e.preventDefault(); addMentionFromSelection(); })` — `mousedown` with `preventDefault` so Monaco does not clear the selection before the handler runs.
   - Add the widget on a non-empty selection and remove it on an empty one, driven from the **existing** `onDidChangeCursorSelection` handler at :1765 (extend it; do not add a second listener).
   - Also remove it while `isAgentThinking` is true.
   - Remove the widget in the mount handler's disposal path so it does not leak across remounts (`editorsNonce` bumps remount the editors).

6. **Chips in both chat forms.** Render `<MentionChips mentions={mentions} onRemove={removeMentionById} disabled={isAgentThinking} />` immediately above the textarea inside the desktop form (:3654) and the mobile form (:3925), next to where attachments already render.

7. **Payload (M3).** In the body built at :2008-2025 add `mentions` when `mentions.length > 0`, serialising each as `{ id, file, start_line, end_line, text, label }`. Keep the existing `selection` key; when `mentions.length > 0`, set `selection` to `{ text, start_line, end_line, file }` taken from `mentions[0]` instead of `activeSelection()`. When `mentions` is empty, `selection` keeps today's `activeSelection()` behaviour exactly. Clear `mentions` after the request is dispatched successfully, in the same place the chat input is cleared.

8. **Props for slice 02 (do not implement the buttons).** At the `<MobileEditorAssist …>` call site ~:3765 pass three new props: `onUndo={handleUndo}`, `onRedo={handleRedo}`, `onMention={addMentionFromSelection}`. `handleUndo` (:1361) and `handleRedo` (:1368) already exist. Slice 02 adds these three to `MobileEditorAssistProps` and renders the buttons — **you must not edit `MobileEditorAssist.tsx`.** Passing a prop the component does not yet declare is a typecheck error, so add the three optional props to the interface **only if** `npx tsc --noEmit` fails without it; if you must, add nothing but the three prop declarations and leave the component body alone. State clearly in your Result which of the two you did.

9. **`scripts/test_mentions.mjs`.** Import from `../lib/mentions.ts` and assert, with plain `node:assert`:
   - `mentionLabel("a/b/main.tex", 4, 4) === "main.tex L4"` and `mentionLabel("main.tex", 4, 9) === "main.tex L4–L9"`;
   - `makeMention` truncates text longer than `MAX_MENTION_CHARS` and appends `"\n…"`, and leaves shorter text untouched;
   - adding a mention with a duplicate `id` replaces it and keeps the list length and its index;
   - the 9th distinct mention is refused with the exact message `"You can mention up to 8 selections."` and leaves the list unchanged;
   - `removeMention` removes by id and is a no-op for an unknown id.

## Done when
- `scripts/test_mentions.mjs` passes under `tools/verify-slice.sh scripts/test_mentions.mjs`.
- `npx tsc --noEmit` is clean for the files you own.
- `bash scripts/run-collab-tests.sh` still passes, including your appended entry.
- Root typecheck passes. Append `## Result`, and state in it the exact prop names you passed to `MobileEditorAssist` and whether you had to declare them in its interface.

## Result
- `lib/mentions.ts` (new): MentionRef, MAX_MENTIONS, MAX_MENTION_CHARS, mentionLabel, makeMention, addMention, removeMention.
- `components/editor/MentionChips.tsx` (new): chip row, mirrors ChatAttachments chip classes.
- `components/editor/EditorLayout.tsx`: mentions state + ref, `addMentionFromSelection`, `removeMentionById`, Ctrl/Cmd+M on both editors, desktop-only content widget driven from the existing `onDidChangeCursorSelection` (hidden while `isAgentThinking`, removed on editor dispose), chips in both chat forms, `mentions` + first-mention `selection` in the agent body, cleared on send / project change / new chat.
- `scripts/test_mentions.mjs` (new), `scripts/run-collab-tests.sh` (one entry appended).
- `components/editor/MobileEditorAssist.tsx`: declared ONLY the three optional props `onUndo?`, `onRedo?`, `onMention?` in `MobileEditorAssistProps` (tsc failed without them, as the brief anticipated); component body untouched.

Props passed at the `<MobileEditorAssist …>` call site: `onUndo={handleUndo}`, `onRedo={handleRedo}`, `onMention={addMentionFromSelection}`. Slice 02 does not need to add the declarations (already in the interface); it only needs to destructure them and render the buttons.

Gate summary:
```
PASS  typecheck
PASS  scripts/test_mentions.mjs
```
`bash scripts/run-collab-tests.sh` passes ("Client-side checks complete.").

Skipped / notes:
- Mentions are included in the body and cleared only on the typed-message path (`customPrompt === undefined`), matching where the chat input is cleared; "Ask AI to Fix" (customPrompt) sends currently pinned mentions but does not clear them.
- Not browser-tested (no headless Chromium run); widget behaviour verified by typecheck and reading only. Scroll-past-viewport hiding is left to Monaco's own content-widget visibility handling.
