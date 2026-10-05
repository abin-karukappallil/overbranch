"""
Copilot integration: the `convert_attached_pdf` tool starts a conversion job for a PDF
attached in the chat, and the agent prompts document it.
"""

import base64

import pytest

from attached_context import attached_context_store
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import TOOL_DEFINITIONS, execute_tool
from pdf2latex import jobs
from tests import pdf2latex_fixtures as fx

DOC = "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path / "jobs"))
    started = []

    def fake_start_job(owner, is_guest, project_id, filename, data, page_count, overwrite=False):
        started.append(dict(owner=owner, project_id=project_id, filename=filename,
                            page_count=page_count, overwrite=overwrite, head=data[:5]))
        return jobs.create_job(owner, project_id, filename, page_count, is_guest)

    monkeypatch.setattr("pdf2latex.runner.start_job", fake_start_job)
    ws = ShadowWorkspace(DOC, project_id="proj-chat", session_id="sess-pdf-tool")
    ws.user_context = {"user_id": "user-chat", "is_guest": False}
    ws.started = started
    yield ws
    attached_context_store.clear_session("sess-pdf-tool")


def _attach(name="report.pdf"):
    data_url = "data:application/pdf;base64," + base64.b64encode(fx.multi_font_pdf()).decode()
    attached_context_store.store_attachment("sess-pdf-tool", {"filename": name, "file_type": "application/pdf",
                                                              "content": data_url})


def test_tool_is_registered_and_documented():
    tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "convert_attached_pdf")
    assert "mode" not in tool["parameters"]
    assert "exact" not in tool["description"] and "editable" not in tool["description"]
    from opencode.agent_loop import OPENCODE_SYSTEM_PROMPT
    from prompt_builder import SYSTEM_PROMPT_CORE
    assert "convert_attached_pdf" in OPENCODE_SYSTEM_PROMPT
    assert "PDF IMPORT" in SYSTEM_PROMPT_CORE


def test_attachment_keeps_pdf_bytes(workspace):
    _attach()
    att = attached_context_store.get_attachment("sess-pdf-tool", "report.pdf")
    assert att["is_pdf"] and att["raw_bytes"][:5] == b"%PDF-"
    assert "Quarterly" in att["full_content"]


def test_tool_starts_job_for_attached_pdf(workspace):
    _attach()
    res = execute_tool("convert_attached_pdf", {}, workspace)
    assert res.get("success"), res
    assert res["job_id"] and res["page_count"] == 1
    call = workspace.started[0]
    assert call["owner"] == "user-chat" and call["project_id"] == "proj-chat"
    assert call["overwrite"] is False and call["head"] == b"%PDF-"


def test_tool_errors_without_attachment(workspace):
    res = execute_tool("convert_attached_pdf", {}, workspace)
    assert "No attached PDF" in res["error"]


def test_tool_requires_user_context(workspace):
    _attach()
    workspace.user_context = {}
    assert "signed-in user" in execute_tool("convert_attached_pdf", {}, workspace)["error"]
