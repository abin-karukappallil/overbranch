import os
import shutil

import pymupdf
from PIL import Image
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import project_storage
import synctex_service
from auth import get_current_user_or_guest
from compiler import _save_synctex_artifacts, generate_pdf_preview_image


def write_pdf(path, text, *, landscape=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        width, height = (400, 300) if landscape else (300, 400)
        page = doc.new_page(width=width, height=height)
        page.insert_text((50, 100), text, fontsize=16)
        doc.save(path)


def write_tex(path, text):
    path.write_text(
        r"\documentclass{article}\begin{document}" + text + r"\end{document}",
        encoding="utf-8",
    )


@pytest.fixture
def preview_workspace(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    monkeypatch.setenv("UPLOADS_BASE_DIR", str(uploads))
    monkeypatch.setattr(project_storage, "UPLOADS_BASE_DIR", uploads)
    monkeypatch.setattr(synctex_service, "SYNCTEX_CACHE_DIR", tmp_path / "synctex")
    monkeypatch.setattr(project_storage, "get_supabase_client", object)
    monkeypatch.setattr(project_storage, "verify_project_access", lambda *_: None)
    monkeypatch.setattr(project_storage, "_preview_compile_tasks", {})
    monkeypatch.setattr(project_storage, "_preview_retry_after", project_storage.OrderedDict())

    app = FastAPI()
    app.include_router(project_storage.router)
    app.dependency_overrides[get_current_user_or_guest] = lambda: {"user_id": "test_user"}
    with TestClient(app) as client:
        yield uploads / "test-project", client


def test_generate_pdf_preview_image(tmp_path):
    pdf = tmp_path / "main.pdf"
    write_pdf(pdf, "Preview Test Page")
    png = tmp_path / "preview.png"
    assert generate_pdf_preview_image(pdf, png)
    with Image.open(png) as image:
        assert image.width == 480


def test_save_synctex_artifacts_generates_one_preview(tmp_path, monkeypatch, preview_workspace):
    project, _ = preview_workspace
    work = tmp_path / "work"
    write_pdf(work / "main.pdf", "OverBranch First Page")

    import compiler

    calls = []

    def render(*args, **kwargs):
        calls.append(args)
        return generate_pdf_preview_image(*args, **kwargs)

    monkeypatch.setattr(compiler, "generate_pdf_preview_image", render)
    _save_synctex_artifacts(work, project.name)
    previews = [directory / "preview.webp" for directory in (
        synctex_service.get_project_build_dir(project.name), project / ".build",
    )]
    assert len(calls) == 1
    assert previews[0].read_bytes() == previews[1].read_bytes()


def test_newer_pdf_replaces_older_webp_and_supports_conditional_requests(preview_workspace):
    project, client = preview_workspace
    pdf = project / ".build" / "main.pdf"
    webp = pdf.with_name("preview.webp")
    url = f"/api/projects/preview?project_id={project.name}"
    write_pdf(pdf, "Old portrait page")
    assert generate_pdf_preview_image(pdf, webp)
    old_mtime = webp.stat().st_mtime_ns

    old = client.get(url)
    assert old.status_code == 200
    assert old.headers["cache-control"] == "private, no-cache"
    unchanged = client.get(url, headers={"If-None-Match": old.headers["etag"]})
    assert unchanged.status_code == 304
    assert unchanged.content == b""

    write_pdf(pdf, "New landscape page", landscape=True)
    now = max(pdf.stat().st_mtime_ns, old_mtime + 1)
    os.utime(pdf, ns=(now, now))
    fresh = client.get(url, headers={"If-None-Match": old.headers["etag"]})
    assert fresh.status_code == 200
    assert fresh.headers["etag"] != old.headers["etag"]
    assert fresh.content != old.content
    assert "x-preview-fallback" not in fresh.headers


@pytest.mark.skipif(not shutil.which("pdflatex"), reason="TeX is unavailable")
def test_saved_edits_and_main_document_changes_refresh_preview(preview_workspace):
    project, client = preview_workspace
    project.mkdir(parents=True)
    main = project / "main.tex"
    alternate = project / "alternate.tex"
    write_tex(main, "First saved page")
    write_tex(alternate, "Alternate main document")
    url = f"/api/projects/preview?project_id={project.name}"

    first = client.get(url)
    assert first.headers["x-preview-pending"] == "true"
    compiled = client.get(f"{url}&wait=true")
    assert compiled.status_code == 200
    assert "x-preview-fallback" not in compiled.headers

    write_tex(main, "Edited first saved page")
    validator = {"If-None-Match": compiled.headers["etag"]}
    stale = client.get(url, headers=validator)
    assert stale.headers["x-preview-fallback"] == "true"
    assert stale.headers["x-preview-pending"] == "true"
    assert stale.content == compiled.content
    updated = client.get(f"{url}&wait=true", headers=validator)
    assert updated.status_code == 200
    assert updated.content != compiled.content

    marker = project / project_storage.MAIN_MARKER
    marker.write_text(alternate.name, encoding="utf-8")
    switched = client.get(f"{url}&wait=true", headers={"If-None-Match": updated.headers["etag"]})
    assert switched.status_code == 200
    with pymupdf.open(project / ".build" / "main.pdf") as doc:
        assert "Alternate main document" in doc[0].get_text()

    marker.unlink()
    reset = client.get(f"{url}&wait=true", headers={"If-None-Match": switched.headers["etag"]})
    assert reset.status_code == 200
    with pymupdf.open(project / ".build" / "main.pdf") as doc:
        assert "Edited first saved page" in doc[0].get_text()
