# 01/10 — Wire `mode` from the HTTP route to the pipeline

Plan folder: [`00-README.md`](00-README.md) · Model: Sonnet · Prerequisites: 01/05, 01/07 · Parallel with: 01/08 (frontend only: `components/pdf-import/*`, `lib/pdf-import-poll.ts`). No overlap.

## Why this slice exists
A gap the orchestrator found when gating slice 07. `pdf2latex/pipeline.py:708` now accepts
`mode: str = "exact"`, but **neither `pdf2latex/runner.py` nor `routes/pdf_convert.py` mentions `mode` at all**,
so there is no way to reach template mode over HTTP and the M13 feature is inert. Both files
belonged to slice 05, which finished before `mode` existed, and slice 07 could not touch them.
Verify the gap yourself before fixing it:

```bash
grep -n "mode" backend/pdf2latex/runner.py backend/routes/pdf_convert.py   # expect no mode plumbing
grep -n "def run_conversion" -A3 backend/pdf2latex/pipeline.py             # expect mode: str = "exact"
```

## Decisions you need
M13 (`mode: "exact" | "template"`, default `"exact"`) — run `grep -E '^\| M13 ' 00-README.md`.
M11 (resume) — run `grep -E '^\| M11 ' 00-README.md`: a resumed job must keep the mode it started with.

Slice 07's `## Result` in `07-template-mode.md` specifies the field: `mode: str = Form("exact")` on
`POST /api/convert/pdf`, values `"exact" | "template"`. Slice 05's `## Result` in `05-job-durability.md`
describes the resume path and `start_job(resume=..., job_id=...)`.

## Read first
- `backend/routes/pdf_convert.py` — the `POST /api/convert/pdf` handler and its existing `Form(...)` parameters, `cancel_previous` (~:144-151), and the GET poll route's resume call added by slice 05.
- `backend/pdf2latex/runner.py` — `start_job` and `_spawn` (slice 05 added `resume` and `job_id` kwargs here; follow exactly that pattern for `mode`).
- `backend/pdf2latex/jobs.py` — `create_job` and `update_job`, for persisting `mode` in `status.json`.
- `backend/pdf2latex/pipeline.py:708-714` — the `run_conversion` signature you are feeding.

## Scope (files you own)
- `backend/routes/pdf_convert.py`
- `backend/pdf2latex/runner.py`
- `backend/pdf2latex/jobs.py`
- `backend/tests/test_pdf2latex_mode_wiring.py` (new)

## Tasks

1. **Route.** Add `mode: str = Form("exact")` to the `POST /api/convert/pdf` handler. Validate it: anything other than `"exact"` or `"template"` is rejected with `HTTPException(400, detail={"code": "bad_mode", "message": "mode must be 'exact' or 'template'."})`. Do not silently coerce an unknown value — a typo that quietly produces exact mode is exactly the bug this slice exists to prevent.

2. **Persist it.** Store `mode` in the job state at `create_job` time (add the field in `jobs.create_job`, defaulting to `"exact"` so older job directories still load). It must appear in `public_view` so the frontend can show which mode a job is running.

3. **Runner.** Add `mode: str = "exact"` to `start_job` and `_spawn` in `runner.py` and pass it to `run_conversion(mode=mode)`. Follow the exact pattern slice 05 used for its `resume` and `job_id` kwargs.

4. **Resume keeps the mode (M11).** The GET poll route's resume path must read `mode` back from the job state and pass it to `start_job`, so a 33-page template import that is interrupted resumes in **template** mode, not exact. Slice 07 already reads the mode back inside the pipeline on resume; your job is to make sure the value reaching it is the stored one, not the default.

5. **`backend/tests/test_pdf2latex_mode_wiring.py`.** Pytest, with `monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path))`. Cover:
   - posting with no `mode` creates a job whose stored mode is `"exact"`;
   - posting `mode="template"` stores `"template"` and the value reaches `run_conversion` (assert with a stubbed `run_conversion`);
   - posting `mode="Template"` or `mode="nonsense"` returns **400** with `code == "bad_mode"` and creates no job;
   - `start_job(..., mode="template")` calls `run_conversion` with `mode="template"`;
   - a job created in template mode and then resumed calls `run_conversion` with `mode="template"` **and** `resume=True`;
   - a job-state dict with no `mode` key (an older directory) loads and resumes as `"exact"` without raising;
   - `public_view` includes `mode`.

## Done when
- `tools/verify-slice.sh backend/tests/test_pdf2latex_mode_wiring.py` passes.
- `cd backend && pytest tests/test_pdf2latex_jobs.py tests/test_pdf2latex_template_mode.py tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py -q` passes (88 tests before your change).
- `grep -n "mode" backend/pdf2latex/runner.py` shows the kwarg threaded through to `run_conversion`.
- Append `## Result`, stating the exact field name and the `public_view` key so slice 08 can bind to it.

## Result

- `backend/routes/pdf_convert.py` — `POST /api/convert/pdf` takes `mode: str = Form("exact")`; anything but `exact`/`template` is `400 {"code": "bad_mode", "message": "mode must be 'exact' or 'template'."}`, checked before the upload is read so no job or project is created. `start_job(..., mode=mode)`. `_resume_if_interrupted` passes the stored mode back to `start_job(resume=True)`; slice 05's debounce, `resume_count`, `is_resumable`, `_running_in_other_worker` and the 404/403 split are untouched.
- `backend/pdf2latex/runner.py` — `start_job(..., mode="exact")` and `_spawn(..., mode)` thread the value to `run_conversion(mode=...)`. An unknown mode raises `ValueError` before a job is created. On `resume=True` the argument is ignored and the stored mode is used (M11).
- `backend/pdf2latex/jobs.py` — `MODES`, `DEFAULT_MODE`, `job_mode(state)`; `create_job(..., mode="exact")` stores `state["mode"]` only when it is not `"exact"` (so an exact job's `status.json` is byte-identical to before, which `test_pdf2latex_template_mode.py::test_mode_defaults_to_exact` asserts); `public_view` always adds `mode`, reading a missing key as `"exact"`.
- `backend/tests/test_pdf2latex_mode_wiring.py` — new, 18 tests.

Deviation: `run_conversion` and the route's resume call are given `mode=` only when it is `"template"`. Existing `test_pdf2latex_jobs.py` stubs `run_conversion`/`start_job` with fixed signatures and exact kwargs, and `"exact"` is the default everywhere, so behaviour is the same.

Gate (`tools/verify-slice.sh backend/tests/test_pdf2latex_mode_wiring.py`):
```
PASS  typecheck
PASS  pytest tests/test_pdf2latex_mode_wiring.py
```
`pytest tests/test_pdf2latex_jobs.py tests/test_pdf2latex_template_mode.py tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py`: 88 passed.

### For slice 08
- Request field: `mode` (multipart form field on `POST /api/convert/pdf`), `"exact"` | `"template"`, default `"exact"`. A 400 with `detail.code == "bad_mode"` means an invalid value.
- Poll key: `mode` on `GET /api/convert/pdf/{job_id}` (the `public_view` key), always present, `"exact"` or `"template"`.
