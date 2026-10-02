"""
tests/test_insert_into_chunk.py — Regression & Unit Tests for Bug 2 (Insert Into Chunk Tool)
===========================================================================================
Tests:
1. ShadowWorkspace.insert_into_chunk appends \\bibitem BEFORE \\end{thebibliography} in bibliography chunks.
2. insert_into_chunk appends \\item BEFORE \\end{itemize} / \\end{enumerate} in list environments.
3. insert_into_chunk with position="begin" inserts after section/chapter headers.
4. insert_into_chunk with position="end" appends to regular sections.
5. Chunk tracking and history recording for insert_into_chunk.
6. Fallback chunk alias resolution ("bibliography" / "references").
7. execute_tool dispatch for insert_into_chunk.
"""

import pytest
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool, TOOL_DEFINITIONS


BIB_DOC = r"""\documentclass{article}
\begin{document}

\section{Introduction}
As discussed in \cite{lamport94}, LaTeX is widely used.

\section{References}
\begin{thebibliography}{99}
\bibitem{lamport94}
L. Lamport, \emph{\LaTeX: A Document Preparation System}, Addison-Wesley, 1994.
\end{thebibliography}

\end{document}
"""

LIST_DOC = r"""\documentclass{article}
\begin{document}

\section{Key Contributions}
Our main contributions are:
\begin{itemize}
\item First contribution.
\item Second contribution.
\end{itemize}

\end{document}
"""

CHAPTER_DOC = r"""\documentclass{report}
\begin{document}

\chapter{Methodology}
Existing methodology description.

\chapter{Results}
Existing results.

\end{document}
"""


def test_insert_into_chunk_bibliography_placement():
    """Verify \\bibitem is inserted INSIDE the thebibliography environment, before \\end{thebibliography}."""
    ws = ShadowWorkspace(BIB_DOC, project_id="test-bib")
    
    new_citation = r"\bibitem{knuth84} D. E. Knuth, \emph{The \TeX book}, Addison-Wesley, 1984."
    result = ws.insert_into_chunk("section_2", new_citation, position="end")

    assert result["success"] is True
    assert result["chunk_id"] == "section_2"

    updated_buffer = ws.get_buffer()
    
    # 1. New citation must be present
    assert r"\bibitem{knuth84}" in updated_buffer

    # 2. Crucial: New citation MUST appear BEFORE \end{thebibliography}
    citation_idx = updated_buffer.find(r"\bibitem{knuth84}")
    end_bib_idx = updated_buffer.find(r"\end{thebibliography}")
    begin_bib_idx = updated_buffer.find(r"\begin{thebibliography}{99}")

    assert begin_bib_idx < citation_idx < end_bib_idx, "Citation must be between begin{thebibliography} and end{thebibliography}"

    # 3. Must be tracked in touched chunks
    assert "section_2" in ws.get_touched_chunks()


def test_insert_into_chunk_bibliography_alias():
    """Verify 'bibliography' or 'references' chunk_id alias resolves correctly."""
    ws = ShadowWorkspace(BIB_DOC, project_id="test-bib-alias")
    
    new_citation = r"\bibitem{smith2024} J. Smith, \emph{Agentic LaTeX IDEs}, 2024."
    result = ws.insert_into_chunk("bibliography", new_citation, position="end")

    assert result["success"] is True
    assert result["chunk_id"] == "section_2"

    updated_buffer = ws.get_buffer()
    citation_idx = updated_buffer.find(r"\bibitem{smith2024}")
    end_bib_idx = updated_buffer.find(r"\end{thebibliography}")
    assert citation_idx < end_bib_idx


def test_insert_into_chunk_list_environment():
    """Verify \\item is inserted before \\end{itemize}."""
    ws = ShadowWorkspace(LIST_DOC, project_id="test-list")
    
    new_item = r"\item Third novel contribution."
    result = ws.insert_into_chunk("section_1", new_item, position="end")

    assert result["success"] is True
    updated = ws.get_buffer()

    item_idx = updated.find(r"\item Third novel contribution.")
    end_itemize_idx = updated.find(r"\end{itemize}")
    begin_itemize_idx = updated.find(r"\begin{itemize}")

    assert begin_itemize_idx < item_idx < end_itemize_idx


def test_insert_into_chunk_position_begin():
    """Verify position='begin' inserts right after the section/chapter header."""
    ws = ShadowWorkspace(CHAPTER_DOC, project_id="test-ch-begin")
    
    inserted_text = "This chapter establishes our theoretical framework."
    result = ws.insert_into_chunk("chapter_1", inserted_text, position="begin")

    assert result["success"] is True
    updated = ws.get_buffer()

    ch1_idx = updated.find(r"\chapter{Methodology}")
    insert_idx = updated.find("This chapter establishes our theoretical framework.")
    existing_idx = updated.find("Existing methodology description.")

    assert ch1_idx < insert_idx < existing_idx


def test_insert_into_chunk_invalid_chunk_id():
    """Verify error reporting with available chunk IDs when chunk_id is invalid."""
    ws = ShadowWorkspace(CHAPTER_DOC, project_id="test-err")
    
    result = ws.insert_into_chunk("chapter_999", "Some content", position="end")
    assert result["success"] is False
    assert "not found" in result["error"]
    assert "available_chunks" in result
    assert "chapter_1" in result["available_chunks"]
    assert "chapter_2" in result["available_chunks"]


def test_execute_tool_dispatches_insert_into_chunk():
    """Verify execute_tool executes insert_into_chunk properly."""
    ws = ShadowWorkspace(BIB_DOC, project_id="test-dispatch")
    
    res = execute_tool(
        tool_name="insert_into_chunk",
        args={
            "chunk_id": "section_2",
            "content": r"\bibitem{vaswani2017} A. Vaswani et al., \emph{Attention Is All You Need}, NeurIPS 2017.",
            "position": "end",
        },
        workspace=ws,
    )

    assert res["success"] is True
    assert r"\bibitem{vaswani2017}" in ws.get_buffer()
    assert ws.get_buffer().find(r"\bibitem{vaswani2017}") < ws.get_buffer().find(r"\end{thebibliography}")


def test_tool_definition_exists_in_schema():
    """Verify insert_into_chunk is declared in TOOL_DEFINITIONS."""
    tool_names = [t["name"] for t in TOOL_DEFINITIONS]
    assert "insert_into_chunk" in tool_names
