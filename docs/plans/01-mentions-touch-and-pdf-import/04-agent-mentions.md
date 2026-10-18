# 01/04 — Agent mention plumbing

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: none · Parallel with: 01/01, 01/02, 01/03 (all frontend), 01/05 (`backend/pdf2latex/*`, `backend/routes/pdf_convert.py`), 01/06 (`backend/main.py`, `backend/compiler.py`, `backend/compile_queue.py`). No overlap with any of them.

## Decisions you need
M3 (wire format — the exact JSON the frontend sends), M4 (agent behaviour: steer, do not restrict) — run `grep -E '^\| M(3|4) ' 00-README.md`.

The frontend half is slice 01 and runs in parallel. Build to M3's contract; do not wait for it and do not edit any frontend file.

## Read first
- `backend/routes/agent_routes.py` — `OpenCodeRequest` at :40-63 (note the existing `selection: Optional[Dict]`), the endpoint `agent_run` at :385 with its manual JSON parse and 10MB cap, and the `stream_agent(...)` call at ~:454-475.
- `backend/agent/agent_loop.py` — `stream_agent` signature at :1316, where `selection` lands on the workspace at :2494-2497, the system prompt constant `OPENCODE_SYSTEM_PROMPT` at :478, its `.format(...)` at :1461, and the first-user-message construction near :2121.
- `backend/agent/elaborate.py:444` — the only current consumer of `selection`. Your change must not alter its behaviour.
- `backend/tests/test_agent_json_latex.py` — the pytest style used for agent tests in this repo (how the loop is driven without a live LLM).

## Scope (files you own)
- `backend/routes/agent_routes.py`
- `backend/agent/agent_loop.py`
- `backend/tests/test_agent_mentions.py` (new)

## Tasks

1. **Request field.** Add `mentions: Optional[List[Dict[str, Any]]] = None` to `OpenCodeRequest` (:40-63). Validate defensively in the endpoint, because the body is parsed manually: drop any entry that is not a dict or is missing `text`; coerce `start_line`/`end_line` with `int()` inside a `try`, defaulting to `0`; cap the list at **8** entries and each `text` at **4000** characters (M1's limits, enforced server-side too — never trust the client). A malformed `mentions` must never 500; worst case it becomes `None`.

2. **Pass it through.** Add `mentions=req.mentions` to the `stream_agent(...)` call (~:454-475) and `mentions: Optional[List[Dict[str, Any]]] = None` to its signature at :1316. Thread it to where `selection` is handled at :2494-2497. Do not change how `selection` reaches `workspace.user_selection` — `elaborate.py` depends on it.

3. **Prompt injection.** Build a `<mentioned_context>` block and append it to the **first user message** (near :2121), after the existing document/context content, only when `mentions` is non-empty. Format, exactly:

   ```
   <mentioned_context>
   The user explicitly mentioned these selections. Treat them as the primary edit target.

   [1] main.tex lines 12-18
   ```tex
   <verbatim text>
   ```

   [2] chapters/intro.tex lines 3-3
   ```tex
   <verbatim text>
   ```
   </mentioned_context>
   ```

   Write a helper `def format_mentioned_context(mentions: list) -> str` next to the other prompt helpers in `agent_loop.py` so it is unit-testable, and return `""` for an empty or `None` list. Use the mention's `file` value as given, falling back to `"main.tex"`.

4. **System prompt (M4).** Add **exactly one** instruction to `OPENCODE_SYSTEM_PROMPT` (:478), in the voice of the surrounding text: mentioned ranges are the primary edit target, and edits outside them are allowed only when the change requires it — a package, a preamble entry, closing an environment. Do not add a tool, a validator rule, or any hard restriction. `backend/edit_validator.py` is **not** in your scope and must not change.

5. **Back-compat (M3).** When `mentions` is present and `selection` is absent, the loop must behave as though `selection` were `mentions[0]`, so `elaborate`/`humanize`/`justify` keep working for a user who mentioned rather than selected. When both are present, `selection` wins — the frontend already sets it from `mentions[0]`.

6. **`backend/tests/test_agent_mentions.py`.** Pytest, no live LLM. Cover:
   - `format_mentioned_context([])` and `format_mentioned_context(None)` both return `""`;
   - a two-mention list produces a block containing `<mentioned_context>`, `[1]`, `[2]`, both file names, `lines 12-18`, and the verbatim text of each;
   - `OpenCodeRequest(**{... "mentions": [...]})` accepts a well-formed list;
   - the endpoint's sanitiser drops a non-dict entry, truncates a 5000-character `text` to 4000, and caps a 12-entry list at 8;
   - a mention whose `start_line` is the string `"7"` is coerced to the int `7` and does not raise;
   - the single new system-prompt sentence is present in `OPENCODE_SYSTEM_PROMPT` (assert on a distinctive substring);
   - with `mentions` set and `selection` `None`, the value that reaches `workspace.user_selection` equals `mentions[0]`.

## Done when
- `tools/verify-slice.sh backend/tests/test_agent_mentions.py` passes.
- `cd backend && pytest tests/test_agent_json_latex.py tests/test_elaborate_content.py tests/test_humanize_content.py -v` still passes — these exercise the `selection` path you must not break.
- `backend/edit_validator.py` is unchanged (`git diff --stat` shows it absent).
- Append `## Result`, naming the exact JSON keys you accept so slice 01 can be checked against them.

## Result
- `backend/routes/agent_routes.py` — `OpenCodeRequest.mentions`, module-level `sanitize_mentions()` (called on the raw body before validation, never raises), `mentions=req.mentions` passed to `stream_agent`.
- `backend/agent/agent_loop.py` — `mentions` parameter, `format_mentioned_context()`, `resolve_user_selection()` (selection wins, else `mentions[0]`), block appended to the first user message, system-prompt item 11c (the one new instruction). `edit_validator.py` untouched.
- `backend/tests/test_agent_mentions.py` — new, 11 tests (gitignored dir, not force-added).

Gate:
```
PASS  typecheck
PASS  pytest tests/test_agent_mentions.py
```
Companion run: `test_agent_json_latex.py test_elaborate_content.py test_humanize_content.py` -> 91 passed.
Full backend suite from backend/: 6 failed, 766 passed. Failures: the known `test_compile_gate_truth.py::test_recovery_success_still_reports_errors`, plus 5 in `test_provider_fallback.py` (minimax-m3 `:free` suffix; provider/env related, in code this slice does not touch).

JSON keys accepted in `mentions[]`: `text` (required, string, capped at 4000), `file` (default "main.tex" when empty), `start_line`, `end_line` (int-coerced, 0 on failure), `id`, `label` (kept as strings; other keys pass through). Max 8 entries; non-dict / missing-text entries dropped; a non-list `mentions` becomes None.

Skipped: no validator rule and no tool (per M4). The sanitiser does not clamp line numbers to the document length.
