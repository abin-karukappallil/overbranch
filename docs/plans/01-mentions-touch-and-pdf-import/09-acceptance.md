# 01/09 — Acceptance

Plan folder: [`00-README.md`](00-README.md) · Model: Opus · Prerequisites: 01/01–01/08 · Parallel with: none.

## Decisions you need
All of them, as the specification you are checking against — run `grep -E '^\| M[0-9]+ ' 00-README.md`.

## Read first
- `00-README.md` — the `## Acceptance checklist`. Every row gets a verdict.
- The `## Result` section of each of `01-mention-core.md` … `08-import-dialog.md`, for what was actually built and anything a slice deliberately skipped.

## Scope (files you own)
- This file (append `## Result`)
- The evidence directory the dispatch names. **No source file changes — you do not fix code.**

## Tasks

1. **Run the full gate** and record the output verbatim:
   ```bash
   tools/verify-slice.sh
   ```
   This runs `tsc --noEmit`, the whole backend pytest suite and `scripts/run-collab-tests.sh`.

2. **Separate the baseline.** Exactly **two** backend test failures are pre-existing (`CLAUDE.md`). Name them explicitly, and confirm no third failure appeared. A new failure is a FAIL row, not baseline.

3. **Verify each checklist row**, writing one evidence file per row named `<row-number>-<slug>.txt` containing the command and its real output. Classify each PASS, FAIL or MANUAL:
   - Rows about pure logic (mention cap and truncation, clipboard fallback order, 429 classification, poll classification, `StyleProfile` derivation, job 404/403 split, resume debounce) are checkable by running the specs — these should be PASS or FAIL, never MANUAL.
   - Rows needing a real browser, a touch device or a physical keyboard — the floating `@ Mention` widget appearing on selection, `Ctrl/Cmd+M`, the touch callout's Undo/Redo and `@` buttons, the manual copy sheet, touch paste not desyncing the room — are **MANUAL**. Give numbered steps a human can follow, including how to reach a phone-width viewport.
   - The restart-resume row needs a running backend: if you can start one, exercise it and mark PASS; otherwise MANUAL with the exact commands.
   - For every test you cite, include the `grep -n` proving the test name exists in its file.

4. **Check cross-slice integration** the individual slices could not:
   - `grep -n "mentions" backend/routes/agent_routes.py components/editor/EditorLayout.tsx` — the field name the frontend sends matches what the backend accepts (M3). A mismatch here is a FAIL even though both slices passed.
   - `grep -rn "mode" components/pdf-import/usePdfConversionJob.ts backend/routes/pdf_convert.py` — the template-mode field name matches end to end (M13).
   - `grep -n "handleCustomCopy\|handleCustomPaste\|safe-mobile-paste" components/editor/EditorLayout.tsx` returns nothing (M7).
   - `grep -n "no longer exists" components/pdf-import/` returns nothing (M12).
   - `grep -rn "tempfile.gettempdir" backend/pdf2latex/config.py` no longer supplies the job-dir default (M10).

5. **Write the runbook** into your `## Result`: how to enable template mode, what `PDF2LATEX_JOB_DIR` now defaults to and what to set it to in a non-Docker deployment, and how to confirm a resumed job.

## Done when
- Every acceptance row has a verdict backed by an evidence file you wrote.
- `## Result` lists PASS / FAIL / MANUAL row numbers, the two baseline failures by name, and the runbook.
- You changed no source file (`git diff --stat` shows only this plan file).

## Result

Evidence: `/tmp/claude-1000/-home-abin-overbranch/7db9a63a-427d-4e03-b4ee-b857b2b1c65f/scratchpad/acceptance-evidence/`, one file per checklist row (`01-…` to `18-…`), plus `00-cross-slice-integration.txt` for Task 4. Each file holds the exact commands and their full output. Every cited test name is backed by a `grep -n` in the same file.

| Verdict | Rows |
| --- | --- |
| PASS | 4, 5, 9, 10, 11, 12, 13, 14, 16, 17, 18 |
| FAIL | 7, 15 |
| MANUAL | 1, 2, 3, 6, 8 |

