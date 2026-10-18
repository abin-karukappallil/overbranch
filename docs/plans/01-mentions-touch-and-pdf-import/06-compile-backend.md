# 01/06 — Compile backend: collab flush and cold-cache timeout

Plan folder: [`00-README.md`](00-README.md) · Model: Opus · Prerequisites: none · Parallel with: 01/01, 01/02, 01/03 (frontend), 01/04 (`agent_routes.py`, `agent_loop.py`), 01/05 (`backend/pdf2latex/*`, `routes/pdf_convert.py`), 01/07 (`backend/pdf2latex/*`). No overlap.

## Decisions you need
M9 (collab flush before compile, timeout 30→60) — run `grep -E '^\| M9 ' 00-README.md`. M8 is the frontend half and belongs to slice 03; read it for context only: `grep -E '^\| M8 ' 00-README.md`.

## Read first
- `backend/main.py:110` (`CompileRequest`) and `:153-197` (`compile_endpoint`) — note it handles only `CompileQueueFullError` → 429, and that compile failures return 200 with `success: false`.
- `backend/compile_queue.py` — `MAX_CONCURRENT_COMPILES = 4`, `MAX_QUEUE_DEPTH = 20`, the 429 reject around :68, the 45s slot wait around :80, and the lazy semaphore/executor creation at :41-60.
- `backend/compiler.py` — `compile_latex` at :1215 (the `timeout_seconds` default at :1221), `_compile_latex_impl` at :1267, the sibling-file copy at :1306-1318 (the hard-coded `"main.tex"` skip at :1311), the Supabase fallback at :1320-1337, the heavy-document 90s path at :1407-1421, the engine chain at :1456-1482, and the `[TIMEOUT]` marker at :1566.
- `backend/collab/room.py` — `_persist_loop` at :626 and `flush` at :645; `backend/collab/config.py:44-56` for the 2.0s idle / 15s max debounce.
- `backend/collab/` room registry — find how a room is looked up by project id (the collab routes do it); you need that to flush one room.

## Background: the bug you are fixing
A compile fails on the first click and succeeds on a retry. Two mechanisms, both real:
1. **Stale siblings.** The request body carries `main.tex`, but every other file — `\input` chapters, `.bib` — is copied from `uploads/projects/<id>/` at `compiler.py:1306-1318`. The collab room persists on a **2.0s idle / 15s max** debounce and nothing flushes it before a compile, so a user who edits a chapter and immediately clicks Compile builds against the previous version.
2. **Cold TeX caches.** `timeout_seconds` defaults to 30 (`compiler.py:1221`). A first run after boot builds font and format caches from scratch and can hit `[TIMEOUT]` at :1566; later runs are warm and succeed.

Per `CLAUDE.md`, **reproduce both against real `pdflatex` before fixing them.** Prompt-only or guess-only fixes have failed on this codebase three times. Write the repro steps into your Result.

## Scope (files you own)
- `backend/main.py`
- `backend/compiler.py`
- `backend/compile_queue.py`
- `backend/tests/test_compile_flush_and_busy.py` (new)

## Tasks

1. **Reproduce first.** Before editing, demonstrate both mechanisms and capture the evidence:
   - write a two-file project (`main.tex` with `\input{chapter}`, plus `chapter.tex`) into a temp `uploads/projects/<id>/`, mutate `chapter.tex` in a collab room without flushing, call the compile path, and show the output PDF/log carries the **old** chapter;
   - show a cold-cache `pdflatex` run exceeding 30s, or, if your machine is too warm to reproduce it naturally, demonstrate the timeout boundary by driving `compile_latex` with `timeout_seconds=1` on a real document and showing the `[TIMEOUT]` marker at :1566 is what surfaces.
   Paste both into your `## Result`.

2. **Flush the collab room before compiling (M9).** In `compile_endpoint` (`main.py:153-197`), before `compile_queue.submit`, await a best-effort flush of the room for `request.project_id`: look the room up in the existing registry, and if one is live, `await room.flush()`. Wrap it so a missing room, a disabled-collab deployment (`COLLAB_ENABLED=0`) or any exception is logged at warning level and compilation proceeds regardless — **a flush failure must never block a compile.** Give the flush its own short timeout (2s) so a wedged room cannot hang the request.

