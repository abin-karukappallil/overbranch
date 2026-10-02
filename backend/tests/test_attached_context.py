"""
tests/test_attached_context.py — Regression & Unit Tests for Bug 3 (Attached File Persistence)
=============================================================================================
Tests:
1. AttachedContextStore stores and retrieves files by session_id.
2. Cross-turn persistence: File uploaded in Turn 1 is available in Turn 2 without resending.
3. Search functionality: search_attachments ranks and finds keyword matches.
4. TTL expiration and cleanup.
5. search_uploaded_references tool integration via execute_tool.
6. stream_opencode_agent uses stored session attachments when attached_file is None in current request.
"""

import time
import json
from unittest.mock import MagicMock, patch
import pytest

from attached_context import AttachedContextStore, attached_context_store
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool, TOOL_DEFINITIONS
from opencode.agent_loop import stream_opencode_agent


SAMPLE_PAPER_CONTENT = """Title: Attention Mechanisms in Neural Networks
Authors: Alice, Bob
Abstract: We present benchmark comparisons of Transformer vs RNN models.
Results: Transformer achieved 94.5% accuracy compared to 82.1% for RNN on dataset X.
Conclusion: Transformer models outperform recurrent architectures significantly.
"""


def test_attached_context_store_and_retrieve():
    """Verify storing and retrieving attached reference documents."""
    store = AttachedContextStore(ttl_seconds=3600)
    session_id = "test-session-1"

    file_payload = {
        "filename": "paper_2024.pdf",
        "file_type": "pdf",
        "content": SAMPLE_PAPER_CONTENT,
    }

    store.store_attachment(session_id, file_payload)
    attachments = store.get_attachments(session_id)

    assert len(attachments) == 1
    assert attachments[0]["filename"] == "paper_2024.pdf"
    assert "94.5% accuracy" in attachments[0]["content"]


def test_attached_context_search():
    """Verify keyword searching across stored reference attachments."""
    store = AttachedContextStore(ttl_seconds=3600)
    session_id = "test-search-session"

    store.store_attachment(session_id, {
        "filename": "benchmarks.txt",
        "file_type": "text",
        "content": SAMPLE_PAPER_CONTENT,
    })

    hits = store.search_attachments(session_id, "Transformer accuracy 94.5%")
    assert len(hits) > 0
    assert hits[0]["filename"] == "benchmarks.txt"
    assert "94.5% accuracy" in hits[0]["snippet"]


def test_attached_context_ttl_expiration():
    """Verify attachments expire after TTL."""
    # Short TTL: 0.1 seconds
    store = AttachedContextStore(ttl_seconds=0.1)
    session_id = "test-expire-session"

    store.store_attachment(session_id, {
        "filename": "temp.pdf",
        "file_type": "pdf",
        "content": "Temporary content",
    })

    assert len(store.get_attachments(session_id)) == 1

    time.sleep(0.15)
    store.cleanup_expired()

    assert len(store.get_attachments(session_id)) == 0


def test_search_uploaded_references_tool_execution():
    """Verify search_uploaded_references tool executes via execute_tool dispatcher."""
    session_id = "tool-test-session"
    attached_context_store.store_attachment(session_id, {
        "filename": "neural_arch.pdf",
        "file_type": "pdf",
        "content": SAMPLE_PAPER_CONTENT,
    })

    ws = ShadowWorkspace(
        original_code=r"\documentclass{article}\begin{document}Hello\end{document}",
        project_id="test-proj",
        session_id=session_id,
    )

    res = execute_tool(
        tool_name="search_uploaded_references",
        args={"query": "Transformer 94.5%"},
        workspace=ws,
    )

    assert res["count"] > 0
    assert len(res["matches"]) > 0
    assert res["matches"][0]["filename"] == "neural_arch.pdf"


