# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Frontend (Next.js)
```bash
bun install          # install dependencies
bun dev              # start dev server on :3000
bun run build        # production build
bun run db:generate  # generate Drizzle migrations
bun run db:push      # push schema to DB (no migration file)
```
ESLint is currently broken — do not run `bun run lint`.

### Backend (FastAPI)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# Collaboration requires exactly one worker:
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

### Tests
```bash
# Run a single backend test file
cd backend && pytest tests/test_agent_json_latex.py -v

# All backend tests (two pre-existing failures are expected)
cd backend && pytest -v

# Specific suites
cd backend && pytest tests/test_collab_sync.py tests/test_collab_auth.py -v
bash scripts/run-collab-tests.sh   # Monaco binding + AI line-diff (needs esbuild)

# PDF→LaTeX integration (skipped without a TeX engine)
cd backend && pytest tests/test_pdf2latex_*.py -v
```

Always reproduce agent/compile bugs with real `pdflatex` + traces before fixing. Prompt-only fixes have failed repeatedly.

## Architecture

### Two-process design
The app is split: a **Next.js frontend** (port 3000) communicates with a **FastAPI Python backend** (port 8000) via REST/SSE. The backend owns LaTeX compilation, the AI agent, and the collaboration WebSocket server. The frontend owns auth sessions (Better Auth), tRPC API, and the Monaco editor.

### Frontend
- **`app/`** — Next.js App Router pages and layouts.
- **`trpc/routers/`** — tRPC procedures for projects, auth, dashboard, notifications, etc. The `ai.ts` router proxies agent calls to the Python backend.
- **`components/editor/`** — The main editor layout, Monaco integration, PDF viewer, collaboration presence bar.
- **`lib/collab/`** — Yjs/y-websocket browser-side CRDT bindings and the hand-written Monaco binding (`monaco-binding.ts`). Avoids the `y-monaco` npm package because OverBranch loads Monaco from CDN, not as a bundled package.
- **`lib/`** — Shared utilities: `latex-edit-apply.ts` (applying AI edits), `pdf-sync.ts` (SyncTeX), `inline-diff.ts`, `EditHistoryStore.ts`.
- **`db/schema.ts`** — Drizzle ORM schema (Postgres via Supabase). `db:push` is used instead of migrations in most cases.

### Backend
- **`main.py`** — FastAPI app; routes compilation (`/api/compile`), SyncTeX (`/api/synctex/*`), and mounts the agent, collab, and storage routers.
- **`opencode/agent_loop.py`** — The core AI agent (ReAct loop). Reads the LaTeX document, makes tool-called edits in a `ShadowWorkspace`, shadow-compiles each step to verify correctness, and streams SSE events to the frontend `AgentReasoningWindow`.
- **`opencode/tools.py`** — Tool definitions (`replace_text`, `grep_document`, etc.) executed inside the agent loop.
- **`providers/router.py`** — `ProviderRouter` selects among Groq, Gemini (Web2API), OpenRouter, and NVIDIA based on availability and fallback chain (`LLM_FALLBACK_CHAIN` env var). The Web2API gateway **rejects image parts**; do not send images through it.
- **`compiler.py`** / **`compile_queue.py`** — Bounded async queue wrapping `pdflatex`/`latexmk` subprocess calls.
- **`collab/`** — Server-side Yjs room management using `pycrdt`. One room per project, one process only (see scaling note in COLLABORATION.md). `routes/collab_routes.py` handles WebSocket auth (Better Auth cookie or one-time HMAC ticket).
- **`project_storage.py`** — File storage under `uploads/projects/<id>/` + Supabase `latex_documents` table. Exposes `/api/projects/get-file` — always use this proxy for asset downloads, never direct backend URLs.
- **`routes/agent_routes.py`** — SSE endpoint `/api/agent/opencode` that drives the agent loop.
- **`synctex_service.py`** — Forward/backward SyncTeX lookups against the last compiled `.synctex.gz`.
- **`edit_validator.py`** — Coverage and expansion validation; guards against AI edits that delete too much content.
- **`document_index.py`** — Chunking / indexing the LaTeX document for targeted context delivery to the agent.

### Auth
Better Auth (Next.js) issues sessions stored in Postgres. The FastAPI backend reads the same session table via Supabase to authenticate API calls. Guest sessions use a short-lived HMAC token (`GUEST_TOKEN_SECRET`).

### Collaboration
Realtime co-editing uses Yjs (browser) + pycrdt (server). The room is authoritative: the Python server holds the full CRDT state, persists to disk + Supabase, and relays updates between clients. **The backend must run as a single uvicorn worker while collaboration is enabled.** See COLLABORATION.md for full design notes.

### AI agent
The agent uses a multi-step tool-calling loop (not RAG). It operates on a shadow copy of the document, calls `replace_text`/`insert_text`/`grep_document` tools, shadow-compiles after each edit, auto-repairs compile failures (up to `SHADOW_COMPILE_MAX_RETRIES`), and returns a diff the user accepts or rejects. Traces are stored under `/tmp/overbranch_traces` (gitignored). Spec tests for agent features that were previously reverted live in `backend/tests/` and are the acceptance criteria for re-implementing those features.

## Key env vars

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres (Supabase) connection string |
| `BETTER_AUTH_SECRET` | Session signing |
| `SUPABASE_*` | Supabase project credentials |
| `GEMINI_WEB2API_BASE_URL` / `_API_KEY` | Primary LLM provider (Gemini via Web2API) |
| `GROQ_API_KEY` | Groq fallback |
| `OPENROUTER_API_KEY_1..5` | OpenRouter fallback (rotated) |
| `LLM_FALLBACK_CHAIN` | Ordered fallback, e.g. `openrouter:minimax/minimax-m3` |
| `NEXT_PUBLIC_BACKEND_URL` | Frontend → backend URL |
| `COLLAB_ENABLED` | Set to `0` to allow multiple uvicorn workers |

Copy `.env.example` to `.env` at the repo root; the backend also loads from root `.env`.
