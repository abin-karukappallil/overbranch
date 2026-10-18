# OverBranch — master plan

Numbered module plans live in [`plans/`](plans/). Each has a `00-README.md` with
its goal, its binding decisions, a dependency table and an acceptance checklist,
plus self-contained slice files that `/run-plan` dispatches to `slice-worker`
agents.

Architecture, commands and environment variables are in the repo root
[`CLAUDE.md`](../CLAUDE.md); the collaboration design is in
[`COLLABORATION.md`](../COLLABORATION.md).

## Module execution order

| NN | Plan | Summary |
| --- | --- | --- |
| 01 | [Editor mentions, touch UX, and PDF import fidelity](plans/01-mentions-touch-and-pdf-import/00-README.md) | `@`-mention selected Monaco lines to the agent; mobile undo/redo and clipboard fixes; compile busy-vs-broken handling and a collab flush before compiling; durable, resumable PDF→LaTeX jobs; an editable template conversion mode. Requires nothing. |

## Conventions

- **Gate:** `tools/verify-slice.sh [spec …]` — `tsc --noEmit`, pytest, and the
  esbuild/node client checks. With no arguments it runs everything.
- **Do not run `bun run lint`** — ESLint is broken in this repo.
- **Six backend pytest failures are pre-existing** on this machine and are not a plan's fault:
  `tests/test_compile_gate_truth.py::test_recovery_success_still_reports_errors`, plus five in
  `tests/test_provider_fallback.py` (the repo `.env` sets a different `LLM_FALLBACK_CHAIN` /
  `OPENROUTER_FALLBACK_MODEL` than those tests expect). `CLAUDE.md` says two; six reproduce here.
  Measuring a baseline needs the repo `.env` and the full local `backend/tests/` directory — a bare
  `git worktree` has neither (both are gitignored) and will under-report.
- `tools/verify-slice.sh` with no arguments reports `FAIL pytest (all)` whenever *any* test fails,
  including the six baseline ones. It compares exit codes, not a baseline, so read the failure list
  rather than the summary line.
- Frontend tests are plain `.mjs` files bundled by esbuild and registered in
  `scripts/run-collab-tests.sh`; backend tests are pytest under `backend/tests/`.
- Agent and compile bugs are reproduced against real `pdflatex` and real traces
  before they are fixed.
