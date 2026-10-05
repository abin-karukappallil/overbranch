"""
tests/test_document_environment_integrity.py
=============================================
Comprehensive unit and integration tests verifying that LaTeX document structure
invariants (specifically \\begin{document} and \\end{document}) are strictly preserved
during all rewrite-like agentic edits, chunk operations, and str_replace edits.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from document_index import DocumentIndex, ensure_document_environment
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool
from opencode.agent_loop import stream_opencode_agent
from tests.test_full_document_rewrite import MULTI_CHAPTER_LATEX_FIXTURE


def test_ensure_document_environment_inserts_missing_begin_document_report():
    """Verify \\begin{document} is correctly inserted before the first chapter in a report."""
    code_missing_begin = r"""\documentclass[11pt,a4paper]{report}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}

\title{Quantum Computing}
\author{Alice}
\date{\today}

\chapter{Introduction}
This is the introduction chapter.
\end{document}"""

    repaired = ensure_document_environment(code_missing_begin)
    assert r"\begin{document}" in repaired
    assert r"\end{document}" in repaired

    # Check order: \documentclass -> \title -> \begin{document} -> \chapter -> \end{document}
    idx_dc = repaired.find(r"\documentclass")
    idx_title = repaired.find(r"\title")
    idx_begin = repaired.find(r"\begin{document}")
    idx_ch = repaired.find(r"\chapter")
    idx_end = repaired.find(r"\end{document}")

    assert 0 <= idx_dc < idx_title < idx_begin < idx_ch < idx_end


def test_ensure_document_environment_inserts_missing_begin_document_beamer():
    """Verify \\begin{document} is correctly inserted before the first frame in Beamer."""
    beamer_missing_begin = r"""\documentclass[aspectratio=169]{beamer}
\usetheme{default}
\usepackage{tikz}
\definecolor{navy}{HTML}{0B2545}
\definecolor{gold}{HTML}{C9A24B}

\title{Quantum Key Distribution}
\author{Bob}

\begin{frame}[plain]
\titlepage
\end{frame}

\begin{frame}{Overview}
\begin{itemize}
\item Point A
\end{itemize}
\end{frame}
\end{document}"""

    repaired = ensure_document_environment(beamer_missing_begin)
    assert r"\begin{document}" in repaired
    assert r"\end{document}" in repaired

    idx_begin = repaired.find(r"\begin{document}")
    idx_frame = repaired.find(r"\begin{frame}")
    assert 0 <= idx_begin < idx_frame


def test_ensure_document_environment_inserts_missing_begin_document_article():
    """Verify \\begin{document} is inserted before \\section or \\maketitle in an article."""
    article_missing_begin = r"""\documentclass{article}
\usepackage{amsmath}

\title{Short Note}
\author{Charlie}

\maketitle

\section{First Section}
Content of first section.
\end{document}"""

    repaired = ensure_document_environment(article_missing_begin)
    assert r"\begin{document}" in repaired
    idx_begin = repaired.find(r"\begin{document}")
    idx_make = repaired.find(r"\maketitle")
    idx_sec = repaired.find(r"\section")
    assert 0 <= idx_begin < idx_make < idx_sec


def test_ensure_document_environment_deduplicates_begin_document():
    """Verify duplicate \\begin{document} tags are cleanly deduplicated."""
    code_duplicate_begin = r"""\documentclass{article}
\usepackage{amsmath}

\begin{document}
\section{One}

\begin{document}
\section{Two}
\end{document}"""

    repaired = ensure_document_environment(code_duplicate_begin)
    assert repaired.count(r"\begin{document}") == 1
    assert r"\section{One}" in repaired
    assert r"\section{Two}" in repaired


def test_ensure_document_environment_subfile_preserved():
    """Verify fragment/auxiliary subfiles without \\documentclass are left unmodified."""
    fragment = r"""\section{Subfile Section}
