# 01/05 — Job store durability and resume

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: none · Parallel with: 01/01, 01/02, 01/03 (frontend), 01/04 (`agent_routes.py`, `agent_loop.py`), 01/06 (`main.py`, `compiler.py`, `compile_queue.py`). **`backend/pdf2latex/pipeline.py` belongs to slice 07 — see Task 4 for the one narrow exception.**

## Decisions you need
M10 (job directory default), M11 (resume and 404/403 split) — run `grep -E '^\| M1(0|1) ' 00-README.md`.

## Read first
- `backend/pdf2latex/jobs.py` — all 150 lines: `job_root`, `job_dir`, `_write_atomic`, `create_job`, `load_job` (and its `STALE_AFTER_S` flip), `update_job`, `update_page`, `active_job_for`, `public_view`, `purge_old_jobs`. Note `TERMINAL = {"done","error","needs_confirmation","cancelled"}`.
- `backend/pdf2latex/config.py:62-87` — `get_settings`, especially the `job_dir` default at :66.
- `backend/pdf2latex/runner.py` — all 77 lines: `_running_tasks`/`_tasks`, `is_job_running`, `cancel_job`, `_spawn`, `start_job`.
- `backend/routes/pdf_convert.py` — `_owned_job` at :65 (the shared 404), the GET poll route, the POST create route and its `cancel_previous` at :144-151.
- `backend/services/guest_cleanup.py:122-123` — the only caller of `purge_old_jobs`.
- `docker-compose.yml:23-25` and `docker-compose.backend.yml:18-20` — the bind mounts; and `entrypoint.sh:32-39` for `--limit-max-requests 10000`.

## Background: the bug you are fixing
A 33-page import dies with "This conversion job no longer exists". `job_dir` defaults to `tempfile.gettempdir()/overbranch_pdf2latex_jobs`, but **only `./uploads` is bind-mounted**. When uvicorn recycles itself at 10000 requests, or the container restarts, `/tmp` goes and the job directory with it, so the next poll 404s. The in-memory asyncio task dies with the worker too, so even a surviving directory would stall at "running" until `STALE_AFTER_S` (900s) flips it to an error.

## Scope (files you own)
- `backend/pdf2latex/config.py`
- `backend/pdf2latex/jobs.py`
- `backend/pdf2latex/runner.py`
- `backend/routes/pdf_convert.py`
- `.env.example`
- `docker-compose.yml`, `docker-compose.backend.yml`
- `backend/tests/test_pdf2latex_jobs.py` (new)

## Tasks

1. **Durable default (M10).** In `config.py:66`, change the fallback from the system temp dir to `<repo>/uploads/pdf2latex_jobs`. Derive the repo root the same way `config.py` already derives `_root_env` (`Path(__file__).resolve().parent.parent.parent`), so it works both in the container (`/app/uploads`) and from a dev checkout. `PDF2LATEX_JOB_DIR` still overrides it. Update the `.env.example:98` entry to document the new default rather than leaving it blank-with-temp-semantics. In both compose files, confirm `./uploads` is mounted (it is) and add a short comment above the mount saying that in-flight PDF import jobs live under it, so nobody "optimises" it away.

2. **Honest status codes (M11).** Split `_owned_job` (:65) so the caller can distinguish the two cases it currently collapses into one 404:
   - job directory/`status.json` absent → `HTTPException(404, detail={"code": "job_unknown", "message": "Conversion job not found."})`
   - job found but `state["owner"] != auth["user_id"]` → `HTTPException(403, detail={"code": "job_forbidden", "message": "You do not have access to this conversion job."})`
   Keep the detail a dict in both cases so the frontend can branch on `code`. Apply it to every route that uses `_owned_job` (poll, cancel, commit, preview), not just the poll.

3. **Resume on poll (M11).** In the GET poll route, after loading the job and before returning: when the status is **non-terminal** and `runner.is_job_running(job_id)` is `False`, relaunch it with `runner.start_job(..., resume=True)` and set `message="Resuming after an interruption…"` via `update_job`. Guard against a relaunch storm — the poll fires every 1.5s — by recording a `resumed_at` timestamp in the job state and refusing to relaunch again within **30 seconds**. Record a `resume_count` and give up with `status="error"` and a clear message after **3** attempts, so a job that cannot make progress does not loop forever.

4. **`runner.start_job(resume=...)` (the pipeline exception).** Add the `resume: bool = False` keyword to `start_job` and `_spawn` in `runner.py`, and pass it into the pipeline entry point. Slice 07 owns `pipeline.py`, so your change there is limited to **exactly one thing**: add a `resume: bool = False` keyword parameter to the pipeline's run entry point and, at the top of its per-page loop, skip any page whose `status == "done"` in the loaded job state and reuse its saved `.tex` rather than regenerating it. Touch nothing else in that file. Name the function and line range you changed in your `## Result` so slice 07 can rebase onto it.

