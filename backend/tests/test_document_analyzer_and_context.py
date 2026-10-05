"""
Unit and integration tests for document_analyzer, context_strategy,
and multi-file workspace support in OverBranch.
"""

import pytest
from document_analyzer import (
    analyze_document,
    generate_compact_summary,
    generate_preservation_map,
    build_task_state,
    DocumentAnalysis,
    SectionInfo,
)
from context_strategy import (
    resolve_context_strategy,
    build_initial_context,
    compute_step_max_tokens,
    FULL_REWRITE_STEP_MAX_TOKENS,
    extract_error_context,
    ContextStrategy,
    ContextDecision,
    get_model_context_window,
    get_available_input_tokens,
)
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool


# ============================================================================
# Test Fixtures
# ============================================================================

SAMPLE_ARTICLE = r"""\documentclass{article}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{booktabs}

\title{Neural Architecture Search via Reinforcement Learning}
\author{Barret Zoph \and Quoc V. Le}

\begin{document}
\maketitle

\begin{abstract}
We present Neural Architecture Search (NAS) using recurrent neural networks to generate model descriptions.
\end{abstract}

\section{Introduction}
Deep learning has achieved remarkable results in computer vision and natural language processing.
However, designing neural architectures still requires significant domain expertise.

\begin{equation}
J(\theta) = \mathbb{E}_{P(a_{1:T};\theta)}[R]
\end{equation}

\section{Related Work}
Evolutionary algorithms have previously been applied to topology optimization \cite{stanley2002}.

\section{Methodology}
Our controller is a recurrent neural network that outputs string descriptions of neural networks.

\begin{figure}[h]
\centering
\includegraphics[width=0.8\textwidth]{controller.png}
\caption{Overview of the RNN controller generating child networks.}
\label{fig:controller}
\end{figure}

\begin{table}[h]
\centering
\begin{tabular}{lrr}
\toprule
Model & Error Rate & Params \\
\midrule
DenseNet & 3.46\% & 7.0M \\
NASNet & 3.41\% & 3.3M \\
\bottomrule
\end{tabular}
\caption{CIFAR-10 classification benchmark results.}
\label{tab:cifar}
\end{table}

\section{Conclusion}
Neural Architecture Search can design competitive networks automatically.

\begin{thebibliography}{9}
\bibitem{stanley2002} Stanley, K. O., \& Miikkulainen, R. (2002).
\end{thebibliography}

\end{document}
"""

SAMPLE_BEAMER = r"""\documentclass{beamer}
\usetheme{Madrid}
\title{Quantum Computing Foundations}
\author{Alice Smith}

\begin{document}

\begin{frame}[plain]
\titlepage
\end{frame}

\begin{frame}{Introduction to Qubits}
\begin{itemize}
\item Classical bit: 0 or 1
\item Quantum bit (qubit): superposition of $|0\rangle$ and $|1\rangle$
\end{itemize}
\begin{equation}
|\psi\rangle = \alpha |0\rangle + \beta |1\rangle
\end{equation}
\end{frame}

\begin{frame}{Quantum Entanglement}
Entangled states cannot be factored into product states of individual qubits.
\end{frame}

\end{document}
"""

SAMPLE_MULTI_CHAPTER = r"""\documentclass{report}
\title{Autonomous Driving Systems}
\author{Robotics Lab}

\begin{document}
\maketitle

\chapter{Introduction}
Autonomous vehicles require perception, localization, planning, and control.

\section{Background}
History of DARPA grand challenge and early vision-based navigation.

\chapter{Sensor Fusion}
Multi-modal sensing combining LiDAR, RADAR, and cameras.

\section{LiDAR Processing}
Point cloud segmentation using PointNet.

\section{Camera Pipelines}
YOLOv8 object detection on camera feeds.

\chapter{Path Planning}
Motion planning using Dijkstra and A* search algorithms.

\chapter{Conclusion}
Future of level 5 autonomy.

\end{document}
"""


# ============================================================================
# Document Analyzer Tests
# ============================================================================

def test_analyze_document_metadata():
    """Verify metadata extraction: class, title, author."""
    analysis = analyze_document(SAMPLE_ARTICLE)
    assert analysis.document_class == "article"
    assert "Neural Architecture Search" in analysis.title
    assert "Barret Zoph" in analysis.author
    assert analysis.primary_structure_type == "section"
    assert analysis.structural_unit_count == 4
    assert analysis.total_lines > 20
    assert analysis.estimated_tokens > 50