def test_agent_loop_persists_attachment_across_turns():
    """
    Verify multi-turn flow:
    Turn 1: User sends attached_file -> stored in session cache.
    Turn 2: User sends follow-up with attached_file=None -> agent loop still receives attachment context!
    """
    session_id = "multi-turn-session-xyz"
    file_payload = {
        "filename": "benchmark_data.pdf",
        "file_type": "pdf",
        "content": SAMPLE_PAPER_CONTENT,
    }

    mock_router = MagicMock()
    mock_router.chat.return_value = {
        "content": json.dumps({"thought": "Done", "done": True}),
        "finish_reason": "stop",
    }

    code = r"\documentclass{article}\begin{document}\section{Intro}Hello\end{document}"

    with patch("opencode.agent_loop.provider_router", mock_router):
        # Turn 1: with attached_file
        list(stream_opencode_agent(
            user_instruction="Analyze this paper",
            project_id="proj-123",
            current_code=code,
            mode="edit",
            attached_file=file_payload,
            session_id=session_id,
            max_steps=1,
        ))

        # Check that it's in the store
        stored = attached_context_store.get_attachments(session_id)
        assert len(stored) == 1

        # Turn 2: follow-up WITHOUT attached_file
        events_turn2 = list(stream_opencode_agent(
            user_instruction="Add the benchmark accuracy numbers from the paper into the document",
            project_id="proj-123",
            current_code=code,
            mode="edit",
            attached_file=None,  # Not resent!
            session_id=session_id,
            max_steps=1,
        ))

        # Check call arguments sent to LLM in turn 2
        last_call_messages = mock_router.chat.call_args[1]["messages"]
        user_msg = next((m["content"] for m in last_call_messages if m["role"] == "user"), "")
        
        # Attachment block should be present in Turn 2 prompt!
        assert "ATTACHED REFERENCE FILE: benchmark_data.pdf" in user_msg
        assert "94.5% accuracy" in user_msg


def test_extract_text_from_pdf_data_uri():
    """Verify extracting real text from a base64 data URI encoded PDF."""
    import base64
    import pymupdf as fitz
    from attached_context import extract_text_from_attachment

    # Create a real in-memory PDF with fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Quantum Computing Benchmark: 99.8% fidelity achieved on Sycamore.")
    pdf_bytes = doc.tobytes()
    data_uri = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("utf-8")

    extracted = extract_text_from_attachment("quantum_paper.pdf", "application/pdf", data_uri)
    assert "Quantum Computing Benchmark" in extracted
    assert "99.8% fidelity" in extracted


def test_agent_loop_with_attached_files_list():
    """Verify passing multiple attached files in attached_files list to stream_opencode_agent."""
    session_id = "multi-file-session-abc"
    files = [
        {"filename": "doc1.txt", "file_type": "text/plain", "content": "Findings from Doc 1: speedup is 4.2x"},
        {"filename": "doc2.txt", "file_type": "text/plain", "content": "Findings from Doc 2: latency is 12ms"},
    ]

    mock_router = MagicMock()
    mock_router.chat.return_value = {
        "content": json.dumps({"thought": "Done", "done": True}),
        "finish_reason": "stop",
    }

    code = r"\documentclass{article}\begin{document}Content\end{document}"

    with patch("opencode.agent_loop.provider_router", mock_router):
        list(stream_opencode_agent(
            user_instruction="Incorporate findings from both documents",
            project_id="proj-multi",
            current_code=code,
            mode="edit",
            attached_files=files,
            session_id=session_id,
            max_steps=1,
        ))

        stored = attached_context_store.get_attachments(session_id)
        assert len(stored) == 2

        last_call_messages = mock_router.chat.call_args[1]["messages"]
        user_msg = next((m["content"] for m in last_call_messages if m["role"] == "user"), "")
        assert "speedup is 4.2x" in user_msg
        assert "latency is 12ms" in user_msg


