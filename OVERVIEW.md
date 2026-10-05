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

# Run all Pytest test suites
pytest tests/ -v

# Run specific focused test suites
pytest tests/test_latex_error_fixer.py -v
pytest tests/test_ask_ai_to_fix.py -v
pytest tests/test_document_analyzer_and_context.py -v
pytest tests/test_attached_context.py -v
pytest tests/test_document_environment_integrity.py -v
pytest tests/test_edit_pipeline_integrity.py -v
pytest tests/test_full_document_rewrite.py -v
pytest tests/test_opencode_fixes.py -v
pytest tests/test_ppt_templates.py -v
pytest tests/test_performance_regression.py -v
pytest tests/test_pdf2latex_*.py -v            # PDF → LaTeX importer (integration test needs pdflatex + pdftoppm)
PDF2LATEX_LIVE_LLM=1 pytest tests/test_pdf2latex_integration.py -k live -s   # one conversion against the real copilot model
pytest tests/eval_harness.py -v
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
└──────────────────┬───────────────────────────────┬─────────────────────┘
                   │                               │
       tRPC / Better-Auth (Next API)        HTTP / SSE / REST
                   │                               │
┌──────────────────▼──────────────┐   ┌────────────▼─────────────────────┐
│    DATABASE & AUTH SERVICE      │   │     FASTAPI PYTHON ENGINE        │
│  - PostgreSQL via Drizzle ORM   │   │  - Port 8000                     │
│  - Shared 'user' & 'session'    │   │  - Async SQLAlchemy Pool         │
│  - Better-Auth Session Tokens   │   │  - Sliding-Window Rate Limiter   │
│  - Project & Invitation Schema  │   │  - Concurrency Compile Queue     │
│  - Collaboration & Comments     │   │  - OpenCode ReAct Agent Loop     │
└──────────────────┬──────────────┘   │  - Scope Classifier & Coverage   │
                   │                  │  - Shadow Workspace & Compiler   │
                   │ (SQLAlchemy)     │  - Structural Chunk Indexer      │
                   │                  │  - LaTeX Error Fixer (Healer)    │
                   │                  │  - Document Analyzer (Local AST) │
                   │                  │  - Attached Context Store (TTL)  │
                   │                  │  - Smart Context Strategy Engine │
                   │                  │  - pdf2latex Importer (Extract)  │
                   │                  │  - Per-Page LLM (copilot model)  │
                   │                  │  - Compile/SSIM Verify & Repair  │
                   │                  │  - Multimodal File Analyzer      │
                   │                  │  - SyncTeX Forward/Backward View │
                   │                  │  - Structured Telemetry (Trace)  │
                   └──────────────────►  - ReportLab Synthetic Fallback  │
                                      └──────────────────────────────────┘