5. **Stale-state honesty in `jobs.py`.** `load_job` currently rewrites a stale running job to `status="error"` **in the returned dict only** — it never persists it, so every caller recomputes it. Leave that behaviour (it is deliberate: a resumable job should not be written off on disk), but add a comment saying so, since it now interacts with the resume path: a job that `load_job` reports as stale must still be resumable, so do **not** treat the synthesised `error` status as terminal when deciding whether to resume. This is the subtle interaction in this slice — get it right.

6. **`backend/tests/test_pdf2latex_jobs.py`.** Pytest with `monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path))`. Cover:
   - the default `job_dir` (with the env var unset) ends with `uploads/pdf2latex_jobs` and is **not** under `tempfile.gettempdir()`;
   - `create_job` → `load_job` round-trips, and `update_page` updates one page without disturbing the others;
   - an unknown job id raises 404 with `code == "job_unknown"`;
   - a job owned by someone else raises 403 with `code == "job_forbidden"`;
   - a non-terminal job whose `updated_at` is older than `STALE_AFTER_S` is reported stale but is **still considered resumable**;
   - the 30-second resume debounce: two polls inside the window trigger exactly one `start_job`;
   - `resume_count` reaching 3 moves the job to `status="error"` and stops relaunching;
   - `purge_old_jobs` leaves a fresh job alone and removes one older than the TTL.

## Done when
- `tools/verify-slice.sh backend/tests/test_pdf2latex_jobs.py` passes.
- `cd backend && pytest tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py -v` still passes (or skips cleanly without a TeX engine) — your change must not alter conversion output.
- `grep -n "pdf2latex" .env.example docker-compose.yml docker-compose.backend.yml` shows the documented default.
- Append `## Result`, naming the pipeline function and line range you touched under a heading `### For slice 07`.

## Result

- `backend/pdf2latex/config.py` — `job_dir` default is now `<repo>/uploads/pdf2latex_jobs` (via a new `_repo_root`); dropped the unused `tempfile` import.
- `backend/pdf2latex/jobs.py` — split out `_read_raw`; `load_job` keeps the stale rewrite (returned dict only, now commented) and adds `stale: True`; new `is_resumable(state)` (non-terminal OR stale); `update_job`/`update_page` now read the raw state so the synthesised stale "error" can never be persisted by a progress write.
- `backend/pdf2latex/runner.py` — `start_job(..., resume=False, job_id=None)` and `_spawn(..., resume)`. Resume reuses the existing job, reads `input.pdf` back from the job dir, takes `overwrite` from state. Non-resume start now stores `overwrite` in state and both paths record `runner_pid`.
- `backend/routes/pdf_convert.py` — `_owned_job` split into 404 `job_unknown` / 403 `job_forbidden` (dict detail, applies to poll, cancel, commit, preview); `_resume_if_interrupted` on the poll route: 30s debounce (`resumed_at`), `resume_count`, error after 3, message "Resuming after an interruption…". Resume decision uses `jobs.is_resumable`, not the status field, so a stale-synthesised error still resumes while a pipeline-persisted error does not. Extra guard `_running_in_other_worker` (live foreign `runner_pid`, ignored once stale) because `is_job_running` is per process and `WORKERS=2` would otherwise double-run a job. Called on the loop thread, not `to_thread`, because `start_job` needs the running loop.
- `backend/pdf2latex/pipeline.py` — see handoff.
- `.env.example`, `docker-compose.yml`, `docker-compose.backend.yml` — documented default and the mount comment.
- `backend/tests/test_pdf2latex_jobs.py` — new, 32 tests.

Gate (`tools/verify-slice.sh backend/tests/test_pdf2latex_jobs.py`):
```
PASS  typecheck
PASS  pytest tests/test_pdf2latex_jobs.py
```
(32 passed.) `tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py`: 31 passed.

Skipped / deviations: none skipped. One deviation from the brief: it assumed each page's `.tex` was already saved, but the pipeline only kept bodies in memory (`ctx.bodies`), so "reuse its saved .tex" had nothing to read. I added the saving (below), which is two one-line calls inside `_process_page` beyond the single skip.

### For slice 07
All in `backend/pdf2latex/pipeline.py`, nothing else touched:
- New helpers `_body_path`, `_save_body`, `_reuse_saved`, inserted immediately above `_process_page` (about lines 467-492). `_save_body` writes `<job>/pages/page_N.tex` atomically; `_reuse_saved(ctx, page, saved)` restores a page whose status.json entry is `done` and whose `.tex` exists (loads `ctx.bodies[n]`, copies matching `PageReport` fields), else returns False so the page is redone.
- `_process_page`: added `_save_body(ctx, n, body)` right after each of the two `ctx.bodies[n] = body` assignments (the `not ctx.has_tex` early return and the final one), before `_page_status`.
- `run_conversion`: new keyword `resume: bool = False` (signature, about line 649); `saved_pages` read just before `report = ConversionReport(...)`; the converting `asyncio.gather` now filters `if not _reuse_saved(ctx, p, saved_pages)` (about line 698).
Only pages with status `done` are reused; `below_threshold` and `failed` are regenerated. The merge-time fallback replacement in `_merge_and_compile` is not persisted to the page file.
