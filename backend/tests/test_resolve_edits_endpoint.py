"""POST /api/agent/resolve-edits: server-side placement of edits the editor could not place."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user_or_guest
from opencode.apply_edits import resolve_and_apply
from opencode.diff_generator import compute_edit_items
from routes.agent_routes import router

ORIGINAL = (
    "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
    "Graph neural networks generalise convolutions to irregular domains.\n"
    "They aggregate messages from neighbouring nodes at every layer.\n"
    "\\section{Results}\nThe model improves accuracy by four points on every benchmark.\n\\end{document}\n"
)
PROPOSED = ORIGINAL.replace("by four points", "by five points")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_or_guest] = lambda: {"user_id": "u1", "is_guest": False}
    return TestClient(app)


def test_item_carries_node_metadata():
    items = compute_edit_items(ORIGINAL, PROPOSED)
    assert items[0]["node_id"] == "sec:results"


def test_stale_item_is_relocated_after_user_typed(client):
    items = compute_edit_items(ORIGINAL, PROPOSED)
    # The user re-indented and re-spaced the line while the agent was running.
    live = ORIGINAL.replace("The model improves accuracy by four points on every benchmark.",
                            "  The model improves  accuracy by four points on every benchmark.")
    live = live.replace("\\section{Introduction}\n", "\\section{Introduction}\nA new first line.\n")
    r = client.post("/api/agent/resolve-edits", json={"current_code": live, "items": items,
                                                      "original_code": ORIGINAL})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True, body
    assert "by five points" in body["code"] and "A new first line." in body["code"]
    assert body["applied"][0]["method"] in ("normalized", "fuzzy", "normalized+hint")


def test_unplaceable_item_returns_unchanged_document_with_attempts(client):
    items = compute_edit_items(ORIGINAL, PROPOSED)
    live = ORIGINAL.replace("\\section{Results}\nThe model improves accuracy by four points on every benchmark.\n", "")
    r = client.post("/api/agent/resolve-edits", json={"current_code": live, "items": items})
    body = r.json()
    assert body["success"] is False and body["document_unchanged"] is True
    assert body["code"] == live
    assert body["failed"][0]["attempts"]


def test_all_or_nothing_when_one_of_two_items_fails():
    proposed = PROPOSED.replace("irregular domains", "arbitrary graphs")
    items = compute_edit_items(ORIGINAL, proposed)
    assert len(items) == 2
    live = ORIGINAL.replace("Graph neural networks generalise convolutions to irregular domains.\n", "")
    out = resolve_and_apply(live, items, ORIGINAL)
    assert out["success"] is False and out["code"] == live


def test_full_document_item_only_when_document_unchanged():
    item = {"original_chunk": "", "proposed_chunk": "\\documentclass{article}", "is_full_document": True}
    assert resolve_and_apply("", [item], "")["success"] is True
    assert resolve_and_apply("changed", [item], "")["success"] is False
