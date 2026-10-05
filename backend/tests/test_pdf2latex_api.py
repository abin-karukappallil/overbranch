"""
HTTP API tests for /api/convert/pdf (validation, limits, ownership, job lifecycle).
The conversion pipeline itself is stubbed; see test_pdf2latex_pipeline / _integration.
"""

import pytest
from fastapi.testclient import TestClient

import main
import rate_limiter
from auth import get_current_user_or_guest
from pdf2latex import jobs
from routes import pdf_convert
from tests import pdf2latex_fixtures as fx

USER = {"user_id": "user-api", "session_id": "s1", "is_guest": False, "authenticated": True, "user": None}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path / "jobs"))

    async def allow(self, key):
        return True, 99, 0.0

    monkeypatch.setattr(rate_limiter.SlidingWindowRateLimiter, "check", allow)
    started = []

    def fake_start_job(owner, is_guest, project_id, filename, data, page_count, overwrite=False):
        st = jobs.create_job(owner, project_id, filename, page_count, is_guest)
        jobs.update_job(st["job_id"], status="done", progress=1.0, report={"pages": []},
                        result={"tex_path": "main.tex"})
        started.append((owner, project_id, overwrite, data[:5]))
        return st

    monkeypatch.setattr(pdf_convert, "start_job", fake_start_job)
    monkeypatch.setattr(pdf_convert, "create_project_for_conversion",
                        lambda owner, name, filename, guest_session_id=None: {"project_id": "proj-new", "name": name or "Doc"})
    main.app.dependency_overrides[get_current_user_or_guest] = lambda: USER
    c = TestClient(main.app)
    c.started = started
    yield c
    main.app.dependency_overrides.clear()


def _post(c, data: bytes, **form):
    return c.post("/api/convert/pdf", files={"file": ("doc.pdf", data, "application/pdf")}, data=form)


def test_config_reports_agent_model_and_limits(client):
    from providers.router import DEFAULT_MODEL
    cfg = client.get("/api/convert/pdf/config").json()
    assert "modes" not in cfg
    assert cfg["model"] == DEFAULT_MODEL
    assert isinstance(cfg["llm_available"], bool)
    assert cfg["max_pages"] > 0 and cfg["max_file_mb"] > 0 and 0 < cfg["threshold"] <= 1


def test_rejects_non_pdf(client):
    r = _post(client, b"GIF89a not a pdf")
    assert r.status_code == 400
    assert "not a PDF" in r.json()["detail"]


def test_size_limit(client, monkeypatch):
    monkeypatch.setenv("PDF2LATEX_MAX_FILE_MB", "1")
    big = fx.multi_font_pdf() + b"0" * (1024 * 1024 + 10)
    assert _post(client, big).status_code == 413


def test_page_limit(client, monkeypatch):
    import pymupdf
    monkeypatch.setenv("PDF2LATEX_MAX_PAGES", "2")
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    r = _post(client, doc.tobytes())
    assert r.status_code == 422
    assert "limit is 2" in r.json()["detail"]


def test_job_lifecycle_new_project(client):
    r = _post(client, fx.multi_font_pdf(), project_name="Report")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["project_id"] == "proj-new" and body["project_created"] is True
    assert body["page_count"] == 1
    assert client.started[0][:3] == ("user-api", "proj-new", False)
    assert client.started[0][3] == b"%PDF-"

    st = client.get(f"/api/convert/pdf/{body['job_id']}")
    assert st.status_code == 200
    data = st.json()
    assert data["status"] == "done" and "owner" not in data


def test_existing_project_checks_access(client, monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_convert, "_supabase_or_503", lambda: object())
    monkeypatch.setattr(pdf_convert, "verify_project_ownership_or_member",
                        lambda sb, pid, uid, is_guest=False: calls.append((pid, uid)))
    r = _post(client, fx.multi_font_pdf(), project_id="proj-existing", overwrite="true")
    assert r.status_code == 202
    assert calls == [("proj-existing", "user-api")]
    assert client.started[-1][1:3] == ("proj-existing", True)


def test_one_active_job_per_user(client):
    jobs.create_job("user-api", "p", "running.pdf", 1)  # stays "queued"
    r = _post(client, fx.multi_font_pdf())
    assert r.status_code == 409
    assert r.json()["job_id"]


def test_cancel_previous_job(client):
    old = jobs.create_job("user-api", "p", "running.pdf", 1)
    r = _post(client, fx.multi_font_pdf(), cancel_previous="true")
    assert r.status_code == 202
    assert jobs.load_job(old["job_id"])["status"] == "error"


def test_cancel_endpoint(client):
    j = jobs.create_job("user-api", "p", "running.pdf", 1)
    r = client.post(f"/api/convert/pdf/{j['job_id']}/cancel")
    assert r.status_code == 200
    assert jobs.load_job(j["job_id"])["status"] == "cancelled"


def test_jobs_are_private(client):
    other = jobs.create_job("someone-else", "p", "x.pdf", 1)
    assert client.get(f"/api/convert/pdf/{other['job_id']}").status_code == 404
    assert client.get("/api/convert/pdf/not-a-job-id").status_code == 404


def test_commit_requires_pending_state(client):
    st = jobs.create_job("user-api", "p", "x.pdf", 1)
    jobs.update_job(st["job_id"], status="done")
    r = client.post(f"/api/convert/pdf/{st['job_id']}/commit", json={"overwrite": True})
    assert r.status_code == 409
    r = client.post(f"/api/convert/pdf/{st['job_id']}/commit", json={"target_path": "../evil.tex"})
    assert r.status_code == 422