This is included from another file.
\begin{equation}
E = mc^2
\end{equation}"""

    repaired = ensure_document_environment(fragment)
    assert repaired == fragment
    assert r"\begin{document}" not in repaired


def test_replace_chunk_preamble_preserves_begin_document():
    """Verify replacing preamble chunk never destroys \\begin{document}."""
    idx = DocumentIndex()
    # Replacement content provided by LLM which omits \begin{document}
    new_preamble = r"""\documentclass[12pt,a4paper]{report}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}"""

    updated_code, updated_chunk, delta = idx.replace_chunk(
        latex_code=MULTI_CHAPTER_LATEX_FIXTURE,
        chunk_id="preamble",
        new_content=new_preamble,
    )

    assert r"\begin{document}" in updated_code
    assert r"\end{document}" in updated_code
    assert r"\chapter{Introduction to Quantum Mechanics}" in updated_code


def test_shadow_workspace_rewrite_chunk_preserves_begin_document():
    """Verify ShadowWorkspace.rewrite_chunk guarantees \\begin{document}."""
    ws = ShadowWorkspace(original_code=MULTI_CHAPTER_LATEX_FIXTURE)

    # Rewrite preamble without \begin{document}
    res = ws.rewrite_chunk(
        chunk_id="preamble",
        new_content=r"\documentclass{report}\usepackage{xcolor}",
    )
    assert res["success"] is True
    assert r"\begin{document}" in ws.get_buffer()

    # Rewrite chapter_1
    res2 = ws.rewrite_chunk(
        chunk_id="chapter_1",
        new_content=r"\chapter{Overhauled Chapter 1}\nNew chapter body.\n",
    )
    assert res2["success"] is True
    assert r"\begin{document}" in ws.get_buffer()


def test_shadow_workspace_str_replace_over_begin_document_auto_repairs():
    """Verify that str_replace wiping out \\begin{document} is auto-repaired immediately."""
    code = r"""\documentclass{article}
\usepackage{amsmath}
\begin{document}
\section{Old Section}
Body text.
\end{document}"""

    ws = ShadowWorkspace(original_code=code)

    # Replace block spanning from \usepackage through \section, omitting \begin{document}
    old_block = r"""\usepackage{amsmath}
\begin{document}
\section{Old Section}"""

    bad_replacement = r"""\usepackage{amsmath,amssymb}
\section{New Section}"""

    res = ws.str_replace(old_str=old_block, new_str=bad_replacement)
    assert res["success"] is True

    # Buffer must still contain \begin{document}
    buf = ws.get_buffer()
    assert r"\begin{document}" in buf
    assert r"\end{document}" in buf
    assert buf.find(r"\begin{document}") < buf.find(r"\section{New Section}")


def test_agent_loop_full_rewrite_preserves_begin_document():
    """Simulate a full rewrite agent run and verify the final emitted code contains \\begin{document}."""
    mock_router = MagicMock()
    mock_router.chat.side_effect = [
        # Step 1: Agent rewrites all content chapters
        {
            "content": json.dumps({
                "thought": "Rewriting chapters",
                "tool_calls": [
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_1", "new_content": r"\chapter{Ch 1}\nCh 1 text.\n"}},
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_2", "new_content": r"\chapter{Ch 2}\nCh 2 text.\n"}},
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_3", "new_content": r"\chapter{Ch 3}\nCh 3 text.\n"}},
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_4", "new_content": r"\chapter{Ch 4}\nCh 4 text.\n"}},
                ]
            }),
            "finish_reason": "stop",
        },
        # Step 2: Agent signals done
        {
            "content": json.dumps({
                "thought": "All chapters rewritten.",
                "done": True,
                "explanation": "Completed full rewrite."
            }),
            "finish_reason": "stop",
        },
    ]

    with patch("opencode.agent_loop.provider_router", mock_router):
        events = list(stream_opencode_agent(
            user_instruction="Rewrite this document completely into a thesis on Deep Learning",
            project_id="proj-rewrite-doc-env",
            current_code=MULTI_CHAPTER_LATEX_FIXTURE,
            mode="edit",
            max_steps=5,
        ))

        # Check final_diff and result events
        diff_event = next((e for e in events if e.get("type") == "final_diff"), None)
        assert diff_event is not None
        proposed_code = diff_event.get("proposed_code", "")
        assert r"\begin{document}" in proposed_code
        assert r"\end{document}" in proposed_code

        res_event = next((e for e in events if e.get("type") == "result"), None)
        assert res_event is not None
        proposed = res_event.get("data", {}).get("proposed_chunk", "")
        assert r"\begin{document}" in proposed
        assert r"\end{document}" in proposed