```

---

### Core Methodological Pipelines

#### A. OpenCode ReAct Agent Loop & Dynamic Adaptive Step Budgeting
1. **Interactive Tool Loop**: [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py) executes an iterative ReAct cycle operating on an in-memory [`ShadowWorkspace`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py).
2. **Dynamic Step Budgeting**: Scales from **6 to 32 steps** dynamically based on detected task scope, document length, number of chapters/sections/frames, and user instruction complexity.
3. **Deterministic Tool Suite**:
   - `read_file_range`: Reads exact line-numbered contents without hallucinated drift (up to 300 lines per call).
   - `grep_search`: Finds structural anchors (`\chapter`, `\section`, `\begin{frame}`, `\label`, `\cite`).
   - `str_replace`: Performs strict character-for-character replacements with zero spatial drift.
   - `rewrite_chunk`: Replaces entire chapters, sections, or frames using AST byte offsets (ideal for full document rewrites).
   - `list_assets`: Discovers available images/PDFs in `assets/` for `\includegraphics`.
   - `verify_compile`: Triggers sandboxed compilation to capture compiler diagnostics with `infra_skip` fallback if the host lacks a TeX engine.
   - `get_template_theme`: Retrieves curated themes (Beamer PPT themes, IEEE conference/journal papers, theses, resumes/CVs, formal letters, lab assignments) and extracts styling preambles for non-destructive redesigns.
   - `read_attached_document`: Extracts content from uploaded reference papers/PDFs stored in the multi-turn session cache.
   - `search_uploaded_references`: Searches user-attached documents for specific technical terminology, equations, and tables.
   - `convert_attached_pdf`: Starts a PDF → LaTeX import job for a PDF attached in chat; the agent then finishes without editing and the UI shows the job's progress and similarity report.
4. **SSE Event Streaming**: Streams real-time reasoning (`thought`, `tool_call`, `tool_result`, `compile_error`, `coverage_check`, `final_diff`, `pdf_conversion`, `result`) to [`components/editor/AgentReasoningWindow.tsx`](file:///home/abin/overbranch/components/editor/AgentReasoningWindow.tsx) and [`components/editor/InlineDiffEditor.tsx`](file:///home/abin/overbranch/components/editor/InlineDiffEditor.tsx).

#### B. Automated LaTeX Error Diagnostics & Deterministic Auto-Healing
1. **Log Parsing**: [`backend/latex_error_fixer.py`](file:///home/abin/overbranch/backend/latex_error_fixer.py) parses raw LaTeX compiler error logs (`! LaTeX Error: ...`, `l.<line>`) into structured `ParsedLatexError` diagnostics containing file names, line numbers, error categories, and contextual code snippets.
2. **Deterministic Auto-Healing (`auto_heal_latex_code`)**: Automatically fixes common syntax failure modes before prompting the LLM:
   - Unclosed environments (`\begin{frame}`, `\begin{tikzpicture}`, `\begin{itemize}`, `\begin{tabular}`, etc.).
   - Missing `\usetikzlibrary{calc}` when coordinate calculations `($...$)` are detected.
   - Missing semicolons (`;`) on TikZ path commands (`\fill`, `\draw`, `\node`, `\path`).
   - Missing `\begin{document}` or `\end{document}` wrappers.
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
3. **Coverage & Leftover Checks**: Verifies all chunks were rewritten during full rewrites and alerts if residual terms from older topics remain.

#### I. Shadow Compilation & Compiler-Feedback Self-Correction
1. **In-Memory Shadow Sandbox**: [`backend/opencode/shadow_workspace.py`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py) maintains an isolated buffer; edits never touch disk during reasoning.
2. **Ephemeral Verification**: [`backend/opencode/shadow_compiler.py`](file:///home/abin/overbranch/backend/opencode/shadow_compiler.py) executes isolated compilation tests (`pdflatex`, `latexmk`, or ReportLab fallback).
3. **Compiler Feedback**: Offending TeX macros and line numbers are fed back into the agent loop for self-correction before returning diffs to the client.

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
5. **Merge**: bodies are joined under the preamble with `\newpage`; the merged document is compiled (pages that break it fall back to the positioned layout) and its page count is checked against the PDF.
6. **Guest Lifecycle**: Guests keep the 1-conversion-per-24h quota; their projects are tracked in `guest_projects` and moved to the account on sign-in via `/api/guest/migrate` ([`components/GuestMigrationListener.tsx`](file:///home/abin/overbranch/components/GuestMigrationListener.tsx)).

#### P. SyncTeX Bidirectional Navigation
- **Forward Lookup**: Placing the cursor at line $L$ in `main.tex` executes `synctex view`, mapping the source code line to the exact PDF page, $x$, and $y$ coordinate, scrolling the PDF viewer automatically.
- **Backward Lookup**: Double-clicking or Cmd+Clicking an element in the PDF viewer translates the point $(page, x, y)$ back into the corresponding source filename, line number, and column in Monaco.

#### Q. Structured Observability, Tracing & Performance Telemetry
- [`backend/trace.py`](file:///home/abin/overbranch/backend/trace.py) provides structured telemetry (`AgentTrace` and `ConversionTrace` — per-job model, page similarity scores, fallback pages and latency), recording tool calls, latencies, node IDs, compiler feedback, and token counts for observability.

---

# 2. Complete Repository & File Structure (As-Is Verbatim)

```
overbranch/
├── .dockerignore                               # Docker build context exclusion rules
├── .env                                        # Local environment variables & secrets (ignored by git)
├── .env.example                                # Documented template for required environment variables
├── .gitignore                                  # Git repository file exclusion rules
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
│   ├── opencode/                               # OpenCode Bounded ReAct Agentic Pipeline
│   │   ├── __init__.py                         # Package exports
│   │   ├── agent_loop.py                       # ReAct loop, dynamic step budget (6-32), SSE streaming, tool dispatcher
│   │   ├── diff_generator.py                   # Unified/split diffs + apply-contract edit items (unique, structurally-closed anchors)
│   │   ├── shadow_compiler.py                  # Ephemeral compilation sandbox verifying code before committing
│   │   ├── shadow_workspace.py                 # Thread-safe in-memory buffer tracking uncommitted mutations
│   │   ├── template_registry.py                # Template/theme registry (Regalia, Nordlight, Prism, IEEE, ACM)
│   │   └── tools.py                            # Deterministic tool suite (str_replace, rewrite_chunk, grep_search, etc.)
│   ├── providers/                              # Multi-Provider LLM Gateway
│   │   ├── __init__.py                         # Package exports
│   │   ├── base_provider.py                    # Abstract LLMProvider interface & token usage dataclasses
│   │   ├── gemini_provider.py                  # Google Gemini adapter (Gemini 3.7 Flash, 2.5 Pro, 2.0 Flash)
│   │   ├── groq_provider.py                    # High-speed Groq inference adapter (LLaMA 3.3 70B, 3.1 8B, Mixtral)
│   │   ├── multimodal.py                       # OpenAI-style image content parts (build, detect, strip for text-only gateways)
│   │   ├── openrouter_provider.py              # OpenRouter multi-model adapter (Claude 3.5 Sonnet, GPT-4o, DeepSeek)
│   │   ├── router.py                           # ProviderRouter managing model registry, routing & API keys (optional cancel_token)
│   │   └── web2api_keys.py                     # GEMINI_WEB2API_* base URL & rotating key loader used by GeminiProvider
│   ├── pdf2latex/                              # Per-page PDF → LaTeX importer (uses the copilot's LLM)
│   │   ├── __init__.py                         # Package exports
│   │   ├── config.py                           # PDF2LATEX_* non-LLM settings (concurrency, timeouts, limits, coverage target, visual floor, job dir)
│   │   ├── extract.py                          # PyMuPDF facts + XY-cut reading order: spans, rules/rects, images, rasters, scans
│   │   ├── facts.py                            # Per-page facts JSON (blocks, side columns, \vspace gaps) + positioned-layout fallback (TikZ)
│   │   ├── jobs.py                             # File-backed job state (works across uvicorn workers), purge
│   │   ├── llm.py                              # provider_router.chat with DEFAULT_MODEL: timeouts, retries, concurrency cap, own thread pool
│   │   ├── models.py                           # Span/Line/Drawing/ImageRef/PageExtract/PageReport/ConversionReport dataclasses
│   │   ├── pipeline.py                         # Orchestration: per-page generate → compile/repair → SSIM → re-run → merge → write
│   │   ├── preamble.py                         # Deterministic preamble (geometry, exact colors, fonts) & page merging/markers
│   │   ├── prompts.py                          # Page, quality re-run and compile-fix prompts
│   │   ├── runner.py                           # Schedules jobs on the server event loop (HTTP endpoint & copilot tool)
│   │   ├── storage.py                          # Writes output into the project (no silent overwrite), creates import projects
│   │   ├── texutil.py                          # pdfLaTeX escaping & Unicode → LaTeX mapping
│   │   └── verify.py                           # pdftoppm render, shift-aligned SSIM, regions, word coverage & word displacement
│   ├── routes/                                 # Modular FastAPI API Routers
│   │   ├── __init__.py                         # Package exports
│   │   ├── agent_routes.py                     # OpenCode SSE stream (POST /api/agent/opencode), abort control & POST /api/agent/validate-latex
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
│   ├── tests/                                  # Pytest Comprehensive Test Suite
│   │   ├── eval_harness.py                     # Benchmark & evaluation harness for OpenCode agent & conversion
│   │   ├── test_ask_ai_to_fix.py               # Unit tests for "Ask AI to Fix" diagnostics & auto-healing flow
│   │   ├── test_attached_context.py            # Multi-turn attached context tests, cache TTL & PDF extraction
│   │   ├── test_auth_and_session.py            # Better-Auth session verification, cookies & RBAC tests
│   │   ├── test_aux_file_diff.py               # Auxiliary .tex diffs: tuple-unpack regression & aux write validation
│   │   ├── test_diff_generator_anchors.py      # Apply contract: unique, structurally-closed anchors & exact replay
│   │   ├── test_document_analyzer_and_context.py# Local LaTeX document analyzer & context strategy engine tests
│   │   ├── test_document_environment_integrity.py# Verification that \begin/\end environments remain balanced
│   │   ├── test_edit_pipeline_integrity.py     # End-to-end edit pipeline tests, AST preservation & auto-repair
│   │   ├── test_full_document_expansion.py     # Content expansion tests (elaborating topics, adding slides)
│   │   ├── test_agent_json_sanitizer.py        # Model JSON -> LaTeX decoding: \nonumber, \\ line breaks, escaped/unescaped modes
│   │   ├── test_full_document_rewrite.py       # Scope classifier, coverage check, step-budget cap & full rewrite tests
│   │   ├── test_heal_does_not_corrupt.py       # Healer must not invent structure; every bundled template validates & survives healing
│   │   ├── test_insert_into_chunk.py           # AST chunk insertion & surgical replacement tests
│   │   ├── test_latex_error_fixer.py           # Automated LaTeX error parser & deterministic repair tests
│   │   ├── test_opencode_fixes.py              # OpenCode ReAct loop, shadow workspace & tool execution tests
│   │   ├── pdf2latex_fixtures.py               # Programmatic fixture PDFs (colors/sizes, images, table, vectors, two-column, scanned, multi-page)
│   │   ├── test_pdf2latex_api.py               # /api/convert/pdf validation, limits, ownership & job lifecycle
│   │   ├── test_pdf2latex_copilot.py           # convert_attached_pdf tool & prompt documentation
│   │   ├── test_pdf2latex_extract.py           # Fact extraction: spans, colors, rules, page{n}_img{k} images, rasters, scans, multi-page
│   │   ├── test_pdf2latex_integration.py       # Convert → pdfLaTeX → compiled page count = source page count, similarity (opt-in live LLM)
│   │   ├── test_pdf2latex_pipeline.py          # Stubbed-LLM pipeline: agent model reuse, retries, compile repair, re-run, fallbacks, strict compile
│   │   ├── test_pdf2latex_preamble.py          # Preamble (geometry, exact colors, fonts), facts, Unicode handling, page merging
│   │   ├── test_provider_multimodal.py         # GeminiProvider image parts & text-only retry
│   │   ├── test_performance_regression.py      # Latency & performance regression benchmarks
│   │   ├── test_scope_classifier_precision.py  # Scope-inflation guards (targeted requests must not buy a 34-step budget)
│   │   ├── test_validate_latex_endpoint.py     # POST /api/agent/validate-latex: auth, heal, 413, partial-apply rejection
│   │   └── test_ppt_templates.py               # Tests for Beamer presentation templates & themes
│   ├── attached_context.py                     # Multi-turn in-memory TTL store for user-attached reference files
│   ├── auth.py                                 # Cross-stack Better-Auth session verification & RBAC
│   ├── cancellation.py                         # Thread-safe cancellation tokens & HTTP stream abort manager
│   ├── compile_queue.py                        # Concurrency-controlled compile semaphore, queue & dedicated compile thread pool
│   ├── compiler.py                             # TeX engine runner (latexmk/pdflatex; `% !TEX program` → xelatex/lualatex), TeX error list & ReportLab fallback
│   ├── context_strategy.py                     # Smart context strategy engine (TARGETED, WHOLE_FILE, SUMMARY_FIRST)
│   ├── database.py                             # Asynchronous SQLAlchemy connection pool & sessionmaker
│   ├── document_analyzer.py                    # Fast local LaTeX AST parser & structural metrics extractor (No LLM)
│   ├── document_index.py                       # LaTeX AST chunk indexer & ensure_document_environment repairer
│   ├── edit_validator.py                       # Coverage validation, single-pass literal masking & differential pre-commit checks (validate_edit; validation only — repair lives in latex_error_fixer)
│   ├── file_analyzer.py                        # Multimodal AI analysis for uploaded files & TikZ synthesizer
│   ├── latex_error_fixer.py                    # LaTeX error log parser & deterministic repairer (masked-view structure, discarded if it raises the error count)
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
│   │   ├── CollaboratorAvatars.tsx             # Active collaborator avatar stack & invite modal
│   │   ├── CompileToolbar.tsx                  # Compile button, engine dropdown, error pill & "Ask AI to Fix"
│   │   ├── EditorLayout.tsx                    # Master resizable split-pane editor shell & AI stream handler
│   │   ├── EditorThemeModal.tsx                # Monaco editor theme & typography customizer modal
│   │   ├── FileAnalyzerModal.tsx               # File inspection & AI multimodal querying modal
│   │   ├── InlineDiffEditor.tsx                # Side-by-side or unified Monaco diff viewer with Accept/Reject
│   │   ├── LatexEditorView.tsx                 # Code editor wrapper with line numbers, markers and SyncTeX
│   │   ├── ModelSelector.tsx                   # Dropdown model picker with provider badges
│   │   ├── PDFViewer.tsx                       # Interactive PDF preview with SyncTeX double-click triggers
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
│   └── schema.ts                               # PostgreSQL tables: user, session, projects, project_files, etc.
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
│   ├── hooks/
│   │   └── use-debounce.ts                     # Debounce value hook for inputs and auto-compiles
│   ├── ai-file-analysis.ts                     # Client helper invoking file analyzer API
│   ├── api-client.ts                           # Standardized fetch API wrapper with auth & error handling
│   ├── auth-client.ts                          # Better-Auth client SDK instance (signIn, signOut, useSession)
│   ├── auth.ts                                 # Better-Auth server configuration & PostgreSQL adapter
│   ├── EditHistoryStore.ts                     # LocalStorage edit history & undo/redo tracking
│   ├── guest-token.ts                          # Guest token cookie management & persistence
│   ├── latex-edit-apply.ts                     # Pure applier for AI edit items (authoritative vs chunk replay, zero silent drops)
│   ├── latex-validate.ts                       # Client for POST /api/agent/validate-latex (partial-apply safety net)
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
│       └── 001_initial_schema.sql              # Baseline PostgreSQL schema for standalone Supabase
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
- **Engines Supported**: `latexmk`, `pdflatex`, `xelatex`, `lualatex`. A `% !TEX program = xelatex|lualatex` magic comment in the first 20 lines overrides the default engine; projects (including imported PDFs) default to pdflatex. On success the result also lists any TeX error lines (`errors`), since nonstopmode can produce a PDF despite errors.
- **`compile_latex` flags**: `-synctex=1` is only passed when `persist_synctex` is set, so throwaway compiles do not write artifacts nobody reads. `allow_recovery=False` skips the patch-and-retry cascade (disable missing packages ×4, lmodern, beamercolorbox `bg`, titlesec) — up to seven extra engine runs whose output the PDF importer rejects anyway, since it treats a PDF obtained by silently disabling a package as a failure and hands the errors to the model instead.
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
  - `POST /api/agent/validate-latex` — heals and/or validates a LaTeX string without writing anything. Body `{latex_code, project_id?, file_path?, heal?}` → `{valid, errors[], fixes_applied[], healed_code, changed}`. `heal` defaults to **false**: healing hoists packages and injects theme colours, so it must never be applied without showing the user `fixes_applied`. Rate limited 60/min; bodies over 2 MB return 413.
