"""
test_validate_latex_endpoint.py — POST /api/agent/validate-latex

The editor calls this after applying a *subset* of the agent's proposed edits.
The whole-document path is already validated on the backend, but accepting only
some edits can leave an orphaned \\end{...} that nothing else would catch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from auth import get_current_user_or_guest
from main import app

VALID_DOC = (
    "\\documentclass{article}\n\\begin{document}\nhello\n\\end{document}\n"
)
BROKEN_DOC = (
    "\\documentclass{article}\n\\begin{document}\n\\begin{itemize}\n"
    "\\item a\n\\end{document}\n"
)


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user_or_guest] = lambda: {
        "user_id": "test-user",
        "is_guest": False,
    }
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user_or_guest, None)


def test_requires_authentication():
    # No dependency override here: the route must reject anonymous callers.
    res = TestClient(app).post("/api/agent/validate-latex", json={"latex_code": "x"})
    assert res.status_code == 401


def test_valid_document_passes(client):
    res = client.post("/api/agent/validate-latex", json={"latex_code": VALID_DOC})
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_broken_document_reports_errors(client):
    res = client.post("/api/agent/validate-latex", json={"latex_code": BROKEN_DOC})
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is False
    assert any("itemize" in e for e in body["errors"])


def test_validate_only_by_default_does_not_heal(client):
    """heal defaults to False: an Accept must never silently rewrite the user's text."""
    res = client.post("/api/agent/validate-latex", json={"latex_code": BROKEN_DOC})
    body = res.json()
    assert body["healed_code"] is None
    assert body["changed"] is False
    assert body["fixes_applied"] == []


def test_heal_returns_repair_and_explains_it(client):
    res = client.post(
        "/api/agent/validate-latex", json={"latex_code": BROKEN_DOC, "heal": True}
    )
    body = res.json()
    assert body["valid"] is True
    assert body["changed"] is True
    assert body["healed_code"] is not None
    assert "\\end{itemize}" in body["healed_code"]
    # The caller must be able to tell the user what changed.
    assert body["fixes_applied"], "a heal that cannot be explained must not be offered"


def test_heal_closes_environment_positionally_not_at_eof(client):
    """
    Regression guard: the repair must insert \\end{itemize} *before*
    \\end{document}, not append it afterwards.
    """
    res = client.post(
        "/api/agent/validate-latex", json={"latex_code": BROKEN_DOC, "heal": True}
    )
    healed = res.json()["healed_code"]
    assert healed.index("\\end{itemize}") < healed.index("\\end{document}")


def test_partial_apply_producing_orphan_tag_is_rejected(client):
    """The exact case this endpoint guards: a half-applied edit set."""
    half_applied = (
        "\\documentclass{beamer}\n\\begin{document}\n"
        "\\begin{frame}{A}\n\\begin{itemize}\n\\item one\n"
        "\\end{frame}\n\\end{document}\n"
    )
    res = client.post("/api/agent/validate-latex", json={"latex_code": half_applied})
    assert res.json()["valid"] is False


def test_oversize_document_is_rejected(client):
    res = client.post(
        "/api/agent/validate-latex", json={"latex_code": "x" * 2_000_001}
    )
    assert res.status_code == 413


def test_empty_document_is_valid(client):
    res = client.post("/api/agent/validate-latex", json={"latex_code": ""})
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_file_path_is_echoed_back(client):
    res = client.post(
        "/api/agent/validate-latex",
        json={"latex_code": VALID_DOC, "file_path": "chapters/ch1.tex"},
    )
    assert res.json()["file_path"] == "chapters/ch1.tex"