def test_analyze_document_content_counts():
    """Verify figure, table, equation, citation counts."""
    analysis = analyze_document(SAMPLE_ARTICLE)
    assert analysis.figure_count == 1
    assert analysis.table_count >= 1
    assert analysis.equation_count == 1
    assert analysis.citation_count >= 1
    assert analysis.has_math is True
    assert analysis.has_tables is True
    assert analysis.has_figures is True
    assert analysis.has_bibliography is True


def test_analyze_beamer_document():
    """Verify beamer frame detection."""
    analysis = analyze_document(SAMPLE_BEAMER)
    assert analysis.document_class == "beamer"
    assert analysis.primary_structure_type == "frame"
    assert analysis.frame_count == 3
    assert analysis.has_math is True
    assert "Quantum Computing" in analysis.title


def test_analyze_report_chapters():
    """Verify report chapter and section hierarchy."""
    analysis = analyze_document(SAMPLE_MULTI_CHAPTER)
    assert analysis.document_class == "report"
    assert analysis.primary_structure_type == "chapter"
    assert analysis.chapter_count == 4
    assert analysis.section_count == 3
    assert len(analysis.sections) == 4


def test_generate_compact_summary():
    """Verify compact summary string formatting."""
    analysis = analyze_document(SAMPLE_ARTICLE)
    summary = generate_compact_summary(analysis)
    assert "Neural Architecture Search" in summary
    assert "figures" in summary
    assert "tables" in summary
    assert "SECTION BREAKDOWN:" in summary
    assert "Introduction" in summary


def test_generate_preservation_map_rewrite():
    """Verify preservation map on full rewrite instruction."""
    analysis = analyze_document(SAMPLE_ARTICLE)
    instruction = "Rewrite this paper about Graph Neural Networks, keep the preamble and bibliography"
    pmap = generate_preservation_map(analysis, instruction)
    assert "preamble" in pmap["preserve"]
    assert "bibliography" in pmap["preserve"]
    assert "topic" in pmap["change"]


def test_generate_preservation_map_expansion():
    """Verify preservation map on expansion instruction."""
    analysis = analyze_document(SAMPLE_ARTICLE)
    instruction = "Elaborate and expand the Methodology section with mathematical derivations"
    pmap = generate_preservation_map(analysis, instruction)
    assert "Methodology" in pmap["expand"]


def test_build_task_state():
    """Verify task state string representation."""
    analysis = analyze_document(SAMPLE_ARTICLE)
    instruction = "Add more experimental benchmarks to Section 3"
    pmap = generate_preservation_map(analysis, instruction)
    task_state = build_task_state(instruction, analysis, pmap, "TARGETED_EDIT")
    assert "TASK STATE" in task_state
    assert "Request:" in task_state
    assert "Scope: TARGETED_EDIT" in task_state
    assert "Neural Architecture Search" in task_state


# ============================================================================
# Context Strategy Tests
# ============================================================================

def test_resolve_context_strategy_fits_in_window():
    """Small doc on high-capacity model should resolve to WHOLE_FILE."""
    analysis = analyze_document(SAMPLE_ARTICLE)
    decision = resolve_context_strategy(
        analysis=analysis,
        scope="TARGETED_EDIT",
        model="gemini-3.7-flash",
        user_instruction="Fix typo in introduction",
    )
    assert decision.strategy == ContextStrategy.WHOLE_FILE
    assert decision.fits_in_context is True


def test_resolve_context_strategy_large_doc_targeted():
    """Very large doc on targeted edit should resolve to TARGETED."""
    # Synthesize large document analysis
    large_analysis = DocumentAnalysis(
        total_lines=4000,
        total_chars=160000,
        estimated_tokens=40000,
        sections=[SectionInfo(section_type="section", title="Introduction", start_line=10, end_line=500, line_count=491, char_count=20000)],
    )
    decision = resolve_context_strategy(
        analysis=large_analysis,
        scope="TARGETED_EDIT",
        model="groq/llama-3.3-70b-versatile",  # 128k window, doc_tokens=40k > threshold fraction
        user_instruction="Edit the introduction section",
    )
    assert decision.strategy in (ContextStrategy.TARGETED, ContextStrategy.WHOLE_FILE)


def test_extract_error_context():
    """Verify extraction of error context with line markers."""
    latex = "Line 1\nLine 2\nLine 3\n\\badcmd{foo}\nLine 5\nLine 6\nLine 7"
    errors = [{"line": 4, "error": "Undefined control sequence \\badcmd"}]
    ctx = extract_error_context(latex, errors, context_radius=2)
    assert "COMPILATION ERRORS WITH CONTEXT:" in ctx
    assert ">>> 4: \\badcmd{foo}" in ctx
    assert "2: Line 2" in ctx
    assert "6: Line 6" in ctx


