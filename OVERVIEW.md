# OverBranch — Comprehensive Method, Architecture & Feature Guide

> **OverBranch** is a 100% free and open-source agentic LaTeX code editor and research environment. Built for students, academics, and scientific authors, it combines lightning-fast compilation, an intelligent RAG-driven AI copilot router, bidirectional SyncTeX synchronization, PDF-to-LaTeX conversion, and multi-user collaboration.

---

## Table of Contents

1. [High-Level Methodology & System Architecture](#1-high-level-methodology--system-architecture)
   - [Architectural Overview](#architectural-overview)
   - [Core Methodological Pipelines](#core-methodological-pipelines)
     - [A. LaTeX Compilation & Fallback Pipeline](#a-latex-compilation--fallback-pipeline)
     - [B. Semantic Chunking & Vector RAG Pipeline](#b-semantic-chunking--vector-rag-pipeline)
     - [C. Structural Document Parsing & Page Indexing](#c-structural-document-parsing--page-indexing)
     - [D. Agentic Editing, Diff Generation & Auto-Repair](#d-agentic-editing-diff-generation--auto-repair)
     - [E. PDF-to-LaTeX Ingestion & Guest Session Lifecycle](#e-pdf-to-latex-ingestion--guest-session-lifecycle)
     - [F. SyncTeX Bidirectional Navigation](#f-synctex-bidirectional-navigation)
2. [Complete Repository & File Structure](#2-complete-repository--file-structure)
   - [Root Directory Layout](#root-directory-layout)
   - [Backend Architecture (`backend/`)](#backend-architecture-backend)
   - [Frontend Application (`app/`)](#frontend-application-app)
   - [UI Components (`components/`)](#ui-components-components)
   - [Database Layer (`db/`)](#database-layer-db)
   - [tRPC API Layer (`trpc/` & `server/`)](#trpc-api-layer-trpc--server)
   - [Libraries & Client Utilities (`lib/`)](#libraries--client-utilities-lib)
3. [Deep-Dive: How Every Feature Works](#3-deep-dive-how-every-feature-works)
   - [Feature 1: Real-Time LaTeX Compilation & ReportLab Fallback](#feature-1-real-time-latex-compilation--reportlab-fallback)
   - [Feature 2: Bidirectional SyncTeX Navigation (Forward & Backward)](#feature-2-bidirectional-synctex-navigation-forward--backward)
   - [Feature 3: Agentic LaTeX Copilot Router & Dual Modes (`Ask` vs. `Edit`)](#feature-3-agentic-latex-copilot-router--dual-modes-ask-vs-edit)
   - [Feature 4: Structural Document Indexing & Targeted Frame Extraction](#feature-4-structural-document-indexing--targeted-frame-extraction)
   - [Feature 5: Semantic Chunking & Qdrant Vector Synchronization](#feature-5-semantic-chunking--qdrant-vector-synchronization)
   - [Feature 6: Pre-Output Validation & Auto-Repair Engine](#feature-6-pre-output-validation--auto-repair-engine)
   - [Feature 7: Multi-Provider LLM Gateway & Fallback Architecture](#feature-7-multi-provider-llm-gateway--fallback-architecture)
   - [Feature 8: PDF to Editable LaTeX Conversion (Dashboard & In-Project)](#feature-8-pdf-to-editable-latex-conversion-dashboard--in-project)
   - [Feature 9: Guest Conversion Session, Quota Enforcement & Auto-Migration](#feature-9-guest-conversion-session-quota-enforcement--auto-migration)
   - [Feature 10: Multimodal AI File Analyzer](#feature-10-multimodal-ai-file-analyzer)
   - [Feature 11: Collaborative Project Management & Role-Based Access](#feature-11-collaborative-project-management--role-based-access)
   - [Feature 12: Inline Diff Editor & Edit History Tracking](#feature-12-inline-diff-editor--edit-history-tracking)
   - [Feature 13: Presentation View Mode (Beamer Decks)](#feature-13-presentation-view-mode-beamer-decks)
   - [Feature 14: LaTeX Template Gallery & Dynamic Cloning](#feature-14-latex-template-gallery--dynamic-cloning)
   - [Feature 15: Editor Customization & Theming Engine](#feature-15-editor-customization--theming-engine)
4. [Deployment, Infrastructure & Environment Configuration](#4-deployment-infrastructure--environment-configuration)

---

# 1. High-Level Methodology & System Architecture

### Architectural Overview

OverBranch adopts a decoupled, micro-service-inspired architecture designed for high responsiveness, complete local isolation, and fault tolerance:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND CLIENT (Next.js 15)                    │
│  - App Router, React 19, TypeScript, Tailwind CSS, Lucide Icons        │
│  - Monaco / CodeMirror LaTeX Editor with syntax tree                   │
│  - Custom PDF Viewer (PDF.js / Iframe / SyncTeX click handlers)        │
│  - Presentation Deck Player (Beamer slide rendering)                   │
│  - Diff Viewer (Side-by-side & Unified diff widgets)                   │
└──────────────────┬───────────────────────────────┬─────────────────────┘
                   │                               │
       tRPC / Better-Auth (Next API)        HTTP / SSE / REST
                   │                               │
┌──────────────────▼──────────────┐   ┌────────────▼─────────────────────┐
│    DATABASE & AUTH SERVICE      │   │     FASTAPI PYTHON ENGINE        │
│  - PostgreSQL via Drizzle ORM   │   │  - Port 8000                     │
│  - Supabase Database Storage    │   │  - Uvicorn / AsyncIO             │
│  - Better-Auth Session Tokens   │   │  - PDF compilation & Fallback    │
│  - Project & Invitation Schema  │   │  - Qdrant Vector Sync & LangChain│
└─────────────────────────────────┘   │  - Thin Agent Router & Evaluator │
                                      │  - PDF to LaTeX OCR / Parser     │
                                      │  - Multimodal File Analyzer      │
                                      └──────────────────────────────────┘
```

---

### Core Methodological Pipelines

#### A. LaTeX Compilation & Fallback Pipeline
1. **Source Bundling**: The frontend packages the active `.tex` document, referenced images (as base64 or project asset filenames), auxiliary files (e.g. `.bib`, `.sty`, `.cls`), and requested TeX engine (`latexmk`, `pdflatex`, `xelatex`, `lualatex`).
2. **Execution Isolation**: The backend spawns a secure temporary directory (`tempfile.mkdtemp()`), copies root templates and packages, decodes assets to disk, and executes the compilation command with timeouts.
3. **Artifact Caching & SyncTeX Extraction**: If compilation succeeds, the resultant `main.pdf` and `main.synctex.gz` are stored in `/tmp/overbranch_synctex_cache/<project_id>/` for fast bidirectional lookup.
4. **Resilient ReportLab Fallback**: If no LaTeX engine is installed on the host system (e.g. lightweight Docker deployment or developer laptop without TeXLive), `compiler.py` engages an intelligent ReportLab synthetic generator that strips TeX control sequences, identifies Beamer frames or article sections, and builds a matching PDF document.

#### B. Semantic Chunking & Vector RAG Pipeline
1. **Boundary-Aware Chunking**: Traditional RAG splits documents by fixed token counts. OverBranch's `chunker.py` analyzes TeX grammatical boundaries: `\section`, `\subsection`, `\begin{frame}`, mathematical blocks (`align`, `equation`), floating tables, and figures.
2. **Quality Weighting**: Each chunk is assigned a categorical weight (e.g., `section: 1.0`, `frame: 0.95`, `figure: 0.88`, `paragraph: 0.6`, `preamble: 0.3`).
3. **Vector Ingestion**: Vectors are generated via `NVIDIAEmbeddings` (`NV-Embed-QA`) or OpenAI embeddings and persisted into a local or remote **Qdrant** collection (`overbranch_latex_chunks`).
4. **Hybrid Retrieval**: When a prompt arrives, `retriever.py` queries Qdrant with hybrid scoring, combining semantic vector similarity with chunk quality weights.

#### C. Structural Document Parsing & Page Indexing
1. **DocumentIndex Engine**: `document_index.py` constructs an in-memory structural representation of the document, mapping every slide or section to a stable `page_id`, offsets (`start_offset`, `end_offset`), and SHA-256 fingerprint.
2. **Targeted Slide Retrieval**: When editing Beamer presentations, the system can isolate the exact frame being discussed by matching frame titles, labels, or ordinal slide numbers, preventing hallucinations outside the target slide.

#### D. Agentic Editing, Diff Generation & Auto-Repair
1. **Prompt Assembly**: `prompt_builder.py` bundles the user query, conversational history from `memory.py`, structural context, retrieved RAG chunks, active compiler errors (if any), and active editor code into a structured system prompt.
2. **Tool / Mode Routing**:
   - `ask` mode: Generates direct explanatory responses, pedagogical math explanations, or suggestions.
   - `edit` mode: Employs tool-calling schemas (`edit_chunk`, `create_content`, `delete_chunk`, `find_replace_all`) or direct structured diff outputs.
3. **Pre-Output Validation**: `edit_validator.py` executes AST-style regex passes to ensure:
   - No duplicate slide IDs or `\label{...}` collisions.
   - Proper balance of LaTeX environments (`\begin{...}` / `\end{...}`).
   - Non-destruction of the document preamble.
4. **LIFO Auto-Repair**: If an LLM response was truncated mid-token, `auto_repair_truncated_latex()` trims dangling commands and closes open environments in Last-In-First-Out order, guaranteeing valid syntax.

#### E. PDF-to-LaTeX Ingestion & Guest Session Lifecycle
1. **Multimodal Deconstruction**: Uploaded PDFs (academic papers, lecture slides, assignments) are parsed via `pdf_parser.py` (using `pypdf` or `PyMuPDF`) to extract text layout, tabular bounding boxes, and images.
2. **Hierarchical Translation**: `pdf_to_latex.py` converts extracted elements into modular LaTeX code, organizing them into standard templates (e.g. `IEEEtran`, `beamer`, `article`).
3. **Guest Session Protection**: Unauthenticated users are granted access through browser device fingerprinting and signed HMAC guest cookies (`guest_identity.py`). Quotas (e.g., 2 conversions per 24 hours) are checked against Postgres before processing.
4. **Transparent Migration**: When a guest signs up or logs in, `GuestMigrationListener` invokes `/api/guest/migrate`, reassigning all guest projects to the authenticated user ID.

#### F. SyncTeX Bidirectional Navigation
- **Forward Lookup**: Placing the cursor at line $L$ in `main.tex` executes `synctex view`, mapping the source code line to the exact PDF page, $x$, and $y$ coordinate, scrolling the PDF viewer automatically.
- **Backward Lookup**: Clicking an equation or paragraph inside the PDF viewer translates the click point $(page, x, y)$ back into the corresponding source filename, line number, and column.

---

# 2. Complete Repository & File Structure

```
overbranch/
├── app/                                 # Next.js App Router (Frontend)
│   ├── (dashboard)/                     # Protected Dashboard Layout Group
│   │   ├── dashboard/page.tsx           # User Dashboard (Recent projects, statistics)
│   │   ├── layout.tsx                   # Dashboard Sidebar, Nav & Shell
│   │   ├── profile/page.tsx             # User Profile & Preferences
│   │   ├── projects/page.tsx            # Project Management (List, Filter, Delete, Star)
│   │   └── templates/page.tsx           # LaTeX Template Explorer
│   ├── api/                             # API Routes (Next.js server-side)
│   │   ├── auth/[...all]/route.ts       # Better-Auth authentication endpoints
│   │   └── trpc/[trpc]/route.ts         # tRPC HTTP Handler
│   ├── auth/                            # Auth verification & callbacks
│   ├── convert/page.tsx                 # Standalone PDF to LaTeX Converter Page
│   ├── editor/[id]/page.tsx             # Main Project Editor Screen (Route handler)
│   ├── globals.css                      # Global Styles, CSS Variables & Tailwind Directives
│   ├── layout.tsx                       # Root HTML Layout & Global Providers
│   ├── login/page.tsx                   # Sign-in Page
│   ├── page.tsx                         # Landing Page (Showcase, CTA, Hero)
│   └── register/page.tsx                # Sign-up Page
│
├── backend/                             # Python FastAPI Engine
│   ├── assets/                          # Static assets and template images
│   ├── providers/                       # Multi-Provider LLM Gateway
│   │   ├── __init__.py                  # Package exports
│   │   ├── base_provider.py             # Abstract LLMProvider base class
│   │   ├── freellm_provider.py          # Free LLM API adapter (Groq fallback)
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
│   │   ├── pdf_parser.py                # PDF extraction via PyMuPDF / pypdf
│   │   ├── pdf_to_latex.py              # LLM conversion prompts & LaTeX synthesis
│   │   └── project_file_writer.py       # Writes generated projects to disk & Supabase
│   ├── templates/                       # Built-in LaTeX project templates
│   │   ├── assignments/                 # Academic Assignment templates
│   │   ├── papers/                      # Research Paper templates (IEEE, ACM, Springer)
│   │   ├── ppt/                         # Beamer presentation themes
│   │   └── reports/                     # Laboratory & Technical reports
│   ├── agent.py                         # Thin Agent Router & orchestration endpoint
│   ├── chunker.py                       # Structural LaTeX chunker with metadata
│   ├── compiler.py                      # TeX Engine compiler & ReportLab fallback
│   ├── context_builder.py               # Token-budgeted context assembler
│   ├── document_index.py                # Page/Frame parser & structural indexer
│   ├── edit_validator.py                # Pre-output LaTeX validator & auto-repair
│   ├── file_analyzer.py                 # Multimodal AI analysis for uploaded files
│   ├── main.py                          # FastAPI entry point & CORS configuration
│   ├── memory.py                        # Conversation & project memory (LRU store)
│   ├── project_storage.py               # File system disk operations & Supabase storage
│   ├── prompt_builder.py                # System prompt generator for LLMs
│   ├── retriever.py                     # Vector & structural retriever
│   ├── synctex_service.py               # Forward & backward SyncTeX locator
│   ├── template_service.py              # Template metadata & thumbnail server
│   ├── tools.py                         # LangChain tool definitions (edit, create, delete)
│   └── vector_sync.py                   # Qdrant client & vector sync endpoints
│
├── components/                          # React Components
│   ├── dashboard/                       # Dashboard-specific widgets (Stats, Cards, Lists)
│   ├── editor/                          # Editor Suite Components
│   │   ├── ApiSettingsModal.tsx         # User custom API keys modal (Gemini, Groq, etc.)
│   │   ├── ChatMessageContent.tsx       # Markdown & LaTeX rendering for AI chat
│   │   ├── ChatModeToggle.tsx           # Toggle between 'Ask' and 'Edit' modes
│   │   ├── CollaboratorAvatars.tsx      # Multi-user avatars & invitation management
│   │   ├── CompileToolbar.tsx           # Compile button, engine dropdown, error pill
│   │   ├── EditorLayout.tsx             # Master resizable split-pane editor shell
│   │   ├── EditorThemeModal.tsx         # Theme customizer (Monaco themes, font sizes)
│   │   ├── FileAnalyzerModal.tsx        # File inspection & AI multimodal querying
│   │   ├── InlineDiffEditor.tsx         # Side-by-side or unified diff viewer
│   │   ├── LatexEditorView.tsx          # Code editor wrapper with line numbers
│   │   ├── ModelSelector.tsx            # Dropdown model picker with provider badges
│   │   ├── PDFViewer.tsx                # Interactive PDF preview with SyncTeX triggers
│   │   ├── PresentationView.tsx         # Fullscreen Beamer slide presentation view
│   │   └── ProjectFilesPanel.tsx        # File tree explorer & asset manager
│   ├── landing/                         # Landing page sections (Hero, Features, Pricing)
│   ├── ui/                              # Radix UI / Shadcn base components
│   ├── DiffWidget.tsx                   # Standalone diff display with Accept/Reject buttons
│   └── GuestMigrationListener.tsx       # Client listener to migrate guest session on login
│
├── db/                                  # Database Access & Schema
│   ├── index.ts                         # Drizzle ORM client initialization
│   └── schema.ts                        # Drizzle PostgreSQL schema definitions
│
├── lib/                                 # Shared Library Code
│   ├── EditHistoryStore.ts              # LocalStorage edit history & undo/redo tracking
│   ├── IndexedDBEmbeddingCache.ts       # Client-side embedding cache
│   ├── ai-file-analysis.ts              # Client utilities for invoking file analyzer
│   ├── auth-client.ts                   # Better-Auth client instance
│   ├── auth.ts                          # Better-Auth server configuration
│   ├── guest-token.ts                   # Guest token cookie management
│   ├── pdf-thumbnail-utils.ts           # PDF page canvas thumbnail rendering
│   └── utils.ts                         # Tailwind CSS class merging utilities
│
├── server/                              # Server procedures
│   └── trpc/
│       ├── context.ts                   # tRPC context setup with authentication
│       ├── init.ts                      # tRPC router & middleware initialization
│       └── routers/
│           └── project.ts               # Core database-level project procedures
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
├── uploads/                             # Local disk storage for project files & assets
│   └── projects/<project_id>/           # Safe, isolated project directories
│
├── docker-compose.yml                   # Docker multi-service composition file
├── Dockerfile                           # Production Next.js & Python container build
├── deploy.sh                            # Automated deployment script for Linux/Ubuntu
└── drizzle.config.ts                    # Drizzle ORM configuration
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

- **File Implementation**: [`backend/compiler.py`](file:///home/abin/overbranch/backend/compiler.py), [`backend/main.py`](file:///home/abin/overbranch/backend/main.py)
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

- **File Implementation**: [`backend/synctex_service.py`](file:///home/abin/overbranch/backend/synctex_service.py), [`components/editor/PDFViewer.tsx`](file:///home/abin/overbranch/components/editor/PDFViewer.tsx)
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

### Feature 3: Agentic LaTeX Copilot Router & Dual Modes (`Ask` vs. `Edit`)

```
+------------------------------------------------------------------------------------+
|                                AI AGENT PIPELINE                                   |
|                                                                                    |
|  User Prompt ──► [Memory Context] ──► [DocumentIndex Frame/Section]                |
|                        │                         │                                 |
|                        ▼                         ▼                                 |
|                 [Vector Retrieval] ──► [Token Budget Context]                      |
|                                                  │                                 |
|                                                  ▼                                 |
|             [Prompt Builder] ──► [LLM Provider] (Gemini / Groq / OpenRouter)       |
|                                                  │                                 |
|                                                  ▼                                 |
|                                   [Pre-Output Edit Validator]                      |
|                                                  │                                 |
|                     ┌────────────────────────────┴───────────────────────────┐     |
|                     ▼                                                        ▼     |
|               Passed Checks                                            Auto-Repair |
|                     │                                                        │     |
|                     └────────────────────────────┬───────────────────────────┘     |
|                                                  │                                 |
|                                                  ▼                                 |
|                                       [Return Diff or Answer]                      |
+------------------------------------------------------------------------------------+
```

- **File Implementation**: [`backend/agent.py`](file:///home/abin/overbranch/backend/agent.py), [`backend/prompt_builder.py`](file:///home/abin/overbranch/backend/prompt_builder.py), [`backend/memory.py`](file:///home/abin/overbranch/backend/memory.py)
- **Endpoint**: `POST /api/agent/chat`
- **Two Distinct Modes**:
  1. **Ask Mode (`mode="ask"`)**:
     - Tailored for Q&A, scientific explanations, debugging advice, or LaTeX syntax queries.
     - System prompt instructs the model to provide educational, conversational explanations with code snippets, without generating full replacement blocks.
  2. **Edit Mode (`mode="edit"`)**:
     - Agentic document modification.
     - Prompt builder provides the full document structure, retrieved chunks, and the target frame/section.
     - The agent generates precise, targeted edits or calls LangChain tools (`edit_chunk`, `create_content`, `delete_chunk`, `find_replace_all`).
     - Outputs a structured diff containing `original_chunk`, `proposed_chunk`, `explanation`, and full replacement code.

---

### Feature 4: Structural Document Indexing & Targeted Frame Extraction

- **File Implementation**: [`backend/document_index.py`](file:///home/abin/overbranch/backend/document_index.py)
- **The Problem**: Passing a 40-page LaTeX paper or a 50-slide Beamer presentation into an LLM exceeds context limits and causes hallucinations or unwanted edits to unrelated sections.
- **The Method**:
  1. `document_index.py` inspects the document AST and splits it into logical `PageEntry` units:
     - For Beamer: Parses every `\begin{frame}...\end{frame}` block.
     - For Articles: Parses `\section{...}` and `\subsection{...}` hierarchies.
  2. Assigns a stable `page_id` based on `\label{...}`, frame title slug, or sequential page index.
  3. Computes SHA-256 hashes for each slide to detect modifications.
  4. When a user asks: *"Change the formula on the methodology slide"*, the indexer locates the exact slide, allowing `context_builder.py` to supply only that slide and its neighboring context to the LLM.

---

### Feature 5: Semantic Chunking & Qdrant Vector Synchronization

- **File Implementation**: [`backend/chunker.py`](file:///home/abin/overbranch/backend/chunker.py), [`backend/vector_sync.py`](file:///home/abin/overbranch/backend/vector_sync.py), [`backend/retriever.py`](file:///home/abin/overbranch/backend/retriever.py)
- **Chunking Method**:
  - Instead of naïve character counts, `chunker.py` splits documents along meaningful LaTeX blocks: sections, frames, floating figures, tables, math environments (`align`, `equation`), and bibliographies.
  - Generates rich metadata: `chunk_type`, `section_title`, `char_start`, `char_end`, and clean textual summaries stripped of TeX commands.
- **Vector Storage**:
  - Chunks are converted to dense vector embeddings using `NVIDIAEmbeddings` (`NV-Embed-QA`).
  - Stored in a local or cloud **Qdrant** collection named `overbranch_latex_chunks`.
  - Vectors include payload filters for `project_id` and `file_path`, guaranteeing complete isolation between users and projects.
- **Retrieval**:
  - `retriever.py` queries Qdrant and applies chunk quality weighting multipliers (`CHUNK_TYPE_WEIGHTS`) so that high-value sections or frames score above generic preambles or comments.

---

### Feature 6: Pre-Output Validation & Auto-Repair Engine

- **File Implementation**: [`backend/edit_validator.py`](file:///home/abin/overbranch/backend/edit_validator.py), [`backend/agent.py`](file:///home/abin/overbranch/backend/agent.py)
- **Validation Checks**:
  1. **Duplicate Slide / Label Check**: Verifies that new or modified frames do not introduce duplicate `\label{...}` entries or identical frame titles.
  2. **Environment Balance**: Checks that all `\begin{env}` tags have matching `\end{env}` tags.
  3. **Preamble Protection**: Ensures modifications do not accidentally strip `\documentclass`, essential packages, or custom macro definitions.
  4. **Scope Violation**: Flags if an edit requested for Section 2 erroneously alters Section 5.
- **LIFO Auto-Repair**:
  - If a model reaches its token cap and cuts off mid-sentence, `auto_repair_truncated_latex()`:
    - Strips dangling fragments (e.g. trailing `\item \textbf{`).
    - Uses an environment stack to close all remaining unclosed environments in LIFO order.
    - Appends `\end{document}` if the document was left open, ensuring the code compiles successfully.

---

### Feature 7: Multi-Provider LLM Gateway & Fallback Architecture

- **File Implementation**: [`backend/providers/`](file:///home/abin/overbranch/backend/providers/)
- **Unified Routing (`router.py`)**:
  - **Gemini Web2API / Google GenAI (`gemini_provider.py`)**: The primary default model (`gemini-3.7-flash`, `gemini-2.5-pro`). High throughput, extensive context window.
  - **Groq (`groq_provider.py`)**: Ultra-low-latency generation using `llama-3.3-70b-versatile` or `mixtral-8x7b-32768`.
  - **OpenRouter (`openrouter_provider.py`)**: Access to deep reasoning models (`deepseek/deepseek-r1`, `nvidia/llama-3.1-nemotron-70b`, `minimax/minimax-01`).
  - **FreeLLM (`freellm_provider.py`)**: Community models with built-in Groq fallback.
- **Custom User API Keys**:
  - Users can input their own Groq, Gemini, or OpenRouter keys via `ApiSettingsModal.tsx`.
  - Stored locally in the user's browser and forwarded via the `api_keys` dictionary in request payloads, overriding environment defaults.

---

### Feature 8: PDF to Editable LaTeX Conversion (Dashboard & In-Project)

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

- **File Implementation**: [`backend/routes/pdf_conversion.py`](file:///home/abin/overbranch/backend/routes/pdf_conversion.py), [`backend/services/pdf_parser.py`](file:///home/abin/overbranch/backend/services/pdf_parser.py), [`backend/services/pdf_to_latex.py`](file:///home/abin/overbranch/backend/services/pdf_to_latex.py), [`app/convert/page.tsx`](file:///home/abin/overbranch/app/convert/page.tsx)
- **Endpoints**:
  - `POST /api/pdf/convert`: Converts an uploaded PDF into a brand new project and returns Server-Sent Events (SSE).
  - `POST /api/pdf/convert-in-project`: Ingests a PDF directly into an active project's `assets/` directory and updates or inserts code into `main.tex`.
- **How It Works**:
  1. The user uploads a PDF (up to 200MB / 100 pages).
  2. `pdf_parser.py` parses document geometry, font styles, embedded images, and math formulas.
  3. The conversion engine analyzes document headers to classify the document type (`beamer` slide deck vs. `article` / `report`).
  4. The document is processed in sequential chunks through the LLM using specialized LaTeX transcription prompts.
  5. The backend emits real-time Server-Sent Events (`event: progress`, `event: page_done`, `event: complete`), allowing the frontend progress bar to update live.
  6. Generated `.tex` files, figures, and bib files are persisted to disk and Postgres via `write_project_files_and_assets()`.

---

### Feature 9: Guest Conversion Session, Quota Enforcement & Auto-Migration

- **File Implementation**: [`backend/routes/guest_pdf.py`](file:///home/abin/overbranch/backend/routes/guest_pdf.py), [`backend/services/guest_identity.py`](file:///home/abin/overbranch/backend/services/guest_identity.py), [`backend/services/guest_quota.py`](file:///home/abin/overbranch/backend/services/guest_quota.py), [`components/GuestMigrationListener.tsx`](file:///home/abin/overbranch/components/GuestMigrationListener.tsx)
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

### Feature 10: Multimodal AI File Analyzer

- **File Implementation**: [`backend/file_analyzer.py`](file:///home/abin/overbranch/backend/file_analyzer.py), [`components/editor/FileAnalyzerModal.tsx`](file:///home/abin/overbranch/components/editor/FileAnalyzerModal.tsx)
- **Endpoint**: `POST /api/analyze-file`
- **Supported Formats**: Images (`.png`, `.jpg`, `.webp`), Data (`.csv`, `.json`), Documents (`.pdf`, `.txt`, `.md`), Code (`.py`, `.tex`, `.ts`), Audio (`.mp3`, `.wav`).
- **How It Works**:
  1. Within the editor, users click the File Analyzer tool to upload data files, figures, or external papers.
  2. `file_analyzer.py` validates file size (up to 200MB) and parses MIME types.
  3. For CSV/JSON, it extracts tabular schemas and summaries; for images, it constructs multimodal vision payloads.
  4. The user can ask: *"Generate a PGFPlots / TikZ graph visualizing the data in this CSV"* or *"Convert this drawn flow chart into a TikZ diagram"*.
  5. The generated LaTeX snippet can be copied or injected into `main.tex` with one click.

---

### Feature 11: Collaborative Project Management & Role-Based Access

- **File Implementation**: [`db/schema.ts`](file:///home/abin/overbranch/db/schema.ts), [`trpc/routers/projects.ts`](file:///home/abin/overbranch/trpc/routers/projects.ts), [`trpc/routers/invitations.ts`](file:///home/abin/overbranch/trpc/routers/invitations.ts), [`components/editor/CollaboratorAvatars.tsx`](file:///home/abin/overbranch/components/editor/CollaboratorAvatars.tsx)
- **Roles**: `Owner`, `Editor`, `Viewer`.
- **Workflow**:
  1. The project owner clicks the "Share" button in the editor toolbar.
  2. An email invitation is submitted via `trpc.invitations.sendInvite`.
  3. An invitation record and an in-app notification (`db/schema.ts: notifications`) are created for the invitee.
  4. Upon accepting, the user is added to `project_members`.
  5. `CollaboratorAvatars.tsx` polls active members, displaying their profile images and access badges.
  6. Ownership can be transferred, or collaborators removed, with instant permission updates.

---

### Feature 12: Inline Diff Editor & Edit History Tracking

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

### Feature 13: Presentation View Mode (Beamer Decks)

- **File Implementation**: [`components/editor/PresentationView.tsx`](file:///home/abin/overbranch/components/editor/PresentationView.tsx)
- **How It Works**:
  1. When opening a Beamer project, the editor displays a "Present" button.
  2. `PresentationView.tsx` launches a fullscreen slide deck environment.
  3. Slides are rendered as high-fidelity SVG/canvas vectors or pre-rendered PDF pages.
  4. Supports keyboard shortcuts (Left/Right arrow keys, Spacebar, Page Up/Down, Esc to exit).
  5. Includes a slide drawer thumbnail strip, laser pointer overlay mode, and speaker notes display.

---

### Feature 14: LaTeX Template Gallery & Dynamic Cloning

- **File Implementation**: [`backend/template_service.py`](file:///home/abin/overbranch/backend/template_service.py), [`app/(dashboard)/templates/page.tsx`](file:///home/abin/overbranch/app/(dashboard)/templates/page.tsx)
- **Categories**:
  - `papers`: IEEE Transactions, ACM Conference, Springer LNCS, arXiv preprints.
  - `ppt`: Modern Beamer presentation slide decks (Nordlight, Metropolis, Navy Gold).
  - `assignments`: Homework, problem sets, exam papers.
  - `reports`: Lab reports, technical documentation, theses.
- **Dynamic Instantiation**:
  - Calling `POST /api/templates/{template_id}/use` copies template `.tex` sources, styles (`.cls`, `.sty`), and figures directly into a new project record, letting users begin writing immediately.

---

### Feature 15: Editor Customization & Theming Engine

- **File Implementation**: [`components/editor/EditorThemeModal.tsx`](file:///home/abin/overbranch/components/editor/EditorThemeModal.tsx), [`trpc/routers/preferences.ts`](file:///home/abin/overbranch/trpc/routers/preferences.ts)
- **User Configurable Parameters**:
  - **Themes**: VS Code Dark, GitHub Light, Nord, Dracula, Monokai, Cyberpunk.
  - **Typography**: Font family (Fira Code, JetBrains Mono, Source Code Pro), font size (12px to 22px), ligatures.
  - **Editor Behavior**: Tab size (2 or 4 spaces), soft wrap, line numbers, auto-closing brackets, and auto-compile triggers (on save vs. keystroke debounce).
  - Preferences sync across devices via Postgres table `editor_preferences`.

---

# 4. Deployment, Infrastructure & Environment Configuration

### Universal Docker Deployment

OverBranch is fully containerized using a multi-stage `Dockerfile` and `docker-compose.yml`:

```yaml
services:
  overbranch:
    build: .
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