Rows are numbered in the order of the README's `## Acceptance checklist`.

**FAIL 7: manual copy sheet.** `MobileEditorAssist` Copy and Cut act on `copyText() === false` and open the sheet. The third `copyText` call site, `components/editor/CopyButton.tsx:36` (the copy button on chat messages), does `if (!ok) return;`, so a failed copy there still does nothing. M6 says every call site must open the sheet. No slice listed `CopyButton.tsx`. Six more components call `navigator.clipboard.writeText` directly and have no fallback (FileAnalyzerModal, ProjectFilesPanel, CollaboratorAvatars, ChatMessageContent, InlineDiffEditor, landing/SelfHosting). These predate the plan.

**FAIL 15: no per-span inline `\fontsize` in template mode.** The preamble always defines `\obBodyFont`, `\obHeadingI..III` and `\obAccentColor`. Results by PDF:
- The synthetic 18-page PDF has 0 inline `\fontsize` in the body.
- The user's own lecturer template ("Seminar Report - Report Format.pdf", already imported twice in `uploads/pdf2latex_jobs`) still has **435** body lines with inline `\fontsize` after re-running it on the current code. It has 101 `\obBodyFont` uses, and exact mode has 547 inline `\fontsize`. Runs that differ from the body style only in colour (107 blue runs at 12bp regular), weight or slant are not mapped to a style command.
- `rules.pdf` emits a bold body-size run inline, even though `\obHeadingII` is exactly `\obBodyFont\bfseries`.

Slice 07 calls this deliberate ("one-off runs keep inline `\fontsize`"). On the real template these runs are the majority, not one-offs.

**Rows passed with caveats:**
- **Row 9:** the classifier, the backoff and the backend 429 were exercised. The toast and retry loop in `handleCompile` were read in the code, not rendered.
- **Row 16:** no live model flagged the PDF, because the configured Gemini Web2API gateway returned an empty response to every call on this machine. That live run did show M14's "logged and ignored" path: the job still finished. The override was proven through the real pipeline on a real PDF, with only the wire reply scripted.

**Live runs.** Rows 11, 12, 13, 15 and 17 ran against the real backend app (`main:app` under uvicorn on :8011–8013, real routes, runner, jobs, pipeline and pdflatex). Only auth, the Supabase project-ownership check, the final project write and the guest-cleanup scheduler were stubbed. For row 13:
- An 18-page import was SIGKILLed after 5 pages and the server restarted.
- The first poll after the restart returned `200 "Resuming after an interruption…"` with `resume_count` 1.
- `page_1..5.tex` kept their mtimes, and pages 6–18 were written after the restart.

Row 10 was proven end to end, using a real CollabRoom, the real `compile_endpoint` and pdflatex. The chapter edited in the room shows as NEW in the compiled PDF. With the flush disabled, the same run shows OLD.

**Task 4 (cross-slice integration): all five checks pass.**
- M3: the frontend and backend both use the field name `mentions`.
- M13: `mode` is wired dialog → form field → route → `start_job` → `_spawn` → `run_conversion`. The live POST with `mode=template` came back with poll `mode: "template"`.
- M7: the grep for the removed paste and copy handlers is empty.
- M12: the grep for "no longer exists" is empty.
- M10: the grep for `tempfile.gettempdir` is empty.

**Other observations (no row of their own):**
- **Chip clearing (row 3):** chips are cleared when the send is dispatched, before the response arrives, and only on the typed-message path. M2 says "after a successful send", so a failed send loses the chips.
- **Non-429 errors (row 9):** a non-429 error status such as 500 sets `errorLog` to its detail. M8 says only a `200 success:false` does.
- **Template margins:** the measured template margins for the seminar PDF are `right=1.13mm`, which looks wrong.

