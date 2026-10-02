# OverBranch — Comprehensive Method, Architecture & Feature Guide

> **OverBranch** is a 100% free and open-source agentic LaTeX code editor and research environment. Built for students, academics, and scientific authors, it combines lightning-fast compilation, an intelligent OpenCode ReAct AI copilot, dynamic adaptive step budgeting, scope classification with AST-level chunk replacement, cross-stack Better-Auth session verification via async SQLAlchemy, sliding-window rate limiting, concurrency-controlled compilation queues, bidirectional SyncTeX synchronization, PDF-to-LaTeX conversion with guest migration, shadow compilation with self-correction, in-memory structural document indexing, multimodal file analysis, and multi-user collaboration.

---

## Table of Contents

1. [High-Level Methodology & System Architecture](#1-high-level-methodology--system-architecture)
   - [Architectural Overview](#architectural-overview)
   - [Core Methodological Pipelines](#core-methodological-pipelines)
     - [A. OpenCode ReAct Agent Loop & Dynamic Adaptive Step Budgeting](#a-opencode-react-agent-loop--dynamic-adaptive-step-budgeting)
     - [B. Scope Classification & AST Structural Chunk Replacement](#b-scope-classification--ast-structural-chunk-replacement)
     - [C. Full Document Rewrite Coverage & Leftover Validation](#c-full-document-rewrite-coverage--leftover-validation)
     - [D. Shadow Compilation & Compiler-Feedback Self-Correction](#d-shadow-compilation--compiler-feedback-self-correction)
     - [E. Cross-Stack Better-Auth Authentication & SQLAlchemy Verification](#e-cross-stack-better-auth-authentication--sqlalchemy-verification)
     - [F. Sliding-Window Rate Limiting & Concurrency Queue](#f-sliding-window-rate-limiting--concurrency-queue)
     - [G. Document Outline Extraction & Context Optimization](#g-document-outline-extraction--context-optimization)
     - [H. Curated Template & Theme Registry Engine](#h-curated-template--theme-registry-engine)
     - [I. Beamer Visibility & Color Contrast Diagnostic](#i-beamer-visibility--color-contrast-diagnostic)
     - [J. Document Creation & Conversion Archetypes](#j-document-creation--conversion-archetypes)
     - [K. Real-Time AI Interruption & Stream Cancellation](#k-real-time-ai-interruption--stream-cancellation)
     - [L. PDF-to-LaTeX Ingestion & Guest Migration Lifecycle](#l-pdf-to-latex-ingestion--guest-migration-lifecycle)
     - [M. LaTeX Compilation & Resilient Fallback Pipeline](#m-latex-compilation--resilient-fallback-pipeline)
     - [N. SyncTeX Bidirectional Navigation](#n-synctex-bidirectional-navigation)
     - [O. Structured Observability & Tracing](#o-structured-observability--tracing)
2. [Complete Repository & File Structure](#2-complete-repository--file-structure)
   - [Root Directory Layout](#root-directory-layout)
   - [Backend Architecture (`backend/`)](#backend-architecture-backend)
   - [Frontend Application (`app/`)](#frontend-application-app)
   - [UI Components (`components/`)](#ui-components-components)
   - [Database Layer (`db/` & `drizzle/`)](#database-layer-db--drizzle)
   - [tRPC API Layer (`trpc/` & `server/`)](#trpc-api-layer-trpc--server)
   - [Libraries & Client Utilities (`lib/`)](#libraries--client-utilities-lib)
   - [Hooks, Providers, Types & Migrations (`hooks/`, `providers/`, `types/`, `supabase/`)](#hooks-providers-types--migrations)
3. [Deep-Dive: How Every Feature Works](#3-deep-dive-how-every-feature-works)
   - [Feature 1: Real-Time LaTeX Compilation, Concurrency Queue & ReportLab Fallback](#feature-1-real-time-latex-compilation-concurrency-queue--reportlab-fallback)
   - [Feature 2: Bidirectional SyncTeX Navigation (Forward & Backward)](#feature-2-bidirectional-synctex-navigation-forward--backward)
   - [Feature 3: OpenCode Bounded ReAct Agent Loop & Dynamic Step Budgeting](#feature-3-opencode-bounded-react-agent-loop--dynamic-step-budgeting)
   - [Feature 4: Scope Classification (`TARGETED_EDIT` vs. `FULL_DOCUMENT_REWRITE`) & Structural `rewrite_chunk`](#feature-4-scope-classification-targeted_edit-vs-full_document_rewrite--structural-rewrite_chunk)
   - [Feature 5: Full Document Rewrite Coverage Validation & Leftover Detection](#feature-5-full-document-rewrite-coverage-validation--leftover-detection)
   - [Feature 6: Shadow Compilation & Sandboxed Self-Correction](#feature-6-shadow-compilation--sandboxed-self-correction)
   - [Feature 7: Cross-Stack Better-Auth Authentication & PostgreSQL Session Sharing](#feature-7-cross-stack-better-auth-authentication--postgresql-session-sharing)
   - [Feature 8: Sliding-Window Rate Limiting & Denial-of-Service Defense](#feature-8-sliding-window-rate-limiting--denial-of-service-defense)
   - [Feature 9: Curated Template/Theme Registry & Non-Destructive Redesign](#feature-9-curated-templatetheme-registry--non-destructive-redesign)
   - [Feature 10: Color Contrast Auto-Diagnostic & Invisible Text Self-Repair](#feature-10-color-contrast-auto-diagnostic--invisible-text-self-repair)
   - [Feature 11: Document Creation & Conversion Archetypes](#feature-11-document-creation--conversion-archetypes)
   - [Feature 12: Real-Time AI Interruption, Stream Abort & Thread-Safe Cancellation](#feature-12-real-time-ai-interruption-stream-abort--thread-safe-cancellation)
   - [Feature 13: Query Rewriting, Semantic Chunking & Hybrid Vector Retrieval](#feature-13-query-rewriting-semantic-chunking--hybrid-vector-retrieval)
   - [Feature 14: Structural Document Indexing & Targeted Frame Extraction](#feature-14-structural-document-indexing--targeted-frame-extraction)
   - [Feature 15: Pre-Output Validation & LIFO Auto-Repair Engine](#feature-15-pre-output-validation--lifo-auto-repair-engine)
   - [Feature 16: Multi-Provider LLM Gateway & Fallback Architecture](#feature-16-multi-provider-llm-gateway--fallback-architecture)
   - [Feature 17: PDF to Editable LaTeX Conversion Engine (Dashboard & In-Project)](#feature-17-pdf-to-editable-latex-conversion-engine-dashboard--in-project)
   - [Feature 18: Guest Conversion Session, Quota Enforcement & Auto-Migration](#feature-18-guest-conversion-session-quota-enforcement--auto-migration)
   - [Feature 19: Multimodal AI File Analyzer & TikZ Synthesizer](#feature-19-multimodal-ai-file-analyzer--tikz-synthesizer)
   - [Feature 20: Collaborative Project Management & Role-Based Access](#feature-20-collaborative-project-management--role-based-access)
   - [Feature 21: Inline Diff Editor & Edit History Tracking](#feature-21-inline-diff-editor--edit-history-tracking)
   - [Feature 22: Presentation View Mode (Beamer Decks)](#feature-22-presentation-view-mode-beamer-decks)
   - [Feature 23: LaTeX Template Gallery & Dynamic Cloning](#feature-23-latex-template-gallery--dynamic-cloning)
   - [Feature 24: Design System ("Celestial Obsidian & Luminescent Iris") & Theming Engine](#feature-24-design-system-celestial-obsidian--luminescent-iris--theming-engine)
   - [Feature 25: Structured Observability, Tracing & Performance Telemetry](#feature-25-structured-observability-tracing--performance-telemetry)
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
│  - Presentation Deck Player (Beamer slide rendering)                   │
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
                   └──────────────────►  - PDF to LaTeX OCR / Parser     │
                                      │  - Multimodal File Analyzer      │
                                      │  - SyncTeX Forward/Backward View │
                                      │  - Structured Telemetry (Trace)  │
                                      └──────────────────────────────────┘
```

---

### Core Methodological Pipelines

#### A. OpenCode ReAct Agent Loop & Dynamic Adaptive Step Budgeting
1. **Interactive Tool Loop**: [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py) executes an iterative ReAct cycle operating on an in-memory [`ShadowWorkspace`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py).
2. **Dynamic Step Budgeting**: Replaces hardcoded step limits with an adaptive formula scaling from **6 to 32 steps** based on the detected scope, document length, number of chapters/sections, and request type.
3. **Deterministic Tool Suite**:
   - `read_file_range`: Reads exact line-numbered contents without hallucinated drift (up to 300 lines per call).
   - `grep_search`: Finds structural anchors (`\chapter`, `\section`, `\begin{frame}`, `\label`, `\cite`).
   - `str_replace`: Performs strict character-for-character replacements with zero spatial drift.
   - `rewrite_chunk`: Replaces entire chapters, sections, or frames using AST byte offsets (ideal for full document rewrites).
   - `list_assets`: Discovers available images/PDFs in `assets/` for `\includegraphics`.
   - `verify_compile`: Triggers sandboxed compilation to capture compiler diagnostics with `infra_skip` fallback if the host lacks a TeX engine.
   - `get_template_theme`: Retrieves curated themes (Beamer PPT themes, IEEE conference/journal papers, theses, resumes/CVs, formal letters, lab assignments) and extracts styling preambles for non-destructive redesigns.
4. **SSE Event Streaming**: Streams real-time reasoning (`thought`, `tool_call`, `tool_result`, `compile_error`, `coverage_check`, `final_diff`, `result`) to [`components/editor/AgentReasoningWindow.tsx`](file:///home/abin/overbranch/components/editor/AgentReasoningWindow.tsx) and [`components/editor/InlineDiffEditor.tsx`](file:///home/abin/overbranch/components/editor/InlineDiffEditor.tsx).

#### B. Scope Classification & AST Structural Chunk Replacement
1. **Scope Classification**: [`backend/scope_classifier.py`](file:///home/abin/overbranch/backend/scope_classifier.py) automatically classifies prompts into `TARGETED_EDIT` (surgical fixes, typos, single section additions) vs. `FULL_DOCUMENT_REWRITE` (topic overhauls, whole document replacements, new source material).
2. **Structural Document Indexing**: [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py) parses the LaTeX AST into discrete `DocumentChunk` entities with byte/character offsets and line numbers.
3. **Chunk-Level Rewriting**: In `FULL_DOCUMENT_REWRITE` mode, the agent uses `rewrite_chunk(chunk_id, new_content)` to replace entire chapters/sections cleanly without exact-string matching errors.

#### C. Full Document Rewrite Coverage & Leftover Validation
1. **Coverage Check**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py) inspects whether all content chunks (chapters/sections/frames) were rewritten during a full rewrite request.
2. **Leftover Detection**: Scans modified code for forbidden residual terms from old topics or unedited boilerplate.
3. **Automatic Rejection & Retries**: If the agent attempts to signal `done=true` while chunks remain untouched, the coverage validator rejects the completion and prompts the agent to finish all unedited sections.

#### D. Shadow Compilation & Compiler-Feedback Self-Correction
1. **In-Memory Shadow Sandbox**: [`backend/opencode/shadow_workspace.py`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py) maintains an isolated buffer; edits never touch disk during reasoning.
2. **Ephemeral Verification**: [`backend/opencode/shadow_compiler.py`](file:///home/abin/overbranch/backend/opencode/shadow_compiler.py) executes isolated compilation tests (`pdflatex`, `latexmk`, or ReportLab fallback).
3. **Compiler Feedback**: Offending TeX macros and line numbers are fed back into the agent loop for self-correction before returning diffs to the client.

#### E. Cross-Stack Better-Auth Authentication & SQLAlchemy Verification
1. **Shared PostgreSQL Database**: Next.js 15 (Better-Auth) and FastAPI Python backend share the same PostgreSQL database.
2. **Direct Session Verification**: [`backend/auth.py`](file:///home/abin/overbranch/backend/auth.py) extracts session tokens from cookies (`better-auth.session_token`) or Bearer headers, unquotes them, strips signatures, and queries the `session` table via async SQLAlchemy (`backend/database.py`, `backend/models.py`).
3. **RBAC & Ownership**: `verify_project_ownership_or_member()` checks project ownership and collaborator memberships in `projects` and `project_members`.
4. **Guest Identity**: HMAC-signed guest tokens (`x-guest-token`, `ob_guest_token`) are verified for anonymous users with 24-hour expiration.

#### F. Sliding-Window Rate Limiting & Concurrency Queue
1. **Sliding-Window Rate Limiter**: [`backend/rate_limiter.py`](file:///home/abin/overbranch/backend/rate_limiter.py) provides thread-safe sliding-window rate limiting keyed by authenticated user ID, guest ID, or client IP, protecting against DDoS and scraping.
2. **Compilation Concurrency Queue**: [`backend/compile_queue.py`](file:///home/abin/overbranch/backend/compile_queue.py) uses an `asyncio.Semaphore` (default: 4 concurrent compiles) and bounded queue depth with HTTP 429 backpressure to prevent CPU exhaustion.

#### G. Document Outline Extraction & Context Optimization
1. **Document Outline Injection**: `_build_document_outline()` extracts preambles, chapters, sections, subsections, and frames with line numbers into the agent prompt.
2. **Conversation History Compaction**: `_compact_conversation_history()` prunes and summarizes older tool results (`read_file_range`, `get_template_theme`, `grep_search`), keeping payload sizes small and preventing context window explosion.
3. **Continuation Handling**: Automatically detects truncated JSON responses (`finish_reason == "length"`) and prompts the model to complete the output.

#### H. Curated Template & Theme Registry Engine
1. **Template Discovery**: [`backend/opencode/template_registry.py`](file:///home/abin/overbranch/backend/opencode/template_registry.py) indexes curated templates across categories: `ppt` (Beamer themes), `papers` (IEEE conference/journal), `thesis` (Reports/Theses), `resume` (CVs), `letters` (Formal letters), and `assignments` (Lab reports).
2. **Preamble Extraction**: Agents can invoke `get_template_theme(category="ppt", theme_name="nordlight", extract_section="preamble")` to extract styling, color schemes, and packages to redesign documents while preserving all user content and equations.

#### I. Beamer Visibility & Color Contrast Diagnostic
1. **Contrast Detection**: When users report unreadable or invisible titles/headings in Beamer presentations, the system diagnoses foreground/background contrast conflicts.
2. **Automatic Pre-prompting**: Injects explicit instructions to update `\setbeamercolor{title}{bg=..., fg=white}` and remove dark color overrides like `\title{\color{black}{...}}`.

#### J. Document Creation & Conversion Archetypes
- Enforces strict architectural archetypes when generating documents from scratch or converting attached PDF references:
  - **Beamer Presentations**: `\documentclass[aspectratio=169]{beamer}`, modern themes (Madrid/metropolis), plain Title frame, Outline frame, and 6–12 structured content frames (max 5–6 bullets/slide).
  - **Multi-Chapter Reports**: `\documentclass[11pt,a4paper,oneside]{report}`, formal front matter, and 4–6 detailed chapters with rich theory and mathematical formulations.
  - **Academic Papers**: `\documentclass[conference]{IEEEtran}` or two-column articles with standard sections and bibliography.
  - **Resumes / CVs**: Structured single/two-page layouts.

#### K. Real-Time AI Interruption & Stream Cancellation
1. **Thread-Safe Cancellation**: [`backend/cancellation.py`](file:///home/abin/overbranch/backend/cancellation.py) provides `CancellationManager` and `CancellationToken`.
2. **Instant Abort**: Clients can hit the "Stop Generation" button or call `POST /api/agent/stop`, triggering immediate abortion of active LLM streaming and background operations.

#### L. PDF-to-LaTeX Ingestion & Guest Migration Lifecycle
1. **Multimodal Deconstruction**: Uploaded PDFs are parsed via [`backend/services/pdf_parser.py`](file:///home/abin/overbranch/backend/services/pdf_parser.py) (using PyMuPDF or pypdf) to extract text layout, tabular structures, and images.
2. **Figure Extraction**: [`backend/services/pdf_figure_extractor.py`](file:///home/abin/overbranch/backend/services/pdf_figure_extractor.py) extracts embedded raster/vector images directly into `assets/`, parsing multi-line captions.
3. **Positional Drift Calibration**: [`backend/services/layout_verifier.py`](file:///home/abin/overbranch/backend/services/layout_verifier.py) measures vertical drift between original PDF pages and generated TeX rendering.
4. **Guest Session Protection & Migration**: Guests receive HMAC-signed tokens with 24-hour expiration. Upon registration or login, [`components/GuestMigrationListener.tsx`](file:///home/abin/overbranch/components/GuestMigrationListener.tsx) triggers `/api/guest/migrate`, transferring all projects to the user account.

#### M. LaTeX Compilation & Resilient Fallback Pipeline
1. **Source Bundling**: The frontend packages the active `.tex` document, referenced images, auxiliary files (`.bib`, `.sty`, `.cls`), and requested TeX engine (`latexmk`, `pdflatex`, `xelatex`, `lualatex`).
2. **Execution Isolation**: The backend spawns a secure temporary directory (`tempfile.mkdtemp()`), copies root templates, decodes assets to disk, and executes compilation.
3. **Resilient ReportLab Fallback**: If no LaTeX engine is installed on the host system, [`backend/compiler.py`](file:///home/abin/overbranch/backend/compiler.py) engages an intelligent ReportLab synthetic generator to build a matching PDF preview immediately.

#### N. SyncTeX Bidirectional Navigation
- **Forward Lookup**: Placing the cursor at line $L$ in `main.tex` executes `synctex view`, mapping the source code line to the exact PDF page, $x$, and $y$ coordinate, scrolling the PDF viewer automatically.
- **Backward Lookup**: Double-clicking or Cmd+Clicking an element in the PDF viewer translates the point $(page, x, y)$ back into the corresponding source filename, line number, and column in Monaco.

#### O. Structured Observability & Tracing
- [`backend/trace.py`](file:///home/abin/overbranch/backend/trace.py) provides structured telemetry (`AgentTrace` and `ConversionTrace`), recording tool calls, latencies, node IDs, compiler feedback, and token counts for observability.

---

# 2. Complete Repository & File Structure

```
overbranch/
├── app/                                 # Next.js 15 App Router (Frontend)
│   ├── (dashboard)/                     # Protected Dashboard Layout Group
│   │   ├── dashboard/page.tsx           # User Dashboard (Recent projects, statistics, quick actions)
│   │   ├── layout.tsx                   # Dashboard Sidebar, Nav & Shell
│   │   ├── profile/page.tsx             # User Profile & Preferences
│   │   ├── projects/page.tsx            # Project Management (List, Filter, Delete, Star)
│   │   └── templates/page.tsx           # LaTeX Template Explorer
│   ├── api/                             # API Routes (Next.js server-side)
│   │   ├── auth/[...all]/route.ts       # Better-Auth authentication endpoints
│   │   └── trpc/[trpc]/route.ts         # tRPC HTTP Handler
│   ├── auth/page.tsx                    # Auth verification & callbacks
│   ├── convert/page.tsx                 # Standalone PDF to LaTeX Converter Page
│   ├── editor/[id]/page.tsx             # Main Project Editor Screen (Route handler)
│   ├── error.tsx                        # Global error boundary
│   ├── not-found.tsx                    # Global 404 page
│   ├── globals.css                      # Global Styles, CSS Variables & Tailwind Directives
│   ├── layout.tsx                       # Root HTML Layout & Global Providers
│   ├── login/page.tsx                   # Sign-in Page
│   ├── page.tsx                         # Landing Page (Showcase, CTA, Hero)
│   └── register/page.tsx                # Sign-up Page
│
├── backend/                             # Python FastAPI Engine
│   ├── assets/                          # Static assets and template figures
│   ├── opencode/                        # OpenCode-Style Agentic Pipeline (Exact-Match & Structural)
│   │   ├── __init__.py                  # Package exports
│   │   ├── agent_loop.py                # ReAct agent loop, adaptive step budget, outline injection
│   │   ├── diff_generator.py            # Line-level diff generator for InlineDiffEditor
│   │   ├── shadow_compiler.py           # Sandboxed compiler verification wrapper
│   │   ├── shadow_workspace.py          # Thread-safe in-memory shadow buffer & chunk tracking
│   │   ├── template_registry.py         # Template & theme registry (preamble extraction)
│   │   └── tools.py                     # Tool suite (read_file_range, str_replace, rewrite_chunk, etc.)
│   ├── providers/                       # Multi-Provider LLM Gateway
│   │   ├── __init__.py                  # Package exports
│   │   ├── base_provider.py             # Abstract LLMProvider base class
│   │   ├── gemini_provider.py           # Gemini Web2API / Google GenAI adapter
│   │   ├── groq_provider.py             # High-speed Groq inference adapter
│   │   ├── openrouter_provider.py       # OpenRouter models adapter
│   │   └── router.py                    # ProviderRouter (Model dispatch & registry)
│   ├── routes/                          # Modular FastAPI Routers
│   │   ├── __init__.py
│   │   ├── agent_routes.py              # OpenCode pipeline SSE endpoint (POST /api/agent/opencode) & stop
│   │   ├── guest_pdf.py                 # Public guest conversion & migration endpoints
│   │   └── pdf_conversion.py            # Authenticated PDF to LaTeX conversion & SSE
│   ├── services/                        # Business Logic & Helpers
│   │   ├── __init__.py
│   │   ├── guest_cleanup.py             # Scheduled daemon to purge expired guest projects
│   │   ├── guest_identity.py            # Device fingerprinting & HMAC guest cookie tokens
│   │   ├── guest_migrator.py            # Reassociates guest projects with user accounts
│   │   ├── guest_quota.py               # 24-hour rate limiting & conversion tracking
│   │   ├── layout_verifier.py           # Positional drift analysis & vertical spacing calibration
│   │   ├── pdf_figure_extractor.py      # Embedded PDF figure extraction & caption parsing
│   │   ├── pdf_parser.py                # PDF extraction via PyMuPDF / pypdf
│   │   ├── pdf_to_latex.py              # LLM conversion prompts & LaTeX synthesis
│   │   └── project_file_writer.py       # Writes generated projects to disk & Supabase
│   ├── templates/                       # Built-in LaTeX project templates
│   │   ├── assignments/                 # Academic Assignment templates
│   │   ├── letters/                     # Formal letter templates
│   │   ├── papers/                      # Research Paper templates (IEEE, ACM, Springer)
│   │   ├── ppt/                         # Beamer presentation themes (Nordlight, Prism, Regalia, etc.)
│   │   ├── reports/                     # Laboratory & Technical reports
│   │   ├── resume/                      # Resumes & CV templates (ModernCV, Deedy, DeveloperCV)
│   │   └── thesis/                      # Master & PhD Thesis templates
│   ├── tests/                           # Pytest Test Suite
│   │   ├── test_auth_and_session.py     # Cross-stack Better-Auth session & auth tests
│   │   ├── test_full_document_rewrite.py# Scope classifier, coverage, and full rewrite tests
│   │   └── test_opencode_fixes.py       # OpenCode tools, shadow workspace, and loop tests
│   ├── auth.py                          # Better-Auth SQLAlchemy session verification & RBAC
│   ├── cancellation.py                  # Thread-safe cancellation tokens & HTTP stream abort manager
│   ├── compile_queue.py                 # Concurrency-controlled compilation semaphore & queue
│   ├── compiler.py                      # TeX Engine compiler & ReportLab fallback
│   ├── database.py                      # Asynchronous SQLAlchemy database engine & connection pool
│   ├── document_index.py                # Structural AST/regex parser & chunk indexer
│   ├── edit_validator.py                # Coverage validation, AST regex rules & auto-repair
│   ├── file_analyzer.py                 # Multimodal AI analysis for uploaded files & TikZ generator
│   ├── main.py                          # FastAPI entry point, CORS, lifespan, compile & synctex endpoints
│   ├── models.py                        # SQLAlchemy ORM models for Better-Auth schema (User, Session)
│   ├── project_storage.py               # File system disk operations & Supabase storage
│   ├── query_rewriter.py                # Fast multi-query expansion for hybrid search
│   ├── rate_limiter.py                  # Sliding-window in-memory rate limiter
│   ├── retriever.py                     # Vector & structural retriever
│   ├── scope_classifier.py              # Request scope classifier (TARGETED_EDIT vs FULL_DOCUMENT_REWRITE)
│   ├── synctex_service.py               # Forward & backward SyncTeX locator
│   ├── template_service.py              # Template metadata & thumbnail server
│   ├── trace.py                         # Structured telemetry & observability records
│   ├── Dockerfile                       # Backend standalone container build
│   ├── pyproject.toml                   # Python package configuration
│   ├── requirements.txt                 # Python dependencies
│   └── uv.lock                          # UV dependency lockfile
│
├── components/                          # React Components
│   ├── dashboard/                       # Dashboard-specific widgets
│   │   ├── NotificationsPopover.tsx     # In-app notification center & invitations
│   │   ├── PDFToLatexModal.tsx          # In-dashboard PDF to LaTeX conversion modal
│   │   ├── Sidebar.tsx                  # Collapsible navigation sidebar
│   │   ├── TopNav.tsx                   # Top navigation bar & breadcrumbs
│   │   └── UserProfileDropdown.tsx      # User menu & sign-out action
│   ├── editor/                          # Editor Suite Components
│   │   ├── AgentReasoningWindow.tsx     # Live ReAct thought / step execution & inspection monitor
│   │   ├── ApiSettingsModal.tsx         # User custom API keys modal (Gemini, Groq, OpenRouter)
│   │   ├── ChatMessageContent.tsx       # Markdown & LaTeX rendering for AI chat
│   │   ├── ChatModeToggle.tsx           # Toggle between 'Ask' and 'Edit' modes
│   │   ├── CollaboratorAvatars.tsx      # Multi-user avatars & invitation management
│   │   ├── CompileToolbar.tsx           # Compile button, engine dropdown, error pill
│   │   ├── EditorLayout.tsx             # Master resizable split-pane editor shell & AI stream handler
│   │   ├── EditorThemeModal.tsx         # Theme customizer (Monaco themes, font sizes)
│   │   ├── FileAnalyzerModal.tsx        # File inspection & AI multimodal querying
│   │   ├── InlineDiffEditor.tsx         # Side-by-side or unified diff viewer
│   │   ├── LatexEditorView.tsx          # Code editor wrapper with line numbers and SyncTeX
│   │   ├── ModelSelector.tsx            # Dropdown model picker with provider badges
│   │   ├── PDFViewer.tsx                # Interactive PDF preview with SyncTeX triggers
│   │   ├── PresentationView.tsx         # Fullscreen Beamer slide presentation view
│   │   └── ProjectFilesPanel.tsx        # File tree explorer & asset manager
│   ├── extend/                          # Extended viewer widgets
│   │   ├── document-viewer-sidebar.tsx  # Document thumbnails & outline sidebar
│   │   └── pdf-viewer.tsx               # Embedded PDF canvas renderer
│   ├── landing/                         # Landing page sections
│   │   ├── BrandMarquee.tsx             # Academic & institution marquee
│   │   ├── CTASection.tsx               # Call-to-action banner
│   │   ├── Features.tsx                 # Core features grid
│   │   ├── Footer.tsx                   # Footer & copyright
│   │   ├── FreeSection.tsx              # 100% Free & open-source badge
│   │   ├── Header.tsx                   # Public navigation header
│   │   ├── Hero.tsx                     # Hero header with dynamic CTA
│   │   ├── Introduction.tsx             # Project vision & architecture intro
│   │   ├── OpenSourceSection.tsx        # GitHub links & open source manifesto
│   │   ├── PdfToLatexSection.tsx        # Interactive PDF to LaTeX demo preview
│   │   ├── SelfHosting.tsx              # Docker self-hosting instructions
│   │   ├── Showcase.tsx                 # Feature showcase tabs
│   │   ├── TechnicalMarquee.tsx         # Tech stack badges marquee
│   │   └── TemplatesSection.tsx         # Template gallery preview
│   ├── ui/                              # Radix UI / Shadcn base components
│   │   ├── alert-dialog.tsx, avatar.tsx, badge-custom.tsx, badge.tsx, button.tsx
│   │   ├── card.tsx, command-palette.tsx, dialog.tsx, dropdown-menu.tsx, empty-state.tsx
│   │   ├── github-icon.tsx, input.tsx, label.tsx, loading-screen.tsx, OverBranchLogo.tsx
│   │   ├── popover.tsx, progress.tsx, scroll-area.tsx, select.tsx, separator.tsx
│   │   ├── sheet.tsx, skeleton-loader.tsx, slider.tsx, spinner.tsx, table.tsx
│   │   ├── tabs-animated.tsx, textarea.tsx, theme-toggle.tsx, toggle.tsx, tooltip.tsx
│   ├── DiffWidget.tsx                   # Standalone diff display with Accept/Reject buttons
│   └── GuestMigrationListener.tsx       # Client listener to migrate guest session on login
│
├── db/                                  # Database Access & Schema
│   ├── index.ts                         # Drizzle ORM client initialization
│   └── schema.ts                        # Drizzle PostgreSQL schema definitions
│
├── drizzle/                             # Drizzle Migrations & Snapshots
│   ├── 0000_condemned_the_twelve.sql    # Generated SQL schema migrations
│   └── meta/                            # Drizzle journal and snapshot history
│
├── hooks/                               # Custom React Hooks
│   └── useGuestMigration.ts             # Hook for guest session migration detection
│
├── lib/                                 # Shared Library Code
│   ├── hooks/
│   │   └── use-debounce.ts              # Debounce utility hook
│   ├── ai-file-analysis.ts              # Client utilities for invoking file analyzer
│   ├── auth-client.ts                   # Better-Auth client instance
│   ├── auth.ts                          # Better-Auth server configuration
│   ├── EditHistoryStore.ts              # LocalStorage edit history & undo/redo tracking
│   ├── guest-token.ts                   # Guest token cookie management
│   ├── IndexedDBEmbeddingCache.ts       # Client-side embedding cache
│   ├── pdf-thumbnail-utils.ts           # PDF page canvas thumbnail rendering
│   └── utils.ts                         # Tailwind CSS class merging utilities
│
├── providers/                           # React Context Providers
│   └── ThemeProvider.tsx                # Next-themes dark/light theme wrapper
│
├── public/                              # Public Static Assets
│   ├── favicon.ico, file.svg, globe.svg, icon.png, next.svg, vercel.svg, window.svg
│
├── scripts/                             # Maintenance & Testing Scripts
│   └── test_file_analysis.py            # Local file analyzer sanity script
│
├── server/                              # Server procedures
│   └── trpc/
│       ├── context.ts                   # tRPC context setup with authentication
│       ├── init.ts                      # tRPC router & middleware initialization
│       └── routers/
│           └── project.ts               # Core database-level project procedures
│
├── supabase/                            # Supabase Migrations
│   └── migrations/
│       └── 001_initial_schema.sql       # Baseline PostgreSQL database schema
│
├── trpc/                                # Full Client-Server tRPC Router Collection
│   ├── client.tsx                       # tRPC React Query Client Provider
│   ├── init.ts                          # Client router initialization
│   └── routers/                         # Sub-routers
│       ├── _app.ts                      # Combined AppRouter definition
│       ├── ai.ts                        # AI proxy procedures
│       ├── auth.ts                      # User authentication status
│       ├── comments.ts                  # Document comments & threads
│       ├── dashboard.ts                 # Dashboard metrics & activity
│       ├── invitations.ts               # Project collaboration invites
│       ├── notifications.ts             # Notification center procedures
│       ├── preferences.ts               # User & editor preferences
│       ├── projects.ts                  # Project CRUD & membership
│       ├── settings.ts                  # Application settings
│       ├── synctex.ts                   # SyncTeX lookup proxy procedures
│       ├── templates.ts                 # Template fetching & instantiation
│       └── user.ts                      # User profile operations
│
├── types/                               # TypeScript Type Definitions
│   └── sync.ts                          # SyncTeX coordinate & bounding box types
│
├── uploads/                             # Local disk storage for project files & assets
│   └── projects/<project_id>/           # Safe, isolated project directories
│
├── DOCKER_DEPLOYMENT.md                 # Complete Docker deployment runbook
├── Dockerfile                           # Production Next.js & Python full-stack container
├── Dockerfile.backend                   # Production Python FastAPI backend container
├── docker-compose.yml                   # Docker Compose (Full stack)
├── docker-compose.backend.yml           # Docker Compose (Backend only)
├── deploy.sh                            # Automated deployment script for Linux/Ubuntu
├── entrypoint.sh                        # Container startup script
├── drizzle.config.ts                    # Drizzle ORM configuration
├── eslint.config.mjs                    # ESLint configuration
├── next.config.ts                       # Next.js configuration
├── package.json                         # Node dependencies & build scripts
├── tsconfig.json                        # TypeScript configuration
└── vercel.json                          # Vercel deployment configuration
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
- **Engines Supported**: `latexmk`, `pdflatex`, `xelatex`, `lualatex`.
- **How It Works**:
  1. The client sends a `CompileRequest` containing `latex_code`, `engine`, `project_id`, `images`, and `files` (with base64 payloads).
  2. Request passes through [`backend/rate_limiter.py`](file:///home/abin/overbranch/backend/rate_limiter.py) (60 requests/minute per caller) and Better-Auth / guest authentication.
  3. `compile_queue.py` gates execution with an `asyncio.Semaphore` (default: 4 concurrent compilations) to prevent server overload, returning HTTP 429 with `Retry-After` if the queue depth exceeds limits.
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
|                 │                                                      │           |
|                 └───────────────────────────┬──────────────────────────┘           |
|                                             │                                      |
|                                             ▼                                      |
|                           [Coverage & Leftover Validation]                         |
|                                             │                                      |
|                                             ▼                                      |
|                                  [Final Diff Generation]                           |
|                                             │                                      |
|                                             ▼                                      |
|                               [SSE Stream to AgentReasoning]                       |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py), [`backend/opencode/shadow_workspace.py`](file:///home/abin/overbranch/backend/opencode/shadow_workspace.py), [`backend/opencode/tools.py`](file:///home/abin/overbranch/backend/opencode/tools.py), [`backend/routes/agent_routes.py`](file:///home/abin/overbranch/backend/routes/agent_routes.py), [`components/editor/AgentReasoningWindow.tsx`](file:///home/abin/overbranch/components/editor/AgentReasoningWindow.tsx)
- **Endpoint**: `POST /api/agent/opencode` (Server-Sent Events)
- **Dynamic Step Budgeting**:
  `determine_adaptive_step_budget()` computes the maximum reasoning steps dynamically:
  - Small targeted edits (typos, author changes): **6–8 steps**
  - Standard edits: **12–16 steps**
  - Broad multi-chapter / Full document rewrites: **18–32 steps** based on the number of chapters and content chunks.
- **Workflow & Features**:
  1. **In-Memory Shadow Sandbox**: Edits are applied to `ShadowWorkspace` in memory without writing to disk during reasoning.
  2. **Document Outline Injection**: Injects structural markers (preamble, chapters, sections, Beamer frames) with line numbers directly into the agent prompt via `_build_document_outline()`.
  3. **Conversation Compaction**: Compresses large earlier tool outputs (`read_file_range`, `get_template_theme`) to prevent context window saturation while preserving system instructions.
  4. **Continuation Handling**: Detects truncated JSON responses (`finish_reason == "length"`) and prompts the model to seamlessly complete the payload.
  5. **SSE Streamed Events**:
     - `status`: Step counters, scope notifications, and compilation state.
     - `thought`: Internal ReAct reasoning.
     - `tool_call` & `tool_result`: Exact arguments and return payloads.
     - `compile_error`: TeX diagnostic logs with self-correction retry notices.
     - `coverage_check`: Structural chunk validation metrics.
     - `final_diff`: Line-level differences for [`components/editor/InlineDiffEditor.tsx`](file:///home/abin/overbranch/components/editor/InlineDiffEditor.tsx).

---

### Feature 4: Scope Classification (`TARGETED_EDIT` vs. `FULL_DOCUMENT_REWRITE`) & Structural `rewrite_chunk`

- **File Implementation**: [`backend/scope_classifier.py`](file:///home/abin/overbranch/backend/scope_classifier.py), [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py), [`backend/opencode/tools.py`](file:///home/abin/overbranch/backend/opencode/tools.py)
- **How It Works**:
  1. **Dual-Tier Classification**:
     - **Fast Heuristic Pass**: Regex patterns matching whole-document phrases (e.g. *"entire document"*, *"rewrite everything"*, *"based on new source material"*, *"replace all chapters"*).
     - **LLM Fallback Pass**: For ambiguous requests, classifies scope into `TARGETED_EDIT` or `FULL_DOCUMENT_REWRITE` with forbidden term extraction.
  2. **Structural Document Chunking**:
     - `document_index.py` breaks the document into `DocumentChunk` records (`chunk_id`, `chunk_type`, `title`, `start_offset`, `end_offset`, `start_line`, `end_line`).
  3. **The `rewrite_chunk` Tool**:
     - In `FULL_DOCUMENT_REWRITE` mode, the agent replaces whole sections via `rewrite_chunk(chunk_id, new_content)` using byte offsets rather than character-matching `str_replace`, eliminating substring collision and drift bugs.

---

### Feature 5: Full Document Rewrite Coverage Validation & Leftover Detection

- **File Implementation**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py), [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py)
- **How It Works**:
  1. **Chunk Coverage Tracking**: `ShadowWorkspace` tracks all touched chunk IDs during the editing session.
  2. **Validation on Done**: When the agent signals `done=true` during a full rewrite or broad request:
     - `validate_coverage()` compares the set of touched chunks against all content chunks in the document.
     - Scans the buffer for forbidden leftover keywords from old topics.
  3. **Rejection & Feedback**: If chunks remain untouched (e.g. Chapter 4 and Chapter 5 were skipped), the loop rejects the completion and instructs the model:
     `"Coverage Check Failed: 2/5 chunks edited. Missing chunks: ['chapter_4', 'chapter_5']. Please use rewrite_chunk on these remaining chunks."`

---

### Feature 6: Shadow Compilation & Sandboxed Self-Correction

- **File Implementation**: [`backend/opencode/shadow_compiler.py`](file:///home/abin/overbranch/backend/opencode/shadow_compiler.py), [`backend/compiler.py`](file:///home/abin/overbranch/backend/compiler.py)
- **How It Works**:
  1. **Ephemeral Sandboxed Compile**: When the agent calls `verify_compile`, `shadow_compiler.py` writes the candidate buffer to a temporary directory.
  2. **Compilation Diagnostic Parsing**: If compilation fails, the stderr and `.log` file are parsed for LaTeX error lines (`Undefined control sequence`, `Missing $ inserted`, `File ended while scanning use of \foo`).
  3. **Infrastructure Graceful Fallback**: If the host environment does not have a TeX engine installed, `shadow_compiler.py` returns `infra_skip=True`, allowing the agent to proceed without getting blocked in infinite compilation retry loops.
  4. **Self-Correction Feedback**: Compiler diagnostics are passed back as a `compile_error` event and tool observation, prompting the model to fix the exact line using `str_replace`.

---

### Feature 7: Cross-Stack Better-Auth Authentication & PostgreSQL Session Sharing

- **File Implementation**: [`backend/auth.py`](file:///home/abin/overbranch/backend/auth.py), [`backend/database.py`](file:///home/abin/overbranch/backend/database.py), [`backend/models.py`](file:///home/abin/overbranch/backend/models.py), [`lib/auth.ts`](file:///home/abin/overbranch/lib/auth.ts), [`lib/auth-client.ts`](file:///home/abin/overbranch/lib/auth-client.ts)
- **How It Works**:
  1. Next.js 15 Better-Auth creates session records in PostgreSQL table `session` (`id`, `token`, `user_id`, `expires_at`).
  2. The browser automatically forwards `better-auth.session_token` / `__Secure-better-auth.session_token` cookies or Bearer headers to FastAPI endpoints.
  3. FastAPI unquotes the token, strips signature suffixes (`<token>.<sig>`), and validates it via asynchronous SQLAlchemy queries with connection pooling.
  4. Enforces project access permissions with `verify_project_ownership_or_member()`, verifying that the caller is the owner or an active collaborator in `project_members`.
  5. Interactive Swagger UI (`/docs`) includes full security schemes (API Key Cookie, Bearer Token, Guest Header) with the interactive "Authorize" modal.

---

### Feature 8: Sliding-Window Rate Limiting & Denial-of-Service Defense

- **File Implementation**: [`backend/rate_limiter.py`](file:///home/abin/overbranch/backend/rate_limiter.py), [`backend/main.py`](file:///home/abin/overbranch/backend/main.py), [`backend/routes/agent_routes.py`](file:///home/abin/overbranch/backend/routes/agent_routes.py)
- **How It Works**:
  1. `SlidingWindowRateLimiter` tracks request timestamps inside an in-memory sliding window.
  2. Keyed hierarchically: authenticated `user_id` > guest `session_id` > client IP (`X-Forwarded-For` / `X-Real-IP`).
  3. Endpoints protected:
     - `/api/compile`: 60 req/min
     - `/api/synctex/backward` & `/forward`: 120 req/min
     - `/api/agent/opencode`: 20 req/min
     - `/api/pdf/convert`: 10 req/min
  4. Returns HTTP 429 with standard headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After`.

---

### Feature 9: Curated Template/Theme Registry & Non-Destructive Redesign

- **File Implementation**: [`backend/opencode/template_registry.py`](file:///home/abin/overbranch/backend/opencode/template_registry.py), [`backend/templates/`](file:///home/abin/overbranch/backend/templates/)
- **Themes Available**:
  - `ppt`: `nordlight` (Dark modern teal/orange), `prism` (Vibrant geometric), `regalia` (Royal gold/crimson), `basic` (Madrid custom), `minimalist` (Focus clean).
  - `papers`: `ieee-conference`, `ieee-journal`, `acm-sigconf`, `springer-lncs`.
  - `thesis`: `5-chapter-thesis-report`, `technical-report`.
  - `resume`: `modern-cv`, `deedy-resume`, `developer-cv`.
- **Non-Destructive Redesign Workflow**:
  1. When a user asks: *"Redesign this presentation using the Nordlight theme"*, the agent calls `get_template_theme(category="ppt", theme_name="nordlight", extract_section="preamble")`.
  2. The agent reads the existing preamble with `read_file_range(1, 35)`.
  3. Uses `str_replace` to swap package imports, theme declarations, and color palettes while **strictly preserving** all user frames, equations, tables, and slide contents.

---

### Feature 10: Color Contrast Auto-Diagnostic & Invisible Text Self-Repair

- **File Implementation**: [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py)
- **The Problem**: In Beamer presentations, dark banner backgrounds (e.g. Madrid default dark blue boxes) paired with black text or `\title{\color{black}{...}}` produce unreadable dark-on-dark titles.
- **The Solution**:
  1. When prompts contain visibility keywords (*"title is not visible"*, *"cannot see heading"*, *"dark on dark"*, *"unreadable"*), the system activates the Visibility Diagnostic.
  2. The agent is directed to inspect `\setbeamercolor{title}{bg=..., fg=white}`, `\setbeamercolor{frametitle}{...}`, and remove conflicting embedded `\color{black}` macros.

---

### Feature 11: Document Creation & Conversion Archetypes

- **File Implementation**: [`backend/opencode/agent_loop.py`](file:///home/abin/overbranch/backend/opencode/agent_loop.py)
- **Supported Archetypes**:
  1. **Beamer Presentations**: Standardized to `\documentclass[aspectratio=169]{beamer}`, `metropolis` or `Madrid` theme, plain title slide, outline frame, and structured content slides with maximum 5–6 bullets per frame.
  2. **Multi-Chapter Seminar & Technical Reports**: `\documentclass[11pt,a4paper,oneside]{report}`, formal front matter (Title, Abstract, Table of Contents), and 4–6 numbered chapters with equations and tables.
  3. **IEEE / ACM Research Papers**: `\documentclass[conference]{IEEEtran}` or two-column articles with numbered sections, abstract, keywords, and IEEE-style bibliography.
  4. **Resumes & CVs**: Clean single/two-page layouts with contact header, education, experience, skills, and projects.

---

### Feature 12: Real-Time AI Interruption, Stream Abort & Thread-Safe Cancellation

- **File Implementation**: [`backend/cancellation.py`](file:///home/abin/overbranch/backend/cancellation.py), [`backend/routes/agent_routes.py`](file:///home/abin/overbranch/backend/routes/agent_routes.py), [`components/editor/EditorLayout.tsx`](file:///home/abin/overbranch/components/editor/EditorLayout.tsx)
- **Endpoints**: `POST /api/agent/stop`
- **How It Works**:
  1. When an agent request begins, an `AbortController` is registered on the client and a `CancellationToken` is registered in `cancellation_manager` on the backend.
  2. Clicking "Stop" triggers `abortController.abort()` and sends `POST /api/agent/stop` with `{ request_id, project_id }`.
  3. The backend cancels active LLM network requests, terminates subprocesses, and closes the SSE stream cleanly.

---

### Feature 13: Query Rewriting, Semantic Chunking & Hybrid Vector Retrieval

- **File Implementation**: [`backend/query_rewriter.py`](file:///home/abin/overbranch/backend/query_rewriter.py), [`backend/retriever.py`](file:///home/abin/overbranch/backend/retriever.py)
- **How It Works**:
  1. **Query Expansion**: `rewrite_query()` expands vague user prompts into 1–3 technical LaTeX search queries containing domain-specific macros (`\begin{align}`, `\section`, `\label`).
  2. **Semantic Chunking**: Splits documents along structural boundaries (chapters, sections, frames, floating tables, figures).
  3. **Hybrid Retrieval**: Combines semantic vector similarity with chunk quality weights (`section: 1.0`, `frame: 0.95`, `figure: 0.88`, `preamble: 0.3`).

---

### Feature 14: Structural Document Indexing & Targeted Frame Extraction

- **File Implementation**: [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py)
- **How It Works**:
  1. Parses the document into logical `DocumentChunk` and `PageEntry` units.
  2. Allows surgical extraction of specific Beamer frames or article sections by index, title, or label.
  3. Calculates SHA-256 fingerprints to track modifications per section.

---

### Feature 15: Pre-Output Validation & LIFO Auto-Repair Engine

- **File Implementation**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py)
- **Validation Checks**:
  1. **Environment Balance**: Verifies that every `\begin{env}` has a corresponding `\end{env}`.
  2. **Preamble Protection**: Ensures modifications do not strip `\documentclass` or essential packages.
  3. **LIFO Auto-Repair**: If an LLM response was truncated mid-token, `auto_repair_truncated_latex()` trims dangling commands and closes open environments in Last-In-First-Out order.

---

### Feature 16: Multi-Provider LLM Gateway & Fallback Architecture

- **File Implementation**: [`backend/providers/`](file:///home/abin/overbranch/backend/providers/)
- **Unified Routing (`router.py`)**:
  - **Gemini (`gemini_provider.py`)**: Primary default model family (`gemini-3.7-flash`, `gemini-2.5-pro`) with high throughput and extensive context.
  - **Groq (`groq_provider.py`)**: Ultra-low-latency generation (`llama-3.3-70b-versatile`, `mixtral-8x7b-32768`).
  - **OpenRouter (`openrouter_provider.py`)**: Access to deep reasoning models (`deepseek/deepseek-r1`, `nvidia/llama-3.1-nemotron-70b`).
  - **Custom User API Keys**: Users can enter custom API keys in [`components/editor/ApiSettingsModal.tsx`](file:///home/abin/overbranch/components/editor/ApiSettingsModal.tsx) stored in browser storage.

---

### Feature 17: PDF to Editable LaTeX Conversion Engine (Dashboard & In-Project)

- **File Implementation**: [`backend/routes/pdf_conversion.py`](file:///home/abin/overbranch/backend/routes/pdf_conversion.py), [`backend/services/pdf_parser.py`](file:///home/abin/overbranch/backend/services/pdf_parser.py), [`backend/services/pdf_to_latex.py`](file:///home/abin/overbranch/backend/services/pdf_to_latex.py), [`backend/services/pdf_figure_extractor.py`](file:///home/abin/overbranch/backend/services/pdf_figure_extractor.py), [`backend/services/layout_verifier.py`](file:///home/abin/overbranch/backend/services/layout_verifier.py), [`app/convert/page.tsx`](file:///home/abin/overbranch/app/convert/page.tsx), [`components/dashboard/PDFToLatexModal.tsx`](file:///home/abin/overbranch/components/dashboard/PDFToLatexModal.tsx)
- **Endpoints**:
  - `POST /api/pdf/convert`: Converts an uploaded PDF into a new project with real-time SSE progress streaming.
  - `POST /api/pdf/convert-in-project`: Ingests a PDF directly into an active project's `assets/` directory and updates `main.tex`.
- **How It Works**:
  1. Parses geometry, fonts, images, and math layout.
  2. Extracts figures into `assets/` and writes clean `\includegraphics` commands.
  3. Analyzes vertical layout drift to mirror original formatting.
  4. Emits real-time SSE progress steps (`analyzing`, `extracting_assets`, `synthesizing_latex`, `done`).

---

### Feature 18: Guest Conversion Session, Quota Enforcement & Auto-Migration

- **File Implementation**: [`backend/routes/guest_pdf.py`](file:///home/abin/overbranch/backend/routes/guest_pdf.py), [`backend/services/guest_identity.py`](file:///home/abin/overbranch/backend/services/guest_identity.py), [`backend/services/guest_quota.py`](file:///home/abin/overbranch/backend/services/guest_quota.py), [`backend/services/guest_migrator.py`](file:///home/abin/overbranch/backend/services/guest_migrator.py), [`backend/services/guest_cleanup.py`](file:///home/abin/overbranch/backend/services/guest_cleanup.py), [`components/GuestMigrationListener.tsx`](file:///home/abin/overbranch/components/GuestMigrationListener.tsx)
- **Guest Flow**:
  1. Unregistered users can convert PDFs on `/convert` or via the dashboard modal.
  2. An HMAC-signed token (`ob_guest_token`) is issued with a 24-hour expiration.
  3. `guest_quota.py` limits guests to 2 conversions per rolling 24-hour window.
  4. Scheduled background daemon (`guest_cleanup.py`) runs every 15 minutes to purge expired guest projects.
  5. When a guest registers or signs in, `GuestMigrationListener` invokes `POST /api/guest/migrate` to transfer all guest projects to the user account.

---

### Feature 19: Multimodal AI File Analyzer & TikZ Synthesizer

- **File Implementation**: [`backend/file_analyzer.py`](file:///home/abin/overbranch/backend/file_analyzer.py), [`components/editor/FileAnalyzerModal.tsx`](file:///home/abin/overbranch/components/editor/FileAnalyzerModal.tsx), [`lib/ai-file-analysis.ts`](file:///home/abin/overbranch/lib/ai-file-analysis.ts)
- **Endpoint**: `POST /api/analyze-file`
- **Supported Formats**: Images (`.png`, `.jpg`, `.webp`), Data (`.csv`, `.json`), Documents (`.pdf`, `.txt`, `.md`), Code (`.py`, `.tex`, `.ts`), Audio (`.mp3`, `.wav`).
- **How It Works**:
  1. Upload data files, charts, or images in the editor.
  2. The analyzer generates PGFPlots / TikZ code, tabular data representations, or multimodal summaries with one-click injection into `main.tex`.

---

### Feature 20: Collaborative Project Management & Role-Based Access

- **File Implementation**: [`db/schema.ts`](file:///home/abin/overbranch/db/schema.ts), [`trpc/routers/projects.ts`](file:///home/abin/overbranch/trpc/routers/projects.ts), [`trpc/routers/invitations.ts`](file:///home/abin/overbranch/trpc/routers/invitations.ts), [`trpc/routers/comments.ts`](file:///home/abin/overbranch/trpc/routers/comments.ts), [`components/editor/CollaboratorAvatars.tsx`](file:///home/abin/overbranch/components/editor/CollaboratorAvatars.tsx), [`components/dashboard/NotificationsPopover.tsx`](file:///home/abin/overbranch/components/dashboard/NotificationsPopover.tsx)
- **Roles**: `Owner`, `Editor`, `Viewer`.
- **Workflow**:
  1. Project owner sends email invitations via `trpc.invitations.sendInvite`.
  2. Notifications are displayed in the in-app notification popover.
  3. Accepting adds the user to `project_members`, granting real-time access.

---

### Feature 21: Inline Diff Editor & Edit History Tracking

- **File Implementation**: [`components/editor/InlineDiffEditor.tsx`](file:///home/abin/overbranch/components/editor/InlineDiffEditor.tsx), [`components/DiffWidget.tsx`](file:///home/abin/overbranch/components/DiffWidget.tsx), [`lib/EditHistoryStore.ts`](file:///home/abin/overbranch/lib/EditHistoryStore.ts)
- **How It Works**:
  1. AI proposals are rendered in `InlineDiffEditor.tsx` with split or unified diff views.
  2. **Accept**: Applies changes to `main.tex` and triggers compilation.
  3. **Reject**: Discards proposals and restores previous buffer.
  4. `EditHistoryStore.ts` persists full revision snapshots in browser `localStorage`.

---

### Feature 22: Presentation View Mode (Beamer Decks)

- **File Implementation**: [`components/editor/PresentationView.tsx`](file:///home/abin/overbranch/components/editor/PresentationView.tsx)
- **How It Works**:
  1. Fullscreen presentation environment for Beamer slide decks.
  2. Supports keyboard navigation (Arrow keys, Space, Esc), laser pointer overlay mode, and slide thumbnail drawer.

---

### Feature 23: LaTeX Template Gallery & Dynamic Cloning

- **File Implementation**: [`backend/template_service.py`](file:///home/abin/overbranch/backend/template_service.py), [`backend/templates/`](file:///home/abin/overbranch/backend/templates/), [`app/(dashboard)/templates/page.tsx`](file:///home/abin/overbranch/app/(dashboard)/templates/page.tsx), [`trpc/routers/templates.ts`](file:///home/abin/overbranch/trpc/routers/templates.ts)
- **Categories**: Papers (IEEE, ACM, Springer), Presentations (Beamer themes), Resumes/CVs, Master/PhD Theses, Assignments, Technical Reports.
- **Cloning**: One-click cloning instantiates project source files, styles (`.cls`, `.sty`), and assets into a new user project.

---

### Feature 24: Design System ("Celestial Obsidian & Luminescent Iris") & Theming Engine

- **File Implementation**: [`app/globals.css`](file:///home/abin/overbranch/app/globals.css), [`components/editor/EditorThemeModal.tsx`](file:///home/abin/overbranch/components/editor/EditorThemeModal.tsx), [`trpc/routers/preferences.ts`](file:///home/abin/overbranch/trpc/routers/preferences.ts)
- **Design System ("Celestial Obsidian & Luminescent Iris")**:
  - Deep Obsidian background (`oklch(0.12 0.012 260)`), Luminescent Iris accent (`oklch(0.65 0.22 265)`), crisp white text (`oklch(0.98 0 0)`), and semantic status colors.
  - Display typography in **Archivo Black**, body text in **Inter**, code in **Space Mono**.
- **User Configurable Parameters**:
  - Themes (VS Code Dark, GitHub Light, Nord, Dracula, Monokai, Cyberpunk), font sizes, tab sizes, soft wrap, and auto-compile triggers synchronized to PostgreSQL `editor_preferences`.

---

### Feature 25: Structured Observability, Tracing & Performance Telemetry

- **File Implementation**: [`backend/trace.py`](file:///home/abin/overbranch/backend/trace.py)
- **Features**:
  - `AgentTrace`: Captures trace ID, task classification, nodes touched, tool call latencies, validation results, shadow compilation diagnostics, and model token usage.
  - `ConversionTrace`: Tracks PDF page counts, fidelity scores, OCR latencies, and layout verification metrics.
  - Telemetry is formatted as JSON to stdout and saved to rotating project log directories under `/tmp/overbranch_traces/`.

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
| `GEMINI_API_KEY` | Backend LLM | Google GenAI / Gemini Web2API key |
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
