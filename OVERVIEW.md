# OverBranch — Comprehensive Method, Architecture & Codebase Guide

> ⚠️ **MANDATORY MAINTENANCE DIRECTIVE:**
> **Update this file (`OVERVIEW.md`) after each and every change to the codebase.**
> Whenever files, folders, routes, components, database schemas, services, or architectures are added, modified, renamed, or deleted, this document must be updated immediately to keep all descriptions, file indexes, and architectural references 100% synchronized with reality.

---

## Quick Reference & Fast Workflow Commands

### Frontend & Web Application (Next.js 15, React 19, TypeScript)
```bash
# Install dependencies
npm install  # or bun install

# Start Next.js development server (Port 3000)
npm run dev

# Build production bundle
npm run build

# Start production server
npm run start

# Run linter
npm run lint

# Generate Drizzle migration artifacts & push schema to PostgreSQL
npm run db:generate
npm run db:push
npm run db:migrate
npm run db:studio
```

### Backend Engine (Python 3.11+, FastAPI, Uvicorn, UV)
```bash
# Navigate to backend directory
cd backend

# Setup virtual environment and dependencies via uv or pip
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
# OR
pip install -r requirements.txt

# Run FastAPI development server with auto-reload (Port 8000)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run all Pytest test suites (no network; TeX-dependent tests skip without pdflatex/pdftoppm)
pytest tests/ -v

# Run specific focused test suites
pytest tests/test_locator.py -v                 # target resolution: node IDs, exact/normalized/fuzzy, ambiguity
pytest tests/test_transactions.py -v            # heal scoping, duplicate guard, compile rollback, provider failure
pytest tests/test_agent_token_budget.py -v      # targeted context: prompt size independent of document length
pytest tests/test_resolve_edits_endpoint.py -v  # POST /api/agent/resolve-edits
pytest tests/test_provider_fallback.py -v       # fallback chain, 5-key rotation, cooldown recovery
pytest tests/test_justify_content.py -v         # fit_fragment ladder, long words, overflow detection
pytest tests/test_layout_repair.py -v           # render-aware layout repair: detect → map → fix → verify → rollback
pytest tests/test_pdf2latex_fidelity.py -v      # bold/size preservation, metric fonts, IRCTC ticket regression
pytest tests/test_converted_document_edits.py -v # agent edits on imported PDFs; fake-bold (overprinted) PDFs
pytest tests/test_agent_json_latex.py -v        # LaTeX decoded from the agent's JSON (escaped / raw / mixed)
pytest tests/test_compile_pre_heal.py -v        # compile pre-heal gating & error lines mapped back to source
pytest tests/test_compile_gate_truth.py -v      # compile gate never reports success when TeX failed; strict fix mode
pytest tests/test_agent_compile_outcomes.py -v  # nothing ships uncompiled; partial fixes; repairs without an LLM round
pytest tests/test_write_gate.py -v              # validator magnitudes, healer correctness (\%, tikz, \end{document}), locator guard
pytest tests/test_required_packages.py -v       # missing \usepackage injection & error-driven _ / & repairs
pytest tests/test_collab_sync.py -v             # realtime rooms: CRDT merge, late joiners, restart, persistence
pytest tests/test_collab_auth.py -v             # realtime auth: tickets, roles, handshake, revocation, origins
```

### Realtime Collaboration Client Checks (Node, no test runner added)
```bash
# Yjs <-> Monaco binding (loop safety, convergence, per-user undo, cursors)
# and the AI-apply line diff. Bundled with the esbuild already in node_modules.
bash scripts/run-collab-tests.sh
```

### Full-Stack Docker Deployment
```bash
# Spin up complete stack (Next.js 3000 + FastAPI 8000 + PostgreSQL)
docker compose up --build -d

# Spin up backend only container
docker compose -f docker-compose.backend.yml up --build -d

# Automated production deployment script
bash deploy.sh
```

---

## Table of Contents

