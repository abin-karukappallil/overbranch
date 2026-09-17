# OverBranch — Comprehensive Method, Architecture & Feature Guide

> **OverBranch** is a 100% free and open-source agentic LaTeX code editor and research environment. Built for students, academics, and scientific authors, it combines lightning-fast compilation, an intelligent RAG-driven AI copilot router, bidirectional SyncTeX synchronization, PDF-to-LaTeX conversion, shadow compilation with self-correction, in-memory symbol indexing, and multi-user collaboration.

---

## Table of Contents

1. [High-Level Methodology & System Architecture](#1-high-level-methodology--system-architecture)
   - [Architectural Overview](#architectural-overview)
   - [Core Methodological Pipelines](#core-methodological-pipelines)
     - [A. Bounded ReAct Agent Loop & Multi-Step Reasoning](#a-bounded-react-agent-loop--multi-step-reasoning)
     - [B. Shadow Compilation & Self-Correction Pipeline](#b-shadow-compilation--self-correction-pipeline)
     - [C. In-Memory Symbol Indexing & Cross-Reference Validation](#c-in-memory-symbol-indexing--cross-reference-validation)
     - [D. Fast Query Rewriting & Hybrid Vector RAG](#d-fast-query-rewriting--hybrid-vector-rag)
     - [E. LaTeX Compilation & Resilient Fallback Pipeline](#e-latex-compilation--resilient-fallback-pipeline)
     - [F. Structural Document Parsing & Page Indexing](#f-structural-document-parsing--page-indexing)
     - [G. Pre-Output Validation & LIFO Auto-Repair](#g-pre-output-validation--lifo-auto-repair)
     - [H. PDF-to-LaTeX Ingestion & Guest Migration Lifecycle](#h-pdf-to-latex-ingestion--guest-migration-lifecycle)
     - [I. SyncTeX Bidirectional Navigation](#i-synctex-bidirectional-navigation)
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
   - [Feature 1: Real-Time LaTeX Compilation & ReportLab Fallback](#feature-1-real-time-latex-compilation--reportlab-fallback)
   - [Feature 2: Bidirectional SyncTeX Navigation (Forward & Backward)](#feature-2-bidirectional-synctex-navigation-forward--backward)
   - [Feature 3: Bounded ReAct Agent Loop & Dual Modes (`Ask` vs. `Edit`)](#feature-3-bounded-react-agent-loop--dual-modes-ask-vs-edit)
   - [Feature 4: Shadow Compilation & Compiler-Feedback Self-Correction](#feature-4-shadow-compilation--compiler-feedback-self-correction)
   - [Feature 5: In-Memory Symbol Indexing & Dangling Reference Validation](#feature-5-in-memory-symbol-indexing--dangling-reference-validation)
   - [Feature 6: Query Rewriting, Semantic Chunking & Hybrid Vector Retrieval](#feature-6-query-rewriting-semantic-chunking--hybrid-vector-retrieval)
   - [Feature 7: Structural Document Indexing & Targeted Frame Extraction](#feature-7-structural-document-indexing--targeted-frame-extraction)
   - [Feature 8: Pre-Output Validation & LIFO Auto-Repair Engine](#feature-8-pre-output-validation--lifo-auto-repair-engine)
   - [Feature 9: Multi-Provider LLM Gateway & Fallback Architecture](#feature-9-multi-provider-llm-gateway--fallback-architecture)
   - [Feature 10: PDF to Editable LaTeX Conversion Engine (Dashboard & In-Project)](#feature-10-pdf-to-editable-latex-conversion-engine-dashboard--in-project)
   - [Feature 11: Guest Conversion Session, Quota Enforcement & Auto-Migration](#feature-11-guest-conversion-session-quota-enforcement--auto-migration)
   - [Feature 12: Multimodal AI File Analyzer & TikZ Synthesizer](#feature-12-multimodal-ai-file-analyzer--tikz-synthesizer)
   - [Feature 13: Collaborative Project Management & Role-Based Access](#feature-13-collaborative-project-management--role-based-access)
   - [Feature 14: Inline Diff Editor & Edit History Tracking](#feature-14-inline-diff-editor--edit-history-tracking)
   - [Feature 15: Presentation View Mode (Beamer Decks)](#feature-15-presentation-view-mode-beamer-decks)
   - [Feature 16: LaTeX Template Gallery & Dynamic Cloning](#feature-16-latex-template-gallery--dynamic-cloning)
   - [Feature 17: Design System ("Celestial Obsidian & Luminescent Iris") & Theming Engine](#feature-17-design-system-celestial-obsidian--luminescent-iris--theming-engine)
4. [Deployment, Infrastructure & Environment Configuration](#4-deployment-infrastructure--environment-configuration)

---

# 1. High-Level Methodology & System Architecture

### Architectural Overview

OverBranch adopts a decoupled, micro-service-inspired architecture designed for high responsiveness, complete local isolation, and fault tolerance:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND CLIENT (Next.js 15)                    │
│  - App Router, React 19, TypeScript, Tailwind CSS, Lucide Icons        │
│  - Monaco LaTeX Editor with syntax highlighting and SyncTeX markers    │
│  - Custom PDF Viewer (PDF.js / Iframe / SyncTeX click handlers)        │
│  - Presentation Deck Player (Beamer slide rendering)                   │
│  - Diff Viewer (Side-by-side & Unified diff widgets)                   │
│  - Agent Reasoning Window (Real-time ReAct loop step visualizer)       │
└──────────────────┬───────────────────────────────┬─────────────────────┘
                   │                               │
       tRPC / Better-Auth (Next API)        HTTP / SSE / REST
                   │                               │
┌──────────────────▼──────────────┐   ┌────────────▼─────────────────────┐
│    DATABASE & AUTH SERVICE      │   │     FASTAPI PYTHON ENGINE        │
│  - PostgreSQL via Drizzle ORM   │   │  - Port 8000                     │
│  - Supabase Database Storage    │   │  - Uvicorn / AsyncIO             │
│  - Better-Auth Session Tokens   │   │  - ReAct Agent Loop & Router     │
│  - Project & Invitation Schema  │   │  - Shadow Compiler & Auto-Repair │
│  - Collaboration & Comments     │   │  - Symbol Index & Cross-Refs     │
└─────────────────────────────────┘   │  - Qdrant Hybrid RAG & Rewriter  │
                                      │  - PDF to LaTeX OCR / Parser     │
                                      │  - Multimodal File Analyzer      │
                                      │  - SyncTeX Forward/Backward View │
                                      └──────────────────────────────────┘
```

---

### Core Methodological Pipelines

#### A. OpenCode-Style Agentic Pipeline & Exact-Match Tool Suite
1. **Interactive Tool Loop**: `opencode/agent_loop.py` executes an iterative ReAct cycle with dynamic adaptive step budgeting (6 to 32 steps) operating on an in-memory `ShadowWorkspace`.
2. **Deterministic Tool Suite**:
   - `read_file_range`: Reads exact line-numbered contents without hallucinated drift.
   - `grep_search`: Finds structural anchors (`\chapter`, `\section`, `\begin{frame}`, `\label`, `\cite`).
   - `str_replace`: Performs strict character-for-character replacements with zero spatial drift.
   - `list_assets`: Discovers available images/PDFs in `assets/` for `\includegraphics`.
   - `verify_compile`: Triggers sandboxed compilation to capture compiler diagnostics.
   - `get_template_theme`: Retrieves curated themes (Beamer PPT themes, IEEE conference/journal papers, 5-chapter thesis reports, resumes/CVs, formal letters, lab assignments) and extracts styling preambles for non-destructive document redesigns.
3. **SSE Event Streaming**: Streams real-time reasoning (`thought`, `tool_call`, `tool_result`, `compile_error`, `final_diff`) to `AgentReasoningWindow.tsx` and `InlineDiffEditor.tsx`.

#### B. Shadow Compilation & Self-Correction Pipeline
1. **In-Memory Shadow Sandbox**: `opencode/shadow_workspace.py` maintains an isolated buffer; edits never touch disk during reasoning.
2. **Ephemeral Verification**: `opencode/shadow_compiler.py` runs fast compilation tests (`pdflatex`, `xelatex`, or ReportLab fallback).
3. **Compiler Feedback**: Offending TeX macros and line numbers are fed back into the agent loop for self-correction.

#### C. In-Memory Symbol Indexing & Cross-Reference Validation
1. **AST Symbol Scraping**: `symbol_index.py` extracts all `\label`, `\ref`, `\eqref`, `\autoref`, `\cref`, `\cite`, `\bibitem`, `\newcommand`, `\def`, and section declarations into an indexed symbol table.
2. **Instant Lookup**: Provides $O(1)$ verification for cross-reference consistency across multi-file LaTeX projects.
3. **Dangling Reference Prevention**: Detects orphan `\ref` calls or missing bibliography keys before finalizing AI-generated code.

#### D. Fast Query Rewriting & Hybrid Vector RAG
1. **Query Expansion**: `query_rewriter.py` expands vague or conversational user prompts (e.g., *"add the baseline table"*) into 1–3 targeted technical search queries containing domain-specific LaTeX terms.
2. **Boundary-Aware Chunking**: `chunker.py` splits documents along grammatical boundaries: `\section`, `\subsection`, `\begin{frame}`, mathematical blocks (`align`, `equation`), floating tables, and figures.
3. **Quality Weighting**: Each chunk is assigned a categorical weight (`section: 1.0`, `frame: 0.95`, `figure: 0.88`, `paragraph: 0.6`, `preamble: 0.3`).
4. **Vector Persistence**: Embeddings generated via `NVIDIAEmbeddings` (`NV-Embed-QA`) or OpenAI embeddings are stored in a **Qdrant** collection (`overbranch_latex_chunks`).
5. **Hybrid Retrieval**: `retriever.py` queries Qdrant with hybrid scoring combining semantic vector similarity with chunk quality weights.

#### E. LaTeX Compilation & Resilient Fallback Pipeline
1. **Source Bundling**: The frontend packages the active `.tex` document, referenced images (as base64 or project asset filenames), auxiliary files (`.bib`, `.sty`, `.cls`), and requested TeX engine (`latexmk`, `pdflatex`, `xelatex`, `lualatex`).
2. **Execution Isolation**: The backend spawns a secure temporary directory (`tempfile.mkdtemp()`), copies root templates and packages, decodes assets to disk, and executes the compilation command with timeouts.
3. **Artifact Caching & SyncTeX Extraction**: If compilation succeeds, the resultant `main.pdf` and `main.synctex.gz` are stored in `/tmp/overbranch_synctex_cache/<project_id>/` for fast bidirectional lookup.
4. **Resilient ReportLab Fallback**: If no LaTeX engine is installed on the host system (e.g. lightweight Docker deployment or developer laptop without TeXLive), `compiler.py` engages an intelligent ReportLab synthetic generator that strips TeX control sequences, identifies Beamer frames or article sections, and builds a matching PDF document.

#### F. Structural Document Parsing & Page Indexing
1. **DocumentIndex Engine**: `document_index.py` constructs an in-memory structural representation of the document, mapping every slide or section to a stable `page_id`, offsets (`start_offset`, `end_offset`), and SHA-256 fingerprint.
2. **Targeted Slide Retrieval**: When editing Beamer presentations, the system can isolate the exact frame being discussed by matching frame titles, labels, or ordinal slide numbers, preventing hallucinations outside the target slide.

#### G. Pre-Output Validation & LIFO Auto-Repair
1. **Pre-Output Validation**: `edit_validator.py` executes AST-style regex passes to ensure:
   - No duplicate slide IDs or `\label{...}` collisions.
   - Proper balance of LaTeX environments (`\begin{...}` / `\end{...}`).
   - Non-destruction of the document preamble.
2. **LIFO Auto-Repair**: If an LLM response was truncated mid-token, `auto_repair_truncated_latex()` trims dangling commands and closes open environments in Last-In-First-Out order, guaranteeing valid syntax.

#### H. PDF-to-LaTeX Ingestion & Guest Migration Lifecycle
1. **Multimodal Deconstruction**: Uploaded PDFs (academic papers, lecture slides, assignments) are parsed via `pdf_parser.py` (using `pypdf` or `PyMuPDF`) to extract text layout, tabular bounding boxes, and images.
2. **Figure Extraction**: `pdf_figure_extractor.py` extracts embedded raster/vector images directly into the project's `assets/` directory, parsing multi-line and plural captions while guarding against raw PDF path leaks in `\includegraphics{...}`.
3. **Positional Drift Calibration**: `layout_verifier.py` measures vertical drift between original PDF pages and generated TeX rendering, calibrating `\vspace` and geometry to mirror original layout fidelity.
4. **Guest Session Protection**: Unauthenticated users are granted access through browser device fingerprinting and signed HMAC guest cookies (`guest_identity.py`). Quotas (e.g., 2 conversions per 24 hours) are checked against Postgres before processing.
5. **Transparent Migration**: When a guest signs up or logs in, `GuestMigrationListener` invokes `/api/guest/migrate`, reassigning all guest projects to the authenticated user ID.

#### I. SyncTeX Bidirectional Navigation
- **Forward Lookup**: Placing the cursor at line $L$ in `main.tex` executes `synctex view`, mapping the source code line to the exact PDF page, $x$, and $y$ coordinate, scrolling the PDF viewer automatically.
- **Backward Lookup**: Clicking an equation or paragraph inside the PDF viewer translates the click point $(page, x, y)$ back into the corresponding source filename, line number, and column.

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
│   ├── providers/                       # Multi-Provider LLM Gateway
│   │   ├── __init__.py                  # Package exports
│   │   ├── base_provider.py             # Abstract LLMProvider base class
│   │   ├── gemini_provider.py           # Gemini Web2API / Google GenAI adapter
│   │   ├── groq_provider.py             # High-speed Groq inference adapter
│   │   ├── openrouter_provider.py       # OpenRouter models adapter
│   │   └── router.py                    # ProviderRouter (Model dispatch & registry)
│   ├── routes/                          # Modular FastAPI Routers
│   │   ├── __init__.py
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
│   │   ├── papers/                      # Research Paper templates (IEEE, ACM, Springer)
│   │   ├── ppt/                         # Beamer presentation themes
│   │   ├── reports/                     # Laboratory & Technical reports
│   │   ├── resume/                      # Resumes & CV templates (ModernCV, Deedy, DeveloperCV)
│   │   └── thesis/                      # Master & PhD Thesis templates
│   ├── tests/                           # Pytest Test Suite
│   │   ├── test_agent_loop_and_shadow.py
│   │   ├── test_cancellation.py
│   │   ├── test_collections_and_anchors.py
│   │   ├── test_guest_identity.py
│   │   ├── test_guest_migrator.py
│   │   ├── test_guest_quota.py
│   │   ├── test_guest_routes.py
│   │   ├── test_hybrid_retrieval.py
│   │   ├── test_missing_images_and_no_fallback.py
│   │   ├── test_pdf_figure_extractor.py
│   │   ├── test_pdf_to_latex.py
│   │   ├── test_smart_addition_positioning.py
│   │   └── test_smart_targeting_and_repairs.py
│   ├── opencode/                        # OpenCode-Style Agentic Pipeline (Exact-Match Shadow Buffer)
│   │   ├── __init__.py                  # Package exports
│   │   ├── agent_loop.py                # ReAct agent loop with exact-match tools
│   │   ├── diff_generator.py            # Line-level diff generator for InlineDiffEditor
│   │   ├── shadow_compiler.py           # Sandboxed compiler verification wrapper
│   │   ├── shadow_workspace.py          # Thread-safe in-memory shadow buffer
│   │   ├── tools.py                     # Tool suite (read_file_range, grep_search, str_replace, etc.)
│   │   └── tests/                       # OpenCode pipeline unit tests
│   ├── routes/                          # FastAPI Route modules
│   │   ├── agent_routes.py              # OpenCode pipeline SSE endpoint (POST /api/agent/opencode)
│   │   ├── guest_pdf.py                 # Guest PDF conversion routes
│   │   └── pdf_conversion.py            # PDF conversion routes
│   ├── agent.py                         # Legacy Agent Router & orchestration endpoint
│   ├── agent_loop.py                    # Legacy Bounded ReAct Agent Loop & multi-step tool caller
│   ├── cancellation.py                  # Thread-safe cancellation tokens & HTTP stream abort manager
│   ├── chunker.py                       # Structural LaTeX chunker with metadata
│   ├── compiler.py                      # TeX Engine compiler & ReportLab fallback
│   ├── context_builder.py               # Token-budgeted context assembler
│   ├── document_index.py                # Page/Frame parser, slide/topic indexer & slide deletion
│   ├── edit_validator.py                # Pre-output LaTeX validator, AST regex rules & auto-repair
│   ├── file_analyzer.py                 # Multimodal AI analysis for uploaded files
│   ├── main.py                          # FastAPI entry point & CORS configuration
│   ├── memory.py                        # Conversation & project memory (LRU store)
│   ├── project_storage.py               # File system disk operations & Supabase storage
│   ├── prompt_builder.py                # System prompt generator for LLMs
│   ├── query_rewriter.py                # Fast multi-query expansion for hybrid search
│   ├── retriever.py                     # Vector & structural retriever
│   ├── shadow_compiler.py               # Shadow compilation & compiler-feedback self-correction
│   ├── symbol_index.py                  # In-memory symbol indexing & cross-reference lookup
│   ├── synctex_service.py               # Forward & backward SyncTeX locator
│   ├── template_service.py              # Template metadata & thumbnail server
│   ├── tools.py                         # LangChain tool definitions (edit, create, delete, search)
│   ├── vector_sync.py                   # Qdrant client & vector sync endpoints
│   ├── Dockerfile                       # Backend standalone container build
│   └── requirements.txt                 # Python dependencies
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
│   │   ├── EditorLayout.tsx             # Master resizable split-pane editor shell
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
│   ├── ui/                              # 26 Radix UI / Shadcn base components
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
├── design.md                            # Canonical design system specification ("Celestial Obsidian")
├── linear-design.md                     # Linear-inspired UI design guide
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

### Feature 1: Real-Time LaTeX Compilation & ReportLab Fallback

```
+--------------------------------------------------------------------------------+
|                             COMPILATION WORKFLOW                               |
|                                                                                |
|  [Editor Code + Assets] ---> POST /api/compile                                 |
|                                     │                                          |
|                       Is TeX engine installed?                                 |
|                       ├── YES: Run latexmk / pdflatex (with synctex=1)         |
|                       │        ├── Success: Output PDF + Save SyncTeX Artifacts|
|                       │        └── Failure: Extract errors from .log file      |
|                       └── NO : Trigger ReportLab Fallback Generator            |
|                                ├── Parse Beamer frames -> Landscape Slides     |
|                                └── Parse Sections     -> Portrait Document     |
+--------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/compiler.py`](file:///home/abin/overbranch/backend/compiler.py), [`backend/main.py`](file:///home/abin/overbranch/backend/main.py), [`components/editor/CompileToolbar.tsx`](file:///home/abin/overbranch/components/editor/CompileToolbar.tsx)
- **Engines Supported**: `latexmk`, `pdflatex`, `xelatex`, `lualatex`.
- **How It Works**:
  1. The client sends a `CompileRequest` with `latex_code`, `engine`, `project_id`, and lists of `images` and `files` (with base64 payloads).
  2. `compiler.py` creates a temporary sandbox folder via `tempfile.TemporaryDirectory()`.
  3. All project assets and subdirectories are written to disk using `write_file_safely()`, which guards against directory traversal attacks.
  4. Path augmentation is run via `augment_path_for_latex()`, locating MiKTeX or TeXLive binaries across Linux and Windows environments.
  5. If `latexmk` or `pdflatex` is detected:
     - Subprocess is spawned: `["latexmk", "-pdf", "-interaction=nonstopmode", "-synctex=1", "main.tex"]`
     - Compilation artifacts (`.pdf`, `.log`, `.synctex.gz`) are collected.
     - SyncTeX artifacts are persisted to `/tmp/overbranch_synctex_cache/<project_id>/` for fast querying.
     - Output PDF is base64-encoded and returned with compilation logs and elapsed runtime.
  6. If no TeX engine exists on the host machine:
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

### Feature 3: Bounded ReAct Agent Loop & Dual Modes (`Ask` vs. `Edit`)

```
+------------------------------------------------------------------------------------+
|                             BOUNDED REACT AGENT LOOP                               |
|                                                                                    |
|  User Prompt ──► [Query Rewriter] ──► [Multi-Step Reasoning Loop (Max 8 Steps)]    |
|                                             │                                      |
|                 ┌───────────────────────────┴──────────────────────────┐           |
|                 ▼                                                      ▼           |
|       [Inspection Tools]                                       [Action Tools]      |
|       - search_document                                        - edit_chunk        |
|       - read_chunk                                             - create_content    |
|       - check_label_exists                                     - delete_chunk      |
|       - get_compile_errors                                     - insert_after      |
|       - run_validator                                          - insert_relative   |
|                 │                                                      │           |
|                 └───────────────────────────┬──────────────────────────┘           |
|                                             │                                      |
|                                             ▼                                      |
|                             [Shadow Compile & Self-Correct]                        |
|                                             │                                      |
|                                             ▼                                      |
|                             [Stream to AgentReasoningWindow]                       |
+------------------------------------------------------------------------------------+
```

- **File Implementation**:
  - **OpenCode Pipeline (Recommended)**: [`backend/opencode/`](file:///home/abin/overbranch/backend/opencode/) (`shadow_workspace.py`, `agent_loop.py`, `tools.py`, `diff_generator.py`, `shadow_compiler.py`), [`backend/routes/agent_routes.py`](file:///home/abin/overbranch/backend/routes/agent_routes.py)
  - **Legacy RAG Pipeline**: [`backend/agent_loop.py`](file:///home/abin/overbranch/backend/agent_loop.py), [`backend/agent.py`](file:///home/abin/overbranch/backend/agent.py)
  - **Cancellation**: [`backend/cancellation.py`](file:///home/abin/overbranch/backend/cancellation.py)
  - **Frontend UI**: [`components/editor/AgentReasoningWindow.tsx`](file:///home/abin/overbranch/components/editor/AgentReasoningWindow.tsx), [`components/editor/InlineDiffEditor.tsx`](file:///home/abin/overbranch/components/editor/InlineDiffEditor.tsx)
- **Endpoints**:
  - `POST /api/agent/opencode` — OpenCode Exact-Match Shadow Workspace Agent with real-time SSE streaming.
  - `POST /api/agent/chat` — Legacy semantic chunking & RAG agent endpoint (maintained for backwards compatibility).
- **OpenCode Agent Architecture**:
  1. **In-Memory Shadow Workspace**: The user's `main.tex` is held in an in-memory buffer (`ShadowWorkspace`). All edits operate on this buffer without touching disk.
  2. **Exact-Match Tool Suite**:
     - `read_file_range`: Read line-numbered slices (`1: \documentclass...`).
     - `grep_search`: Regex or literal pattern matching with line numbers.
     - `str_replace`: Verbatim character-for-character replacement (strictly rejects hallucinated strings and ambiguous matches).
     - `list_assets`: Inspect figures and images in `assets/` for `\includegraphics`.
     - `verify_compile`: Sandboxed compilation to check for TeX errors and self-correct.
  3. **Line-Level Diff Generation**: `diff_generator.py` uses `difflib.SequenceMatcher` to compute the `final_diff` payload and `EditItem[]` for direct consumption by the frontend `InlineDiffEditor`.
  4. **Thread-Safe Cancellation**: Supported via `cancellation.py` (`CancellationManager` & `CancellationToken`) with active client disconnect monitoring.

---

### Feature 4: Shadow Compilation & Compiler-Feedback Self-Correction

- **File Implementation**: [`backend/shadow_compiler.py`](file:///home/abin/overbranch/backend/shadow_compiler.py)
- **How It Works**:
  1. **In-Memory Diff Application**: `apply_candidate_edits()` applies proposed chunks against the document in memory, producing a temporary candidate code buffer.
  2. **Non-Blocking Compile Test**: `shadow_compile_candidate()` triggers an ephemeral compilation in a background thread.
  3. **Log Diagnostic Parsing**: Extracts TeX error messages (e.g. `Undefined control sequence \foo`, `Missing $ inserted`) and maps them to line numbers.
  4. **Self-Correction Retry**: If the candidate fails to compile, `self_correct_edits()` sends the compiler diagnostic back to the LLM with instructions to repair the exact syntax error (up to `SHADOW_COMPILE_MAX_RETRIES` times) before returning the diff to the client.

---

### Feature 5: In-Memory Symbol Indexing & Dangling Reference Validation

- **File Implementation**: [`backend/symbol_index.py`](file:///home/abin/overbranch/backend/symbol_index.py)
- **How It Works**:
  1. **Symbol Scraping**: Scans document source code for:
     - Labels: `\label{key}`
     - References: `\ref{key}`, `\eqref{key}`, `\autoref{key}`, `\cref{key}`
     - Citations: `\cite{key}`, `\citep{key}`, `\citet{key}`, `\bibitem{key}`
     - Macros: `\newcommand{\name}`, `\def\name`
  2. **Symbol Table Maintenance**: Constructs an in-memory `SymbolIndex` tracking definition locations, chunk indices, and line numbers.
  3. **Dangling Detection**: `get_dangling_refs()` identifies broken references before code is compiled or saved.
  4. **Tool Integration**: Powers the agent loop's `check_label_exists` tool so the AI never references non-existent labels.

---

### Feature 6: Query Rewriting, Semantic Chunking & Hybrid Vector Retrieval

- **File Implementation**: [`backend/query_rewriter.py`](file:///home/abin/overbranch/backend/query_rewriter.py), [`backend/chunker.py`](file:///home/abin/overbranch/backend/chunker.py), [`backend/vector_sync.py`](file:///home/abin/overbranch/backend/vector_sync.py), [`backend/retriever.py`](file:///home/abin/overbranch/backend/retriever.py)
- **Fast Query Rewriting**:
  - `rewrite_query()` expands natural language prompts into 1–3 specific LaTeX search strings using ultra-fast LLM inference (Groq / Gemini) with fallback to rule-based keyword heuristics (`_heuristic_expand`).
- **Semantic Chunking**:
  - `chunker.py` splits documents along LaTeX boundaries: sections, frames, floating figures, tables, math environments (`align`, `equation`), and bibliographies.
  - Generates rich metadata: `chunk_type`, `section_title`, `char_start`, `char_end`, and clean textual summaries.
- **Qdrant Vector Storage**:
  - Embeddings created with `NVIDIAEmbeddings` (`NV-Embed-QA`) or OpenAI embeddings.
  - Stored in Qdrant collection `overbranch_latex_chunks` with `project_id` tenant isolation.
- **Hybrid Retrieval**:
  - Combines dense vector similarity with keyword BM25 filtering and categorical quality multipliers (`CHUNK_TYPE_WEIGHTS`).

---

### Feature 7: Structural Document Indexing & Targeted Frame Extraction

- **File Implementation**: [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py)
- **The Problem**: Passing a 40-page LaTeX paper or a 50-slide Beamer presentation into an LLM exceeds context limits and causes hallucinations or unwanted edits to unrelated sections.
- **The Method**:
  1. `document_index.py` inspects the document AST and splits it into logical `PageEntry` units:
     - For Beamer: Parses every `\begin{frame}...\end{frame}` block.
     - For Articles: Parses `\section{...}` and `\subsection{...}` hierarchies.
  2. **Multi-Criterion Targeting**:
     - **Slide Number**: Direct targeting by slide index (e.g. Slide 3).
     - **Position**: Relative positioning (`start`, `middle`, `end`).
     - **Topic / Label**: Semantic matching on section headings, frame titles, and `\label{...}` entries.
  3. **Instant Slide Operations**: Supports surgical operations such as instant slide deletion and slide movement directly in the document structural index.
  4. Computes SHA-256 hashes for each slide to detect modifications.
  5. When a user asks: *"Change the formula on the methodology slide"*, the indexer locates the exact slide, allowing `context_builder.py` to supply only that slide and its neighboring context to the LLM.

---

### Feature 8: Pre-Output Validation & LIFO Auto-Repair Engine

- **File Implementation**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py), [`backend/agent.py`](file:///home/abin/overbranch/backend/agent.py)
- **Validation Checks**:
  1. **Duplicate Slide / Label Check**: Verifies that new or modified frames do not introduce duplicate `\label{...}` entries or identical frame titles.
  2. **Environment Balance & AST Validation**: Checks that all `\begin{env}` tags have matching `\end{env}` tags.
  3. **Preamble Protection & Scope Lock**: Ensures modifications do not accidentally strip `\documentclass`, essential packages, or custom macro definitions, locking edits strictly to requested target boundaries.
  4. **Content-Fill Validation**: Validates insertion points and target slots before applying generated code changes.
- **LIFO Auto-Repair**:
  - If a model reaches its token cap and cuts off mid-sentence, `auto_repair_truncated_latex()`:
    - Strips dangling fragments (e.g. trailing `\item \textbf{`).
    - Uses an environment stack to close all remaining unclosed environments in LIFO order.
    - Appends `\end{document}` if the document was left open, ensuring the code compiles successfully.

---

### Feature 9: Multi-Provider LLM Gateway & Fallback Architecture

- **File Implementation**: [`backend/providers/`](file:///home/abin/overbranch/backend/providers/)
- **Unified Routing (`router.py`)**:
  - **Gemini Web2API / Google GenAI (`gemini_provider.py`)**: The primary default model family (`gemini-3.7-flash`, `gemini-2.5-pro`). High throughput, extensive context window, and streaming support.
  - **Groq (`groq_provider.py`)**: Ultra-low-latency generation using high-speed hardware (`llama-3.3-70b-versatile`, `mixtral-8x7b-32768`).
  - **OpenRouter (`openrouter_provider.py`)**: Access to deep reasoning models (`deepseek/deepseek-r1`, `nvidia/llama-3.1-nemotron-70b`, `minimax/minimax-01`).
  - **Cancellation Aware**: Integrates with `cancellation.py` to allow instant abort of streaming requests across all providers.
- **Custom User API Keys**:
  - Users can input their own Groq, Gemini, or OpenRouter keys via `ApiSettingsModal.tsx`.
  - Stored locally in the user's browser and forwarded via the `api_keys` dictionary in request payloads, overriding environment defaults.

---

### Feature 10: PDF to Editable LaTeX Conversion Engine (Dashboard & In-Project)

```
+------------------------------------------------------------------------------------+
|                         PDF TO LATEX CONVERSION FLOW                               |
|                                                                                    |
|  Uploaded PDF ──► [PyMuPDF / pypdf Parser] ──► Extracted Text, Tables, Math        |
|                                                       │                            |
|                                                       ▼                            |
|  [SSE Progress Stream] ◄── [Chunked LLM Synthesis (Page by Page)]                  |
|          │                                            │                            |
|          ▼                                            ▼                            |
|  Client UI Updates ◄─────── [Modular Project Assembly (main.tex, assets/)]         |
|                                                       │                            |
|                                                       ▼                            |
|                             [Save to Supabase & Local Disk Workspace]              |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/routes/pdf_conversion.py`](file:///home/abin/overbranch/backend/routes/pdf_conversion.py), [`backend/services/pdf_parser.py`](file:///home/abin/overbranch/backend/services/pdf_parser.py), [`backend/services/pdf_to_latex.py`](file:///home/abin/overbranch/backend/services/pdf_to_latex.py), [`backend/services/pdf_figure_extractor.py`](file:///home/abin/overbranch/backend/services/pdf_figure_extractor.py), [`backend/services/layout_verifier.py`](file:///home/abin/overbranch/backend/services/layout_verifier.py), [`app/convert/page.tsx`](file:///home/abin/overbranch/app/convert/page.tsx), [`components/dashboard/PDFToLatexModal.tsx`](file:///home/abin/overbranch/components/dashboard/PDFToLatexModal.tsx)
- **Endpoints**:
  - `POST /api/pdf/convert`: Converts an uploaded PDF into a brand new project and returns Server-Sent Events (SSE).
  - `POST /api/pdf/convert-in-project`: Ingests a PDF directly into an active project's `assets/` directory and updates or inserts code into `main.tex`.
- **How It Works**:
  1. The user uploads a PDF (up to 200MB / 100 pages).
  2. **PDF Parsing & Geometry Extraction**: `pdf_parser.py` parses document geometry, font styles, embedded images, and math formulas.
  3. **PDF Figure Extraction**: `pdf_figure_extractor.py` extracts embedded raster/vector images directly into the project's `assets/` directory, parsing multi-line and plural captions while guarding against raw PDF path leaks in `\includegraphics{...}`.
  4. **Hierarchical Transcription**: The conversion engine analyzes document headers to classify document type (`beamer` slide deck vs. `article` / `report`) and streams chunked LLM synthesis via Server-Sent Events (`event: progress`, `event: page_done`, `event: complete`).
  5. **Positional Drift Calibration & Layout Verification**: `layout_verifier.py` measures vertical drift between original PDF pages and generated TeX rendering, calibrating `\vspace` and geometry to mirror original layout fidelity.
  6. Generated `.tex` files, figure assets, and bib files are persisted to disk and Postgres via `write_project_files_and_assets()`.

---

### Feature 11: Guest Conversion Session, Quota Enforcement & Auto-Migration

- **File Implementation**: [`backend/routes/guest_pdf.py`](file:///home/abin/overbranch/backend/routes/guest_pdf.py), [`backend/services/guest_identity.py`](file:///home/abin/overbranch/backend/services/guest_identity.py), [`backend/services/guest_quota.py`](file:///home/abin/overbranch/backend/services/guest_quota.py), [`backend/services/guest_migrator.py`](file:///home/abin/overbranch/backend/services/guest_migrator.py), [`backend/services/guest_cleanup.py`](file:///home/abin/overbranch/backend/services/guest_cleanup.py), [`components/GuestMigrationListener.tsx`](file:///home/abin/overbranch/components/GuestMigrationListener.tsx), [`hooks/useGuestMigration.ts`](file:///home/abin/overbranch/hooks/useGuestMigration.ts)
- **Guest Flow**:
  1. Unregistered visitors can test PDF-to-LaTeX conversion on `/convert`.
  2. `guest_identity.py` computes a SHA-256 fingerprint from the visitor's IP address, User-Agent, and browser headers, issuing an HMAC-signed JWT cookie (`ob_guest_token`).
  3. `guest_quota.py` limits guests to 2 conversions per rolling 24-hour window.
  4. Guest projects are created with an expiration timestamp (`expires_at = NOW() + 24 hours`).
- **Scheduled Background Cleanup**:
  - `guest_cleanup.py` runs a background task every 15 minutes (`start_cleanup_scheduler`), automatically purging expired guest projects and unlinking temp files.
- **Seamless Account Migration**:
  - When the guest registers or logs in, `GuestMigrationListener.tsx` detects the session and triggers `POST /api/guest/migrate`.
  - All projects created under the guest session are reassigned to the new user ID, removing the 24-hour expiration lock.

---

### Feature 12: Multimodal AI File Analyzer & TikZ Synthesizer

- **File Implementation**: [`backend/file_analyzer.py`](file:///home/abin/overbranch/backend/file_analyzer.py), [`components/editor/FileAnalyzerModal.tsx`](file:///home/abin/overbranch/components/editor/FileAnalyzerModal.tsx), [`lib/ai-file-analysis.ts`](file:///home/abin/overbranch/lib/ai-file-analysis.ts)
- **Endpoint**: `POST /api/analyze-file`
- **Supported Formats**: Images (`.png`, `.jpg`, `.webp`), Data (`.csv`, `.json`), Documents (`.pdf`, `.txt`, `.md`), Code (`.py`, `.tex`, `.ts`), Audio (`.mp3`, `.wav`).
- **How It Works**:
  1. Within the editor, users click the File Analyzer tool to upload data files, figures, or external papers.
  2. `file_analyzer.py` validates file size (up to 200MB) and parses MIME types.
  3. For CSV/JSON, it extracts tabular schemas and summaries; for images, it constructs multimodal vision payloads.
  4. The user can ask: *"Generate a PGFPlots / TikZ graph visualizing the data in this CSV"* or *"Convert this drawn flow chart into a TikZ diagram"*.
  5. The generated LaTeX snippet can be copied or injected into `main.tex` with one click.

---

### Feature 13: Collaborative Project Management & Role-Based Access

- **File Implementation**: [`db/schema.ts`](file:///home/abin/overbranch/db/schema.ts), [`trpc/routers/projects.ts`](file:///home/abin/overbranch/trpc/routers/projects.ts), [`trpc/routers/invitations.ts`](file:///home/abin/overbranch/trpc/routers/invitations.ts), [`trpc/routers/comments.ts`](file:///home/abin/overbranch/trpc/routers/comments.ts), [`components/editor/CollaboratorAvatars.tsx`](file:///home/abin/overbranch/components/editor/CollaboratorAvatars.tsx), [`components/dashboard/NotificationsPopover.tsx`](file:///home/abin/overbranch/components/dashboard/NotificationsPopover.tsx)
- **Roles**: `Owner`, `Editor`, `Viewer`.
- **Workflow**:
  1. The project owner clicks the "Share" button in the editor toolbar.
  2. An email invitation is submitted via `trpc.invitations.sendInvite`.
  3. An invitation record and an in-app notification (`db/schema.ts: notifications`) are created for the invitee.
  4. Upon accepting, the user is added to `project_members`.
  5. `CollaboratorAvatars.tsx` polls active members, displaying their profile images and access badges.
  6. Ownership can be transferred, or collaborators removed, with instant permission updates.

---

### Feature 14: Inline Diff Editor & Edit History Tracking

- **File Implementation**: [`components/editor/InlineDiffEditor.tsx`](file:///home/abin/overbranch/components/editor/InlineDiffEditor.tsx), [`components/DiffWidget.tsx`](file:///home/abin/overbranch/components/DiffWidget.tsx), [`lib/EditHistoryStore.ts`](file:///home/abin/overbranch/lib/EditHistoryStore.ts)
- **How It Works**:
  1. When the AI Copilot returns an edit, the application avoids overwriting the editor content directly.
  2. The changes are sent to `InlineDiffEditor.tsx`, which calculates character- and line-level diffs.
  3. The user can toggle between:
     - **Split View**: Original code on the left, proposed code on the right.
     - **Unified View**: Inline additions in green and deletions in red.
  4. **Accept**: Replaces the source code and automatically triggers re-compilation.
  5. **Reject**: Discards the proposal and restores the previous buffer.
  6. `EditHistoryStore.ts` stores full revision snapshots in browser `localStorage`, supporting instant undo/redo across sessions.

---

### Feature 15: Presentation View Mode (Beamer Decks)

- **File Implementation**: [`components/editor/PresentationView.tsx`](file:///home/abin/overbranch/components/editor/PresentationView.tsx)
- **How It Works**:
  1. When opening a Beamer project, the editor displays a "Present" button.
  2. `PresentationView.tsx` launches a fullscreen slide deck environment.
  3. Slides are rendered as high-fidelity SVG/canvas vectors or pre-rendered PDF pages.
  4. Supports keyboard shortcuts (Left/Right arrow keys, Spacebar, Page Up/Down, Esc to exit).
  5. Includes a slide drawer thumbnail strip, laser pointer overlay mode, and speaker notes display.

---

### Feature 16: LaTeX Template Gallery & Dynamic Cloning

- **File Implementation**: [`backend/template_service.py`](file:///home/abin/overbranch/backend/template_service.py), [`backend/templates/`](file:///home/abin/overbranch/backend/templates/), [`app/(dashboard)/templates/page.tsx`](file:///home/abin/overbranch/app/(dashboard)/templates/page.tsx), [`trpc/routers/templates.ts`](file:///home/abin/overbranch/trpc/routers/templates.ts)
- **Categories**:
  - `papers`: IEEE Transactions, ACM Conference, Springer LNCS, arXiv preprints.
  - `ppt`: Modern Beamer presentation slide decks (Nordlight, Metropolis, Navy Gold).
  - `resume`: ModernCV (Banking, Casual, Classic), Deedy Resume, Developer CV, Freeman CV.
  - `thesis`: Master and PhD Thesis chapter templates.
  - `assignments`: Homework, problem sets, exam papers.
  - `reports`: Lab reports, technical documentation, research whitepapers.
- **Dynamic Instantiation**:
  - Calling `POST /api/templates/{template_id}/use` copies template `.tex` sources, styles (`.cls`, `.sty`), fonts, and figures directly into a new project record, letting users begin writing immediately.

---

### Feature 17: Design System ("Celestial Obsidian & Luminescent Iris") & Theming Engine

- **File Implementation**: [`design.md`](file:///home/abin/overbranch/design.md), [`linear-design.md`](file:///home/abin/overbranch/linear-design.md), [`app/globals.css`](file:///home/abin/overbranch/app/globals.css), [`components/editor/EditorThemeModal.tsx`](file:///home/abin/overbranch/components/editor/EditorThemeModal.tsx), [`trpc/routers/preferences.ts`](file:///home/abin/overbranch/trpc/routers/preferences.ts)
- **Design System ("Celestial Obsidian & Luminescent Iris")**:
  - **Locked Palette**: Deep Obsidian background (`oklch(0.12 0.012 260)`), Luminescent Iris primary accent (`oklch(0.65 0.22 265)`), crisp white text (`oklch(0.98 0 0)`), and strict semantic emerald/amber/rose indicators.
  - **Typography Scale**: Display headings in **Archivo Black**, body text in **Inter**, and monospace code/editor in **Space Mono**.
  - **CTA Voice**: Solid iris primary buttons (`bg-indigo-600 rounded-xl`), obsidian secondary containers (`bg-zinc-800/80 border-zinc-700/60`), and active nav pills (`bg-indigo-500/10 text-indigo-300`).
- **User Configurable Parameters**:
  - **Themes**: VS Code Dark, GitHub Light, Nord, Dracula, Monokai, Cyberpunk.
  - **Typography**: Font family (Space Mono, Fira Code, JetBrains Mono, Source Code Pro), font size (12px to 22px), ligatures.
  - **Editor Behavior**: Tab size (2 or 4 spaces), soft wrap, line numbers, auto-closing brackets, and auto-compile triggers (on save vs. keystroke debounce).
  - Preferences sync across devices via Postgres table `editor_preferences`.

---

# 4. Deployment, Infrastructure & Environment Configuration

### Universal Docker Deployment

OverBranch is fully containerized using a multi-stage `Dockerfile`, `Dockerfile.backend`, and Compose configurations (`docker-compose.yml`, `docker-compose.backend.yml`):

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
| `DATABASE_URL` | Frontend & Drizzle | PostgreSQL connection string |
| `BETTER_AUTH_SECRET` | Frontend Auth | Secret key used to sign session cookies |
| `BETTER_AUTH_URL` | Frontend Auth | Canonical URL of the application (e.g. `http://localhost:3000`) |
| `NEXT_PUBLIC_APP_URL`| Frontend | Public facing web domain |
| `NEXT_PUBLIC_BACKEND_URL`| Frontend | URL of the FastAPI engine (`http://localhost:8000`) |
| `SUPABASE_URL` | Backend & Storage | Supabase project endpoint |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | High-privilege key for storage & direct operations |
| `QDRANT_HOST` / `QDRANT_API_KEY` | Backend RAG | Vector database connection details |
| `NVIDIA_API_KEY` | Backend Embeddings| NVIDIA API key for `NV-Embed-QA` vector generation |
| `GEMINI_API_KEY` | Backend LLM | Google GenAI / Gemini Web2API key |
| `GROQ_API_KEY` | Backend LLM | Groq cloud key for high-speed inference |
| `OPENROUTER_API_KEY` | Backend LLM | OpenRouter gateway key |
| `GUEST_TOKEN_SECRET` | Backend Guest | HMAC signing secret for 24-hour guest tokens |
| `SHADOW_COMPILE_MAX_RETRIES` | Backend AI | Max retries for shadow compiler self-correction (Default: `2`) |