def test_list_and_read_attached_document_tools():
    """Verify list_attached_documents and read_attached_document tool execution."""
    session_id = "tools-session-123"
    import base64
    import pymupdf as fitz

    # Create a 3-page test PDF
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 50), "Page 1: Introduction and Abstract of the Study.")
    p2 = doc.new_page()
    p2.insert_text((50, 50), "Page 2: Core Methodology and Mathematical Formulations: E = mc^2.")
    p3 = doc.new_page()
    p3.insert_text((50, 50), "Page 3: Experimental Benchmark Results: 98.4% F1 score.")
    pdf_bytes = doc.tobytes()
    data_uri = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("utf-8")

    attached_context_store.store_attachment(session_id, {
        "filename": "study.pdf",
        "file_type": "application/pdf",
        "content": data_uri,
    })

    ws = ShadowWorkspace(
        original_code=r"\documentclass{article}\begin{document}Draft\end{document}",
        project_id="proj-tools",
        session_id=session_id,
    )
    # Also mount into workspace as reference file
    att = attached_context_store.get_attachment(session_id, "study.pdf")
    assert att is not None
    assert att.get("page_count") == 3
    ws.add_reference_file("study.pdf", att.get("full_content", ""))

    # 1. Test list_attached_documents
    list_res = execute_tool("list_attached_documents", {}, ws)
    assert list_res["count"] == 1
    assert list_res["documents"][0]["filename"] == "study.pdf"
    assert list_res["documents"][0]["page_count"] == 3

    # 2. Test read_attached_document by page range
    read_p2 = execute_tool("read_attached_document", {
        "filename": "study.pdf",
        "start_page": 2,
        "end_page": 2,
    }, ws)
    assert "E = mc^2" in read_p2["content"]
    assert "Page 1: Introduction" not in read_p2["content"]

    # 3. Test read_attached_document page 3
    read_p3 = execute_tool("read_attached_document", {
        "filename": "study.pdf",
        "start_page": 3,
        "end_page": 3,
    }, ws)
    assert "98.4% F1 score" in read_p3["content"]

    # 4. Test reading reference file directly via read_file_range
    read_range_res = execute_tool("read_file_range", {
        "file": "study.pdf",
        "start_line": 1,
        "end_line": 20,
    }, ws)
    assert "content" in read_range_res
    assert "Introduction and Abstract" in read_range_res["content"]

    # 5. Test searching reference file via grep_search
    grep_res = execute_tool("grep_search", {
        "file": "study.pdf",
        "query": "F1 score",
    }, ws)
    assert grep_res["match_count"] > 0
    assert "98.4% F1 score" in grep_res["matches"][0]["content"]

    # 6. Test that reference files are protected against str_replace
    rep_res = execute_tool("str_replace", {
        "file": "study.pdf",
        "old_str": "98.4%",
        "new_str": "100%",
    }, ws)
    assert "read-only" in rep_res["error"].lower()


def test_agent_loop_emits_step0_attachment_status_and_creation_mode():
    """Verify stream_opencode_agent emits Step 0 status for attachments and switches to creation mode."""
    session_id = "status-creation-session"
    file_payload = {
        "filename": "deep_learning_survey.pdf",
        "file_type": "text/plain",
        "content": "Deep Learning Survey 2024: Transformers lead across NLP and Vision benchmarks.",
    }

    mock_router = MagicMock()
    mock_router.chat.return_value = {
        "content": json.dumps({"thought": "Done", "done": True}),
        "finish_reason": "stop",
    }

    code = r"\documentclass{beamer}\begin{document}\end{document}"

    with patch("opencode.agent_loop.provider_router", mock_router):
        events = list(stream_opencode_agent(
            user_instruction="Create a presentation from this pdf",
            project_id="proj-creation",
            current_code=code,
            mode="edit",
            attached_file=file_payload,
            session_id=session_id,
            max_steps=1,
        ))

        # Check for Step 0 status event confirming attachment loaded
        status_events = [e for e in events if e.get("type") == "status"]
        att_status = next((s for s in status_events if "Attached reference document(s) loaded" in s.get("message", "")), None)
        assert att_status is not None
        assert "deep_learning_survey.pdf" in att_status["message"]

        # Check prompt sent to LLM contains CREATION / CONVERSION MODE
        last_call_messages = mock_router.chat.call_args[1]["messages"]
        user_msg = next((m["content"] for m in last_call_messages if m["role"] == "user"), "")
        assert "DOCUMENT CREATION / CONVERSION MODE" in user_msg
        assert "ATTACHED REFERENCE DOCUMENTS (PRIMARY SOURCE MATERIAL)" in user_msg
        assert "deep_learning_survey.pdf" in user_msg