1. [High-Level Methodology & System Architecture](#1-high-level-methodology--system-architecture)
   - [Architectural Overview](#architectural-overview)
   - [Core Methodological Pipelines](#core-methodological-pipelines)
     - [A. OpenCode ReAct Agent Loop & Dynamic Adaptive Step Budgeting](#a-opencode-react-agent-loop--dynamic-adaptive-step-budgeting)
     - [B. Automated LaTeX Error Diagnostics & Deterministic Auto-Healing](#b-automated-latex-error-diagnostics--deterministic-auto-healing)
     - [C. Local Document Structural Analysis & Preservation Mapping](#c-local-document-structural-analysis--preservation-mapping)
     - [D. Multi-Turn Attached Context Session Store](#d-multi-turn-attached-context-session-store)
     - [E. Smart Context Strategy & Model Context Window Management](#e-smart-context-strategy--model-context-window-management)
     - [F. Scope Classification & AST Structural Chunk Replacement](#f-scope-classification--ast-structural-chunk-replacement)
     - [G. Document Environment Integrity & AST Auto-Repair](#g-document-environment-integrity--ast-auto-repair)
     - [H. Pre-Commit Validation & Deterministic Repair](#h-pre-commit-validation--deterministic-repair)
     - [I. Shadow Compilation & Compiler-Feedback Self-Correction](#i-shadow-compilation--compiler-feedback-self-correction)
     - [J. Regalia Presentation Standard & Theme Registry](#j-regalia-presentation-standard--theme-registry)
     - [K. PDF → LaTeX Per-Page Verification, Repair & Best-Version Selection](#k-pdf--latex-per-page-verification-repair--best-version-selection)
     - [L. Scanned Pages & Vector Art](#l-scanned-pages--vector-art)
     - [M. Cross-Stack Better-Auth Authentication & SQLAlchemy Session Verification](#m-cross-stack-better-auth-authentication--sqlalchemy-session-verification)
     - [N. Sliding-Window Rate Limiting & Concurrency Queue](#n-sliding-window-rate-limiting--concurrency-queue)
     - [O. PDF → LaTeX Importer (pdf2latex): Local Facts, Shared Preamble, Per-Page LLM](#o-pdf--latex-importer-pdf2latex-local-facts-shared-preamble-per-page-llm)
     - [P. SyncTeX Bidirectional Navigation](#p-synctex-bidirectional-navigation)
     - [Q. Structured Observability, Tracing & Performance Telemetry](#q-structured-observability-tracing--performance-telemetry)
     - [R. Layout Engine: justify_content, Defect Detection & Minimal Repair](#r-layout-engine-justify_content-defect-detection--minimal-repair)
     - [S. Target Resolution, Targeted Context & Transactional Edits](#s-target-resolution-targeted-context--transactional-edits)
     - [T. Provider Fallback Chain & Key Health](#t-provider-fallback-chain--key-health)
     - [U. Realtime Collaborative Editing (Yjs CRDT over WebSocket)](#u-realtime-collaborative-editing-yjs-crdt-over-websocket)
2. [Complete Repository & File Structure (As-Is Verbatim)](#2-complete-repository--file-structure-as-is-verbatim)
   - [Root Configuration & Deployment Files](#root-configuration--deployment-files)
   - [Frontend Application (`app/`)](#frontend-application-app)
   - [UI & Editor Components (`components/`)](#ui--editor-components-components)
   - [Backend Core Engine (`backend/`)](#backend-core-engine-backend)
   - [Backend OpenCode ReAct Subpackage (`backend/opencode/`)](#backend-opencode-react-subpackage-backendopencode)
   - [Backend Providers Gateway (`backend/providers/`)](#backend-providers-gateway-backendproviders)
   - [Backend HTTP API Routes (`backend/routes/`)](#backend-http-api-routes-backendroutes)
   - [Backend PDF → LaTeX Importer (`backend/pdf2latex/`)](#backend-pdf--latex-importer-backendpdf2latex)
   - [Backend Conversion & Support Services (`backend/services/`)](#backend-conversion--support-services-backendservices)
   - [Backend Curated LaTeX Templates (`backend/templates/`)](#backend-curated-latex-templates-backendtemplates)
   - [Backend Test Suite & Evaluation Harness (`backend/tests/`)](#backend-test-suite--evaluation-harness-backendtests)
   - [Database Layer (`db/` & `drizzle/`)](#database-layer-db--drizzle)
   - [Client & Shared Libraries (`lib/`)](#client--shared-libraries-lib)
   - [Server tRPC Layer (`server/trpc/`)](#server-trpc-layer-servertrpc)
   - [Full tRPC Router Collection (`trpc/`)](#full-trpc-router-collection-trpc)
   - [Custom Hooks, Providers & Global Types (`hooks/`, `providers/`, `types/`)](#custom-hooks-providers--global-types-hooks-providers-types)
   - [Static Assets & Public Directory (`public/`, `backend/assets/`)](#static-assets--public-directory-public-backendassets)
   - [Maintenance Scripts & Storage (`scripts/`, `uploads/`, `supabase/`)](#maintenance-scripts--storage-scripts-uploads-supabase)
3. [Deep-Dive: How Every Feature Works](#3-deep-dive-how-every-feature-works)
   - [Feature 1: Real-Time LaTeX Compilation, Concurrency Queue & ReportLab Fallback](#feature-1-real-time-latex-compilation-concurrency-queue--reportlab-fallback)
   - [Feature 2: Bidirectional SyncTeX Navigation (Forward & Backward)](#feature-2-bidirectional-synctex-navigation-forward--backward)
   - [Feature 3: OpenCode Bounded ReAct Agent Loop & Dynamic Step Budgeting](#feature-3-opencode-bounded-react-agent-loop--dynamic-step-budgeting)
   - [Feature 4: Automated LaTeX Error Diagnostics & Deterministic Auto-Healing](#feature-4-automated-latex-error-diagnostics--deterministic-auto-healing)
   - [Feature 5: Prompt Assembly, Environment Preservation & Minimal Surgical Edits](#feature-5-prompt-assembly-environment-preservation--minimal-surgical-edits)
   - [Feature 6: Local LaTeX Document Analysis & Preservation Mapping](#feature-6-local-latex-document-analysis--preservation-mapping)
   - [Feature 7: Multi-Turn Attached Context Session Store & File Injection](#feature-7-multi-turn-attached-context-session-store--file-injection)
   - [Feature 8: Smart Context Strategy Engine & Token Budgeting](#feature-8-smart-context-strategy-engine--token-budgeting)
   - [Feature 9: Scope Classification & AST Structural Chunk Replacement](#feature-9-scope-classification--ast-structural-chunk-replacement)
   - [Feature 10: Full Document Rewrite Coverage Validation & Leftover Detection](#feature-10-full-document-rewrite-coverage-validation--leftover-detection)
   - [Feature 11: Document Environment Integrity & Delimiter Auto-Balancing](#feature-11-document-environment-integrity--delimiter-auto-balancing)
   - [Feature 12: Pre-Commit Structural Validation](#feature-12-pre-commit-structural-validation)
   - [Feature 13: Shadow Compilation & Compiler-Feedback Self-Correction](#feature-13-shadow-compilation--compiler-feedback-self-correction)
   - [Feature 14: Regalia Default Presentation Template & Curated Theme Registry](#feature-14-regalia-default-presentation-template--curated-theme-registry)
   - [Feature 15: Cross-Stack Better-Auth Authentication & Session Sharing](#feature-15-cross-stack-better-auth-authentication--session-sharing)
   - [Feature 16: Sliding-Window Rate Limiting & Denial-of-Service Defense](#feature-16-sliding-window-rate-limiting--denial-of-service-defense)
   - [Feature 17: Real-Time AI Interruption, Stream Abort & Cancellation Tokens](#feature-17-real-time-ai-interruption-stream-abort--cancellation-tokens)
   - [Feature 18: Multi-Provider LLM Gateway & Fallback Architecture](#feature-18-multi-provider-llm-gateway--fallback-architecture)
   - [Feature 19: PDF → LaTeX Importer — Per-Page LLM Pipeline](#feature-19-pdf--latex-importer--per-page-llm-pipeline)
   - [Feature 20: Fonts, Exact Colors & Unicode for pdfLaTeX](#feature-20-fonts-exact-colors--unicode-for-pdflatex)
   - [Feature 21: Compile Repair, Visual Verification & Best-Version Selection](#feature-21-compile-repair-visual-verification--best-version-selection)
   - [Feature 22: Scanned Pages, Vector Art & Positioned-Layout Fallback](#feature-22-scanned-pages-vector-art--positioned-layout-fallback)
   - [Feature 23: Guest Conversion Session, Quota Enforcement & Auto-Migration](#feature-23-guest-conversion-session-quota-enforcement--auto-migration)
   - [Feature 24: Multimodal AI File Analyzer & TikZ Synthesizer](#feature-24-multimodal-ai-file-analyzer--tikz-synthesizer)
   - [Feature 25: Collaborative Project Management, Invitations & Role-Based Access](#feature-25-collaborative-project-management-invitations--role-based-access)
   - [Feature 26: Inline Diff Editor, Diff Generator & Edit History Tracking](#feature-26-inline-diff-editor-diff-generator--edit-history-tracking)
   - [Feature 27: Fullscreen Presentation View Mode with Laser Pointer](#feature-27-fullscreen-presentation-view-mode-with-laser-pointer)
   - [Feature 28: LaTeX Template Gallery, Metadata Explorer & Dynamic Cloning](#feature-28-latex-template-gallery-metadata-explorer--dynamic-cloning)
   - [Feature 29: Design System ("Celestial Obsidian & Luminescent Iris") & Theming Engine](#feature-29-design-system-celestial-obsidian--luminescent-iris--theming-engine)
   - [Feature 30: Structured Observability, Tracing & Performance Telemetry](#feature-30-structured-observability-tracing--performance-telemetry)
   - [Feature 31: Comprehensive Pytest Test Suite & Evaluation Harness](#feature-31-comprehensive-pytest-test-suite--evaluation-harness)
   - [Feature 32: Mobile Touch Editing, Find & Replace & the Dual-Editor Resolver](#feature-32-mobile-touch-editing-find--replace--the-dual-editor-resolver)
   - [Feature 33: Realtime Collaborative Editing, Presence & Remote Cursors](#feature-33-realtime-collaborative-editing-presence--remote-cursors)
   - [Feature 34: Render-Aware Layout Repair (`justify_content`)](#feature-34-render-aware-layout-repair-justify_content)
4. [Deployment, Infrastructure & Environment Configuration](#4-deployment-infrastructure--environment-configuration)

---

# 1. High-Level Methodology & System Architecture

### Architectural Overview

OverBranch adopts a decoupled, microservice-inspired architecture designed for high responsiveness, complete local isolation, and fault tolerance:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND CLIENT (Next.js 15)                    │
│  - App Router, React 19, TypeScript, Tailwind CSS, Lucide Icons        │
│  - Monaco LaTeX Editor with syntax highlighting and SyncTeX markers    │
│  - Custom PDF Viewer (PDF.js / Iframe / SyncTeX click handlers)        │
│  - Presentation Deck Player (Beamer slide rendering & laser pointer)   │
│  - Diff Viewer (Side-by-side & Unified diff widgets)                   │
│  - Agent Reasoning Window (Real-time ReAct loop step visualizer)       │
│  - AI Interruption / Stop Generation Controls (AbortController / SSE)  │
│  - Collaboration: Y.Doc + y-websocket, remote cursors, presence bar    │
└──────────────────┬───────────────────────────────┬─────────────────────┘
                   │                               │
       tRPC / Better-Auth (Next API)      HTTP / SSE / REST / WebSocket
                   │                               │
┌──────────────────▼──────────────┐   ┌────────────▼─────────────────────┐
│    DATABASE & AUTH SERVICE      │   │     FASTAPI PYTHON ENGINE        │
│  - PostgreSQL via Drizzle ORM   │   │  - Port 8000                     │
│  - Shared 'user' & 'session'    │   │  - Async SQLAlchemy Pool         │
│  - Better-Auth Session Tokens   │   │  - Sliding-Window Rate Limiter   │
│  - Project & Invitation Schema  │   │  - Concurrency Compile Queue     │
│  - Collaboration & Comments     │   │  - OpenCode ReAct Agent Loop     │
│  - collab_doc_state (CRDT blob) │   │  - Scope Classifier & Coverage   │
└──────────────────┬──────────────┘   │  - Shadow Workspace & Compiler   │
                   │                  │  - Structural Chunk Indexer      │
                   │ (SQLAlchemy)     │  - LaTeX Error Fixer (Healer)    │
                   │                  │  - Document Analyzer (Local AST) │
                   │                  │  - Attached Context Store (TTL)  │
                   │                  │  - Smart Context Strategy Engine │
                   │                  │  - pdf2latex Importer (Extract)  │
                   │                  │  - Per-Page LLM (copilot model)  │
                   │                  │  - Compile/SSIM Verify & Repair  │
                   │                  │  - Multimodal File Analyzer      │
                   │                  │  - SyncTeX Forward/Backward View │
                   │                  │  - Collab Rooms (Yjs CRDT / WS)  │
                   │                  │  - Presence & Debounced Persist  │
                   │                  │  - Structured Telemetry (Trace)  │
                   └──────────────────►  - ReportLab Synthetic Fallback  │
                                      └──────────────────────────────────┘
```

---

### Core Methodological Pipelines

#### A. OpenCode ReAct Agent Loop & Dynamic Adaptive Step Budgeting
1. **Interactive Tool Loop**: [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py) executes an iterative ReAct cycle operating on an in-memory [`ShadowWorkspace`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py).
2. **Dynamic Step Budgeting**: starts at 4–32 steps from task scope, document length and instruction complexity, and is then **extended on demand** — by the agent (`request_more_steps`) or by the loop when work is still landing at the limit — up to `ABSOLUTE_MAX_STEPS` (64). An extension requires evidence that the document moved since the last one, so a looping agent still stops. See [Feature 3](#feature-3-opencode-bounded-react-agent-loop--dynamic-step-budgeting).
3. **Deterministic Tool Suite** (old names `str_replace`, `grep_search`, `verify_compile`, `read_document_summary` are still accepted as aliases):
   - `inspect_document` / `get_block(node_id)`: Outline of every block with its **stable node ID**, and one block (optionally with its parent header and the preamble lines that style it).
   - `read_file_range`: Reads exact line-numbered contents (up to 300 lines per call); lines the model can still see unchanged are not re-sent (`ContextLedger`).
   - `search_document`: Finds structural anchors (`\chapter`, `\section`, `\begin{frame}`, `\label`, `\cite`).
   - `replace_text`: Replaces text located by the **target locator** (node → exact → normalized → fuzzy); `node_id` / `line_hint` scope it. A target that cannot be found confidently changes nothing and returns the region.
   - `replace_block` / `insert_block` / `delete_block`: Node-addressed edits (before/after/start/end of a block).
   - `rewrite_chunk` / `insert_into_chunk`: Full-rewrite chunk tools (chunk IDs or node IDs).
   - `list_assets`: Discovers available images/PDFs in `assets/` for `\includegraphics`.
   - `compile_latex`: Sandboxed compilation; **differential** — only errors the edits introduced fail it (`infra_skip` if the host lacks a TeX engine). Edits are also compiled automatically when the agent finishes.
   - `validate_edit` / `rollback_edit`: Structural check against the original; undo the last edit.
   - `request_more_steps`: Asks for more reasoning steps when the remaining budget will not cover the work. Granted only against progress since the last request.
   - `detect_overflow` / `inspect_pdf_geometry` / `justify_content`: Layout tools. `justify_content` with `scope="document"` is the render-aware layout repair — compile, measure every page, map each defect to its source, apply the smallest fix, recompile, keep it only if the page measurably improved (see [R](#r-layout-engine-justify_content-defect-detection--minimal-repair)).
   - `get_template_theme`: Retrieves curated themes (Beamer PPT themes, IEEE conference/journal papers, theses, resumes/CVs, formal letters, lab assignments) and extracts styling preambles for non-destructive redesigns.
   - `read_attached_document`: Extracts content from uploaded reference papers/PDFs stored in the multi-turn session cache.
   - `search_uploaded_references`: Searches user-attached documents for specific technical terminology, equations, and tables.
   - `convert_attached_pdf`: Starts a PDF → LaTeX import job for a PDF attached in chat; the agent then finishes without editing and the UI shows the job's progress and similarity report.
4. **SSE Event Streaming**: Streams real-time reasoning (`thought`, `tool_call`, `tool_result`, `phase`, `compile_error`, `coverage_check`, `final_diff`, `pdf_conversion`, `result`) to [`components/editor/AgentReasoningWindow.tsx`](file:///home/abin/overbranch/components/editor/AgentReasoningWindow.tsx) and [`components/editor/InlineDiffEditor.tsx`](file:///home/abin/overbranch/components/editor/InlineDiffEditor.tsx).

#### B. Automated LaTeX Error Diagnostics & Deterministic Auto-Healing
1. **Log Parsing**: [`backend/latex_error_fixer.py`](file:///home/abin/overbranch/backend/latex_error_fixer.py) parses raw LaTeX compiler error logs (`! LaTeX Error: ...`, `l.<line>`) into structured `ParsedLatexError` diagnostics containing file names, line numbers, error categories, and contextual code snippets.
2. **Deterministic Auto-Healing (`auto_heal_latex_code`)**: Automatically fixes common syntax failure modes before prompting the LLM:
   - Unclosed environments (`\begin{frame}`, `\begin{tikzpicture}`, `\begin{itemize}`, `\begin{tabular}`, etc.).
   - Missing `\usetikzlibrary{calc}` when coordinate calculations `($...$)` are detected.
   - Missing semicolons (`;`) on TikZ path commands (`\fill`, `\draw`, `\node`, `\path`).
   - Missing `\begin{document}` or `\end{document}` wrappers.
   - Truncated booktabs rule: a bare `\bottom` → `\bottomrule` (only when booktabs rules are in use; `\top` and `\mid` are left alone because they are valid math commands).
   - Bare `&` inside a frame title (`\begin{frame}{a & b}` / `\frametitle{...}`) → `\&` (a misplaced alignment tab that, in a TikZ-node frametitle template, can take down the title); `&` in the frame *body* (real tabulars) is untouched.
   - **Missing packages** (`ensure_required_packages`): a curated macro/environment → package map (booktabs, amsmath, amssymb/amsfonts, xcolor, colortbl, graphicx, hyperref, url, tabularx, multirow, listings, siunitx, subcaption, caption, ulem[normalem], soul, mathtools, bm, cancel, pifont, fancyhdr, titlesec, setspace, geometry, lipsum, xspace, enumitem) — the most common compile error in LLM-written LaTeX. Uses are found on the masked view; a need is skipped when the package, an equivalent (`color`/`tikz`/beamer ⇒ xcolor, beamer ⇒ graphicx/hyperref, `[table]{xcolor}` ⇒ colortbl) or a document-level definition already covers it. The option-less `\usepackage` goes before the first preamble use, else at the end of the preamble.
   - TikZ: use/loading detected on the masked view (`\usepackage{tikz,pgfplots}`, `\RequirePackage`, not comments); a missing `\usepackage{tikz}` is inserted at the end of the preamble — right after `\documentclass` it loaded xcolor before the document's `\usepackage[table]{xcolor}` (option clash). The semicolon fixer treats `\%` as text (it used to turn `97\%};` into `97\;%};`), keeps the line's newline when a comment follows, and never closes a statement inside an open group (`\matrix … {` cells).
   - `ensure_document_environment` finds `\begin/\end{document}` on the masked view (a commented `\end{document}` after the real one used to delete it); `balance_latex_environments` never drops an `\end{X}` whose `\begin{X}` is inside a macro definition.
   - **Error-driven repairs** (`repair_from_compile_errors`, used by the agent's compile gate before an LLM repair round, kept only if a recompile has fewer errors): `Missing $ inserted` → bare `_`/`^` in text escaped (not in math, math environments, or `\label`/`\ref`/`\url`/`\includegraphics`… arguments); `Misplaced alignment tab character &` outside tabular/align/matrix-like environments → `\&`.
   - Undefined standard colors in Beamer / Regalia (`navy`, `navylight`, `gold`, `cream`, `ink`, `muted`).
3. **Interactive Fix Prompt Assembly (`format_compilation_fix_prompt`)**: When user triggers "Ask AI to Fix" in [`components/editor/CompileToolbar.tsx`](file:///home/abin/overbranch/components/editor/CompileToolbar.tsx), builds surgical prompts containing line numbers, surrounding context, and exact error explanations for 1-step repair.

#### C. Local Document Structural Analysis & Preservation Mapping
1. **Local AST Analysis**: [`backend/document_analyzer.py`](file:///home/abin/overbranch/backend/document_analyzer.py) performs blazing-fast local LaTeX parsing with zero LLM overhead.
2. **Structural Inventory**: Extracts document class, title, author, Beamer frame count, chapter/section hierarchy, equation count, table count, figure count, code listing count, and byte/line ranges into `DocumentAnalysis`.
3. **Preservation Mapping**: Identifies sacred front-matter (Title Page, Certificate, Acknowledgement, Abstract, Table of Contents, Slide 1 Title Slide) to ensure the AI never modifies or destroys them during document overhauls.

#### D. Multi-Turn Attached Context Session Store
1. **In-Memory TTL Store**: [`backend/attached_context.py`](file:///home/abin/overbranch/backend/attached_context.py) provides a thread-safe, 2-hour TTL cache for uploaded reference documents (PDFs, papers, benchmarks).
2. **Page-by-Page PDF Extraction**: Uses PyMuPDF (`fitz`) or `pypdf` to extract plain text and structural page maps up to 60,000 characters without crashing memory.
3. **Multi-Turn Retention**: Keeps uploaded context alive across follow-up chat messages so users do not have to re-upload files when asking subsequent questions.

#### E. Smart Context Strategy & Model Context Window Management
1. **Strategy Selection**: [`backend/context_strategy.py`](file:///home/abin/overbranch/backend/context_strategy.py) chooses between 4 context delivery strategies based on document scale and model token capacity:
   - `TARGETED`: Sends only the target section and surrounding lines (best for large documents & small models).
   - `WHOLE_FILE`: Injects the entire document (best when document fits comfortably in context window).
   - `SUMMARY_FIRST`: Injects structural outline summary followed by targeted chunks.
   - `PLAN_EXECUTE`: Generates multi-phase transformation plan executed step-by-step.
2. **Model Registry**: Catalogs exact token limits for Gemini 3.7/2.5/2.0 (900K tokens), Groq LLaMA 3.3 70B (120K tokens), OpenRouter Claude 3.5 Sonnet (180K tokens), GPT-4o (120K tokens), and DeepSeek (60K tokens).

#### F. Scope Classification & AST Structural Chunk Replacement
1. **Scope Classification**: [`backend/scope_classifier.py`](file:///home/abin/overbranch/backend/scope_classifier.py) classifies incoming prompts into:
   - `TARGETED_EDIT`: Surgical fixes, typos, single section additions.
   - `FULL_DOCUMENT_REWRITE`: Topic overhauls, whole document replacements.
   - `EXPAND_CONTENT`: Elaboration, adding slides for each topic, deepening theory.
   - `STYLE_REDESIGN`: Theme/template switching, color updates.
2. **Structural Document Indexing**: [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py) parses the LaTeX AST into discrete `DocumentChunk` entities with byte/character offsets and line numbers.
3. **Chunk-Level Rewriting**: In `FULL_DOCUMENT_REWRITE` mode, the agent uses `rewrite_chunk(chunk_id, new_content)` to replace entire chapters/sections cleanly without exact-string matching errors.

#### G. Document Environment Integrity & AST Auto-Repair
1. **Structural Invariants**: [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py) provides `ensure_document_environment(code)`:
   - Ensures any code defining `\documentclass` contains exactly one `\begin{document}` and `\end{document}`.
   - Automatically finds the optimal boundary between preamble package imports and document body.
   - Deduplicates multiple stray `\begin{document}` or `\end{document}` tags emitted by careless edits.

#### H. Pre-Commit Validation & Deterministic Repair
1. **Validation Checks**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py) checks AST integrity before committing edits:
   - Ensures all opened environments (`\begin{env}`) have matching `\end{env}` tags.
   - Checks balance of math delimiters (`$`, `$$`, `\[`, `\]`) and curly braces (`{`, `}`).
   - Ensures list integrity (`\item` is strictly inside `itemize` or `enumerate`).
   - Ensures TikZ statements end with semicolons (`;`).
2. **Deterministic Repair**: `latex_error_fixer.auto_heal_latex_code` closes unclosed environments **positionally** — before the enclosing `\end{frame}` / `\end{document}` — never by appending them at end-of-file, and hoists stray `\usepackage` into the preamble. Validation and repair are deliberately separate (`edit_validator` only reports) but share one **masked view** of the document, and healing is **discarded if it raises the error count**. See [Feature 4](#feature-4-automated-latex-error-diagnostics--deterministic-auto-healing).
2b. **Differential Pre-Commit Check**: writes are gated by `validate_edit(before, after)`, not by an absolute pass. A defect the validator cannot model in the user's *original* document no longer rejects every subsequent edit for the rest of the run.
2c. **Magnitudes, not presence**: the whole-document checks (brace depth, `$`/`$$` parity, `\(`/`\)`, `\[`/`\]`, `\left`/`\right`) emit one message whatever their size, so comparing messages let a document with one unclosed brace accept any number of new ones. They are compared by magnitude (an edit fails if the imbalance grows; shrinking it is an improvement), and when an imbalance of that kind already exists, each changed hunk must keep its own balance in that dimension.
3. **Coverage & Leftover Checks**: Verifies all chunks were rewritten during full rewrites and alerts if residual terms from older topics remain.

#### I. Shadow Compilation & Compiler-Feedback Self-Correction
1. **In-Memory Shadow Sandbox**: [`backend/opencode/shadow_workspace.py`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py) maintains an isolated buffer; edits never touch disk during reasoning.
2. **Ephemeral Verification**: [`backend/opencode/shadow_compiler.py`](file:///home/abin/overbranch/backend/opencode/shadow_compiler.py) executes isolated compilation tests (`pdflatex`, `latexmk`, or ReportLab fallback).
3. **Compiler Feedback**: Offending TeX macros and line numbers are fed back into the agent loop for self-correction before returning diffs to the client.
4. **The verdict tells the truth** (`compile_shadow_buffer`). Every case below used to return success, and only on a host *with* TeX — on a dev box every compile is infrastructure-skipped — which is why broken edits only shipped in production:
   - *Infra* is decided by explicit markers only (`[INFRASTRUCTURE ERROR]` from the compiler, the ReportLab preview, an empty log), not by `"not found"` / `"timed out"` anywhere in the result — a missing image line made a real failure "compiler unavailable" and switched compilation off for the rest of the run.
   - Errors come from the compiler's full `errors` list (TeX's `file:line:` lines), parsed with their line and **file**; a failure with nothing parseable (timeout, unparsed fatal) is a synthesized `COMPILE_FAILED` error. A timed-out buffer is retried once at 2× the budget (agent compiles bypass `compile_queue`).
   - The differential compares errors by **(file, message, text of the source line)** as a multiset — keyed by message alone, a document that already had one `Undefined control sequence` hid every new one. An error left on a line the edit changed counts as the edit's.
   - **Strict mode** (`workspace.compile_strict`, set for "fix the compile errors" requests): success needs zero errors; the result reports `errors_before` / `errors_after`. Summaries never say "cleanly" while errors remain.
   - Editing a non-main `.tex` file compiles the project's real `main.tex` (`compiler.load_project_text_file`: uploads dir, then Supabase) with the buffer passed as that file, instead of compiling the fragment as the document.

#### J. Regalia Presentation Standard & Theme Registry
1. **Default Presentation Standard**: Regalia (`regalia`) is the designated default presentation template across OverBranch:
   - `\documentclass[aspectratio=169]{beamer}`
   - `\usetheme{default}` with `cream` background canvas (`\setbeamercolor{background canvas}{bg=cream}`).
   - `navy` (`#0B2545`) and `gold` (`#C9A24B`) accent palette with TikZ frametitle decorations.
   - Dedicated `[plain]` title slide and 6–12 structured content slides.
2. **Curated Themes**: [`backend/opencode/template_registry.py`](file:///home/abin/overbranch/backend/opencode/template_registry.py) indexes themes (`nordlight`, `prism`, `minimalist`, `sorbonne`, `uwm`, `regalia`, `ieee`, `acm`, `moderncv`) and extracts styling preambles without destroying user content.

#### K. PDF → LaTeX Per-Page Verification, Repair & Best-Version Selection
1. **Strict Compile**: every page is compiled on its own through the shared compile queue with pdfLaTeX. A PDF produced *despite* TeX errors (nonstopmode) or a reference to a missing image counts as a failure — `compile_latex` reports the TeX error lines in an `errors` field for this.
2. **Repair Loop**: [`backend/pdf2latex/pipeline.py`](file:///home/abin/overbranch/backend/pdf2latex/pipeline.py) first applies the deterministic `auto_heal_latex_code`, then sends the compile errors + page body back to the same LLM ("fix only the compile error") up to `PDF2LATEX_MAX_COMPILE_REPAIRS` (3) times; a page that still fails uses the positioned-layout fallback, then the page image.
3. **Render & Compare**: [`backend/pdf2latex/verify.py`](file:///home/abin/overbranch/backend/pdf2latex/verify.py) renders source and output with `pdftoppm` (PyMuPDF fallback). The render is first **aligned vertically** against the original (normalized ink-profile correlation, scanned outwards from zero so a uniform line pitch cannot be read as "shifted by one whole line") and both images are **block-mean softened**, then scored as `0.85 × SSIM + 0.15 × (1 − pixel-diff ratio)`. An 8×8 grid finds the most different regions; a word-level comparison finds missing **and invented** text (ligatures and line-break hyphenation normalized).
4. **Acceptance, Re-run & Selection** — the gate is the **text and where it sits**, not the pixels: a page is accepted when it compiles to exactly ONE page carrying at least `PDF2LATEX_COVERAGE_TARGET` (0.995) of the source's words with no more than 5% invented, with the median word within `PDF2LATEX_MAX_DISPLACEMENT` (25 pt) of its position in the PDF, and clearing the `PDF2LATEX_VISUAL_FLOOR` (0.55) backstop. Only an unacceptable page gets ONE re-run, with a note naming the missing words, the invented words, the overflow and the measured offset. An overflowing page is wrapped in `\obfit{…}`, which scales it down to fit one page. The positioned layout **rescues** a page that is still unacceptable (and only when clearly closer, +0.03); it never displaces a page whose text is complete. See [Feature 21](#feature-21-compile-repair-visual-verification--best-version-selection) for why full-page SSIM cannot be the gate.

#### L. Scanned Pages & Vector Art
1. **Scanned Pages**: pages with almost no visible text and a page-covering image are placed as the scan at its exact position; an existing OCR text layer becomes invisible, searchable text (`text opacity=0`). No LLM call.
2. **Vector Art**: [`backend/pdf2latex/extract.py`](file:///home/abin/overbranch/backend/pdf2latex/extract.py) keeps axis-aligned rules and rectangles as facts for LaTeX (`\rule`, `\hline`, `\colorbox`) and rasterizes what LaTeX cannot express: curve / gradient / chart regions become `page{n}_fig{k}.png` (their labels included), artwork covering ≥ 40% of the page becomes a text-free background `page{n}_bg.png` placed with eso-pic behind the real text.

#### M. Cross-Stack Better-Auth Authentication & SQLAlchemy Session Verification
1. **Shared PostgreSQL Database**: Next.js 15 (Better-Auth) and FastAPI Python backend share the same PostgreSQL database.
2. **Direct Session Verification**: [`backend/auth.py`](file:///home/abin/overbranch/backend/auth.py) extracts session tokens from cookies (`better-auth.session_token`) or Bearer headers, unquotes them, strips signatures, and queries the `session` table via async SQLAlchemy (`backend/database.py`, `backend/models.py`).
3. **RBAC & Ownership**: `verify_project_ownership_or_member()` checks project ownership and collaborator memberships in `projects` and `project_members`.
4. **Guest Identity**: HMAC-signed guest tokens (`x-guest-token`, `ob_guest_token`) are verified for anonymous users with 24-hour expiration.

#### N. Sliding-Window Rate Limiting & Concurrency Queue
1. **Sliding-Window Rate Limiter**: [`backend/rate_limiter.py`](file:///home/abin/overbranch/backend/rate_limiter.py) provides thread-safe sliding-window rate limiting keyed by authenticated user ID, guest ID, or client IP, protecting against DDoS and scraping.
2. **Compilation Concurrency Queue**: [`backend/compile_queue.py`](file:///home/abin/overbranch/backend/compile_queue.py) uses an `asyncio.Semaphore` (default: 4 concurrent compiles) and bounded queue depth with HTTP 429 backpressure to prevent CPU exhaustion.

#### O. PDF → LaTeX Importer (pdf2latex): Local Facts, Shared Preamble, Per-Page LLM
1. **Facts, No LLM**: [`backend/pdf2latex/extract.py`](file:///home/abin/overbranch/backend/pdf2latex/extract.py) extracts per page the size, content margins, text spans (font, size, exact RGB, bold/italic/superscript flags, bbox, baseline), rules/rectangles, and images saved as `assets/pdf_<id>/page{n}_img{k}.<png|jpg>`. Lines are then put into **reading order** (`order_lines`): PyMuPDF returns them in PDF content-stream order, so a page whose margin notes were drawn after the body handed the model the whole body and then jumped back to the top of the page. Lines are clustered into text blocks by horizontal overlap and vertical adjacency (PyMuPDF's own blocks are one-per-line when the producer writes each line with its own text operator) and the blocks are ordered by **XY-cut** — split on an empty horizontal band, else on an empty vertical gutter, else top-to-bottom. [`facts.py`](file:///home/abin/overbranch/backend/pdf2latex/facts.py) turns this into compact JSON with coordinates relative to the LaTeX text area, a precomputed `gap` (the `\vspace` to emit before each line), and text already escaped for pdfLaTeX ([`texutil.py`](file:///home/abin/overbranch/backend/pdf2latex/texutil.py) maps Unicode to LaTeX).
2. **One Deterministic Preamble**: [`preamble.py`](file:///home/abin/overbranch/backend/pdf2latex/preamble.py) builds `article` + `geometry` (page size, smallest content margins) + `xcolor` with one `\definecolor{cRRGGBB}{RGB}{r,g,b}` per distinct color + graphicx/amsmath/amssymb/tabularx/booktabs/multicol/enumitem/tikz/eso-pic + the closest pdfLaTeX fonts (mathptmx / mathpazo / helvet / courier / lmodern).
3. **Same LLM as the Copilot**: [`llm.py`](file:///home/abin/overbranch/backend/pdf2latex/llm.py) calls `providers.router.provider_router.chat` with `DEFAULT_MODEL` — the exact client, base URL, keys and model the agent uses (GEMINI_WEB2API_*, OpenRouter fallback). Pages run in parallel (`PDF2LATEX_CONCURRENCY`, also a process-wide cap on LLM calls) with a per-call timeout (cancel token aborts the stream) and retries. `GeminiProvider` accepts OpenAI image parts and retries text-only if the gateway rejects them.
4. **Page Prompt**: [`prompts.py`](file:///home/abin/overbranch/backend/pdf2latex/prompts.py) — body only, ALL text verbatim, predefined color names, exact `\fontsize{sz}{1.2 sz}`, images from the facts, real tabular/itemize/math, no floats or absolute positioning, `\newpage` except on the last page. Lines carry **block structure**: `nb` marks the first line of an independent region with its absolute `top`, and `side` + `bw` mark a margin-note column that must not push the main text down (emitted as a zero-size `\makebox` + `\raisebox` pinned to the top of the text area). A block break never carries a relative `gap`, because the previous line is elsewhere on the page — chaining one across the jump is what produced a `\vspace{-222pt}` that dropped the notes over the title. Vertical spacing within a block comes from each line's **precomputed `gap`** (`\vspace*` on the first line of a page, since LaTeX discards ordinary `\vspace` there) rather than from the model deriving it from baselines — a baseline is not where `\vspace` takes effect, and making the model do that arithmetic drifted every page downwards. Following `gap` lifted a dense page from 0.555 to 0.855 similarity, i.e. up to the deterministic layout's own fidelity. An empty answer or one missing most of the words is retried once.
12. **Merge**: bodies are joined under the preamble with `\newpage`; the merged document is compiled (pages that break it fall back to the positioned layout) and its page count is checked against the PDF.
6. **Guest Lifecycle**: Guests keep the 1-conversion-per-24h quota; their projects are tracked in `guest_projects` and moved to the account on sign-in via `/api/guest/migrate` ([`components/GuestMigrationListener.tsx`](file:///home/abin/overbranch/components/GuestMigrationListener.tsx)).

#### P. SyncTeX Bidirectional Navigation
- **Forward Lookup**: Placing the cursor at line $L$ in `main.tex` executes `synctex view`, mapping the source code line to the exact PDF page, $x$, and $y$ coordinate, scrolling the PDF viewer automatically.
- **Backward Lookup**: Double-clicking or Cmd+Clicking an element in the PDF viewer translates the point $(page, x, y)$ back into the corresponding source filename, line number, and column in Monaco.

#### Q. Structured Observability, Tracing & Performance Telemetry
- [`backend/trace.py`](file:///home/abin/overbranch/backend/trace.py) provides structured telemetry (`AgentTrace` and `ConversionTrace` — per-job model, page similarity scores, fallback pages and latency), recording tool calls, latencies, node IDs, compiler feedback, and token counts for observability.
- `AgentTrace` also records `agent_run_id`, `request_id`, `document_id`, the provider/model that answered, **key IDs** (`openrouter#2` — never keys), every provider attempt, per-edit `edit_type` + `target_resolution_method`, the context levels sent, `compile_result`, `retry_count` and `failure_reason`. Tool arguments are logged **redacted** (identifiers and numbers kept; document text reduced to its length).

#### R. Layout Engine: justify_content, Defect Detection & Minimal Repair
[`backend/latex_layout/`](file:///home/abin/overbranch/backend/latex_layout/) is shared by the agent and the PDF importer:
- `metrics.py` — width of a string in the **TeX font file that will set it** (located with `kpsewhich`; Base-14 fallback).
- `blocks.py` — `TextBlock{text, x, y, width, height, font_size, font_weight, italic}` per line of a PDF page (extracted *without* the mediabox clip, so off-page text is visible), and `compare_blocks(src, out)`: words are paired with the **nearest same-text word** (both pages share coordinates), so repeated words are not mis-paired; reports `weight` / `italic` / `size` / `overflow_right` / `clipped` runs. A horizontally condensed word is not a size change (height compared too).
- `overflow.py` — overfull boxes from the log (mapped to source lines) + lines past the inferred text-area right edge + glyphs off the page.
- `justify.py` — `fit_fragment` (still exported as `justify_content` for callers of the old name): measures with TeX itself (`\settowidth` in draft mode with the document's preamble) and applies the smallest fix for **one fragment against one width** — alignment only → paragraph wrap with `\emergencystretch` → horizontal condense (`\resizebox{W}{\height}`), with a note when the reduction is large. Content inside an LR box (`\makebox`, `\mbox`, tabular cell) is always treated as one line. **There is no font-size rung**: making content fit by setting it smaller than the text around it is visible on the page, it spreads (the next overflow invites the same treatment), and it is never what a typesetter would do. `probe_page_geometry` asks TeX for the document's own `\textwidth` / `\textheight` and margins in big points.
- `issues.py` — **what is wrong with the rendered pages**, measured: `LayoutIssue{page, type, severity, description, text, region, source, evidence}` over a taxonomy (`MARGIN_VIOLATION`, `VERTICAL_OVERFLOW`, `TABLE_WIDTH`, `TABLE_CELL_OVERFLOW`, `LONG_PATH`, `LONG_URL`, `LONG_IDENTIFIER`, `AWKWARD_LINE_BREAK`, `OVERFLOW`, …). Three independent signals, because each misses what the others catch: TeX's overfull warnings (exact, and already mapped to source lines), word boxes against the text area, and adjacent line pairs (a token split across a break is a defect no width measurement can see — every line *does* fit).
- `repair.py` — **the smallest LaTeX change for one defect**, from a closed operation set. The model never writes LaTeX for these: it decides *that* a document should be tidied, `repair.py` decides *how*. Content-typed: `LONG_URL` → `\url{}`; `LONG_PATH` / `LONG_IDENTIFIER` → `\allowbreak{}` at separators or camelCase boundaries; prose → `sloppypar`; `TABLE_WIDTH` / `TABLE_CELL_OVERFLOW` → `tabularx` at `\textwidth` with a `>{\raggedright\arraybackslash}X` column; `VERTICAL_OVERFLOW` → `longtable` with `\endhead`.
- `vision.py` — an **optional, advisory** second opinion (`JUSTIFY_VISION=1`), batched 5 pages at a time, only on pages measurement could not explain. It reports `VISUAL_INCONSISTENCY` and never repairs, because no repair in the catalogue can be chosen from a sentence of prose.

**Four decisions that are load-bearing, each made after the obvious alternative failed on a real document:**
1. **The text area comes from TeX, not from the page.** `text_right_edge` needs three lines to agree on a right edge; a page dominated by a wide table has no such agreement, so it returns `None` and every overflow check silently passes — on exactly the pages that need checking. `probe_page_geometry` asks LaTeX, which knows.
2. **A "broken token" is confirmed against the source.** Geometry cannot distinguish "one token was split" from "a token ended the line and the next word began the following one": in the PDF both are just "line ends here, line starts there". Without the check, every paragraph whose line happens to end in a file path is reported broken.
3. **The score counts magnitude, not issues.** A repair taking an overflow from 57 pt to 32 pt is real progress, but scored by presence it ties with the original, is rolled back, and the next repair in the ladder — which would have finished the job — is never tried. (The document write gate compares structural errors by magnitude for the same reason, see [H](#h-pre-commit-validation--deterministic-repair).)
4. **Vertical overflow is measured from text, not from table rules.** PyMuPDF reports a path's *bounding box*, so a run of `\hline` rules can come back merged into one shape whose geometry says nothing about where the rows ended up. Lines below the text block are counted instead, and the running footer is told apart from overflowing content by **continuity** — overflow keeps coming at the body's line pitch; a footer sits alone after a wide gap. Position alone would flag every page in the document.

**Repairs are forbidden, in code, from:** `\small` / `\scriptsize` / `\tiny` / `\fontsize` / `\linespread`, any `\geometry` / `\newgeometry` / `\setlength{\textwidth}`, and a bare `\\` as an overflow fix. Every operation is checked with `preserves_text`: the visible characters before and after must be equal once the inserted break commands are removed, so a repair that would drop, reword or truncate content is discarded whatever it would do for the layout. That is the mechanical form of *same information, better presentation*.

#### S. Target Resolution, Targeted Context & Transactional Edits
- **Stable node IDs** ([`document_index.index_nodes`](file:///home/abin/overbranch/backend/document_index.py)): `preamble`, `meta:title`, `maketitle`, `page:2` (pages of an imported PDF, from the `OB-PAGE` markers), `sec:introduction`, `frame:results#2`, `env:table:tab-main` (label), `env:tabular@sec:results#1` — derived from kind + title/label, so they survive edits elsewhere; in memory only, never written into the LaTeX. Lookup also accepts `label:<x>`, `slide 3`, `section 2` and the legacy positional chunk IDs. A node whose own title an edit changes keeps its old ID as an alias.
- **Locator** ([`opencode/locator.py`](file:///home/abin/overbranch/backend/opencode/locator.py)): node → exact (unique, or disambiguated by context / line hint) → normalized (CRLF, indentation, blank runs, smart quotes, `~`) → same text in another case, if unique ("jacob" → "JACOB") → fuzzy (line windows, accepted at ≥ 0.88 and ≥ 0.05 over the runner-up; never on a tie; never for snippets < 24 chars; never when the window's brace / `\begin` / `\end` / `$` counts differ from the needle's — a whole-line window used to take the `}` the model did not copy). Cheap methods run document-wide before fuzzy runs anywhere. Every attempt is recorded. Write paths strip `N: ` prefixes copied from `read_file_range` (consecutive, and only when the unprefixed text is what is in the document), give `new_str` the replaced text's trailing newline (a missing one merged lines; a trailing `% comment` then commented out the next), and report the healer's changes (`auto_repairs`) from every path, so the model's next `old_str` matches the buffer.
- **Write gate** (`ShadowWorkspace._heal_and_validate` + [`opencode/edit_guard.py`](file:///home/abin/overbranch/backend/opencode/edit_guard.py)): differential validation; the healer's repairs are kept **only on lines the edit changed** (plus preamble insertions the edit itself requires — ones the original already "needed" are excluded); a heal that makes validation worse is dropped; an edit that makes a frame/section appear twice is refused.
- **Targeted context** ([`opencode/context_builder.py`](file:///home/abin/overbranch/backend/opencode/context_builder.py)): for a targeted edit on a document over 150 lines the first message carries the outline + matched blocks (level 1), parent header (2), neighbouring lines (3) and the preamble lines that style them (4) — not the file. When no block matches (an imported PDF has no sections), the lines containing the request's own words (ignoring case) are sent; an unstructured document under 400 lines with no match at all is sent whole. `search_document` retries ignoring case when the exact case finds nothing. The prompt for a 5,000-line document is within 2× of a 70-line one.
- **Transactions**: the whole agent run is one transaction (`begin_transaction` / `rollback_transaction`). Finishing with unverified edits triggers a compile; failing errors first get the deterministic `repair_from_compile_errors`, then ≤ `SHADOW_COMPILE_MAX_RETRIES` LLM repair rounds — granted even on the last step (the budget is extended by at most that many steps; an error found at the end used to roll back with no repair attempt) — after which the run is **rolled back** and the result says *"Couldn't safely apply this change. The document was not modified."* with the reason and attempts. The loop ending without `done` (budget exhausted) runs the same gate (deterministic repairs only) instead of shipping uncompiled edits; on the last step with unverified edits the model is told to finish. A **fix request** that removed some errors, added none and could not remove the rest keeps its progress: `result.partial` and the explanation say *"Fixed X of Y compile error(s); Z still fail"*. Every changed run's explanation ends with the compiler's real status ("✓ Compiles without errors." / "No new compile errors; N error(s) … remain"). The fix-request pre-heal no longer re-heals the whole document unvalidated after `replace_all`. A run cut short by the LLM provider is rolled back the same way. A target that fails twice is given up rather than retried.

#### T. Provider Fallback Chain & Key Health
- [`providers/errors.py`](file:///home/abin/overbranch/backend/providers/errors.py) classifies every failure (`rate_limit`, `quota`, `auth`, `timeout`, `unavailable`, `model_unavailable`, `bad_request`, `cancelled`). `ProviderRouter.chat` walks `LLM_FALLBACK_CHAIN` (default `openrouter:minimax/minimax-m3`) only for provider-side failures — never on a cancellation or a malformed request — and returns `provider`, `model_used`, `key_id`, `is_fallback`, `attempts`. An `observer` callback feeds each attempt to the trace. New providers are added with `register_provider` + a chain entry.
- [`providers/key_pool.py`](file:///home/abin/overbranch/backend/providers/key_pool.py): OpenRouter's five server-side keys (`OPENROUTER_API_KEY_1..5`) with per-key `{status, last_failure, cooldown_until, failure_count}`. Selection is **sticky** (the key that last worked); 429 cools down for `Retry-After` or 30 s doubling to 10 min, quota 1 h, auth 6 h, transient errors 15 s; a cooled-down key rejoins automatically. Keys never leave the server or reach logs.

#### U. Realtime Collaborative Editing (Yjs CRDT over WebSocket)
Full architecture and rationale: [`COLLABORATION.md`](file:///home/abin/overbranch/COLLABORATION.md).

1. **Transport & room**: [`backend/routes/collab_routes.py`](file:///home/abin/overbranch/backend/routes/collab_routes.py) serves `WS /ws/collab/{project_id}` speaking the **y-websocket wire protocol** unchanged (sync step1/step2/update, awareness, queryAwareness), so the browser runs the stock [`y-websocket`](file:///home/abin/overbranch/lib/collab/useCollaboration.ts) provider. [`backend/collab/room.py`](file:///home/abin/overbranch/backend/collab/room.py) holds one **authoritative `pycrdt.Doc` per project**: a `Y.Text` per open file (`file:<path>`) plus a `Y.Map` `meta` (`loaded:<path>`, `saved:<path>`).
2. **Why the server holds a real CRDT, not a relay**: a late joiner's sync step 1 needs a step 2 from *somebody* (a relay fails when everyone has left); and rebuilding a room by inserting the stored text into a fresh doc gives that text a **new CRDT identity**, so a client reconnecting with its old doc merges both insertions and the user sees the document twice. Re-applying the stored update keeps one identity.
3. **Authorization is OverBranch's own** — nothing the client claims is believed. Cookie (same-site deployment) or a **single-use, 60 s, HMAC** ticket from `POST /api/collab/ticket` (identity only), then `projects.owner_id` / `project_members.role` ([`collab/access.py`](file:///home/abin/overbranch/backend/collab/access.py)), re-resolved every `COLLAB_REAUTH_INTERVAL` (30 s) so a removed collaborator loses their **live** session. An **Origin allowlist** closes the cross-site-websocket-hijacking hole CORS does not cover. The socket is accepted *before* the checks and then closed with a specific code (`4401`/`4402`/`4403`/`4404`/`4429`), because a close before `accept()` reaches the browser as 1006 and the client cannot tell "forbidden" from "network blip" — `y-websocket` would reconnect forever. **`4402` (credentials required) is distinct from `4401` (credential rejected)**, and that distinction is what made collaboration work in development and fail in production: a browser attaches the Better-Auth cookie to a websocket upgrade only when the API is same-site with the app, and in the deployed setup (`overbranch.…dev` → `overapi.…dev`) it is not, so the first attempt legitimately arrives with no credential at all. Answering `4401` told the client it had been *denied*; the client treated that as fatal, never ran the ticket fallback that would have connected it, and showed “Your access to this project was revoked” to people with full access. Guests are excluded (their projects are single-session).
4. **The two Monaco instances must share one model.** `EditorLayout` renders a desktop and a mobile editor and hides one with CSS. The binding syncs text to the **one** model it is constructed with, while `addEditor` attaches cursor decorations to **every** editor — so the two instances sharing a model is a hard requirement, not an optimisation. They did not: `@monaco-editor/react` resolves a model with `getModel(Uri.parse(path)) || createModel(value, lang, path ? uri : undefined)`, and with no `path` prop that argument is `""` — **falsy** — so each instance quietly received its own anonymous model. The result was remote carets appearing and moving perfectly over a document in which not one character ever crossed, because the binding was reading and writing the *hidden* editor's model while the user typed in the visible one. `handleEditorMount` now adopts the peer's model, and the hook's `pickBindableEditor` prefers the **visible** editor (`offsetParent != null`, the same test the hidden find bar uses to refuse focus) so a future regression degrades to "works in the editor you can see" rather than silently syncing nothing. Both cases are pinned in [`scripts/test_collab_binding.mjs`](file:///home/abin/overbranch/scripts/test_collab_binding.mjs).
5. **Monaco binding is hand-written** ([`lib/collab/monaco-binding.ts`](file:///home/abin/overbranch/lib/collab/monaco-binding.ts)): `y-monaco` peer-depends on the `monaco-editor` npm package, which this project deliberately does not bundle (it loads Monaco from a CDN). Loop safety: local `onDidChangeContent` → `Y.Text` ops in a transaction whose **origin is the binding**; remote `ytext.observe` → `model.applyEdits`, skipped when `transaction.origin === binding`. Filtering on the origin rather than `transaction.local` is required because a `Y.UndoManager` undo *is* local and Monaco must follow it; `applyEdits` (not `pushEditOperations`) keeps a collaborator's keystroke off this user's native undo stack.
6. **React must stop driving Monaco**: `@monaco-editor/react` implements a `value` prop change as a full-model-range replace (and `setValue` outright when read-only). Under a CRDT that is "delete the document, insert a new one" — wiping concurrent edits and resetting every remote cursor — so `value={collabBound ? undefined : code}`; `code` becomes a 150 ms-throttled mirror and `currentDocumentText()` reads the live model for compile and the agent.
7. **Presence & cursors**: `y-protocols` awareness, mirrored server-side by `pycrdt.Awareness` so a late joiner sees existing cursors at once. **Never persisted to Postgres**; `remove_awareness_states` on disconnect stops ghost cursors. Positions are Yjs **relative positions** (they survive edits earlier in the document, and a peer who switched files resolves against another `Y.Text` and is not drawn). A caret is published **only while that user's editor has focus** — Monaco fires `onDidChangeCursorSelection` whenever *remote* text shifts positions, so without the gate someone who merely had the project open broadcast a caret at line 1 and appeared, name label and all, to be sitting there in everyone else's window; blurring withdraws it while leaving them in the collaborator list. Updates throttled to 80 ms. Each caret is a decoration plus a generated CSS rule with the user's colour (derived from their id) and name as an absolutely positioned `::after` — **not** Monaco injected text, which takes part in layout and would shove the local user's characters sideways on every remote caret move. Idle 12 s → dimmed, label hidden. [`components/editor/CollabPresenceBar.tsx`](file:///home/abin/overbranch/components/editor/CollabPresenceBar.tsx) shows who is live, their file and 🟢/🟡/🔴.
8. **Persistence is debounced and server-side**: the room writes the text to disk + Supabase `latex_documents` after 2 s of silence (and at least every 15 s under continuous typing), on last-leave and on shutdown; the CRDT snapshot goes to `uploads/collab-state/<id>.ybin` + `collab_doc_state`. The browser stops POSTing the document entirely while bound. A failed write stays dirty for the next tick. Edits made while a room was **closed** (AI commit, PDF import, template clone) are adopted on cold start by comparing the stored text against the hash recorded at the last flush — and the room's own unflushed edits win when *it* is the one that moved.
9. **AI edits are ordinary CRDT operations**: the agent returns diffs and the user accepts them, so the accept path was made surgical — [`lib/collab/text-diff.ts`](file:///home/abin/overbranch/lib/collab/text-diff.ts) replaces the old `getFullModelRange()` replace with the minimal changed line ranges (a whole-document replace *is* last-write-wins over every concurrent keystroke). Backend writes are routed **into** the live room by [`collab/inject.py`](file:///home/abin/overbranch/backend/collab/inject.py) via `project_storage.write_document_text`, so a PDF import cannot vanish under the room's next flush.
10. **Undo is per user**: Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z and the toolbar route to a `Y.UndoManager` scoped to `trackedOrigins: {binding}`, so undo means "undo *my* last edit" and can never delete a collaborator's paragraph.
11. **A room is opened only when one is needed** ([`collab/presence.py`](file:///home/abin/overbranch/backend/collab/presence.py), `POST /api/collab/presence`). A room costs a websocket, a uvicorn concurrency slot, an authoritative CRDT document and a persistence timer for as long as the tab is open — spent, before this, on the overwhelmingly common case of one person editing alone, who needs none of it and is served by the REST autosave path. But "is anyone else here?" is what a room is *for*, so asking it cannot require one: the client posts a heartbeat every ~8 s and opens the socket only once the project is **actually shared** (one indexed `project_members` lookup) **and a second person has it open**. Two tabs of one person count once; a stale viewer expires after `COLLAB_PRESENCE_TTL`; an open room keeps its occupants connected as the count falls back to one, because the room's own last-leave path flushes and closes it rather than the socket being pulled out mid-keystroke. The heartbeat is a hint, never an authorization — `resolve_project_role` still gates every connect and every re-auth tick — and membership lookup failures **fail open**, since a needless room wastes a connection while a refused one silently drops a real collaborator to single-user editing. The presence bar shows this as a neutral **Solo**, not the red "Offline" the unknown status used to fall through to.
12. **Scaling caveat**: rooms are per-process, so `entrypoint.sh` and `Dockerfile.backend` pin the backend to **one worker** while collaboration is on (`COLLAB_ENABLED=0` or `COLLAB_MULTI_WORKER=1` opt out, and `warn_if_multi_worker()` logs loudly). A websocket holds a `--limit-concurrency` slot and one `--limit-max-requests` request for its whole life, so both limits were raised.
13. **Structured logs** ([`collab/events.py`](file:///home/abin/overbranch/backend/collab/events.py), [`lib/collab/log.ts`](file:///home/abin/overbranch/lib/collab/log.ts)): `COLLAB_CONNECT/DISCONNECT/JOIN/LEAVE/SYNC/PERSIST/RECONNECT/AUTH_FAILURE/CONFLICT/ROOM_OPEN/ROOM_CLOSE/FILE_LOAD/EXTERNAL_CHANGE/AWARENESS/UPDATE/ERROR`. Per-message events are DEBUG unless `COLLAB_DEBUG=1` so cursor traffic cannot flood production; no event carries document text or a token.

---

# 2. Complete Repository & File Structure (As-Is Verbatim)

```
overbranch/
├── .dockerignore                               # Docker build context exclusion rules
├── .env                                        # Local environment variables & secrets (ignored by git)
├── .env.example                                # Documented template for required environment variables
├── .gitignore                                  # Git repository file exclusion rules
├── COLLABORATION.md                            # Realtime collaborative editing: architecture, auth, persistence, scaling
├── DOCKER_DEPLOYMENT.md                        # Production container deployment runbook
├── Dockerfile                                  # Production Next.js & Python full-stack multi-stage build
├── Dockerfile.backend                          # Production Python FastAPI standalone container build
├── LICENSE                                     # MIT Open Source License
├── OVERVIEW.md                                 # Master architecture, method & file reference guide
├── README.md                                   # Project introduction, showcase & quickstart
├── bun.lock                                    # Bun package manager lockfile
├── components.json                             # shadcn/ui component configuration
├── deploy.sh                                   # Automated Linux/Ubuntu deployment & rollback script
├── docker-compose.backend.yml                  # Docker Compose configuration (FastAPI backend only)
├── docker-compose.yml                          # Docker Compose configuration (Full-stack Next.js + FastAPI + DB)
├── drizzle.config.ts                           # Drizzle ORM schema paths & migration settings
├── entrypoint.sh                               # Production container startup supervisor script
├── eslint.config.mjs                           # ESLint 9 modern flat configuration
├── middleware.ts                               # Next.js edge middleware routing & auth cookie inspection
├── next.config.ts                              # Next.js 15 App Router build, image & proxy configurations
├── package-lock.json                           # NPM dependency lockfile
├── package.json                                # Node.js project manifest, dependencies & build scripts
├── postcss.config.mjs                          # PostCSS Tailwind CSS v4 processor configuration
├── skills-lock.json                            # Antigravity CLI skills configuration lockfile
├── tsconfig.json                               # TypeScript 5 compiler configuration & path aliases
├── vercel.json                                 # Vercel serverless deployment overrides
│
├── app/                                        # Next.js 15 App Router Frontend Application
│   ├── (dashboard)/                            # Protected Authenticated Dashboard Layout Group
│   │   ├── dashboard/page.tsx                  # Primary user dashboard (Recent projects, metrics, quick start)
│   │   ├── layout.tsx                          # Dashboard shell with responsive Sidebar and TopNav
│   │   ├── profile/page.tsx                    # User profile, account management & API key settings
│   │   ├── projects/page.tsx                   # Project management list (Search, Filter, Star, Delete, Clone)
│   │   └── templates/page.tsx                  # Interactive LaTeX template explorer & instant cloning
│   ├── api/                                    # Server-Side API Route Handlers
│   │   ├── auth/[...all]/route.ts              # Better-Auth server endpoint handler
│   │   └── trpc/[trpc]/route.ts                # tRPC HTTP batch request handler
│   ├── auth/page.tsx                           # Authentication callback, verification & onboarding handler
│   ├── convert/page.tsx                        # Guest PDF → LaTeX importer page (quota-limited, uses ImportPdfDialog)
│   ├── editor/[id]/page.tsx                    # Master LaTeX project editor screen loader
│   ├── error.tsx                               # Global React error boundary with retry UI
│   ├── not-found.tsx                           # Global 404 Not Found page
│   ├── globals.css                             # Global CSS variables, "Celestial Obsidian" theme & Tailwind v4
│   ├── layout.tsx                              # Root HTML layout, font declarations (Archivo, Inter, Space Mono)
│   ├── login/page.tsx                          # User sign-in page with credentials & OAuth buttons
│   ├── register/page.tsx                       # User registration page
│   ├── page.tsx                                # High-conversion marketing landing page
│   ├── apple-icon.png                          # Apple touch icon
│   ├── favicon.ico                             # Browser favicon
│   ├── icon.png                                # Application brand icon (PNG)
│   └── icon.svg                                # Application brand icon (Vector SVG)
│
├── backend/                                    # Python FastAPI High-Performance Backend Engine
│   ├── assets/                                 # Static assets & figure placeholders
│   │   ├── image_p1_1.png                      # Sample converted document figure 1
│   │   └── image_p1_2.png                      # Sample converted document figure 2
│   ├── collab/                                 # Realtime collaborative editing (authoritative Yjs CRDT rooms)
│   │   ├── __init__.py                         # Package overview & exports (config, room_manager)
│   │   ├── access.py                           # Project role from projects / project_members; fails closed
│   │   ├── config.py                           # COLLAB_* settings (persistence, limits, origins, tickets, debug)
│   │   ├── events.py                           # Structured COLLAB_* logging; per-message events DEBUG unless COLLAB_DEBUG
│   │   ├── inject.py                           # Routes backend document writes INTO a live room (AI commit, PDF import)
│   │   ├── manager.py                          # Room registry, idle reaping, shutdown flush, multi-worker warning
│   │   ├── persistence.py                      # Document text (disk + latex_documents) & CRDT snapshot (.ybin + collab_doc_state)
│   │   ├── room.py                             # One room per project: y-websocket protocol, seeding, presence, debounced persistence
│   │   └── tickets.py                          # One-time HMAC websocket admission tickets (identity only)
│   ├── opencode/                               # OpenCode Bounded ReAct Agentic Pipeline
│   │   ├── __init__.py                         # Package exports
│   │   ├── agent_loop.py                       # ReAct loop, step budget, targeted context, compile gate, run-level rollback, phase events, self-validating LaTeX-in-JSON parser
│   │   ├── apply_edits.py                      # Server-side all-or-nothing placement of edits the editor could not place (resolve-edits); whole-document items only over the unchanged original
│   │   ├── context_builder.py                  # Levels 1-5 targeted context, node outline, request→node matching, ContextLedger
│   │   ├── diff_generator.py                   # Unified/split diffs + apply-contract v3 edit items (unique, structurally-closed, node-annotated)
│   │   ├── edit_guard.py                       # Scoped healing (edited lines only) & duplicate-block guard
│   │   ├── layout_tools.py                     # detect_overflow / inspect_pdf_geometry / justify_content; the render→measure→repair→verify loop, per-defect rollback, stale-version guard
│   │   ├── locator.py                          # Target resolution: node → exact → normalized → fuzzy (structure-guarded), with recorded attempts
│   │   ├── shadow_compiler.py                  # Truthful compile verdict: explicit infra markers, (file, message, source line) multiset differential, strict fix mode, timeout retry, real main.tex for non-main files; pre_heal=False so error lines match the buffer
│   │   ├── shadow_workspace.py                 # In-memory buffer: locator-based edits, node ops, transactions, scoped heal; line-number-prefix & trailing-newline hygiene, auto_repairs reported
│   │   ├── template_registry.py                # Template/theme registry (Regalia, Nordlight, Prism, IEEE, ACM)
│   │   └── tools.py                            # Tool definitions & dispatcher (replace_text, replace_block, insert_block, compile_latex, …; old names aliased)
│   ├── providers/                              # Multi-Provider LLM Gateway
│   │   ├── __init__.py                         # Package exports
│   │   ├── base_provider.py                    # Abstract LLMProvider interface; LLMProviderError carries a FailureKind
│   │   ├── errors.py                           # Failure classification (rate_limit/quota/auth/timeout/…) & which kinds fall back
│   │   ├── gemini_provider.py                  # Google Gemini adapter (Gemini 3.7 Flash, 2.5 Pro, 2.0 Flash)
│   │   ├── groq_provider.py                    # High-speed Groq inference adapter (LLaMA 3.3 70B, 3.1 8B, Mixtral)
│   │   ├── key_pool.py                         # Sticky, health-tracked key rotation with per-failure cooldowns
│   │   ├── multimodal.py                       # OpenAI-style image content parts (build, detect, strip for text-only gateways)
│   │   ├── openrouter_provider.py              # OpenRouter adapter (MiniMax M3 fallback) over a 5-key KeyPool; returns key_id, never keys
│   │   ├── router.py                           # ProviderRouter: routing + LLM_FALLBACK_CHAIN walk on provider failures, attempt observer
│   │   └── web2api_keys.py                     # GEMINI_WEB2API_* base URL & rotating key loader used by GeminiProvider
│   ├── pdf2latex/                              # Per-page PDF → LaTeX importer (uses the copilot's LLM)
│   │   ├── __init__.py                         # Package exports
│   │   ├── config.py                           # PDF2LATEX_* non-LLM settings (concurrency, timeouts, limits, coverage target, visual floor, job dir)
│   │   ├── extract.py                          # PyMuPDF facts + XY-cut reading order: spans, rules/rects, images, rasters, scans
│   │   ├── facts.py                            # Per-page facts JSON (blocks, side columns, \vspace gaps, `fit` widths) + positioned-layout fallback (TikZ)
│   │   ├── fontmap.py                          # Font class (metric-compatible Carlito/Caladea), bold from name/descriptor/synthetic rendering
│   │   ├── geometry.py                         # Post-compile repair: bold/italic restored, right-edge overflow fitted with \obhfit
│   │   ├── jobs.py                             # File-backed job state (works across uvicorn workers), purge
│   │   ├── llm.py                              # provider_router.chat with DEFAULT_MODEL: timeouts, retries, concurrency cap, own thread pool
│   │   ├── models.py                           # Span/Line/Drawing/ImageRef/PageExtract/PageReport/ConversionReport dataclasses
│   │   ├── pipeline.py                         # Orchestration: per-page generate → compile/repair → SSIM → geometry repair → re-run → merge → write
│   │   ├── preamble.py                         # Deterministic preamble (geometry, exact colors, fonts) & page merging/markers
│   │   ├── prompts.py                          # Page, quality re-run and compile-fix prompts
│   │   ├── runner.py                           # Schedules jobs on the server event loop (HTTP endpoint & copilot tool)
│   │   ├── storage.py                          # Writes output into the project (no silent overwrite), creates import projects
│   │   ├── texutil.py                          # pdfLaTeX escaping & Unicode → LaTeX mapping
│   │   └── verify.py                           # pdftoppm render, shift-aligned SSIM, regions, word coverage & word displacement
│   ├── routes/                                 # Modular FastAPI API Routers
│   │   ├── __init__.py                         # Package exports
│   │   ├── agent_routes.py                     # OpenCode SSE stream (POST /api/agent/opencode), abort, validate-latex & resolve-edits
│   │   ├── collab_routes.py                    # WS /ws/collab/{project_id}, POST /api/collab/ticket & /api/collab/presence, config & room introspection
│   │   └── pdf_convert.py                      # PDF import jobs (POST/GET /api/convert/pdf…), previews, guest session & migration
│   ├── services/                               # Business Logic & Support Services
│   │   ├── __init__.py                         # Package exports
│   │   ├── guest_cleanup.py                    # Scheduled daemon purging expired guest projects & old PDF import jobs
│   │   ├── guest_identity.py                   # HMAC-SHA256 guest cookie tokens & fingerprint verification
│   │   ├── guest_migrator.py                   # Project & file migration from guest session to user account
│   │   └── guest_quota.py                      # 24-hour guest conversion quota tracking
│   ├── templates/                              # Built-in Curated LaTeX Project Templates
│   │   ├── assignments/                        # Academic Assignment Templates
│   │   │   ├── Minimalist Monochrome Assignment# Clean monochrome coursework template
│   │   │   ├── Modern Lab Report Assignment    # Technical laboratory report template
│   │   │   └── Navy Gold Academic Assignment   # High-elegance academic assignment template
│   │   ├── letters/                            # Formal Letter Templates
│   │   │   ├── letter1/                        # Standard executive business letter
│   │   │   ├── letter2/                        # Academic recommendation letter
│   │   │   └── letter3/                        # Modern minimalist correspondence letter
│   │   ├── papers/                             # Academic & Conference Paper Templates
│   │   │   ├── IEEE Conference Paper           # Standard double-column IEEE conference paper
│   │   │   ├── IEEE Journal Paper              # Formal double-column IEEE Transactions journal paper
│   │   │   └── Research Paper Proposal         # Multi-section scientific grant/research proposal
│   │   ├── ppt/                                # Beamer Slide Presentation Templates
│   │   │   ├── A Minimalist Beamer Theme       # Clean Focus-style presentation deck
│   │   │   ├── Basic Presentation Template     # Standard Madrid presentation deck
│   │   │   ├── Nordlight Presentation Template # Dark modern teal & orange Beamer deck
│   │   │   ├── Prism Presentation Template     # Vibrant geometric modern presentation deck
│   │   │   ├── Regalia Presentation Template   # DEFAULT PPT TEMPLATE (Navy/Gold/Cream aspectratio=169)
│   │   │   ├── Sorbonne University Template    # Formal academic university deck
│   │   │   └── UW Milwaukee Beamer Template    # University branded presentation deck
│   │   ├── resume/                             # Professional CV & Resume Templates
│   │   │   ├── 63abeea21637a200a47e07cf/       # ModernCV Banking style
│   │   │   ├── 63abf6ac1637a200a47e0c87/       # ModernCV Casual style
│   │   │   ├── 63ac46dc1637a200a47e7bf2/       # ModernCV Classic style
│   │   │   ├── 63b80c6d78d656009cf7a623/       # Academic Curriculum Vitae
│   │   │   ├── 63b80d2578d656009cf7a659/       # DeveloperCV with fontawesome icons
│   │   │   ├── 63b80e4f78d656009cf7a6c2/       # Deedy Resume (Two-column technical layout)
│   │   │   ├── 63b80edf78d656009cf7a70a/       # Compact Executive Resume
│   │   │   ├── 63b8103a78d656009cf7a7d3/       # Stylish Professional Resume
│   │   │   └── 63b810f378d656009cf7a813/       # Minimalist Res.cls Resume
│   │   └── thesis/                             # Master's & Doctoral Thesis Templates
│   │       └── Thesis Chapter Template/        # Multi-chapter graduate thesis template
│   ├── latex_layout/                           # Page geometry: measuring, judging & repairing typeset layout (agent + importer)
│   │   ├── __init__.py                         # Package overview
│   │   ├── blocks.py                           # TextBlocks from a PDF page; source/output comparison (weight, size, overflow)
│   │   ├── issues.py                           # LayoutIssue taxonomy + geometric detection (margins, broken tokens, tables, page bottom)
│   │   ├── justify.py                          # fit_fragment ladder; TeX-measured widths & page geometry (\settowidth / \textwidth probes)
│   │   ├── repair.py                           # Closed set of minimal repairs per defect; text-preservation & no-shrink guards
│   │   ├── vision.py                           # Optional advisory vision pass on pages geometry could not explain (JUSTIFY_VISION=1)
│   │   ├── metrics.py                          # String widths from the TeX font files (kpsewhich), latex_to_plain
│   │   └── overflow.py                         # Overfull boxes, past-the-text-area and off-page detection
│   ├── tests/                                  # Pytest suite (no network; TeX-dependent tests skip without pdflatex)
│   │   ├── conftest.py                         # ScriptedLLM stub for provider_router.chat, stub shadow compiler, run_agent helpers
│   │   ├── pdf2latex_fixtures.py               # IRCTC-like ticket PDF (Carlito, bold labels, right edge, long IDs), synthetic bold
│   │   ├── test_agent_json_latex.py            # LaTeX inside agent JSON: escaped / raw / mixed replies, &, \n, \\\hline, prompt rule
│   │   ├── test_agent_compile_outcomes.py      # Budget exhaustion compiles, last-step repair turn, strict fix requests, partial fixes, honest explanation
│   │   ├── test_agent_token_budget.py          # Targeted context: prompt size vs document size, one-call edits, ledger
│   │   ├── test_collab_auth.py                 # Realtime auth: ticket signing/expiry/replay/binding, roles, handshake codes, revocation, origins
│   │   ├── test_collab_sync.py                 # Realtime rooms: CRDT merge, same-offset concurrency, late joiners, Viewer writes, restart, persistence, external writes
│   │   ├── test_compile_pre_heal.py            # compile_latex pre-heal gating (editor / agent / importer) & line remap to source
│   │   ├── test_compile_gate_truth.py          # Compile gate: no false passes (infra, masked errors, timeout, fix mode), engine, failure log, parser
│   │   ├── test_justify_content.py             # fit_fragment ladder, long words, overfull parsing, compiled overflow fix
│   │   ├── test_layout_repair.py               # Render-aware repair: detection, source mapping, tables, longtable, rollback, stale version, meaning preserved
│   │   ├── test_locator.py                     # Node IDs, exact/normalized/fuzzy, ambiguity, structured failure, legacy chunk IDs
│   │   ├── test_pdf2latex_fidelity.py          # Bold signals, sizes, font mapping, body repair, ticket conversion regression
│   │   ├── test_provider_fallback.py           # Fallback chain, 429 rotation, 5-key exhaustion, cooldown recovery, no key leaks
│   │   ├── test_required_packages.py           # Missing \usepackage injection, error-driven `_` / `&` repairs
│   │   ├── test_resolve_edits_endpoint.py      # resolve-edits endpoint, node metadata, all-or-nothing
│   │   ├── test_converted_document_edits.py    # Agent edits on imported PDFs (text-match context, case-insensitive), fake-bold PDFs
│   │   ├── test_transactions.py                # Scoped heal, duplicate guard, compile rollback/repair, provider-failure rollback
│   │   └── test_write_gate.py                  # Validator magnitudes, \% / tikz / \end{document} healer fixes, fuzzy guard, edit hygiene, resolve-edits guard
│   ├── attached_context.py                     # Multi-turn in-memory TTL store for user-attached reference files
│   ├── auth.py                                 # Cross-stack Better-Auth session verification & RBAC
│   ├── cancellation.py                         # Thread-safe cancellation tokens & HTTP stream abort manager
│   ├── compile_queue.py                        # Concurrency-controlled compile semaphore, queue & dedicated compile thread pool
│   ├── compiler.py                             # TeX engine runner (latexmk/pdflatex; `% !TEX program` or fontspec auto → xelatex/lualatex; latexmk→direct fallback; biber/bibtex; heavy-doc timeout; pre-heal with error lines mapped back to source; recovery runs keep their error list), TeX error list & ReportLab fallback
│   ├── context_strategy.py                     # Smart context strategy engine (TARGETED, WHOLE_FILE, SUMMARY_FIRST)
│   ├── database.py                             # Asynchronous SQLAlchemy connection pool & sessionmaker
│   ├── document_analyzer.py                    # Fast local LaTeX AST parser & structural metrics extractor (No LLM)
│   ├── document_index.py                       # LaTeX AST chunk indexer & ensure_document_environment repairer (real \begin/\end{document} found on the masked view)
│   ├── edit_validator.py                       # Coverage validation, single-pass literal masking & differential pre-commit checks (validate_edit: per-occurrence multiset + aggregate magnitudes; validation only — repair lives in latex_error_fixer)
│   ├── file_analyzer.py                        # Multimodal AI analysis for uploaded files & TikZ synthesizer
│   ├── latex_error_fixer.py                    # LaTeX error log parser & deterministic repairer (env balance, lonely \item, TikZ semicolons, \bottom→\bottomrule, bare & in frame titles, colors; masked-view structure, discarded if it raises the error count)
│   ├── main.py                                 # FastAPI application entry point, CORS, lifespan, compile & synctex
│   ├── models.py                               # SQLAlchemy ORM models for Better-Auth schema (User, Session, Account)
│   ├── project_storage.py                      # Local filesystem disk storage & Supabase storage manager
│   ├── prompt_builder.py                       # Structured system prompt assembler enforcing surgical edits & Regalia
│   ├── query_rewriter.py                       # Fast multi-query expansion for hybrid RAG retrieval
│   ├── rate_limiter.py                         # Sliding-window in-memory rate limiter per IP / User ID
│   ├── retriever.py                            # Vector & structural retriever interfacing with Qdrant
│   ├── scope_classifier.py                     # Request scope classifier (TARGETED_EDIT vs FULL_DOCUMENT_REWRITE)
│   ├── synctex_service.py                      # SyncTeX forward (view) & backward (edit) coordinate locator
│   ├── template_service.py                     # Template discovery, metadata parsing & thumbnail server
│   ├── trace.py                                # Structured telemetry & observability records (AgentTrace, ConversionTrace)
│   ├── Dockerfile                              # Backend standalone production container build
│   ├── pyproject.toml                          # Python package manifest & tool configurations
│   ├── requirements.txt                        # Python production pip dependencies
│   ├── uv.lock                                 # UV package manager exact dependency lockfile
│   └── README.md                               # Backend development & setup guide
│
├── components/                                 # React UI & Workspace Components
│   ├── dashboard/                              # Dashboard UI Components
│   │   ├── NotificationsPopover.tsx            # In-app notification popover for collaboration invites
│   │   ├── Sidebar.tsx                         # Collapsible dashboard sidebar with route links
│   │   ├── TopNav.tsx                          # Dashboard top header bar with breadcrumbs & user profile
│   │   └── UserProfileDropdown.tsx             # User avatar dropdown menu with settings & sign-out
│   ├── editor/                                 # Master LaTeX Editor Suite Components
│   │   ├── AgentReasoningWindow.tsx            # Live ReAct thought / step execution & inspection monitor
│   │   ├── ApiSettingsModal.tsx                # Custom user API keys dialog (Gemini, Groq, OpenRouter)
│   │   ├── ChatMessageContent.tsx              # Markdown & LaTeX formula renderer using KaTeX
│   │   ├── ChatModeToggle.tsx                  # Mode toggle switching between 'Ask' and 'Edit' modes
│   │   ├── CollabPresenceBar.tsx               # Who is live right now: avatars, their file, idle state, 🟢/🟡/🔴 link state
│   │   ├── CollaboratorAvatars.tsx             # Invited collaborators: avatar stack, invite, remove, transfer ownership
│   │   ├── CompileToolbar.tsx                  # Compile button, engine dropdown, error pill & "Ask AI to Fix"
│   │   ├── CopyButton.tsx                      # Copy-to-clipboard affordance on chat messages (prompt recall)
│   │   ├── EditorLayout.tsx                    # Master resizable split-pane editor shell & AI stream handler (getActiveEditor resolves the visible Monaco; result merged into final_diff; file-tagged edits; compile errors kept with the PDF)
│   │   ├── EditorSearchBar.tsx                 # Find & replace over the active model (match counter, case/word/regex, replace all); replaces Monaco's find widget on both platforms
│   │   ├── EditorThemeModal.tsx                # Monaco editor theme & typography customizer modal
│   │   ├── FileAnalyzerModal.tsx               # File inspection & AI multimodal querying modal
│   │   ├── InlineDiffEditor.tsx                # Side-by-side or unified Monaco diff viewer with Accept/Reject
│   │   ├── LatexEditorView.tsx                 # Code editor wrapper with line numbers, markers and SyncTeX
│   │   ├── MobileEditorAssist.tsx              # Touch editing layer for Monaco: draggable caret & selection handles + action callout (Select/Copy/Cut/Paste/Find, iOS paste fallback)
│   │   ├── ModelSelector.tsx                   # Dropdown model picker with provider badges
│   │   ├── PDFViewer.tsx                       # Interactive PDF preview with SyncTeX double-click triggers; non-blocking error bar + Ask AI to Fix for PDFs compiled with errors
│   │   ├── PresentationView.tsx                # Fullscreen Beamer slide player with laser pointer mode
│   │   └── ProjectFilesPanel.tsx               # File tree explorer, asset uploader & file manager
│   ├── pdf-import/                             # PDF → LaTeX importer UI (dashboard, /convert, editor, copilot)
│   │   ├── ImportPdfDialog.tsx                 # Upload, mode selector, per-page progress, cancellation, report & preview
│   │   └── usePdfConversionJob.ts              # Job start/poll/commit/cancel hooks, config & authenticated page previews
│   ├── extend/                                 # Extended Viewer Widgets
│   │   ├── document-viewer-sidebar.tsx         # Document thumbnails & outline sidebar
│   │   └── pdf-viewer.tsx                      # Embedded PDF canvas renderer
│   ├── landing/                                # Landing Page Showcase Sections
│   │   ├── BrandMarquee.tsx                    # Academic & institutional logo marquee
│   │   ├── CTASection.tsx                      # Call-to-action bottom banner
│   │   ├── Features.tsx                        # Core features grid
│   │   ├── Footer.tsx                          # Footer with navigation & copyright
│   │   ├── FreeSection.tsx                     # 100% Free & open-source badge showcase
│   │   ├── Header.tsx                          # Public navigation header with sign-in buttons
│   │   ├── Hero.tsx                            # Animated hero header with dynamic CTAs
│   │   ├── Introduction.tsx                    # Project vision & architecture introduction
│   │   ├── OpenSourceSection.tsx               # GitHub links & open source manifesto
│   │   ├── PdfToLatexSection.tsx               # Interactive PDF to LaTeX demo preview
│   │   ├── SelfHosting.tsx                     # Docker self-hosting instructions
│   │   ├── Showcase.tsx                        # Feature showcase tabs with interactive previews
│   │   ├── TechnicalMarquee.tsx                # Tech stack badges marquee
│   │   └── TemplatesSection.tsx                # Template gallery preview
│   ├── ui/                                     # Radix UI & shadcn Accessible Primitives
│   │   ├── alert-dialog.tsx                    # Modal confirmation alert dialog
│   │   ├── avatar.tsx                          # User image avatar with fallback initials
│   │   ├── badge-custom.tsx                    # Customized status badge
│   │   ├── badge.tsx                           # Standard UI badge component
│   │   ├── button.tsx                          # Accessible button with variants (default, outline, ghost)
│   │   ├── card.tsx                            # Content card container with header, content & footer
│   │   ├── command-palette.tsx                 # Keyboard-driven command palette (Cmd+K)
│   │   ├── dialog.tsx                          # Accessible modal dialog window
│   │   ├── dropdown-menu.tsx                   # Dropdown menu primitive
│   │   ├── empty-state.tsx                     # Empty state illustration & call-to-action
│   │   ├── github-icon.tsx                     # SVG GitHub brand icon
│   │   ├── input.tsx                           # Form text input
│   │   ├── label.tsx                           # Accessible form field label
│   │   ├── loading-screen.tsx                  # Full-page loading animation
│   │   ├── OverBranchLogo.tsx                  # OverBranch logo brand mark & typography
│   │   ├── popover.tsx                         # Floating popover anchor & content
│   │   ├── progress.tsx                        # Linear progress bar
│   │   ├── scroll-area.tsx                     # Custom scrollable area primitive
│   │   ├── select.tsx                          # Accessible dropdown select input
│   │   ├── separator.tsx                       # Horizontal & vertical divider rule
│   │   ├── sheet.tsx                           # Slide-out drawer sheet
│   │   ├── skeleton-loader.tsx                 # Animated skeleton placeholder
│   │   ├── slider.tsx                          # Accessible numeric slider input
│   │   ├── spinner.tsx                         # Animated circular loading spinner
│   │   ├── table.tsx                           # Accessible data table components
│   │   ├── tabs-animated.tsx                   # Animated tabs with sliding active indicator
│   │   ├── textarea.tsx                        # Multi-line text input
│   │   ├── theme-toggle.tsx                    # Light/dark mode toggle button
│   │   ├── toggle.tsx                          # Two-state toggle button
│   │   └── tooltip.tsx                         # Hover tooltip popup
│   ├── DiffWidget.tsx                          # Compact floating diff widget with accept/revert
│   └── GuestMigrationListener.tsx              # Client listener migrating guest session on user login
│
├── db/                                         # Database Layer (Drizzle ORM & PostgreSQL)
│   ├── index.ts                                # Drizzle client initialization with pg connection pool
│   └── schema.ts                               # PostgreSQL tables: user, session, projects, project_members, collab_doc_state, etc.
│
├── drizzle/                                    # Drizzle SQL Migrations & Schema Snapshots
│   ├── 0000_condemned_the_twelve.sql           # Initial baseline SQL schema migration
│   └── meta/                                   # Drizzle schema snapshot history & migration journal
│       ├── 0000_snapshot.json                  # Schema snapshot JSON
│       └── _journal.json                       # Migration execution journal
│
├── hooks/                                      # Custom React Hooks
│   └── useGuestMigration.ts                    # Hook managing guest cookie token & migration dispatch
│
├── lib/                                        # Shared Library Utilities & Client SDKs
│   ├── collab/                                 # Browser side of realtime collaboration
│   │   ├── colors.ts                           # Stable per-user cursor/avatar colour derived from the user id
│   │   ├── log.ts                              # Structured COLLAB_* console logging (NEXT_PUBLIC_COLLAB_DEBUG / localStorage)
│   │   ├── monaco-binding.ts                   # Hand-written Yjs <-> Monaco binding + remote cursors, labels & per-user UndoManager
│   │   ├── text-diff.ts                        # Minimal line edits + applyTextToEditor: AI output as surgical CRDT ops
│   │   └── useCollaboration.ts                 # Session hook: Y.Doc, y-websocket provider, tickets, status, peers, file re-binding
│   ├── hooks/
│   │   └── use-debounce.ts                     # Debounce value hook for inputs and auto-compiles
│   ├── ai-file-analysis.ts                     # Client helper invoking file analyzer API
│   ├── api-client.ts                           # Standardized fetch API wrapper with auth & error handling
│   ├── auth-client.ts                          # Better-Auth client SDK instance (signIn, signOut, useSession)
│   ├── auth.ts                                 # Better-Auth server configuration & PostgreSQL adapter
│   ├── clipboard.ts                            # copyText / readClipboard with execCommand fallback; shared by the toolbar, CopyButton and the mobile callout
│   ├── EditHistoryStore.ts                     # LocalStorage edit history & undo/redo tracking
│   ├── guest-token.ts                          # Guest token cookie management & persistence
│   ├── latex-edit-apply.ts                     # Pure applier for AI edit items (authoritative vs chunk replay, zero silent drops)
│   ├── latex-validate.ts                       # Clients for POST /api/agent/validate-latex and /api/agent/resolve-edits
│   ├── IndexedDBEmbeddingCache.ts              # Browser IndexedDB cache for client-side embeddings
│   ├── pdf-thumbnail-utils.ts                  # PDF.js page canvas thumbnail rendering
│   └── utils.ts                                # Tailwind CSS class merging utility (cn)
│
├── providers/                                  # React Context Providers
│   └── ThemeProvider.tsx                       # Next-themes dark/light theme wrapper
│
├── public/                                     # Public Static Web Assets
│   ├── favicon.ico                             # Browser icon
│   ├── file.svg                                # File graphic icon
│   ├── globe.svg                               # Globe graphic icon
│   ├── icon.png                                # Brand logo PNG
│   ├── next.svg                                # Next.js framework logo
│   ├── vercel.svg                              # Vercel hosting logo
│   └── window.svg                              # Window graphic icon
│
├── scripts/                                    # Maintenance & Diagnostics Scripts
│   ├── run-collab-tests.sh                     # Bundles & runs the browser-side collaboration checks (esbuild from node_modules)
│   ├── test_collab_binding.mjs                 # Yjs <-> Monaco binding: loop safety, convergence, per-user undo, cursor decorations
│   ├── test_collab_text_diff.mjs               # computeLineEdits / applyTextToEditor round trips incl. 300 randomized cases
│   └── test_file_analysis.py                   # Local sanity script testing multimodal file analyzer
│
├── server/                                     # Server tRPC Core Layer
│   └── trpc/
│       ├── context.ts                          # tRPC context building with Better-Auth session extraction
│       ├── init.ts                             # tRPC router & procedure builders (publicProcedure, protectedProcedure)
│       └── routers/
│           └── project.ts                      # Core database-level project procedures
│
├── supabase/                                   # Supabase Migrations & Configurations
│   └── migrations/
│       ├── 001_initial_schema.sql              # Baseline PostgreSQL schema for standalone Supabase
│       └── 002_collab_doc_state.sql            # collab_doc_state table (service-role only, RLS enabled)
│
├── trpc/                                       # Client-Server tRPC Router Collection
│   ├── client.tsx                              # tRPC React Query provider component
│   ├── init.ts                                 # Client-side tRPC proxy initialization
│   └── routers/                                # Feature-Specific tRPC Routers
│       ├── _app.ts                             # Master AppRouter combining all sub-routers
│       ├── ai.ts                               # AI assistant queries & proxy procedures
│       ├── auth.ts                             # User authentication status procedures
│       ├── comments.ts                         # Document inline comments & resolution
│       ├── dashboard.ts                        # Dashboard metrics, recent projects & activity
│       ├── invitations.ts                      # Project collaboration invites & member management
│       ├── notifications.ts                    # Notification center procedures
│       ├── preferences.ts                      # User & editor preferences synchronization
│       ├── projects.ts                         # Project CRUD, file trees, starring & cloning
│       ├── settings.ts                         # System & account settings
│       ├── synctex.ts                          # SyncTeX forward/backward proxy procedures
│       ├── templates.ts                        # LaTeX template listing, details & cloning
│       └── user.ts                             # User profile updates & preference queries
│
├── types/                                      # TypeScript Global Type Definitions
│   └── sync.ts                                 # SyncTeX coordinate packets, bounding boxes & compile errors
│
└── uploads/                                    # Local Isolated File System Project Storage
    ├── collab-state/                           # <project_id>.ybin CRDT snapshots (restart safety; purged after 30 days)
    └── projects/                               # Project directories partitioned by project_id
```

---

# 3. Deep-Dive: How Every Feature Works

---

### Feature 1: Real-Time LaTeX Compilation, Concurrency Queue & ReportLab Fallback

```
+------------------------------------------------------------------------------------+
|                             COMPILATION WORKFLOW                                   |
|                                                                                    |
|  [Editor Code + Assets] ──► POST /api/compile (Rate Limited: 60/min)               |
|                                     │                                              |
|                       [CompileQueue Semaphore (Max 4)]                             |
|                                     │                                              |
|                       Is TeX engine installed?                                     |
|                       ├── YES: Run latexmk / pdflatex (with synctex=1)             |
|                       │        ├── Success: Output PDF + Save SyncTeX Artifacts    |
|                       │        └── Failure: Extract errors from .log file          |
|                       └── NO : Trigger ReportLab Fallback Generator                |
|                                ├── Parse Beamer frames -> Landscape Slides         |
|                                └── Parse Sections     -> Portrait Document         |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/compiler.py`](file:///home/abin/overbranch/backend/compiler.py), [`backend/compile_queue.py`](file:///home/abin/overbranch/backend/compile_queue.py), [`backend/main.py`](file:///home/abin/overbranch/backend/main.py), [`components/editor/CompileToolbar.tsx`](file:///home/abin/overbranch/components/editor/CompileToolbar.tsx)
- **Engines Supported**: `latexmk`, `pdflatex`, `xelatex`, `lualatex`. A `% !TEX program = xelatex|lualatex` magic comment in the first 20 lines overrides the default engine; projects (including imported PDFs) default to pdflatex. On success the result also lists any TeX error lines (`errors`), since nonstopmode can produce a PDF despite errors, and the overfull boxes (`overfull`: amount and source lines), which never reach the truncated `log`.
- **Overleaf-parity hardening** (so LLM-generated documents that compile on Overleaf also compile here): when the caller leaves the engine at its default and there is no magic comment, `needs_unicode_engine()` detects `fontspec` / `unicode-math` / `polyglossia` / `\setmainfont` etc. and switches to **XeLaTeX** (both the `latexmk` invocation — via `-xelatex` — and the recovery engine). The `latexmk` branch now falls back to a direct engine run if `latexmk` is not installed (a missing `latexmk` previously surfaced as an empty, mysterious failure). A **direct** (non-`latexmk`) engine run resolves bibliographies itself: `_bibliography_backend()` picks `biber` (biblatex) or `bibtex` and runs it plus two extra passes. `is_heavy_document()` raises the per-run timeout to ≥90 s for large or TikZ/pgfplots-heavy documents. Note: `-shell-escape` is **not** enabled (it would let user LaTeX run arbitrary shell commands), so `minted` / `svg` still require a source-level substitution.
- **`compile_latex` flags**: `-synctex=1` is only passed when `persist_synctex` is set, so throwaway compiles do not write artifacts nobody reads. `allow_recovery=False` skips the patch-and-retry cascade (disable missing packages ×4, lmodern, beamercolorbox `bg`, titlesec) — up to seven extra engine runs whose output the PDF importer rejects anyway, since it treats a PDF obtained by silently disabling a package as a failure and hands the errors to the model instead. `pre_heal` (default: follows `allow_recovery`) runs the deterministic whole-document healer (`latex_error_fixer.auto_heal_latex_code`) before TeX, in the public `compile_latex` wrapper around `_compile_latex_impl`. The editor's `/api/compile` path heals (so a plain Compile fixes the same faults the agent self-corrects); the PDF importer (`pipeline.py`, `allow_recovery=False`) and the agent's `shadow_compiler.py` (`allow_recovery=True, pre_heal=False`, which heals only the lines it edited via `heal_touched`) compile their exact code. A heal can insert lines (e.g. `\usetikzlibrary{calc}` after `\usepackage{tikz}`), so every TeX line reference in the result — `main.tex:N:`, `l.N`, `on input line N`, `at lines a--b`, `overfull[].lines` — is mapped back to the caller's source by `_remap_result_lines` (difflib line map); otherwise the error panel and "Ask AI to Fix" pointed two or more lines off, and the agent repaired the wrong lines. `tests/test_compile_pre_heal.py` covers the gating and the remap with a faked TeX.
- **Errors are never dropped**: `_compile_failure`'s `error_log` keeps TeX's own `file:line:` / `! …` lines with their `l.N` context (it used to keep only lines starting `!` or containing `error:`, which dropped `Undefined control sequence` and `Missing $ inserted` under `-file-line-error` and left "Ask AI to Fix" with only *Fatal error occurred*) and failures carry the full `errors` list. Recovery recompiles run with `-file-line-error`, report `errors` (a disabled package used to hide every other error) and remap lines when a patch inserted one (lmodern). The missing-package recovery now recognises the `./main.tex:N: LaTeX Error: File … not found` form — every direct engine run uses it, so that recovery never fired before. An explicit `pdfLaTeX` request (the editor and the agent both send it) honours the fontspec/unicode-math → XeLaTeX detection. The Docker images install `biber` (a separate Debian package) for the direct-engine bibliography path.
- **How It Works**:
  1. The client sends a `CompileRequest` containing `latex_code`, `engine`, `project_id`, `images`, and `files` (with base64 payloads).
  2. Request passes through [`backend/rate_limiter.py`](file:///home/abin/overbranch/backend/rate_limiter.py) (60 requests/minute per caller) and Better-Auth / guest authentication.
  3. `compile_queue.py` gates execution with an `asyncio.Semaphore` (default: 4 concurrent compilations) to prevent server overload, returning HTTP 429 with `Retry-After` if the queue depth exceeds limits. Compiles run on a **dedicated `ThreadPoolExecutor` sized to the semaphore**, not the event loop's default executor: a slot is taken before a thread is, so sharing the default pool (only `min(32, cpu+4)` threads — 8 on a 4-core host) let a compile hold a concurrency slot while queued behind unrelated blocking work, notably the PDF importer's provider calls, which park a thread for as long as `PDF2LATEX_PAGE_TIMEOUT` allows.
  4. `compiler.py` creates a temporary sandbox folder via `tempfile.TemporaryDirectory()`.
  5. All project assets and subdirectories are written to disk using `write_file_safely()`, which guards against directory traversal attacks.
  6. Path augmentation is run via `augment_path_for_latex()`, locating MiKTeX or TeXLive binaries across Linux and Windows environments.
  7. If `latexmk` or `pdflatex` is detected:
     - Subprocess is spawned: `["latexmk", "-pdf", "-interaction=nonstopmode", "-synctex=1", "main.tex"]`.
     - Compilation artifacts (`.pdf`, `.log`, `.synctex.gz`) are collected.
     - SyncTeX artifacts are persisted to `/tmp/overbranch_synctex_cache/<project_id>/` for fast querying.
     - Output PDF is base64-encoded and returned with compilation logs and elapsed runtime.
  8. If no TeX engine exists on the host machine:
     - `generate_fallback_pdf()` automatically activates.
     - It cleans LaTeX macros via `clean_tex_syntax()`, detects whether the document is a Beamer presentation or an article, and uses ReportLab flowables (`Paragraph`, `Table`, `Spacer`, `PageBreak`) to render a clean, high-resolution PDF preview immediately without requiring gigabytes of TeX distributions.

---

### Feature 2: Bidirectional SyncTeX Navigation (Forward & Backward)

- **File Implementation**: [`backend/synctex_service.py`](file:///home/abin/overbranch/backend/synctex_service.py), [`components/editor/PDFViewer.tsx`](file:///home/abin/overbranch/components/editor/PDFViewer.tsx), [`types/sync.ts`](file:///home/abin/overbranch/types/sync.ts)
- **Backward Sync (PDF Click -> Source Line)**:
  1. In the PDF viewer, double-clicking or Cmd+Clicking on text records the click's page number and exact $(x, y)$ coordinates in 72 DPI PDF point space.
  2. Frontend fires `POST /api/synctex/backward` with `{ project_id, page, x, y }`.
  3. `synctex_service.py` executes:
     ```bash
     synctex edit -o "<page>:<x>:<y>:<pdf_path>"
     ```
  4. The output is parsed to extract the source file name, line number, and column.
  5. The Monaco editor automatically moves the cursor to that line and smoothly scrolls it into view.
- **Forward Sync (Source Line -> PDF Location)**:
  1. When editing code or pressing a "Sync to PDF" shortcut, the client fires `POST /api/synctex/forward` with `{ project_id, file: "main.tex", line: 42 }`.
  2. `synctex_service.py` runs `synctex view -i "<line>:<col>:<file>" -o "<pdf_path>"`.
  3. Returns `{ page, x, y, width, height }`.
  4. `PDFViewer.tsx` navigates to that page and renders a pulsing yellow highlight box over the corresponding text element.

---

### Feature 3: OpenCode Bounded ReAct Agent Loop & Dynamic Step Budgeting

```
+------------------------------------------------------------------------------------+
|                         OPENCODE REACT AGENT PIPELINE                              |
|                                                                                    |
|  User Prompt ──► [Scope Classifier] ──► [Document Outline Injection]               |
|                                             │                                      |
|                                             ▼                                      |
|                         [Adaptive Step Budget (6 to 32 Steps)]                     |
|                                             │                                      |
|                 ┌───────────────────────────┴──────────────────────────┐           |
|                 ▼                                                      ▼           |
|       [Inspection Tools]                                       [Action Tools]      |
|       - read_file_range (up to 300 lines)                      - str_replace       |
|       - grep_search (regex / literal)                          - rewrite_chunk     |
|       - list_assets (images / figures)                         - verify_compile    |
|       - get_template_theme (preamble styles)                   - done=true         |
|       - read_attached_document                                                     |
|       - search_uploaded_references                                                 |
|                 │                                                      │           |
|                 └───────────────────────────┬──────────────────────────┘           |
|                                             │                                      |
|                                             ▼                                      |
|                                [Shadow Compilation Sandbox]                        |
|                                             │                                      |
|                                     Did compile pass?                              |
|                                     ├── NO:  Feed back error log -> Self-Correct   |
|                                     └── YES: Run Pre-Commit Validation             |
|                                                  │                                 |
|                                             Generate Diff                          |
|                                                  │                                 |
|                                      Stream Diff to Client                         |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py), [`backend/opencode/tools.py`](file:///home/abin/overbranch/backend/opencode/tools.py), [`backend/opencode/shadow_workspace.py`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py), [`backend/routes/agent_routes.py`](file:///home/abin/overbranch/backend/routes/agent_routes.py)
- **Agent API**:
  - `POST /api/agent/opencode` — SSE reasoning stream (`progress`, `coverage_check`, `compile_error`, `final_diff`, `result`, `pdf_conversion`, `cancelled`, `error`).
  - `POST /api/agent/stop` — cancels an in-flight run.
  - `POST /api/agent/resolve-edits` — `{current_code, items, original_code?}` → places accepted edits the editor could not locate by exact text, using the agent's locator; all-or-nothing (`{success, code, applied[{id, method}], failed[{id, op, target, reason, attempts}], document_unchanged}`). Writes nothing. Rate limited 60/min.
  - `POST /api/agent/validate-latex` — heals and/or validates a LaTeX string without writing anything. Body `{latex_code, project_id?, file_path?, heal?}` → `{valid, errors[], fixes_applied[], healed_code, changed}`. `heal` defaults to **false**: healing hoists packages and injects theme colours, so it must never be applied without showing the user `fixes_applied`. Rate limited 60/min; bodies over 2 MB return 413.
- **The step budget is an estimate the agent can revise, not a contract.** `determine_adaptive_step_budget` sets a *starting* budget from document structure, capped at `MAX_STEP_BUDGET` (32); from there it is extensible.
  - **Why it cannot be fixed.** Running out mid-edit is the worst outcome the loop produces: the transaction is rolled back, so the user waits for a whole run and receives nothing, having lost work the agent had already done correctly. Guessing high instead is no answer — every step is an LLM round trip, so a generous fixed budget is a latency bill paid on every request.
  - **The agent asks** (`request_more_steps`): it is told where it is in its budget on every turn (`[Step 3/8 · 5 remaining…]`, refreshed on the live user message rather than appended, so it never accumulates) — without that it could not judge whether to ask at all, and the tool would be inert.
  - **The loop also grants one itself** when it reaches the limit with edits still unverified, rather than rolling back a half-finished job.
  - **An extension is earned.** It is refused unless the document has actually changed since the last one: an agent re-reading the same block and asking again is precisely the case the ceiling exists for, and more turns make a bad run slower, not better. Bounded three ways at once — `EXTENSION_CHUNK` (6) per grant, `MAX_STEP_EXTENSIONS` (4) requested plus `MAX_AUTO_EXTENSIONS` (2) automatic, and `ABSOLUTE_MAX_STEPS` (64) overall. `AgentTrace.step_extensions` records how often it happened.
  - `TARGETED_EDIT`: 4–12 steps (4 for a typo or citation, 10–12 for creation / redesign).
  - `FULL_DOCUMENT_REWRITE` / `FULL_DOCUMENT_EXPANSION`: `8 + ceil(chunks / 2)`, capped at 32.
  - Ask mode: 4 steps.
  - **Every step is a full LLM round trip, and round trips dominate wall-clock time, so an uncapped budget is an uncapped latency bill.** The previous `max(16, chunks * 2 + 4)` had no ceiling at all: it handed a 20-section report 44 steps and a 40-frame deck 84 — and gave even a 2-chunk rewrite a floor of 16 — for work the prompt explicitly asks the model to **batch** into a handful of turns (and that `compute_step_max_tokens` funds with 16 K output tokens precisely so batching is possible). The budget now assumes several chunks land per turn, plus headroom for `verify_compile` and self-correction.
- **In-Memory Shadow Workspace**:
  All mutations apply to [`ShadowWorkspace`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py). Disk files remain untouched until the user accepts the diff in the UI.
- **Scope precision matters more than step count**: on a 15-chunk deck, `FULL_DOCUMENT_EXPANSION` raises the budget from 4 to 16 steps *and* makes coverage validation demand that every chunk be rewritten. `scope_classifier.py` therefore keeps explicitly singular targets (`"expand the conclusion paragraph"`, `"explain this slide"`, `"fix slide 3"`) as `TARGETED_EDIT` via `SINGLE_TARGET_PATTERNS`, and only promotes to document-wide scope on genuine all-document language (`ALL_DOCUMENT_PATTERNS`: `"every section"`, `"all slides"`, `"the entire document"`).
- **Output budget must permit batching**: the prompt asks the model to batch several `rewrite_chunk` calls per turn, so `compute_step_max_tokens` allocates `FULL_REWRITE_STEP_MAX_TOKENS` (16 K) for rewrite scopes. A 4 K cap made batching impossible and pushed the model into truncation recovery, which costs a second full LLM call and then discards the response. `TARGETED_EDIT` gets **4 K** for the same reason: 2 K sat below the size of one Beamer frame once JSON escaping is paid for, so ordinary targeted edits tripped the truncation path — an extra LLM call to continue the JSON, then a discarded step and a third call when the continuation also ran long.
- **The model's JSON must decode back to the LaTeX it wrote** (`_parse_agent_response` / `sanitize_latex_json`). Models escape LaTeX for JSON inconsistently — correctly (`\\begin`), raw (`\begin`, `\\` for a line break, `\n` for newlines), or mixed — and `\b`, `\f`, `\t`, `\r`, `\n`, `\u` and `\\` are all valid JSON escapes, so a reply can parse yet decode to the wrong LaTeX.
  - **Decode every plausible reading, then judge the result.** The reply is parsed as written and through `sanitize_latex_json` in three modes — `escaped` (an odd run has one stray LaTeX backslash), `escaped_n` (also recognises a stray `\noindent` / `\newline`), `unescaped` (every backslash is literal except a final JSON escape: `\\\n` is a line break then a newline, `\\\hline` a line break then `\hline`). Each decoding is scored on the *decoded* strings by `_corruption_score` — control characters from `\b`/`\f`, a leftover `\u0026`, a literal `\n` control word, a doubly widened `\\begin`, a newline followed by `ewline`/`oindent`, a tab/CR before a letter — and the first clean reading wins (otherwise the least corrupted). Order only breaks ties: as written, then the style `_emits_unescaped_latex` detects.
  - **Why**: the previous version committed to *one* guess for the whole reply. A correctly escaped reply containing a single JSON-only escape — `\u0026` for `&` (a Gemini habit), `\u2014`, `\/`, a `\t` tab — or a newline before `e.g.` / `i)` was taken for raw LaTeX, so every `\\begin` decoded to a line break followed by the word "begin" and every newline to a literal `\n`. Its raw mode also doubled *every* `\n` (contradicting its own docstring) and widened `\\\hline` to `\\hline`. Each turned a whole edit into one line of undefined control sequences; the model's repair edits went through the same parser, so the compile gate's repairs failed and the run was rolled back ("Couldn't safely apply this change…").
  - `\uXXXX`, `\/`, and a `\t` / `\r` not followed by a letter are treated as JSON escapes in every mode. Proof of raw LaTeX ignores those and the ambiguous 2-letter n-macros (`\ne`, `\ni`, `\nu`).
  - The system prompt now states the rule explicitly: every LaTeX backslash doubled, a line break as `\\\\`, `\n` only for newlines, no `\uXXXX` escapes.
  The whole transform runs in **one pass** over the original text, so a run it widens is never reconsidered and widened twice. `tests/test_agent_json_latex.py` pins the decoded LaTeX for each style.
- **Write-path cost**: every write goes through one gate, `ShadowWorkspace._heal_and_validate` — one `auto_heal_latex_code`, then one **differential** `validate_edit` against the pre-edit buffer ([Feature 12](#feature-12-pre-commit-structural-validation)). Healing again *after* the commit (via `ensure_document_structure`) both doubled per-edit cost and mutated the buffer after validation, so the post-commit step is now `_refresh_indexes()`, which only re-derives the line list and chunk index. The end-of-run pass heals **once** and then validates, for the same reason. `get_buffer()` is pure — reads never mutate.
- **Telemetry**: `AgentTrace.record_llm_call` records per-round-trip latency and `usage` tokens, so `summary()` reports `llm_invocations`, `llm_total_latency_ms`, `llm_share_pct` and `tokens_in`/`tokens_out`. LLM round trips dominate wall-clock time; this makes the split measurable instead of inferred.

---

### Feature 4: Automated LaTeX Error Diagnostics & Deterministic Auto-Healing

- **File Implementation**: [`backend/latex_error_fixer.py`](file:///home/abin/overbranch/backend/latex_error_fixer.py), [`components/editor/CompileToolbar.tsx`](file:///home/abin/overbranch/components/editor/CompileToolbar.tsx), [`backend/tests/test_latex_error_fixer.py`](file:///home/abin/overbranch/backend/tests/test_latex_error_fixer.py), [`backend/tests/test_heal_does_not_corrupt.py`](file:///home/abin/overbranch/backend/tests/test_heal_does_not_corrupt.py)
- **The healer reads structure through the validator's masked view** (`_structure_view` → `clean_latex_for_validation`, see [Feature 12](#feature-12-pre-commit-structural-validation)). It used to scan raw text while the validator scanned the masked view, so the two disagreed about what the document contains and the healer "repaired" structure that was never there. Because `auto_heal_latex_code` runs on the **whole buffer on every agent write**, that damage compounded twice over: the user got broken LaTeX, *and* the corrupted buffer failed validation on the next write, so every later edit was rejected and the agent burned its full step budget before the final rollback discarded the run. Observed on shipped templates:
  - `letters/letter3`: `\date{...\begin{flushleft}\today\end{flushleft}}` — ends were processed before begins, so the `\end` on the *same line* looked orphaned, was deleted, and a replacement emitted before `\end{document}`, silently wrapping the rest of the document in a `flushleft` group. **Tags are now processed in the order they appear within a line.**
  - A trailing comment such as `% use \begin{itemize} here later` added a stray `\end{itemize}`, after which no edit to that document could ever pass validation.
  - `resume/63abeea…`: `\item` inside moderncv's class-defined `rSubsection` was wrapped in `\begin{itemize}`, re-rendering the section. **A lonely `\item` is now wrapped only when the innermost open environment is one where `\item` is certainly illegal** (`ITEM_ILLEGAL_HOSTS`: `document`, `frame`, `block`, `column`, `center`, `minipage`, …); any *unknown* environment is assumed to be a class- or package-defined list.
  - `resume/63b8103a…/structure.tex`: `\newenvironment{indentsection}{\begin{list}…}{\end{list}}` is balanced template text, and healing it turned a valid file into an invalid one.
  - `\item` / `\begin{...}` inside `verbatim` and `lstlisting` bodies, and `\usepackage` shown inside a listing being torn out of the example and pasted into the preamble.
- **Healing never makes a document worse.** `auto_heal_latex_code` applies its passes speculatively and **discards all of them** if the structural error count rises, returning the input unchanged. This is the outermost guarantee behind the write path: one bad repair no longer poisons the buffer for the rest of the run.
- **How It Works**:
  1. When LaTeX compilation fails, the raw compiler log is passed to `parse_compilation_errors(error_text)`.
  2. The parser scans for error patterns (`! LaTeX Error: ...`, `l.<line> <snippet>`) and produces structured `ParsedLatexError` records.
  3. `auto_heal_latex_code(code, errors)` runs the deterministic passes in `_apply_heal_passes`, all of them reading structure from the masked view:
     - Closes unclosed environments **positionally** via stack tracking — before the next `\begin{frame}`, before the `\end` that closes an outer environment, or before `\end{document}` — and drops a genuinely orphaned `\end{...}`.
     - Injects `\usetikzlibrary{calc}` into the preamble if TikZ coordinate math `($ ... $)` is present.
     - Adds missing semicolons to TikZ path operations, skipping any `tikzpicture` shown inside a listing (that is example text, not code to repair).
     - Ensures `\begin{document}` and `\end{document}` exist.
     - Injects missing standard color definitions (`navy`, `gold`, `cream`, …) **only where the name is used as a colour argument** (`fg=navy`, `\textcolor{gold}`, `[cream]`), not merely as the word in prose — "the gold standard" was rewriting preambles that never asked for a palette.
  4. When users click "Ask AI to Fix" in [`CompileToolbar.tsx`](file:///home/abin/overbranch/components/editor/CompileToolbar.tsx), `format_compilation_fix_prompt` constructs a targeted prompt sent to the agent loop with exact line numbers and suggested actions.

---

### Feature 5: Prompt Assembly, Environment Preservation & Minimal Surgical Edits

- **File Implementation**: [`backend/prompt_builder.py`](file:///home/abin/overbranch/backend/prompt_builder.py), [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py)
- **How It Works**:
  1. Centralizes the core AI instructions into `SYSTEM_PROMPT_CORE`.
  2. Enforces **minimal, surgical edits**: The agent is strictly forbidden from rewriting entire documents when only changing a few sentences or formulas.
  3. Enforces **strict environment preservation**:
     - Never remove or alter `\begin{...}` or `\end{...}` unless replacing the whole environment.
     - Always include both opening and closing tags on replacements.
     - Never emit partial environments.
     - Math delimiters (`$`, `$$`, `\(`, `\)`) and braces (`{`, `}`) must be strictly balanced.
     - All `\item` commands must reside strictly inside `itemize` or `enumerate`.
     - TikZ statements must terminate with semicolons.
  4. Designates **Regalia** as the default Beamer presentation template for all slide deck generation tasks.

---

### Feature 6: Local LaTeX Document Analysis & Preservation Mapping

- **File Implementation**: [`backend/document_analyzer.py`](file:///home/abin/overbranch/backend/document_analyzer.py), [`backend/tests/test_document_analyzer_and_context.py`](file:///home/abin/overbranch/backend/tests/test_document_analyzer_and_context.py)
- **How It Works**:
  1. Blazing-fast regex and AST scanner executing locally in under 5 milliseconds without calling any LLM API.
  2. Extracts document class, options, title, author, date, and detects Beamer vs. Article vs. Report.
  3. Builds `SectionInfo` entries for all chapters, sections, subsections, and frames with line numbers and character counts.
  4. Flags elements requiring preservation (Title pages, certificates, acknowledgements, abstracts, tables of contents).
  5. Generates compact summaries used by `context_strategy.py` to conserve token budgets.

---

### Feature 7: Multi-Turn Attached Context Session Store & File Injection

- **File Implementation**: [`backend/attached_context.py`](file:///home/abin/overbranch/backend/attached_context.py), [`backend/tests/test_attached_context.py`](file:///home/abin/overbranch/backend/tests/test_attached_context.py)
- **How It Works**:
  1. When a user uploads a reference PDF, paper, or dataset in chat, the file payload is decoded from base64.
  2. `extract_text_and_pages_from_pdf` uses PyMuPDF (`fitz`) or `pypdf` to extract high-fidelity text with page indices.
  3. The parsed document is stored in an in-memory session cache keyed by `project_id` / `session_id` with a 2-hour TTL.
  4. In follow-up messages, the agent accesses tools `read_attached_document` and `search_uploaded_references` to extract real empirical data, formulas, and diagrams without requiring the user to re-upload.

---

### Feature 8: Smart Context Strategy Engine & Token Budgeting

- **File Implementation**: [`backend/context_strategy.py`](file:///home/abin/overbranch/backend/context_strategy.py), [`backend/tests/test_document_analyzer_and_context.py`](file:///home/abin/overbranch/backend/tests/test_document_analyzer_and_context.py)
- **How It Works**:
  1. Analyzes document size, model context capacity, and user intent.
  2. Maps model IDs (Gemini 3.7 Flash: 900K tokens, Groq LLaMA 3.3 70B: 120K tokens, OpenRouter Claude 3.5 Sonnet: 180K tokens).
  3. Selects optimal strategy:
     - `TARGETED`: Sends only the target section and surrounding lines (best for large documents & small models).
     - `WHOLE_FILE`: Injects the entire document (best when document fits comfortably in context window).
     - `SUMMARY_FIRST`: Injects structural outline summary followed by targeted chunks.
     - `PLAN_EXECUTE`: Generates multi-phase transformation plan executed step-by-step.

---

### Feature 9: Scope Classification & AST Structural Chunk Replacement

- **File Implementation**: [`backend/scope_classifier.py`](file:///home/abin/overbranch/backend/scope_classifier.py), [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py), [`backend/tests/test_full_document_rewrite.py`](file:///home/abin/overbranch/backend/tests/test_full_document_rewrite.py)
- **How It Works**:
  1. `classify_scope(prompt, code)` detects whether a prompt is a surgical fix (`TARGETED_EDIT`), topic overhaul (`FULL_DOCUMENT_REWRITE`), expansion request (`EXPAND_CONTENT`), or redesign (`STYLE_REDESIGN`).
  2. `DocumentIndex` parses the LaTeX AST into discrete `DocumentChunk` records with character offsets and line bounds.
  3. In `FULL_DOCUMENT_REWRITE` mode, the agent uses `rewrite_chunk(chunk_id, new_content)` to cleanly replace complete structural blocks without exact string-matching failures.

---

### Feature 10: Full Document Rewrite Coverage Validation & Leftover Detection

- **File Implementation**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py), [`backend/tests/test_full_document_rewrite.py`](file:///home/abin/overbranch/backend/tests/test_full_document_rewrite.py)
- **How It Works**:
  1. `validate_coverage(original_chunks, modified_code, modified_chunk_ids)` checks if all content sections were rewritten during full document overhaul requests.
  2. `detect_leftovers(modified_code, forbidden_terms)` scans for residual terms from old topics or unedited boilerplate.
  3. Rejection & Retries: If the agent attempts to signal `done=true` while chunks remain untouched, the validator rejects completion and prompts the agent to finish unedited sections.

---

### Feature 11: Document Environment Integrity & Delimiter Auto-Balancing

- **File Implementation**: [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py), [`backend/tests/test_document_environment_integrity.py`](file:///home/abin/overbranch/backend/tests/test_document_environment_integrity.py)
- **How It Works**:
  1. `ensure_document_environment(code)` ensures every standalone document contains both `\begin{document}` and `\end{document}`.
  2. Deduplicates multiple occurrences of `\begin{document}` or `\end{document}` created by flawed agent edits.
  3. Finds the exact boundary line between preamble imports (`\usepackage`, `\definecolor`) and document content, inserting `\begin{document}` where missing.

---

### Feature 12: Pre-Commit Structural Validation

- **File Implementation**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py), [`backend/tests/test_edit_pipeline_integrity.py`](file:///home/abin/overbranch/backend/tests/test_edit_pipeline_integrity.py)
- **This module validates only.** Repair lives in `auto_heal_latex_code` ([Feature 4](#feature-4-automated-latex-error-diagnostics--deterministic-auto-healing)), which closes environments **positionally** — before the enclosing `\end` — rather than appending them at end-of-file. (`\item` placement and TikZ semicolons are healer rules, not validator checks.) **Both read structure through the same masked view** (`clean_latex_for_validation`); when they disagreed about what the document contains, the healer "repaired" structure that was never there — see [Feature 4](#feature-4-automated-latex-error-diagnostics--deterministic-auto-healing).
- **Validation is differential** (`validate_edit(before, after)`). Every write validates the **whole** buffer, so an absolute check let a single defect the validator cannot model — a list environment defined in a `.cls`, an `\end{...}` its grammar cannot pair — reject *every* edit for the rest of the run: the agent retried until its step budget ran out and the final rollback discarded the work. Only defects an edit **adds** are that edit's fault, so only those block it. Error signatures are compared position-independently (`Line 12:` prefixes and digits normalised), so a pre-existing defect that merely *moves* is not counted as new. Brand-new documents (empty buffer) are still held to the absolute standard, and so is `POST /api/agent/validate-latex`.
- **How It Works**:
  1. Every `ShadowWorkspace` write goes through one gate, `_heal_and_validate`: `auto_heal_latex_code`, then `validate_edit` against the pre-edit buffer. A write that adds a defect is **rejected** and the agent gets the new errors as feedback. This includes the document-creation path and auxiliary `.tex` files. The final pass in `agent_loop` uses the same differential check against `workspace.get_original()`.
  2. `clean_latex_for_validation(code)` first neutralises everything that must not be read as structure, replacing characters **in place** so the total length and exact newline count are preserved — reported line numbers stay accurate and callers (the healer) can map any offset in the view straight back onto the input:
     - **One left-to-right pass** (`_mask_literal_regions`) for `%` comments, verbatim-like environment bodies, inline `\verb` spans and URL arguments, because **each decides what the others mean**. A `%` inside a `verbatim` body or a `\verb` span is literal; `%20` inside `\url{}` is literal; and a `\begin{lstlisting}` inside a *comment* does not open a block. Masking comments first ate the bodies of real verbatim blocks; masking verbatim first let a commented-out usage example swallow the `%` that disabled its own `\end{lstlisting}`, leaving a live orphan tag — which is why `assignments/Modern Lab Report Assignment` validated as broken and every edit to it failed.
     - Verbatim-like environments: `verbatim`, `semiverbatim` (Beamer `[fragile]` frames), `Verbatim`/`BVerbatim`/`LVerbatim` (fancyvrb), `alltt`, `lstlisting`, `minted`, `listing`, `comment`, `filecontents` and their starred forms. Only the forms that genuinely take one (`minted`, `filecontents`, `SaveVerbatim`, `listing`) may consume a `{...}` argument; allowing it for all of them read `\begin{alltt}{ $ %\end{alltt}` as a 16-character environment name.
     - Inline `\verb` with **any** delimiter, including the starred `\verb*` form. (`\verb` cannot span lines in TeX, so the masking is line-bounded by construction.)
     - The brace group of `\url` / `\nolinkurl` / `\path` / `\href`, so `%`, `#`, `$`, `&` and `_` inside a URL are literal. Math in `\href` *link text* is still validated.
     - Bodies of `\newcommand` / `\renewcommand` / `\providecommand` / `\newenvironment` / `\def`, via a brace-matched scan. Their enclosing braces are kept, so genuine brace imbalance is still caught. Without this, `\newcommand{\openlist}{\begin{itemize}}` reported an unclosed environment and — because every write validates the whole buffer — made **all** subsequent edits fail.
  3. Then checks, with line numbers: environment nesting order via a stack (accepting `\begin {env}` with whitespace, matching the healer's grammar), `$` / `$$` / `\(…\)` / `\[…\]` balance, curly-brace depth, and `\left` / `\right` pairing.
- **Every bundled template is covered** by `tests/test_heal_does_not_corrupt.py`: each `backend/templates/**/*.tex` must validate clean *and* survive a heal unchanged in error count. These are the documents users start from, so one false positive there blocks every edit to a brand-new project.

---

### Feature 13: Shadow Compilation & Compiler-Feedback Self-Correction

- **File Implementation**: [`backend/opencode/shadow_compiler.py`](file:///home/abin/overbranch/backend/opencode/shadow_compiler.py), [`backend/opencode/shadow_workspace.py`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py)
- **How It Works**:
  1. Executes isolated ephemeral compilation in temporary directories.
  2. If compilation fails, extracts error messages and offending line numbers.
  3. Injects compiler diagnostics back into the agent conversation loop for self-correction (up to 2 retries) before delivering diffs to the client.

---

### Feature 14: Regalia Default Presentation Template & Curated Theme Registry

- **File Implementation**: [`backend/opencode/template_registry.py`](file:///home/abin/overbranch/backend/opencode/template_registry.py), [`backend/templates/ppt/Regalia Presentation Template/`](file:///home/abin/overbranch/backend/templates/ppt/Regalia%20Presentation%20Template/)
- **How It Works**:
  1. Regalia is the designated default presentation template across OverBranch:
     - 16:9 widescreen layout (`\documentclass[aspectratio=169]{beamer}`).
     - Custom palette: `cream` canvas, `navy` primary, `gold` accent.
     - Custom frametitle banner with TikZ decoration.
     - Plain title frame banner and 6–12 structured content frames.
  2. `get_template_theme` tool allows agents to extract styling preambles from curated templates (`nordlight`, `prism`, `minimalist`, `ieee`, `acm`) to restyle documents non-destructively while preserving all equations, text, and tables.

---

### Feature 15: Cross-Stack Better-Auth Authentication & Session Sharing

- **File Implementation**: [`backend/auth.py`](file:///home/abin/overbranch/backend/auth.py), [`backend/models.py`](file:///home/abin/overbranch/backend/models.py), [`lib/auth.ts`](file:///home/abin/overbranch/lib/auth.ts), [`lib/auth-client.ts`](file:///home/abin/overbranch/lib/auth-client.ts)
- **How It Works**:
  1. Next.js 15 uses Better-Auth to manage sign-in, registration, and sessions, storing records in the shared PostgreSQL `user` and `session` tables.
  2. The Python FastAPI backend uses async SQLAlchemy to query the `session` table directly, validating session tokens passed in cookies (`better-auth.session_token`) or Bearer headers.
  3. `verify_project_ownership_or_member` enforces role-based access control (owner, editor, viewer).
  4. Guest users receive HMAC-signed tokens with 24-hour expiration.

---

### Feature 16: Sliding-Window Rate Limiting & Denial-of-Service Defense

- **File Implementation**: [`backend/rate_limiter.py`](file:///home/abin/overbranch/backend/rate_limiter.py)
- **How It Works**:
  1. Implements an in-memory, thread-safe sliding-window rate limiter.
  2. Tracks request timestamps per caller key (authenticated user ID, guest token, or IP address).
  3. Limits:
     - Compilation: 60 requests/minute.
     - AI Agent: 30 requests/minute.
     - Guest Conversions: 5 requests/day.
  4. Automatically evicts expired timestamps and returns HTTP 429 when limits are breached.

---

### Feature 17: Real-Time AI Interruption, Stream Abort & Cancellation Tokens

- **File Implementation**: [`backend/cancellation.py`](file:///home/abin/overbranch/backend/cancellation.py), [`backend/routes/agent_routes.py`](file:///home/abin/overbranch/backend/routes/agent_routes.py), [`components/editor/EditorLayout.tsx`](file:///home/abin/overbranch/components/editor/EditorLayout.tsx)
- **How It Works**:
  1. When an AI generation begins, a `CancellationToken` is registered under `(project_id, user_id)`.
  2. The agent loop checks `token.is_cancelled` before and after each LLM call and tool execution.
  3. Clicking "Stop Generation" in the UI sends `POST /api/agent/stop` or triggers an `AbortController`.
  4. The backend cancels active HTTP streams and releases resources immediately.

---

### Feature 18: Multi-Provider LLM Gateway & Fallback Architecture

- **File Implementation**: [`backend/providers/router.py`](file:///home/abin/overbranch/backend/providers/router.py), [`backend/providers/gemini_provider.py`](file:///home/abin/overbranch/backend/providers/gemini_provider.py), [`backend/providers/groq_provider.py`](file:///home/abin/overbranch/backend/providers/groq_provider.py), [`backend/providers/openrouter_provider.py`](file:///home/abin/overbranch/backend/providers/openrouter_provider.py)
- **Supported Providers**:
  - **Google Gemini**: Gemini 3.7 Flash, 2.5 Pro, 2.0 Flash (Long context, multimodal reasoning).
  - **Groq**: LLaMA 3.3 70B Versatile, LLaMA 3.1 8B Instant (Ultra-fast inference).
  - **OpenRouter**: Claude 3.5 Sonnet, GPT-4o, DeepSeek Chat/Coder, MiniMax-01.
- **Failover**: failures are classified (`providers/errors.py`). Rate limits, exhausted quota, timeouts, outages and unavailable models walk `LLM_FALLBACK_CHAIN` (default OpenRouter **MiniMax M3**, `minimax/minimax-m3`); a cancellation or a malformed request does not. OpenRouter's five server-side keys rotate through a health-tracked `KeyPool` (sticky selection, per-failure cooldowns, automatic recovery). See [T](#t-provider-fallback-chain--key-health).

---

### Feature 19: PDF → LaTeX Importer — Per-Page LLM Pipeline

```
+------------------------------------------------------------------------------------+
|                            PDF → LATEX IMPORT PIPELINE                             |
|                                                                                    |
|  POST /api/convert/pdf (multipart) ──► validate (%PDF-, size, pages, quota)        |
|        │                                   └─► job id (202) ── GET …/{job_id} poll |
|        ▼                                                                           |
|  extract facts (PyMuPDF, no LLM) ──► one preamble (geometry, \definecolor, fonts)  |
|        ▼                                                                           |
|  per page, in parallel (PDF2LATEX_CONCURRENCY):                                    |
|     page PNG (150 DPI) + facts JSON ──► provider_router.chat(DEFAULT_MODEL)        |
|     ──► compile page (pdflatex, strict) ──► heal / LLM fix (≤3) ──► words + SSIM   |
|     ──► re-run ONLY if text/overflow is wrong ──► \obfit ──► layout only as rescue |
|        ▼                                                                           |
|  merge with \newpage ──► compile ──► page count == PDF ──► main.tex + assets       |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/pdf2latex/`](file:///home/abin/overbranch/backend/pdf2latex/), [`backend/routes/pdf_convert.py`](file:///home/abin/overbranch/backend/routes/pdf_convert.py), [`components/pdf-import/ImportPdfDialog.tsx`](file:///home/abin/overbranch/components/pdf-import/ImportPdfDialog.tsx), [`components/pdf-import/usePdfConversionJob.ts`](file:///home/abin/overbranch/components/pdf-import/usePdfConversionJob.ts), [`app/convert/page.tsx`](file:///home/abin/overbranch/app/convert/page.tsx)
- **API**:
  - `GET /api/convert/pdf/config` — `llm_available`, `model` (the copilot's), size/page limits, similarity `threshold`.
  - `POST /api/convert/pdf` — multipart `file`, optional `project_id` (else a project is created), `project_name`, `overwrite`, `cancel_previous`. Validates the `%PDF-` header, parses with PyMuPDF, rejects encrypted files, enforces `PDF2LATEX_MAX_FILE_MB` / `PDF2LATEX_MAX_PAGES`, a per-user hourly rate limit, one active job per user (HTTP 409 with `job_id`), and the guest quota. Returns `202 {job_id, project_id}`.
  - `GET /api/convert/pdf/{job_id}` — status, stage, progress, per-page status/similarity/attempts/fallback, report, result (owner only).
  - `POST /api/convert/pdf/{job_id}/commit` — `{overwrite, target_path}` for jobs in `needs_confirmation`.
  - `POST /api/convert/pdf/{job_id}/cancel` — cancels an in-flight or queued job (open LLM streams are aborted via cancellation tokens).
  - `GET /api/convert/pdf/{job_id}/preview/{page}?which=original|converted|diff` — PNG renders for the side-by-side view.
- **LLM**: no converter-specific LLM settings — `llm.py` goes through `provider_router.chat` with `DEFAULT_MODEL`, like the agent loop. Without a configured LLM every page uses the positioned layout and the report says so.
- **Storage**: output goes into `main.tex` (or a chosen `.tex`) and `assets/pdf_<job>/` (extracted images, figure/background rasters) through the normal project storage (disk + `latex_documents`). A non-empty target file is never overwritten without confirmation.
- **Jobs & Cancellation**: state lives in `PDF2LATEX_JOB_DIR/<job_id>/status.json`, so any uvicorn worker can answer polls. Jobs are purged after 24 h by the cleanup scheduler.
- **Entry points**: dashboard "PDF to LaTeX" (new project), `/convert` (guests), editor Files panel "Import PDF" (current project), and the copilot tool `convert_attached_pdf` (the editor opens the same dialog with the job's live progress and asks before replacing `main.tex`).

---

### Feature 20: Fonts, Exact Colors & Unicode for pdfLaTeX

- **File Implementation**: [`backend/pdf2latex/preamble.py`](file:///home/abin/overbranch/backend/pdf2latex/preamble.py), [`backend/pdf2latex/texutil.py`](file:///home/abin/overbranch/backend/pdf2latex/texutil.py)
- **How It Works**:
  1. Every distinct text, rule and fill color is defined once in the preamble with its exact RGB, named after its hex value (`c1F4E79`), so the LLM and the fallback reference the same names.
  2. PDF font names map to pdfLaTeX font packages ([`fontmap.py`](file:///home/abin/overbranch/backend/pdf2latex/fontmap.py)). **Metric-compatible substitutes first** — Calibri → `carlito` (`[sfdefault,lf,t]`: Calibri's tabular lining figures), Cambria → `caladea` — when installed, because a wider substitute moves every line end: Calibri set in Helvetica is 10–25% wider, which pushed the IRCTC ticket's right column past its border and made labels overprint. Otherwise Times-like → `mathptmx`, Palatino/Garamond-like → `mathpazo`, Arial/Helvetica-like → `helvet`, Courier-like → `courier`, Computer/Latin Modern → `lmodern`. The most used family becomes the main font; secondary sans/mono families are loaded too. Exact sizes are kept with `\fontsize`.
  2a. **Overprinted text is one run.** Producers often fake bold by drawing a run twice (fill + stroke, or two fills a fraction of a point apart). PyMuPDF reports each copy as its own line, and the word-coverage gate counts words as a multiset — so every bold label had to be typeset twice and came out "double-layered". `extract.collapse_overprint` keeps one copy and marks it bold; source word boxes and TextBlocks drop the copies the same way.
  2b. **Bold** comes from every signal a PDF offers: name tokens (`Bold`, `Semibold`, `Demi`, `Heavy`, `Black`, `,Bd`, `-B`), PyMuPDF flags, the FontDescriptor (`/FontWeight` ≥ 600, ForceBold) and **synthetic bold** (glyphs filled *and* stroked). Lines that would still come out wider than in the PDF carry a `fit` width in the facts and are wrapped in `\obhfit{w}{…}` (condenses only if needed).
  3. Text in the facts is pre-escaped; Unicode is mapped to LaTeX (quotes, dashes, bullets, math symbols, Greek, ligatures) and characters pdfLaTeX cannot typeset are reported per page.

---

### Feature 21: Compile Repair, Visual Verification & Best-Version Selection

- **File Implementation**: [`backend/pdf2latex/pipeline.py`](file:///home/abin/overbranch/backend/pdf2latex/pipeline.py), [`backend/pdf2latex/verify.py`](file:///home/abin/overbranch/backend/pdf2latex/verify.py), [`backend/compiler.py`](file:///home/abin/overbranch/backend/compiler.py)
- **How It Works**:
  1. Each page is compiled standalone (same preamble) with pdfLaTeX; TeX errors or missing files are failures even if a PDF was produced.
  2. Deterministic heal, then up to `PDF2LATEX_MAX_COMPILE_REPAIRS` LLM fixes with the compile errors; after that the positioned-layout fallback, then the page image.
  3. Renders at `PDF2LATEX_RENDER_DPI`, **aligns the render vertically** against the original, softens both, and scores SSIM + pixel diff; separately compares the words of the compiled page with the PDF's.
  4. **Why text coverage is the gate and SSIM is not.** Full-page SSIM is dominated by the white background and is exquisitely sensitive to glyph registration, so it ranks pages in the wrong order. Measured on a dense A4 page at 100 DPI: a pixel-perfect page nudged down by **1 pt** scores **0.825**; the same text at +3% leading scores **0.766**; an expertly hand-written reflow of the page scores **0.660**; a **blank** page scores **0.795**; a page **missing half its text** scores **0.891**. Gating on `PDF2LATEX_SIM_THRESHOLD` therefore failed essentially every page of every real document, bought each one a re-run that could not succeed (the prompt forbids absolute positioning, which is the only way to win on pixel registration), and then handed the page to the positioned-layout fallback — which scores **0.856** on that page by construction. The user received a wall of TikZ `\node` commands instead of editable LaTeX, after paying for two LLM calls and three compiles per page. Acceptance is now: compiles to one page, `PDF2LATEX_COVERAGE_TARGET` of the words present, ≤5% invented, above `PDF2LATEX_VISUAL_FLOOR`. On a 3-page dense document this took the job from 6 LLM calls / 10 compiles / a 78-node TikZ dump to **3 LLM calls / 4 compiles / editable LaTeX**.
  5. **Why text coverage alone is not enough either.** Coverage says every word is *present*, not that it is in the right *place*. A page whose margin-note column was woven into the running text scored **1.000 coverage and 0.86 similarity** — indistinguishable from a faithful reproduction on both existing metrics — while being visibly scrambled. `verify.displacement` therefore matches the source's words to the output's by text, greedily and in order, and reports the **median distance a word moved**. Measured: a faithful re-setting of a dense page **8.3 pt**, the same margin page laid out correctly **12.6 pt**; the scrambled version **39.2 pt**, a reflow that ignores the spacing facts **65.8 pt**. That is the signal SSIM cannot give, and it is now part of acceptance.
  5b. **Geometry repair (no LLM).** After a page compiles, its TextBlocks are compared with the PDF's ([`geometry.py`](file:///home/abin/overbranch/backend/pdf2latex/geometry.py), [`latex_layout/blocks.py`](file:///home/abin/overbranch/backend/latex_layout/blocks.py)). Runs that lost their bold/italic are wrapped in `\textbf`/`\textit`; lines past their original right edge are wrapped in `\obhfit`. Only text found exactly once in the body is touched (a repeated phrase is placed by reading order when the counts agree). Up to 2 rounds; a round is kept only if coverage is unchanged and visual rank does not drop. Compilation success is not visual correctness: on the ticket regression page this restores 25 bold runs and leaves 0 style mismatches and 0 overflowing lines. What cannot be fixed locally (sizes) goes into the re-run note as concrete items. Text clipped past the page edge makes a page unacceptable.
  6. Only an unacceptable page is re-run, with the missing words, the invented words, the overflow, the measured vertical offset, the median word displacement and the remaining style / right-edge differences. Overflowing pages are scaled to fit with `\obfit`. The positioned layout rescues a page that is still unacceptable, never one that merely reflowed differently.
  7. The report lists per-page similarity (a **reference figure**, not a verdict), SSIM, text coverage, invented-word ratio, measured offset, median word displacement, LLM calls, compile repairs, the source of each page (LLM / positioned layout / page image), warnings, and the compiled vs source page count. It states that the result is best-effort and that a faithful page scores well below 100%.

---

### Feature 22: Scanned Pages, Vector Art & Positioned-Layout Fallback

- **File Implementation**: [`backend/pdf2latex/extract.py`](file:///home/abin/overbranch/backend/pdf2latex/extract.py), [`backend/pdf2latex/facts.py`](file:///home/abin/overbranch/backend/pdf2latex/facts.py)
- **How It Works**:
  1. Scanned pages (fewer than ~20 visible characters, page-covering image) are placed as the scan; an OCR text layer, if present, is added as invisible searchable text.
  2. Curves, gradients and charts are rasterized as figures (with their labels); full-page artwork becomes a text-free background behind the real text.
  3. The positioned layout (`fallback_body`) is a TikZ picture of the text area with every text run, image and rule at its measured position — used when the LLM is unavailable or fails, for scans, and when it is measurably closer to the original.

---

### Feature 23: Guest Conversion Session, Quota Enforcement & Auto-Migration

- **File Implementation**: [`backend/services/guest_identity.py`](file:///home/abin/overbranch/backend/services/guest_identity.py), [`backend/services/guest_quota.py`](file:///home/abin/overbranch/backend/services/guest_quota.py), [`backend/services/guest_migrator.py`](file:///home/abin/overbranch/backend/services/guest_migrator.py), [`backend/routes/pdf_convert.py`](file:///home/abin/overbranch/backend/routes/pdf_convert.py), [`components/GuestMigrationListener.tsx`](file:///home/abin/overbranch/components/GuestMigrationListener.tsx)
- **How It Works**:
  1. Anonymous visitors get an HMAC-signed `ob_guest_token` (24 h) from `GET /api/guest/session`.
  2. Guests may run 1 PDF import per 24 hours (checked and consumed by `POST /api/convert/pdf` and by the copilot tool); the created project is recorded in `guest_projects` with a 24 h expiry.
  3. On sign-up / sign-in, `GuestMigrationListener.tsx` calls `POST /api/guest/migrate`, and `guest_migrator.py` reassigns the projects to the account.

---

### Feature 24: Multimodal AI File Analyzer & TikZ Synthesizer

- **File Implementation**: [`backend/file_analyzer.py`](file:///home/abin/overbranch/backend/file_analyzer.py), [`components/editor/FileAnalyzerModal.tsx`](file:///home/abin/overbranch/components/editor/FileAnalyzerModal.tsx)
- **How It Works**:
  1. Allows users to upload images (PNG, JPG), data files (CSV), or diagrams in the editor.
  2. Analyzes file contents using multimodal LLMs.
  3. Can automatically generate clean, scalable TikZ code replicating uploaded diagrams and charts.

---

### Feature 25: Collaborative Project Management, Invitations & Role-Based Access

- **File Implementation**: [`db/schema.ts`](file:///home/abin/overbranch/db/schema.ts), [`trpc/routers/projects.ts`](file:///home/abin/overbranch/trpc/routers/projects.ts), [`trpc/routers/invitations.ts`](file:///home/abin/overbranch/trpc/routers/invitations.ts), [`components/editor/CollaboratorAvatars.tsx`](file:///home/abin/overbranch/components/editor/CollaboratorAvatars.tsx)
- **How It Works**:
  1. Project owners can invite collaborators via email with specific roles (`editor`, `viewer`).
  2. Invitee receives in-app notifications via [`NotificationsPopover.tsx`](file:///home/abin/overbranch/components/dashboard/NotificationsPopover.tsx) to accept or decline.
  3. Invited members are displayed in [`CollaboratorAvatars.tsx`](file:///home/abin/overbranch/components/editor/CollaboratorAvatars.tsx); who is **live right now** comes from the realtime layer's presence set — see [Feature 33](#feature-33-realtime-collaborative-editing-presence--remote-cursors).
  4. The same `projects.owner_id` / `project_members.role` lookup is what gates a collaboration socket, so revoking a member also ends their live editing session (within `COLLAB_REAUTH_INTERVAL`).

---

### Feature 26: Inline Diff Editor, Diff Generator & Edit History Tracking

- **File Implementation**: [`backend/opencode/diff_generator.py`](file:///home/abin/overbranch/backend/opencode/diff_generator.py), [`lib/latex-edit-apply.ts`](file:///home/abin/overbranch/lib/latex-edit-apply.ts), [`lib/latex-validate.ts`](file:///home/abin/overbranch/lib/latex-validate.ts), [`components/editor/EditorLayout.tsx`](file:///home/abin/overbranch/components/editor/EditorLayout.tsx), [`lib/EditHistoryStore.ts`](file:///home/abin/overbranch/lib/EditHistoryStore.ts)

#### The Apply Contract (`apply_contract_version: 2`)

`compute_edit_items` guarantees, for every emitted item (contract v3 adds `node_id` / `node_path`: the structural node enclosing the edit):

| Guarantee | Why |
|---|---|
| **Non-empty anchor** | Raw `difflib` insert opcodes have `i1 == i2`, producing `original_chunk == ""`, which the client cannot locate and used to drop silently. |
| **Unique anchor** | `original_chunk` occurs exactly once in the original, so substring resolution is unambiguous. |
| **Structurally closed** | The item changes no net environment nesting, brace depth or `$` parity, so a `\begin{...}` and its matching `\end{...}` always travel in the **same** item. This is what makes *any subset* of accepted edits safe. |
| **Non-overlapping** | Line ranges are disjoint, so a client resolves all positions up front and splices in descending order. |
| **Line-addressed** | `orig_start_line` / `orig_end_line` (1-based, inclusive) allow positional application, plus `context_before` / `context_after` so the UI highlights only the genuinely changed lines. |

`proposed_code` + `original_sha256` is **authoritative**. Items are produced in four passes: collect non-`equal` opcodes → merge neighbours until each hunk is structurally closed → expand context until each anchor is unique (bounded by sibling hunks) → emit. A near-total rewrite collapses to one `is_full_document` item rather than duplicating the document in `edits`.

- **How It Works**:
  1. `diff_generator.py` produces contract-compliant edit items plus the authoritative buffer.
  2. `lib/latex-edit-apply.ts` (`applyEditItems`) is the single pure applier. **"Accept All" writes `proposed_code` verbatim** — byte-identical to what passed pre-commit validation — but only when the live document still equals `original_code`. The editor is *not* locked while the agent streams, so it falls back to chunk replay (safe thanks to the contract) when the user typed mid-run, and says so.
  - The SSE handler merges the final `result` event **into** the stored `final_diff` (document fields from `final_diff` win). `result` carries `proposed_chunk`, so it used to be taken for a diff and *replace* `final_diff` — `original_code`/`proposed_code` were lost, the authoritative path never ran, and any anchor miss surfaced as *"Couldn't safely apply this change"* although the backend had succeeded. `result` now also carries `has_changes`, `original_code`, `proposed_code` (and `has_changes: false` on no-change runs, so prose is no longer scraped into an unappliable edit).
  - A single whole-document item is applied (client and `/api/agent/resolve-edits`) only when the live document equals `original_code` / the item's `original_chunk`; otherwise it is skipped as `document-changed` — it used to overwrite text typed during the run or another open file. Pending diffs are cleared on file switch, and chat-card edits are tagged with their file (`editsFile`) and refused for any other file.
  - `handleCompile` keeps `data.errors` from a compile that still produced a PDF; `PDFViewer` shows a non-blocking "N LaTeX errors" bar with **Ask AI to Fix** above the PDF (those errors used to be invisible). Ask AI to Fix always runs in Edit mode (`sendPromptMessage(prompt, "edit")`).
  3. **No edit is ever dropped silently, and no accept is half-applied.** When the exact/positional pass skips any item (the document moved under it), the editor sends the live document and *all* items of that accept to `POST /api/agent/resolve-edits`, which re-locates them with the agent's locator (node → normalized → fuzzy) and returns either the fully applied, validated document or the unchanged one with per-item attempts. The user sees *"Couldn't safely apply this change. The document was not modified."* (details in development builds and the console).
  4. The editor keeps every contract field when it builds its edit list (it used to keep only the two chunks, which turned whole-document items into "no anchor" failures).
  5. `commitEditOutcome` in `EditorLayout.tsx` is the one place that touches Monaco, `EditHistoryStore`, `saveDocument` and `handleCompile` — previously duplicated across four handlers with diverging behaviour.
  6. `final_diff` payloads are accumulated **keyed by file**, so an auxiliary `.tex` file's diff no longer clobbers the main one, and `result` **merges** into the accumulated payload instead of replacing it.
  7. `EditHistoryStore.ts` records snapshots in browser LocalStorage for instant undo/redo.
  8. **One accept marks exactly one message.** `commitEditOutcome` only sets `isApplied`/`historyEntryId` when it is given `opts.msgId`. Its old `else` branch stamped **every** message that still carried an `edits` array, so untouched proposals were badged "Applied" and all of them shared one `historyEntryId` — one Revert click then flipped every card (`m.historyEntryId === editId` matched them all), and a message whose own entry had been overwritten restored the *wrong* document. The three floating diff cards (desktop in-editor, desktop sidebar, mobile) now pass `pendingEditsMsgIdRef`, the id of the assistant message whose edits are in `diffEditsList`; revert/reapply resolve a single target (`historyEntryId` first, then `id`); and `repairSharedEditHistoryIds` clears the flags once on load for chats already corrupted in LocalStorage.

> Note: `components/editor/InlineDiffEditor.tsx` currently exports the `EditItem` type that the rest of the editor consumes, but the component itself is not rendered — the inline preview blocks in `EditorLayout.tsx` display diffs instead. The handlers that only it called (`handleAcceptDiff`, `handleAcceptSingleEdit`, `handleRejectSingleEdit`) have been removed.

---

### Feature 27: Fullscreen Presentation View Mode with Laser Pointer

- **File Implementation**: [`components/editor/PresentationView.tsx`](file:///home/abin/overbranch/components/editor/PresentationView.tsx)
- **How It Works**:
  1. Fullscreen presentation environment for Beamer slide decks.
  2. Keyboard navigation (Arrow keys, Space, Esc), laser pointer overlay mode, and slide thumbnail drawer.

---

### Feature 28: LaTeX Template Gallery, Metadata Explorer & Dynamic Cloning

- **File Implementation**: [`backend/template_service.py`](file:///home/abin/overbranch/backend/template_service.py), [`backend/templates/`](file:///home/abin/overbranch/backend/templates/), [`app/(dashboard)/templates/page.tsx`](file:///home/abin/overbranch/app/(dashboard)/templates/page.tsx), [`trpc/routers/templates.ts`](file:///home/abin/overbranch/trpc/routers/templates.ts)
- **Categories**: Papers (IEEE, ACM, Springer), Presentations (Regalia, Nordlight, Prism), Resumes/CVs, Master/PhD Theses, Assignments, Technical Reports.
- **Cloning**: One-click cloning instantiates project source files, styles (`.cls`, `.sty`), and assets into a new user project.

---

### Feature 29: Design System ("Celestial Obsidian & Luminescent Iris") & Theming Engine

- **File Implementation**: [`app/globals.css`](file:///home/abin/overbranch/app/globals.css), [`components/editor/EditorThemeModal.tsx`](file:///home/abin/overbranch/components/editor/EditorThemeModal.tsx), [`trpc/routers/preferences.ts`](file:///home/abin/overbranch/trpc/routers/preferences.ts)
- **Design System ("Celestial Obsidian & Luminescent Iris")**:
  - Deep Obsidian background (`oklch(0.12 0.012 260)`), Luminescent Iris accent (`oklch(0.65 0.22 265)`), crisp white text (`oklch(0.98 0 0)`), and semantic status colors.
  - Display typography in **Archivo Black**, body text in **Inter**, code in **Space Mono**.
- **User Configurable Parameters**:
  - Themes (VS Code Dark, GitHub Light, Nord, Dracula, Monokai, Cyberpunk), font sizes, tab sizes, soft wrap, and auto-compile triggers synchronized to PostgreSQL `editor_preferences`.
- **Every surface must be a `light dark:` pair.** A hardcoded hex utility with no `dark:` prefix stays dark in light mode. `AgentReasoningWindow.tsx` had **zero** `dark:` prefixes in the whole file, and the mobile AI panel's own root (`bg-[#141519] text-[#E2E4E9]`) kept the entire tab dark while its correctly-paired children rendered light-on-dark. The agent chat path — reasoning window, message edits card, mobile AI/files/PDF pane roots, the mobile floating diff card and the remaining unpaired sidebar controls — is now paired throughout. Saturated accent buttons (the emerald Compile/Accept, the red Stop) are deliberately left unpaired: white text on a brand fill reads correctly in both themes, and pairing them only produced pale borders around saturated fills. The reasoning window's scrollbar moved from an inline `scrollbarColor` to the themed `.ob-thin-scroll` class for the same reason.

---

### Feature 30: Structured Observability, Tracing & Performance Telemetry

- **File Implementation**: [`backend/trace.py`](file:///home/abin/overbranch/backend/trace.py)
- **Features**:
  - `AgentTrace`: Captures trace ID, task classification, nodes touched, tool call latencies, validation results, shadow compilation diagnostics, and model token usage.
  - `ConversionTrace`: Tracks the model, PDF page count, per-page similarity scores, fallback pages, compile success and latency.
  - Telemetry is formatted as JSON to stdout and saved to rotating project log directories under `/tmp/overbranch_traces/`.

---

### Feature 31: Comprehensive Pytest Test Suite & Evaluation Harness

- **File Implementation**: [`backend/tests/`](file:///home/abin/overbranch/backend/tests/)
- **Test Modules** (all run without network; LLM calls go through a scripted stub of `provider_router.chat`, and the agent's compile through a stub unless a test needs real TeX):
  1. `test_locator.py`: stable node IDs and lookup forms, exact / normalized / fuzzy resolution, ambiguity refusal, structured failure with the document unchanged, node aliases after a rename, legacy chunk IDs.
  2. `test_transactions.py`: healer repairs only edited lines, duplicate-block refusal, transaction rollback, `rollback_edit`, compile failure → bounded repair → whole-run rollback, pre-existing compile errors tolerated, provider failure leaves the document unchanged.
  3. `test_agent_token_budget.py`: initial prompt for a targeted edit on a ~5,300-line document within 2× of a ~70-line one, one LLM call for a one-step edit, title requests pull the title and its colour definition, ledger de-duplication.
  4. `test_resolve_edits_endpoint.py`: node metadata on items, re-location after the user typed, all-or-nothing, whole-document items.
  5. `test_provider_fallback.py`: fallback to OpenRouter MiniMax M3 on 429/402/503/504/timeouts, none on bad request or cancel, sticky 429 rotation, five-key exhaustion, cooldown recovery, keys absent from responses/logs.
  6. `test_justify_content.py`: the strategy ladder, break points only in over-long tokens (separators first), overfull parsing, TeX measurement, compiled end-to-end overflow fix, and that type is never shrunk to fit.
  6a. `test_layout_repair.py`: content typing (a path and an identifier are repaired, ordinary prose is not), breaks that add no character and no hyphen, column specs that keep their rules, detection against really-rendered pages (margin overflow, a short page that is *not* overflowing, a line merely ending in a path that is *not* a broken token), repair verified by re-rendering (`tabularx`, `longtable` with a repeated header, `\url`), and the tool's guarantees: dry run, rollback when a repair does not compile, rollback when it compiles but does not measurably help, refusal to commit against a document that moved underneath, and meaning preserved by every repair.
  6b. `test_converted_document_edits.py`: "change jacob to tims ittus" on a long imported PDF — the line is in the first message, lower-case search and `replace_text` still find "JACOB", nothing else changes; overprinted fake bold is extracted once and converts without double text.
  7. `test_pdf2latex_fidelity.py`: bold from names / descriptor / synthetic rendering, sizes in the facts, Carlito mapping and fallback, body repair, and the **IRCTC ticket regression**: real pipeline with a model that drops all bold → bold restored, 0 overflowing lines, with and without Carlito; a faithful body is left untouched.
  8. `test_collab_sync.py`: `CollabRoom` driven with the real y-websocket protocol (one `pycrdt.Doc` per "browser") — seeding, an edit reaching the other peer, simultaneous inserts at the same offset converging, concurrent delete+insert, a late joiner getting the live state rather than the stored snapshot, a peer leaving, a Viewer's writes dropped, a role downgrade taking effect, restart **without duplicating the document**, adopting an edit made outside the session, keeping unflushed edits over stale storage, debounced persistence and flush retry, presence relay and ghost-cursor cleanup, path/size/garbage rejection, and a backend write (AI commit / PDF import) reaching live editors.
  9. `test_collab_auth.py`: ticket round trip, single use, project binding, tampering, expiry; role resolution from `projects` / `project_members` including deleted projects and fail-closed on a database error; the websocket handshake with no credential, a forged ticket, a valid ticket for a non-member, a ticket for another project; a Viewer connecting read-only; revocation closing a live socket; a foreign `Origin` refused.
  10. `scripts/run-collab-tests.sh` (Node, outside pytest): the Yjs ↔ Monaco binding — loop safety, two-editor convergence, offline merge, per-user undo/redo, remote cursor decorations and name labels, read-only — and `computeLineEdits` / `applyTextToEditor` round trips including 300 randomized cases.

---

### Feature 32: Mobile Touch Editing, Find & Replace & the Dual-Editor Resolver

- **File Implementation**: [`components/editor/MobileEditorAssist.tsx`](file:///home/abin/overbranch/components/editor/MobileEditorAssist.tsx), [`components/editor/EditorSearchBar.tsx`](file:///home/abin/overbranch/components/editor/EditorSearchBar.tsx), [`lib/clipboard.ts`](file:///home/abin/overbranch/lib/clipboard.ts), [`components/editor/EditorLayout.tsx`](file:///home/abin/overbranch/components/editor/EditorLayout.tsx), [`app/globals.css`](file:///home/abin/overbranch/app/globals.css)

- **`getActiveEditor()` — the dual-editor resolver.** `EditorLayout` renders **two** Monaco instances (desktop `hidden md:flex`, mobile `flex md:hidden`); both always mount and only CSS hides one. `handleEditorMount` used to end with an unconditional `editorRef.current = editor`, and because the mobile editor is later in the JSX it mounted last and **won on desktop too** — so Undo/Redo, symbol insertion, `commitEditOutcome`, revert/reapply and the diff decorations all drove a hidden, zero-sized editor. `editorRef` is gone; `getActiveEditor()` picks the instance matching the viewport, and an `editorsNonce` state bump on mount re-runs the effects that need an instance. The touch `paste` listener now closes over its bound `editor` and is attached to the mobile editor only.

- **Why Monaco needs a touch layer at all.** Monaco paints text into non-editable DOM and keeps the caret in an off-screen textarea, so a touch device gets no native selection handles. Two things made it worse: `app/globals.css` forced `touch-action: pan-x pan-y !important` on `.monaco-editor`, overriding the `touch-action: none` Monaco's own `Gesture` layer sets on its targets and handing every single-finger gesture to the browser scroller (so a tap could never place the caret); and the mobile `<Editor>` options were a stripped-down subset that also **omitted `readOnly: isViewer`**, giving a Viewer-role collaborator an editable buffer on a phone. The CSS rule is removed, `touch-action` is Monaco's to set again, and the mobile options match desktop.

- **`MobileEditorAssist`** overlays the mobile editor (`pointer-events: none`, `auto` only on its own controls, so Monaco keeps every gesture it already handles):
  - A draggable **caret handle** and two **selection handles**. Drags use pointer capture and `editor.getTargetAtClientPoint(x, y ∓ probeOffset)` — the probe is offset by `lineHeight/2 + handleSize/2` so the sampled glyph is the one the handle points at, not the one under the fingertip. The start handle hangs above its line (`+offset`), the caret and end handles below (`−offset`). Dragging near an edge auto-scrolls; collapsing a selection onto itself mid-drag is refused so the handles cannot vanish under the finger.
  - Handle positions come from `editor.getScrolledVisiblePosition`, which Monaco documents as *inaccurate* (not null) outside the viewport, so results are bound-checked against `getLayoutInfo().height` — otherwise a stale handle hovers at the pane edge and drags from the wrong place.
  - An **action callout** (Select word / Select All / Copy / Cut / Paste / Find), dismissed on a tap elsewhere and while typing.
  - **iOS paste fallback**: `navigator.clipboard.readText()` does not exist in iOS Safari, so when it returns nothing the callout opens a real, focused textarea and forwards its `paste`/`input` into `executeEdits`. This is the only route to the clipboard there.
  - There is deliberately **no docked key bar**. An earlier version pinned one (arrows, Tab, Undo/Redo, Find, TeX symbols) against `window.visualViewport`; it covered the bottom navigation and duplicated affordances the keyboard already provides. Search moved to the editor header instead, and `visualViewport` is still watched purely to re-`layout()` Monaco and re-measure the handles when the keyboard opens.

- **`EditorSearchBar`** replaces Monaco's built-in find widget on **both** platforms (the built-in one needs a hardware keyboard and has no UI trigger, so it is unreachable on mobile). `model.findMatches` drives a live `n/total` counter, case / whole-word / regex toggles, prev-next with wrap, and Replace / Replace All (descending ranges inside one `pushUndoStop` pair, so it is a single undo). All matches are highlighted with `.ob-find-match` / `.ob-find-match-current` decorations, cleared on close and unmount. Opened by the desktop tab-bar button, by the **mobile header button sitting immediately left of the theme toggle** (`md:hidden`), by the touch callout's Find, or by `Ctrl/Cmd+F` registered on both editors; `Esc` closes. Both editors stay mounted so the bar renders twice — the hidden copy refuses focus via an `offsetParent` check.

- **The editor shell was never actually `fixed`.** Its root carried both `fixed` and `relative`; Tailwind emits `.fixed{position:fixed}` *before* `.relative{position:relative}`, so at equal specificity `relative` won and the shell was an ordinary in-flow block of `height: 100dvh` inside a `min-h-screen` body. On mobile that left a dead strip of page background below the bottom navigation whenever `100dvh` disagreed with the visible viewport. The root is now `fixed inset-0` with no competing `position` utility and no explicit height — for a fixed element the containing block is the viewport, so the shell matches it exactly.

- **`lib/clipboard.ts`** holds `copyText` (async clipboard → hidden-textarea `execCommand`) and `readClipboard`, shared by the editor toolbar, the chat `CopyButton` and the mobile callout, so all three behave identically.

---

### Feature 33: Realtime Collaborative Editing, Presence & Remote Cursors

```
+------------------------------------------------------------------------------------+
|                        REALTIME COLLABORATION PIPELINE                             |
|                                                                                    |
|  Monaco (one shared model)  --onDidChangeContent-->  Y.Text ops (origin = binding)  |
|          ^                                                    |                    |
|          |  model.applyEdits (origin != binding)              v                    |
|          +------------------------------  y-websocket provider / Y.Doc             |
|                                                               |                    |
|            wss://<backend>/ws/collab/<project_id>  -----------+                    |
|                                 |                                                  |
|            Origin allowlist -> cookie | one-time ticket -> project role            |
|                                 |            (re-checked every 30s)                |
|                                 v                                                  |
|                CollabRoom: authoritative pycrdt Doc per project                    |
|                  Y.Text "file:<path>"   Y.Map "meta" loaded:/saved:                |
|                  Awareness (presence, memory only, never in Postgres)              |
|                                 |                                                  |
|          debounced 2s / >=15s   v   last-leave + shutdown flush                    |
|      uploads/projects + latex_documents  (text)                                    |
|      uploads/collab-state/<id>.ybin + collab_doc_state  (CRDT snapshot)            |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/collab/`](file:///home/abin/overbranch/backend/collab/), [`backend/routes/collab_routes.py`](file:///home/abin/overbranch/backend/routes/collab_routes.py), [`lib/collab/`](file:///home/abin/overbranch/lib/collab/), [`components/editor/CollabPresenceBar.tsx`](file:///home/abin/overbranch/components/editor/CollabPresenceBar.tsx), [`components/editor/EditorLayout.tsx`](file:///home/abin/overbranch/components/editor/EditorLayout.tsx), [`COLLABORATION.md`](file:///home/abin/overbranch/COLLABORATION.md)
- **API**:
  - `WS /ws/collab/{project_id}` — the y-websocket protocol (`?ticket=`, `?file=`).
  - `POST /api/collab/ticket` — `{project_id}` → `{ticket, expires_in, role, can_edit}`; single-use, 60 s, rate limited 120/min.
  - `GET /api/collab/config` — capability flags only (no project data).
  - `GET /api/collab/rooms/{project_id}` — who is live, open files, pending writes; **members only**.
- **New dependencies**: `yjs`, `y-websocket`, `y-protocols` (browser) and `pycrdt` (backend). Nothing else — notably **not** `y-monaco`, whose `monaco-editor` peer dependency would ship a second copy of an editor this project loads from a CDN.
- **New schema**: one table, `collab_doc_state(project_id PK, state_b64, updated_at)` — [`db/schema.ts`](file:///home/abin/overbranch/db/schema.ts) (`collabDocState`) plus an idempotent [`supabase/migrations/002_collab_doc_state.sql`](file:///home/abin/overbranch/supabase/migrations/002_collab_doc_state.sql). No `drizzle/` migration: `drizzle/meta` is still at the 0000 baseline while `db/schema.ts` has grown a dozen tables since, so `drizzle-kit generate` would emit all of them at once — `npm run db:push` or the SQL file is the path. Service-role only; browsers never read it.
- **Four things that look like details and are not**:
  1. **The desktop and mobile editors must share one Monaco model.** The binding syncs text to the single model it is constructed with, but attaches cursor decorations to *every* editor registered with it. `@monaco-editor/react` gives each instance its own anonymous model unless both are handed the same `path` — the `path ? uri : undefined` argument is `""` without it — so the binding owned the hidden editor's model while the user typed in the visible one. Remote carets moved perfectly and not one character of text ever crossed. `handleEditorMount` adopts the peer's model; `pickBindableEditor` prefers the visible instance so the same mistake can only ever degrade, not silence.
  2. **`value={collabBound ? undefined : code}`.** `@monaco-editor/react` implements a `value` prop change as a replace over `getFullModelRange()` — and an unconditional `setValue` when the editor is read-only. Under a CRDT that is "delete the document, insert a new one": it discards every concurrent keystroke in the span and collapses every remote cursor to line 1. While the binding owns the model, React must not pass `value` at all. `code` becomes a 150 ms-throttled mirror (a collaborator typing a paragraph would otherwise force one shell re-render per character) and `currentDocumentText()` reads the live model wherever exactness matters (Compile, the agent).
  3. **The AI accept path is a line diff, not a full replace.** `commitEditOutcome`, `handleRevertEdit` and `handleReapplyEdit` used to execute one edit over `getFullModelRange()`. [`lib/collab/text-diff.ts`](file:///home/abin/overbranch/lib/collab/text-diff.ts) (`computeLineEdits` → common prefix/suffix trim, then LCS, capped at 1,500 lines per side) turns the result into the minimal changed ranges. An accepted AI edit therefore enters the collaborative document through the same path as typing, and the single-user case gets one undo entry per real change instead of one giant one.
  4. **The socket is accepted before it is authorized.** Closing an ASGI websocket before `accept()` rejects the upgrade, which a browser reports as close code 1006 with no detail — so the client cannot distinguish "forbidden, stop asking" from "network blip, retry" and `y-websocket` reconnects forever against a project the user cannot open. Nothing is sent before the checks pass, and a rejected socket closes in the same round trip with `4401` / `4402` / `4403` / `4404` / `4429` — `4402` meaning “no credential was offered, authenticate and retry”, which is what a cross-site upgrade without a cookie actually is.
- **Seeding handshake**: a client announces its file (`?file=` and in awareness), the room reads it from storage and sets `meta["loaded:<path>"]`; Monaco binds **only** then. Binding to a not-yet-seeded (empty) `Y.Text` and typing into it would merge those keystrokes into offset 0 of a document that is about to arrive.
- **Cross-site websocket hijacking**: WebSocket is exempt from CORS, so `new WebSocket(...)` from any page the user has open would carry their Better-Auth cookie. `_origin_allowed` checks `Origin` against `COLLAB_ALLOWED_ORIGINS` / `ALLOWED_ORIGINS` / `NEXT_PUBLIC_APP_URL` / `BETTER_AUTH_URL`. A request with no `Origin` is not a browser and falls through to the credential checks.
- **Undo**: Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z and the toolbar buttons go to a `Y.UndoManager` with `trackedOrigins: {binding}` while bound, so undo is scoped to this user's own transactions. Monaco's native stack is wrong here: it contains edits whose surroundings a collaborator has since changed and does not know whose they were. Remote text is applied with `model.applyEdits` (not `pushEditOperations`) so it never lands on the local stack at all.
- **Guests** keep the existing REST autosave path: guest projects are single-session, and `POST /api/collab/ticket` refuses them.
- **Deployment constraint**: rooms are per-process, so `entrypoint.sh` and `Dockerfile.backend` pin the backend to **one uvicorn worker** while collaboration is enabled (`COLLAB_ENABLED=0` or `COLLAB_MULTI_WORKER=1` opt out) and `warn_if_multi_worker()` logs loudly otherwise. A websocket also holds a `--limit-concurrency` slot and counts as one `--limit-max-requests` request for its whole life, so both were raised (200 / 10000).
- **Tests**: [`backend/tests/test_collab_sync.py`](file:///home/abin/overbranch/backend/tests/test_collab_sync.py) drives `CollabRoom` with the real wire protocol (one `pycrdt.Doc` per "browser"); [`backend/tests/test_collab_auth.py`](file:///home/abin/overbranch/backend/tests/test_collab_auth.py) covers tickets, roles, handshake codes, revocation and origins; [`scripts/run-collab-tests.sh`](file:///home/abin/overbranch/scripts/run-collab-tests.sh) bundles the browser-side binding and line-diff checks with the esbuild already in `node_modules`. Three bugs were found by these tests and fixed: a `pycrdt` callback-arity trap that filled the dirty set with transactions instead of file paths, a `reject(reason=…)` keyword collision that turned a non-member's rejection into a 500, and `applyTextToEditor` dropping an appended trailing newline.

---

---

### Feature 34: Render-Aware Layout Repair (`justify_content`)

```
+------------------------------------------------------------------------------------+
|                      LAYOUT REPAIR LOOP (justify_content)                          |
|                                                                                    |
|  buffer ──► compile (cached by content) ──► PDF bytes + overfull log               |
|                                   │                                                |
|                     detect_layout_issues()   TeX \textwidth/\textheight            |
|                                   │          + word boxes + adjacent line pairs    |
|                     [LayoutIssue …] ranked worst-first                             |
|                                   │          (+ optional advisory vision pass)     |
|                     map_issue_to_source()    overfull `at lines a--b`              |
|                                   │          → locator → plain-text line match     |
|                     plan_repairs()           closed, content-typed operation set   |
|                                   │                                                |
|            one transaction per defect ──► recompile ──► re-measure                 |
|                                   │                                                |
|        new compile errors?  OR  layout score did not fall?  ──► rollback           |
|                                   │ no                                             |
|                                 keep                                               |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/latex_layout/issues.py`](file:///home/abin/overbranch/backend/latex_layout/issues.py), [`backend/latex_layout/repair.py`](file:///home/abin/overbranch/backend/latex_layout/repair.py), [`backend/latex_layout/vision.py`](file:///home/abin/overbranch/backend/latex_layout/vision.py), [`backend/opencode/layout_tools.py`](file:///home/abin/overbranch/backend/opencode/layout_tools.py), [`backend/tests/test_layout_repair.py`](file:///home/abin/overbranch/backend/tests/test_layout_repair.py)

- **What the request actually means.** "Fix the justification of the whole document" is not a request to insert `\justifying`, and not a request to rewrite paragraphs. It means: find where the rendered pages look wrong and make the smallest edit that fixes each one. **None of that is visible in the source.** Whether a file path runs into the margin, whether a table is wider than the text block, whether a row prints over the footer — only the compiled PDF knows. So the tool closes a loop the source cannot close on its own.

- **Why the previous tool could not do this.** `justify_content` was a *single-fragment width fitter*: hand it one fragment and a width in pt and it rewrote that fragment. It had no `scope`, so for a whole-document request there was nothing to call — the model had to already know which fragment was broken and what width it should fit. Detection (`detect_overflow`) and repair were unconnected tools, so each defect cost a hand-copied call out of a 4–12 step budget. It had no notion of content type, so a URL, a file path, an identifier and a prose sentence all took the same branch. Tables were invisible to it (`in_lr_box` detected "I am in a cell" only so it could force the *condense* branch — the worst possible table fix). Vertical overflow was not modelled at all. And its terminal rungs were `\resizebox` and `\fontsize` — shrinking type to fit, the one thing a layout repair must never do.

- **Three properties make the loop safe to run unattended**:
  1. **The model does not write the LaTeX.** It decides *that* the document should be tidied; `repair.py` decides *how*, from a closed operation set. There is no path by which "fix the formatting" becomes a rewrite.
  2. **Nothing is kept on faith.** A repair survives only if the document still compiles **and** the measured layout improved. Compiling is a precondition, never evidence that a layout fix worked — the broken version compiled too.
  3. **One defect at a time.** Each repair is its own transaction, judged alone, so a fix that makes another page worse is rolled back by itself instead of taking the good ones with it.

- **A real document is not one file.** A thesis's `main.tex` holds a preamble and a list of `\input{chapters/…}`; the text that overflows lives in a chapter. Detection runs on the rendered PDF either way, but the repair has to find and edit the *file that produced* the line, so `locate_issue` searches every `.tex` the compile reads and writes back through `str_replace_file`; packages still go to the main buffer, since a `\usepackage` inside an included chapter is an error. Two things had to be fixed for this to work at all: TeX's `at lines a--b` numbers the file it was *reading*, so applying those numbers to the main buffer pointed at the preamble (the hint is dropped once there is more than one source); and `compile_workspace` keyed its cache on the main buffer alone, so a document whose main file never changes had **every chapter edit judged against the compile from before it** — a bug that affected any auxiliary-file edit the agent made, not just this tool.

- **Mapping a rendered defect back to source**, best signal first: TeX's own `at lines a--b` for an overfull box; the locator (`exact → normalized → fuzzy`, the same ladder every other edit in this codebase uses); and finally a **plain-text line match** — comparing what each source line would *print* against what the page actually printed. That last step exists because the locator matches source against source, while a line read back from the PDF is neither: TeX has already stripped the markup and re-broken the text, so `…its manifests (packag` exists nowhere in a source reading `…its manifests (\texttt{package.json}`. An issue that still cannot be placed is **reported unrepaired**, never guessed at.

- **Collaboration safety.** The buffer's `base_sha256` / `base_version` are read at entry and re-checked before committing. A user may be typing while the pages are being measured; a candidate built on a version that no longer exists would overwrite their work, so it is discarded with `{stale: true}` and the caller is told to run again.

- **Measured end to end** on a three-page fixture reproducing all three reported defects (a path overflowing the margin, a two-column table wider than the page, a 29-row table printing over the footer): layout score **96.6 → 12.8**, four repairs — `longtable`, `tabularx`, `\allowbreak` break points and one `sloppypar` — with the body's visible text byte-identical and no `\small`, `\fontsize` or margin change anywhere in the diff.

# 4. Deployment, Infrastructure & Environment Configuration

### Universal Docker Deployment

OverBranch is fully containerized using a multi-stage `Dockerfile`, `Dockerfile.backend`, and Docker Compose configurations (`docker-compose.yml`, `docker-compose.backend.yml`):

```yaml
services:
  overbranch:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "3000:3000"   # Next.js Frontend
      - "8000:8000"   # FastAPI Python Engine
    environment:
      - NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
      # Collaboration rooms are per-process: entrypoint.sh pins the backend to
      # one uvicorn worker while COLLAB_ENABLED != 0. Set COLLAB_ENABLED=0 to
      # keep multiple workers, or COLLAB_MULTI_WORKER=1 behind a proxy that
      # pins /ws/collab/<project_id> to one worker.
      - WORKERS=1
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
      - DATABASE_URL=${DATABASE_URL}
      - GROQ_API_KEY=${GROQ_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
```

### Essential Environment Variables (`.env`)

| Variable | Target | Description |
|---|---|---|
| `DATABASE_URL` | Frontend & Backend | PostgreSQL connection string (supports direct and connection poolers) |
| `BETTER_AUTH_SECRET` | Frontend & Backend Auth | Secret key used to sign and verify Better-Auth session tokens |
| `BETTER_AUTH_URL` | Frontend Auth | Canonical URL of the application (e.g. `http://localhost:3000`) |
| `NEXT_PUBLIC_APP_URL`| Frontend | Public-facing web application domain |
| `NEXT_PUBLIC_BACKEND_URL`| Frontend | URL of the FastAPI Python engine (`http://localhost:8000`) |
| `SUPABASE_URL` | Backend Storage | Supabase project endpoint |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend Storage | Supabase service role key for storage buckets |
| `QDRANT_HOST` / `QDRANT_API_KEY` | Backend RAG | Vector database connection details |
| `NVIDIA_API_KEY` | Backend Embeddings | NVIDIA API key for `NV-Embed-QA` vector generation |
| `GEMINI_API_KEY` | Backend LLM | Google GenAI / Gemini API key |
| `GROQ_API_KEY` | Backend LLM | Groq cloud key for high-speed inference |
| `OPENROUTER_API_KEY` | Backend LLM | OpenRouter gateway key |
| `GUEST_TOKEN_SECRET` | Backend Guest Auth | HMAC signing secret for 24-hour guest tokens |
| `MAX_CONCURRENT_COMPILES` | Backend Compiler | Max concurrent pdflatex/latexmk compile processes (Default: `4`) |
| `MAX_QUEUE_DEPTH` | Backend Compiler | Max wait queue depth before returning HTTP 429 (Default: `20`) |
| `COMPILE_QUEUE_TIMEOUT` | Backend Compiler | Max seconds a compile task can wait in queue (Default: `45.0`) |
| `SHADOW_COMPILE_MAX_RETRIES`| Backend AI | LLM repair rounds when the agent's edits do not compile, before the whole run is rolled back (Default: `2`) |
| `LLM_FALLBACK_CHAIN` | Backend LLM | Fallback chain `provider:model,…` walked on rate limit / quota / timeout / outage (Default: `openrouter:minimax/minimax-m3`) |
| `OPENROUTER_API_KEY_1` … `_5` | Backend LLM | Up to five server-side OpenRouter keys, rotated with per-key cooldowns (never sent to the browser) |
| `OPENROUTER_FALLBACK_MODEL` / `OPENROUTER_TIMEOUT` | Backend LLM | Fallback model (Default: `minimax/minimax-m3`) and request timeout in s (Default: `90`) |
| `DB_POOL_SIZE` | Backend Database | SQLAlchemy connection pool size (Default: `10`) |
| `DB_MAX_OVERFLOW` | Backend Database | SQLAlchemy connection pool max overflow (Default: `20`) |
| `DB_POOL_RECYCLE` | Backend Database | SQLAlchemy connection pool recycle seconds (Default: `300`) |
| `PDF2LATEX_CONCURRENCY` | Backend PDF import | Pages converted in parallel; also the process-wide cap on concurrent LLM calls (Default: `4`). The LLM itself is the copilot's (`GEMINI_WEB2API_*`, `DEFAULT_MODEL`) |
| `PDF2LATEX_PAGE_TIMEOUT` / `PDF2LATEX_PAGE_RETRIES` | Backend PDF import | Per-LLM-call timeout in seconds (Default: `180`) and extra attempts (Default: `2`) |
| `PDF2LATEX_MAX_COMPILE_REPAIRS` | Backend PDF import | LLM attempts to fix a page that fails to compile (Default: `3`) |
| `PDF2LATEX_COVERAGE_TARGET` | Backend PDF import | **The quality gate**: share of the PDF's words a page must carry to be accepted (Default: `0.995`) |
| `PDF2LATEX_MAX_DISPLACEMENT` | Backend PDF import | **The layout gate**: median pt a word may sit away from its place in the PDF (Default: `25`). A faithful re-setting lands at 8–13 pt, a scrambled page at 40–65 pt |
| `PDF2LATEX_VISUAL_FLOOR` | Backend PDF import | Backstop for a page that has all its words but looks nothing like the original (Default: `0.55`) |
| `PDF2LATEX_SIM_THRESHOLD` / `PDF2LATEX_QUALITY_RERUN` | Backend PDF import | Reported visual-similarity reference — a **diagnostic, not a gate** — and whether an unacceptable page gets one re-run (Defaults: `0.85`, `true`) |
| `PDF2LATEX_MAX_FILE_MB` / `PDF2LATEX_MAX_PAGES` | Backend PDF import | Upload limits (Defaults: `50` MB, `50` pages) |
| `PDF2LATEX_RENDER_DPI` | Backend PDF import | Comparison DPI (Default: `100`) |
| `PDF2LATEX_RATE_PER_HOUR` | Backend PDF import | Conversions per caller per hour (Default: `10`) |
| `PDF2LATEX_JOB_DIR` | Backend PDF import | Job state/output directory shared by workers (Default: system temp `overbranch_pdf2latex_jobs`) |
| `JUSTIFY_MAX_PAGES` | Backend Layout | Most pages `justify_content` measures in one run (Default: `40`) |
| `JUSTIFY_VISION` | Backend Layout | `1` turns on the advisory vision pass over pages geometry could not explain. Report-only: its findings are never repaired automatically (Default: `0`) |
| `JUSTIFY_VISION_BATCH` / `JUSTIFY_VISION_DPI` | Backend Layout | Pages per vision prompt and their render resolution (Defaults: `5`, `100`) |
| `COLLAB_ENABLED` | Backend Collaboration | Master switch for realtime collaborative editing (Default: `1`) |
| `COLLAB_CONNECT_THRESHOLD` | Backend Collaboration | People who must have a project open before a realtime room is held (Default: `2`). Below it, editing uses the REST autosave path |
| `COLLAB_PRESENCE_TTL` / `COLLAB_PRESENCE_POLL` | Backend Collaboration | How long a viewer counts as present after their last heartbeat, and how often the client sends one (Defaults: `30`, `8` seconds) |
| `NEXT_PUBLIC_COLLAB_ENABLED` | Frontend Collaboration | Turns the browser side off without touching the backend (Default: `1`) |
| `COLLAB_MULTI_WORKER` | Backend Collaboration | `1` = "my proxy pins `/ws/collab/<project_id>` to one worker"; suppresses the one-worker pin and the startup warning (Default: `0`) |
| `COLLAB_ALLOWED_ORIGINS` | Backend Collaboration | Origins allowed to open a collaboration socket. WebSocket is exempt from CORS, so this is what prevents cross-site websocket hijacking. Defaults to `ALLOWED_ORIGINS` + `NEXT_PUBLIC_APP_URL` + `BETTER_AUTH_URL` |
| `COLLAB_REQUIRE_ORIGIN` | Backend Collaboration | Enforce the Origin allowlist; a request with no `Origin` is never a browser and is always allowed (Default: `1`) |
| `COLLAB_PERSIST_DEBOUNCE` / `COLLAB_PERSIST_MAX_INTERVAL` | Backend Collaboration | Seconds of edit silence before a room writes the document, and the longest it will wait while someone types continuously (Defaults: `2.0`, `15.0`) |
| `COLLAB_ROOM_IDLE_TTL` | Backend Collaboration | Seconds an empty room stays in memory, so a refresh rejoins the same live document (Default: `60`) |
| `COLLAB_REAUTH_INTERVAL` | Backend Collaboration | How often an open socket's project membership is re-verified, so revocation ends the live session (Default: `30`) |
| `COLLAB_TICKET_SECRET` / `COLLAB_TICKET_TTL` | Backend Collaboration | HMAC key for one-time websocket tickets (falls back to `BETTER_AUTH_SECRET`) and their lifetime in seconds (Default: `60`) |
| `COLLAB_MAX_CONNECTIONS_PER_ROOM` / `COLLAB_MAX_ROOMS` / `COLLAB_MAX_FILES_PER_ROOM` | Backend Collaboration | Per-room and per-process bounds (Defaults: `32`, `500`, `64`) |
| `COLLAB_MAX_MESSAGE_BYTES` / `COLLAB_MAX_FILE_BYTES` / `COLLAB_SEND_QUEUE_SIZE` | Backend Collaboration | Largest accepted websocket frame, largest file persisted, and the per-connection send queue beyond which a slow client is dropped (Defaults: `2 MiB`, `4 MiB`, `256`) |
| `COLLAB_TEXT_EXTENSIONS` | Backend Collaboration | Extensions synchronized as collaborative text; binary assets keep the existing upload path (Default: `.tex,.bib,.cls,.sty,.txt,.md,.bbl`) |
| `COLLAB_STATE_DIR` | Backend Collaboration | Where `<project_id>.ybin` CRDT snapshots are written (Default: `uploads/collab-state`) |
| `COLLAB_DEBUG` / `NEXT_PUBLIC_COLLAB_DEBUG` | Backend & Frontend | Promote per-message `COLLAB_AWARENESS` / `COLLAB_UPDATE` events to INFO, and enable the browser console logs. A single browser can also be switched on with `localStorage.ob_collab_debug = "1"` (Default: `0`) |

---

> ⚠️ **MANDATORY MAINTENANCE DIRECTIVE:**
> **Update this file (`OVERVIEW.md`) after each and every change to the codebase.**
> Whenever files, folders, routes, components, database schemas, services, or architectures are added, modified, renamed, or deleted, this document must be updated immediately to keep all descriptions, file indexes, and architectural references 100% synchronized with reality.