3. **Timeout (M9).** Raise the `timeout_seconds` default at `compiler.py:1221` from 30 to 60. Leave the heavy-document 90s path at :1407-1421 as it is. Do **not** change the hard-coded `"main.tex"` skip at :1311 — M9 explicitly keeps it, because the flush is the intended fix and changing both at once would make it impossible to tell which one worked.

4. **Make 429 honest.** Confirm the queue's reject path returns a body the frontend can classify: `{"detail": ..., "retry_after_seconds": N}` with HTTP **429**, both when the depth cap of 20 is hit and when the 45s slot wait expires. Slice 03 branches on exactly this. If the slot-wait timeout currently surfaces as something else (a 500, or a 200 with a failure log), fix it to a 429 with the same shape — that path is a first-click failure that a retry "fixes", and it is likely a direct cause of the reported bug.

5. **Queue warmup (optional, only if your repro justifies it).** The semaphore and `ThreadPoolExecutor` are created lazily on first submit (`compile_queue.py:41-60`). If — and only if — your Task 1 evidence shows this contributing to first-compile latency, add an idempotent `warmup()` and call it from the app's startup hook. If the evidence does not show it, skip this and say so; do not add speculative code.

6. **`backend/tests/test_compile_flush_and_busy.py`.** Pytest. Cover:
   - `compile_endpoint` calls `room.flush()` for the request's project when a room exists (assert with a stub room);
   - a flush that raises does **not** prevent the compile from being submitted;
   - a flush that hangs past 2s does not hang the request;
   - no room for the project → compile still submitted, warning logged;
   - `CompileQueueFullError` → HTTP 429 with both `detail` and `retry_after_seconds` present;
   - a slot-wait timeout also yields 429 with that shape;
   - `compile_latex`'s default `timeout_seconds` is 60;
   - a compile failure still returns HTTP 200 with `success: false` and an `error_log` (the contract slice 03 relies on to tell broken from busy).

## Done when
- `tools/verify-slice.sh backend/tests/test_compile_flush_and_busy.py` passes.
- `cd backend && pytest tests/test_compile_gate_truth.py tests/test_compile_pre_heal.py tests/test_latex_compilation_pipeline_fixes.py tests/test_collab_sync.py -v` still passes.
- Your `## Result` contains the real `pdflatex` evidence from Task 1, and states explicitly whether you added the Task 5 warmup and why.

## Result

Files changed:
- `backend/main.py`: added `COLLAB_FLUSH_TIMEOUT_SECONDS = 2.0` and `_flush_collab_room_before_compile()`, which `compile_endpoint` awaits before `compile_queue.submit`. It looks the room up with `room_manager.get(project_id)`. Disabled collab, no room, an exception or a timeout each log a warning, and the compile goes ahead anyway. The flush is wrapped in `asyncio.shield`, so on timeout the request stops waiting but the flush itself is not cancelled. `CollabRoom.flush` clears `_dirty` before it writes, so cancelling it partway would drop files it had not yet written.
- `backend/compiler.py`: the `compile_latex` default `timeout_seconds` is now 60 (was 30). The heavy-document 90s path is unchanged, and so is the `"main.tex"` skip, as M9 requires.
- `backend/compile_queue.py`: **unchanged.** For Task 4, the slot-wait timeout already raises `CompileQueueFullError(estimated_wait_s=5.0)`, and `compile_endpoint` already maps that to 429 `{detail, retry_after_seconds}` with a `Retry-After` header. The depth cap goes through the same path. Both are now pinned by tests.
- `backend/tests/test_compile_flush_and_busy.py` (new): 11 tests.