**Baseline.** The slice text and `CLAUDE.md` say "two" pre-existing failures. The baseline measured at HEAD on this machine is **6 failed, 712 passed**:
- `tests/test_compile_gate_truth.py::test_recovery_success_still_reports_errors`
- `tests/test_provider_fallback.py::test_primary_failure_falls_back_to_openrouter_minimax_m3[429]`
- `tests/test_provider_fallback.py::test_primary_failure_falls_back_to_openrouter_minimax_m3[402]`
- `tests/test_provider_fallback.py::test_primary_failure_falls_back_to_openrouter_minimax_m3[503]`
- `tests/test_provider_fallback.py::test_primary_failure_falls_back_to_openrouter_minimax_m3[504]`
- `tests/test_provider_fallback.py::test_minimax_m3_aliases_do_not_map_to_text_01`

The five provider failures happen because the repo `.env` sets `LLM_FALLBACK_CHAIN` / `OPENROUTER_FALLBACK_MODEL` to a different value than these tests expect.

After the plan, `tools/verify-slice.sh` shows **6 failed, 809 passed**: the same six IDs, no new failure, and 97 more tests. `tsc` and `scripts/run-collab-tests.sh` pass. The script's `FAIL pytest (all)` line only means it compares exit codes rather than the baseline. `git diff --stat` is identical before and after this check: no source file was changed. The harness left 9 job directories under `uploads/pdf2latex_jobs/`, all with owners starting `acc-`. Job TTL purging removes them, or they can be deleted by hand.

### Runbook

**Enable template mode.** No env flag is needed.
- **UI:** in the Import PDF dialog, pick "Editable template" (the default is "Exact copy").
- **API:** `POST /api/convert/pdf` takes the multipart field `mode=template`. It defaults to `exact`. Any other value returns `400 {"code":"bad_mode"}`, and no job is created.
- **Poll:** `GET /api/convert/pdf/<job_id>` always returns `mode`.
- **Rule detection** uses the copilot's LLM (`GEMINI_WEB2API_*`) with one text-only call over the first 3 pages or fewer. If that call fails, the job still completes from measured styles. `report.style_profile` is present in every template run. `report.template_rules` is present only when the document states rules. A resumed job keeps its stored mode and does not run detection again.

**`PDF2LATEX_JOB_DIR`.**
- **Default:** when it is unset or empty, jobs go to `<repo>/uploads/pdf2latex_jobs`. That is `Path(backend/pdf2latex/config.py).parent.parent.parent / "uploads" / "pdf2latex_jobs"`.
- **Docker:** both compose files build images with the backend at `/app/backend`, so the default is `/app/uploads/pdf2latex_jobs`, which is inside the `./uploads:/app/uploads` bind mount. Leave the variable empty there.
- **Non-Docker** (systemd, bare uvicorn, a PaaS):
  - Leave it empty only if the checkout's `uploads/` is on persistent disk.
  - Otherwise set an absolute path on a persistent volume that every worker on the host shares and the backend user can write to, e.g. `PDF2LATEX_JOB_DIR=/var/lib/overbranch/pdf2latex_jobs`.
  - Never point it at `/tmp`: tmpfs, systemd `PrivateTmp` and container `/tmp` are wiped on restart, which brings back the "job no longer exists" bug.

**Confirm a resumed job.**
1. A resume only starts on a poll. The open import dialog polls, or you can poll yourself with `curl -b <session cookie> $BACKEND/api/convert/pdf/<job_id>`.
2. After a restart, the first poll returns `200` with `"message": "Resuming after an interruption…"` and an incremented `resume_count`. It is never a 404.
3. On disk, `<job_dir>/<job_id>/status.json` shows the new `runner_pid`, plus `resumed_at` and `resume_count`.
4. Pages finished before the interruption are not regenerated: `stat -c '%y %n' <job_dir>/<job_id>/pages/page_*.tex` shows their old mtimes, and only the remaining pages get new ones.
5. Relaunches are debounced to once per 30s. After 3 resumes, the job ends with "Conversion failed: it was interrupted 3 times without finishing."
6. An unknown id returns `404 {"code":"job_unknown"}`. Another user's job returns `403 {"code":"job_forbidden"}`.