- **Dynamic Adaptive Step Budgeting** (`determine_adaptive_step_budget`): the budget scales with document structure and is **hard-capped at `MAX_STEP_BUDGET` (32)**.
  - `TARGETED_EDIT`: 4–12 steps (4 for a typo or citation, 10–12 for creation / redesign).
  - `FULL_DOCUMENT_REWRITE` / `FULL_DOCUMENT_EXPANSION`: `8 + ceil(chunks / 2)`, capped at 32.
  - Ask mode: 4 steps.
  - **Every step is a full LLM round trip, and round trips dominate wall-clock time, so an uncapped budget is an uncapped latency bill.** The previous `max(16, chunks * 2 + 4)` had no ceiling at all: it handed a 20-section report 44 steps and a 40-frame deck 84 — and gave even a 2-chunk rewrite a floor of 16 — for work the prompt explicitly asks the model to **batch** into a handful of turns (and that `compute_step_max_tokens` funds with 16 K output tokens precisely so batching is possible). The budget now assumes several chunks land per turn, plus headroom for `verify_compile` and self-correction.
- **In-Memory Shadow Workspace**:
  All mutations apply to [`ShadowWorkspace`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py). Disk files remain untouched until the user accepts the diff in the UI.
- **Scope precision matters more than step count**: on a 15-chunk deck, `FULL_DOCUMENT_EXPANSION` raises the budget from 4 to 16 steps *and* makes coverage validation demand that every chunk be rewritten. `scope_classifier.py` therefore keeps explicitly singular targets (`"expand the conclusion paragraph"`, `"explain this slide"`, `"fix slide 3"`) as `TARGETED_EDIT` via `SINGLE_TARGET_PATTERNS`, and only promotes to document-wide scope on genuine all-document language (`ALL_DOCUMENT_PATTERNS`: `"every section"`, `"all slides"`, `"the entire document"`).
- **Output budget must permit batching**: the prompt asks the model to batch several `rewrite_chunk` calls per turn, so `compute_step_max_tokens` allocates `FULL_REWRITE_STEP_MAX_TOKENS` (16 K) for rewrite scopes. A 4 K cap made batching impossible and pushed the model into truncation recovery, which costs a second full LLM call and then discards the response. `TARGETED_EDIT` gets **4 K** for the same reason: 2 K sat below the size of one Beamer frame once JSON escaping is paid for, so ordinary targeted edits tripped the truncation path — an extra LLM call to continue the JSON, then a discarded step and a third call when the continuation also ran long.
- **The model's JSON must decode back to the LaTeX it wrote** (`sanitize_latex_json`). Models routinely emit `\begin` rather than `\\begin` inside JSON strings, so odd-length backslash runs are doubled before `json.loads`. Two shapes are ambiguous and both used to be resolved the wrong way, silently, inside the string the agent then wrote into the document:
  - `\n` is both the JSON newline escape and the prefix of real macros. The rule was a hand-kept whitelist, so every macro missing from it — `\nonumber`, `\notag`, `\nicefrac`, `\notin`, `\normalfont` — decoded to a **literal newline plus the rest of the command name**, i.e. an undefined control sequence. It is now resolved by first deciding whether the response escapes LaTeX *at all* (`_emits_unescaped_latex`): in an unescaped response any `\n<letters>` is a macro; in a properly escaped one `\n` stays a newline.
  - `\\` is both an escaped backslash and the LaTeX line break. In an unescaped response a bare pair is widened to four, so a `tabular` row break survives and `\\[0.3em]` no longer decodes to `\[0.3em]` — opening display math where a spaced line break was meant. (That corruption was common enough that `auto_heal_latex_code` still carries a rule to undo one symptom of it.)
  The whole transform runs in **one pass** over the original text, so a run it widens is never reconsidered and widened twice; `tests/test_agent_json_sanitizer.py` covers both modes and idempotence.
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
- **Failover**: If a user custom API key fails or experiences rate limits, the router can failover to configured backup providers.

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
  2. PDF font names map to pdfLaTeX font packages: Times-like → `mathptmx`, Palatino/Garamond-like → `mathpazo`, Arial/Helvetica/Calibri-like → `helvet`, Courier-like → `courier`, Computer/Latin Modern → `lmodern`; the most used family becomes the main font and secondary sans/mono families are loaded too. Exact sizes are kept with `\fontsize`.
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
  6. Only an unacceptable page is re-run, with the missing words, the invented words, the overflow, the measured vertical offset and the median word displacement. Overflowing pages are scaled to fit with `\obfit`. The positioned layout rescues a page that is still unacceptable, never one that merely reflowed differently.
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
  3. Active users in a project are displayed in [`CollaboratorAvatars.tsx`](file:///home/abin/overbranch/components/editor/CollaboratorAvatars.tsx).

---

### Feature 26: Inline Diff Editor, Diff Generator & Edit History Tracking

- **File Implementation**: [`backend/opencode/diff_generator.py`](file:///home/abin/overbranch/backend/opencode/diff_generator.py), [`lib/latex-edit-apply.ts`](file:///home/abin/overbranch/lib/latex-edit-apply.ts), [`lib/latex-validate.ts`](file:///home/abin/overbranch/lib/latex-validate.ts), [`components/editor/EditorLayout.tsx`](file:///home/abin/overbranch/components/editor/EditorLayout.tsx), [`lib/EditHistoryStore.ts`](file:///home/abin/overbranch/lib/EditHistoryStore.ts)

#### The Apply Contract (`apply_contract_version: 2`)

`compute_edit_items` guarantees, for every emitted item:

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
  3. **No edit is ever dropped silently.** Every item ends in `applied` or `skipped` with a reason (`no-anchor`, `not-found`, `not-unique`, `stale-position`, `overlap`), aggregated into one message. If nothing applies, the buffer is left untouched and nothing is saved or compiled.
  4. A *partial* accept is re-checked through `POST /api/agent/validate-latex` before saving, since accepting edit 3 but not edit 2 can leave an orphaned tag. Validation failure rolls back inside the same undo stop; a network failure fails **open** (keeps the edit, skips auto-compile, warns).
  5. `commitEditOutcome` in `EditorLayout.tsx` is the one place that touches Monaco, `EditHistoryStore`, `saveDocument` and `handleCompile` — previously duplicated across four handlers with diverging behaviour.
  6. `final_diff` payloads are accumulated **keyed by file**, so an auxiliary `.tex` file's diff no longer clobbers the main one, and `result` **merges** into the accumulated payload instead of replacing it.
  7. `EditHistoryStore.ts` records snapshots in browser LocalStorage for instant undo/redo.

> Note: `components/editor/InlineDiffEditor.tsx` currently exports the `EditItem` type that the rest of the editor consumes, but the component itself is not rendered — the inline preview blocks in `EditorLayout.tsx` display diffs instead.

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
- **Test Modules**:
  1. `eval_harness.py`: Benchmark and evaluation harness for OpenCode agent and conversion pipelines.
  2. `test_ask_ai_to_fix.py`: Unit tests for "Ask AI to Fix" compiler error diagnostics, prompt construction, and auto-healing flow.
  3. `test_attached_context.py`: Multi-turn attached context session tests, cache TTL, and PDF text extraction.
  4. `test_auth_and_session.py`: Cross-stack Better-Auth session verification, cookies, and RBAC tests.
  5. `test_document_analyzer_and_context.py`: Local LaTeX document analysis and context strategy engine tests.
  6. `test_document_environment_integrity.py`: Verification that environments (`frame`, `tikzpicture`, `itemize`, etc.) remain balanced and closed during edits.
  7. `test_edit_pipeline_integrity.py`: End-to-end edit pipeline tests, AST preservation, and auto-repair.
  8. `test_full_document_expansion.py`: Tests for expanding documents with new sections/chapters.
  9. `test_full_document_rewrite.py`: Scope classifier, coverage check, leftover detection, and full document rewrite tests.
  10. `test_insert_into_chunk.py`: AST chunk insertion and surgical replacement tests.
  11. `test_latex_error_fixer.py`: Automated LaTeX error parser and deterministic syntax repair tests.
  12. `test_opencode_fixes.py`: OpenCode ReAct loop, shadow workspace, and tool execution tests.
  12b. `test_heal_does_not_corrupt.py`: the healer must not invent structure from comments, verbatim/listing bodies, macro definition bodies or class-defined list environments; healing is discarded if it raises the error count; **every** `backend/templates/**/*.tex` must validate clean and survive a heal; differential validation tolerates a pre-existing defect but still blocks a newly introduced one.
  12c. `test_agent_json_sanitizer.py`: LaTeX survives decoding out of the model's JSON in both escaped and unescaped modes — `\nonumber` is not a newline, `\\` stays a line break, `\\[0.3em]` does not become `\[0.3em]`, and the transform is idempotent.
  13. `test_performance_regression.py`: Benchmarks and performance regression tests for compilation and token usage.
  14. `test_ppt_templates.py`: Tests for Beamer/PPT templates (Regalia, Nordlight, Prism, etc.) rendering and theme compilation.
  15. `test_pdf2latex_*.py` & `test_provider_multimodal.py`: PDF → LaTeX importer — fact extraction, preamble/facts/merging, stubbed-LLM pipeline (retries, compile repair, re-run, fallbacks), the acceptance predicate (a faithful reflow is accepted without a re-run; the positioned layout rescues but never displaces a complete page), shift-tolerant page comparison, API, copilot tool, provider image parts, and an end-to-end pdfLaTeX test asserting compiled page count = source page count (skipped without pdflatex + pdftoppm; `PDF2LATEX_LIVE_LLM=1` adds a real-model run).

---

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
| `SHADOW_COMPILE_MAX_RETRIES`| Backend AI | Max retries for shadow compiler self-correction (Default: `2`) |
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

---

> ⚠️ **MANDATORY MAINTENANCE DIRECTIVE:**
> **Update this file (`OVERVIEW.md`) after each and every change to the codebase.**
> Whenever files, folders, routes, components, database schemas, services, or architectures are added, modified, renamed, or deleted, this document must be updated immediately to keep all descriptions, file indexes, and architectural references 100% synchronized with reality.