Gate (`tools/verify-slice.sh backend/tests/test_compile_flush_and_busy.py`):
```
11 passed, 1 warning in 5.17s
──────── verify-slice summary ────────
PASS  typecheck
PASS  pytest tests/test_compile_flush_and_busy.py
```
Regression run (`test_compile_gate_truth.py test_compile_pre_heal.py test_latex_compilation_pipeline_fixes.py test_collab_sync.py`): `1 failed, 60 passed`. The one failure is `test_compile_gate_truth.py::test_recovery_success_still_reports_errors`, which the coordinator confirmed already fails at HEAD. The other 20 tests in `test_compile_gate_truth.py` pass: not_found_in_log_is_not_compiler_unavailable, new_error_is_not_masked_by_an_old_one_of_the_same_kind, pre_existing_error_moved_by_an_insert_is_still_pre_existing, timeout_is_a_failure_after_one_retry, timeout_then_success_on_retry_passes, missing_tex_engine_is_still_infra, strict_mode_fails_while_the_original_error_remains, strict_mode_passes_when_fixed, editing_a_non_main_file_compiles_the_projects_real_main, explicit_pdflatex_switches_to_xelatex_for_fontspec, explicit_pdflatex_stays_pdflatex_for_plain_documents, compile_failure_keeps_file_line_errors_and_context, parse_classic_bang_format_with_l_number, parse_keeps_file_and_drops_lines_of_packages, pdflatex_non_utf8_output_byte_0xed_does_not_raise_infra_error, the_budget_comes_from_the_whole_project_not_just_main, the_retry_does_not_double_past_the_ceiling, a_timeout_the_original_also_has_does_not_fail_a_fix_request, a_timeout_only_the_edit_has_still_fails, a_real_error_in_strict_mode_still_fails.

### Task 1 evidence (real pdfTeX 3.141592653-2.6-1.40.29, TeX Live 2026, run before any code change)

**Mechanism 1: stale siblings.** I wrote a temp `UPLOADS_BASE_DIR/<id>/` containing `main.tex` (`\input{chapter}`) and `chapter.tex` = "CHAPTER VERSION OLD". I opened a real `CollabRoom` (Supabase stubbed out, disk persistence kept) and changed the chapter with `room.replace_file_text` without flushing. Then I called `compile_latex(MAIN, "pdflatex", project_id=<id>)` and read the PDF text with PyMuPDF:
```
room text after edit  : 'CHAPTER VERSION NEW\n'
disk chapter.tex      : 'CHAPTER VERSION OLD\n'
room dirty set        : ['chapter.tex']
compile WITHOUT flush (0.54s) success=True pdf words: ['Main', 'body.', 'CHAPTER', 'VERSION', 'OLD', '1']
flush wrote files     : 1 disk now: 'CHAPTER VERSION NEW\n'
compile AFTER flush   (0.43s) success=True pdf words: ['Main', 'body.', 'CHAPTER', 'VERSION', 'NEW', '1']
```

**Mechanism 2: cold cache / timeout.** I could not reproduce a cold run over 30s on this machine. With fresh `TEXMFVAR`/`TEXMFCACHE` directories, pdflatex took 0.25s (run 1) and 0.27s (run 2), and xelatex took 0.80s and 0.81s. The format files and fontconfig cache are system-wide and stay warm, and dropping the page cache needs root. So I showed the boundary instead. I compiled a real 154-char document (`lipsum` in a 150-iteration loop, `is_heavy_document=False`) with `compile_latex(engine="pdflatex")`:
```
timeout_seconds=1:  success=False wall=1.04s pdf=no   error_log: '[TIMEOUT] pdflatex exceeded 1s'
timeout_seconds=60: success=True  wall=3.55s pdf=yes
```
So a first run slower than the budget comes back as a `[TIMEOUT]` failure (the marker at compiler.py:1566), and a retry with a warm cache succeeds. After the change, a document that never terminates (`\def\x{\x}\x`) with the default budget returned `'[TIMEOUT] pdflatex exceeded 60s'` after 60.1s, which confirms the new default is the one in effect.

Repro scripts: `/tmp/claude-1000/-home-abin-overbranch/7db9a63a-427d-4e03-b4ee-b857b2b1c65f/scratchpad/repro_stale.py`, `.../repro_timeout.py`, `.../cold_timing.py` (run with `backend/.venv/bin/python`).

### Task 5 (queue warmup): **not added**
The evidence does not justify it. Timing `CompileQueue.submit` on a no-op job: submit #1 = 0.509ms, #2 = 0.186ms, #3 = 0.149ms. Creating the semaphore and executor lazily costs about 0.3ms once, which is negligible next to a compile (0.2–3.5s here) and far from the 30s timeout.