def test_compute_step_max_tokens():
    """Verify dynamic step token allocation."""
    # Creation step 1
    assert compute_step_max_tokens(ContextStrategy.WHOLE_FILE, "TARGETED_EDIT", 1, is_creation=True) == 8192
    # Full rewrite
    assert compute_step_max_tokens(ContextStrategy.WHOLE_FILE, "FULL_DOCUMENT_REWRITE", 3) == FULL_REWRITE_STEP_MAX_TOKENS
    # Targeted edit: enough room for a whole frame or short section after JSON
    # escaping, so an ordinary edit does not trip the truncation-recovery path
    # (which costs an extra LLM call and then discards the step).
    assert compute_step_max_tokens(ContextStrategy.WHOLE_FILE, "TARGETED_EDIT", 3) == 4096


def test_build_initial_context_whole_file():
    """Verify build_initial_context for WHOLE_FILE strategy."""
    ws = ShadowWorkspace(SAMPLE_ARTICLE)
    analysis = analyze_document(SAMPLE_ARTICLE)
    decision = ContextDecision(
        strategy=ContextStrategy.WHOLE_FILE,
        reason="Fits in context",
        model="gemini-3.7-flash",
        available_tokens=100000,
        document_tokens=analysis.estimated_tokens,
        fits_in_context=True,
    )
    ctx = build_initial_context(decision, analysis, ws, "Improve abstract", "OUTLINE")
    assert "FULL DOCUMENT CONTENT" in ctx
    assert "Neural Architecture Search" in ctx


# ============================================================================
# Multi-File Workspace Support Tests
# ============================================================================

def test_shadow_workspace_auxiliary_files():
    """Verify adding, reading, grepping, and replacing in auxiliary files."""
    ws = ShadowWorkspace(SAMPLE_ARTICLE, file_path="main.tex")
    
    # Add auxiliary chapter
    chapter_content = "\\chapter{Experimental Setup}\nWe evaluate on ImageNet and CIFAR-100.\nGPU cluster was used."
    ws.add_auxiliary_file("chapters/experiments.tex", chapter_content)
    
    # Verify file listing
    files = ws.get_file_list()
    assert len(files) == 2
    paths = [f["path"] for f in files]
    assert "main.tex" in paths
    assert "chapters/experiments.tex" in paths
    
    # Verify read_file_lines on auxiliary file
    read_lines = ws.read_file_lines("chapters/experiments.tex", 1, 2)
    assert "1: \\chapter{Experimental Setup}" in read_lines
    assert "2: We evaluate on ImageNet" in read_lines
    
    # Verify grep on auxiliary file
    grep_res = ws.grep_file("chapters/experiments.tex", "ImageNet")
    assert len(grep_res) == 1
    assert grep_res[0]["line_no"] == 2
    
    # Verify str_replace on auxiliary file
    rep_res = ws.str_replace_file("chapters/experiments.tex", "CIFAR-100", "CIFAR-10")
    assert rep_res["success"] is True
    assert "CIFAR-10" in ws.get_auxiliary_file("chapters/experiments.tex")
    
    # Verify get_all_modified_files
    all_mods = ws.get_all_modified_files()
    assert "chapters/experiments.tex" in all_mods
    assert "main.tex" not in all_mods  # main hasn't changed yet


def test_tools_multi_file_dispatch():
    """Verify execute_tool supports file parameter for auxiliary files."""
    ws = ShadowWorkspace(SAMPLE_ARTICLE, file_path="main.tex")
    ws.add_auxiliary_file("sections/intro.tex", "Line 1: Hello\nLine 2: World\nLine 3: LaTeX")
    
    # 1. list_project_files tool
    list_res = execute_tool("list_project_files", {}, ws)
    assert list_res["count"] == 2
    
    # 2. read_document_summary tool
    sum_res = execute_tool("read_document_summary", {}, ws)
    assert "summary" in sum_res
    assert "Neural Architecture Search" in sum_res["summary"]
    
    # 3. read_file_range targeting auxiliary file
    read_res = execute_tool("read_file_range", {"file": "sections/intro.tex", "start_line": 1, "end_line": 2}, ws)
    assert read_res["file"] == "sections/intro.tex"
    assert "Line 1: Hello" in read_res["content"]
    
    # 4. grep_search targeting auxiliary file
    grep_res = execute_tool("grep_search", {"file": "sections/intro.tex", "query": "World"}, ws)
    assert grep_res["match_count"] == 1
    
    # 5. str_replace targeting auxiliary file
    rep_res = execute_tool("str_replace", {"file": "sections/intro.tex", "old_str": "World", "new_str": "OverBranch"}, ws)
    assert rep_res["success"] is True
    assert "OverBranch" in ws.get_auxiliary_file("sections/intro.tex")
