"""Member-safety pass and happy path of POST /api/projects/import-zip."""
import io
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import project_storage
from auth import get_current_user_or_guest
from routes import project_import as pi


def make_zip(members, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for m in members:
            if isinstance(m, zipfile.ZipInfo):
                zf.writestr(m, b"x")
            else:
                name, data = m
                zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(project_storage, "UPLOADS_BASE_DIR", (tmp_path / "projects").resolve())
    (tmp_path / "projects").mkdir()

    def no_supabase():
        raise RuntimeError("no supabase in tests")
    monkeypatch.setattr(project_storage, "get_supabase_client", no_supabase)

    app = FastAPI()
    app.include_router(pi.router, prefix="/api/projects")
    app.dependency_overrides[get_current_user_or_guest] = lambda: {"user_id": "u1", "is_guest": False, "session_id": "s1"}
    app.dependency_overrides[pi._rate_limit] = lambda: None
    return TestClient(app)


def post(client, data, name="proj.zip", project_name=None):
    form = {"project_name": project_name} if project_name else {}
    return client.post("/api/projects/import-zip", files={"file": (name, data, "application/zip")}, data=form)


def detail(r):
    return r.json()["detail"]


def test_zip_slip(client):
    r = post(client, make_zip([("../etc/passwd", "x")]))
    assert r.status_code == 400 and detail(r) == "unsafe-path"
    r = post(client, make_zip([("a/../../b.tex", "x")]))
    assert detail(r) == "unsafe-path"


def test_absolute_path(client):
    r = post(client, make_zip([("/etc/x", "x")]))
    assert r.status_code == 400 and detail(r) == "unsafe-path"


def test_backslash_traversal(client):
    r = post(client, make_zip([("..\\evil.tex", "x")]))
    assert detail(r) == "unsafe-path"


def test_symlink(client):
    zi = zipfile.ZipInfo("link.tex")
    zi.create_system = 3
    zi.external_attr = (0o120777 << 16)
    r = post(client, make_zip([zi]))
    assert r.status_code == 400 and detail(r) == "unsafe-symlink"


def test_encrypted_flag(client):
    data = bytearray(make_zip([("secret.tex", "x")]))
    # ZipFile.writestr rewrites flag_bits, so set the encryption bit in the raw bytes:
    # local header (PK\x03\x04, flags at +6) and central directory (PK\x01\x02, flags at +8).
    lh = data.index(b"PK\x03\x04")
    cd = data.index(b"PK\x01\x02")
    data[lh + 6] |= 0x1
    data[cd + 8] |= 0x1
    assert zipfile.ZipFile(io.BytesIO(bytes(data))).infolist()[0].flag_bits & 0x1
    r = post(client, bytes(data))
    assert r.status_code == 400 and detail(r) == "encrypted"


def test_oversized_member(client, monkeypatch):
    monkeypatch.setattr(pi, "IMPORT_ZIP_MAX_FILE_MB", 1)
    r = post(client, make_zip([("big.bin", b"\0" * (2 * 1024 * 1024))]))
    assert r.status_code == 400 and detail(r) == "file-too-large"


def test_total_uncompressed_cap(client, monkeypatch):
    monkeypatch.setattr(pi, "IMPORT_ZIP_MAX_UNCOMPRESSED_MB", 1)
    r = post(client, make_zip([(f"f{i}.bin", b"\0" * 600_000) for i in range(3)]))
    assert r.status_code == 400 and detail(r) == "too-large"


def test_upload_too_large(client, monkeypatch):
    monkeypatch.setattr(pi, "IMPORT_ZIP_MAX_MB", 0)
    r = post(client, make_zip([("main.tex", "hi")]))
    assert r.status_code == 413 and detail(r) == "too-large"


def test_ratio_exceeded(client, monkeypatch):
    monkeypatch.setattr(pi, "RATIO_MIN_COMPRESSED_BYTES", 1000)
    # 20 x 1 MB of repetitive data: ~1 KB compressed each, ratio >> 100
    r = post(client, make_zip([(f"z{i}.dat", b"A" * (1024 * 1024)) for i in range(20)]))
    assert r.status_code == 400 and detail(r) == "ratio-exceeded"


def test_hidden_members_filtered_then_empty(client):
    r = post(client, make_zip([(".DS_Store", "x"), ("__MACOSX/._a.tex", "x"), ("p/.git/config", "x")]))
    assert r.status_code == 400 and detail(r) == "empty-archive"


def test_dirs_only_is_empty(client):
    zi = zipfile.ZipInfo("onlydir/")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zi, b"")
    r = post(client, buf.getvalue())
    assert detail(r) == "empty-archive"


def test_not_a_zip(client):
    r = post(client, b"this is not a zip")
    assert r.status_code == 400 and detail(r) == "bad-zip"
    r = post(client, make_zip([("a.tex", "x")]), name="proj.tar")
    assert detail(r) == "bad-zip"


def test_analyze_strips_root_and_hidden(client):
    zf = zipfile.ZipFile(io.BytesIO(make_zip([
        ("paper/main.tex", "\\documentclass{article}"), ("paper/fig/a.png", b"png"),
        ("paper/.hidden", "x"), ("__MACOSX/paper/._main.tex", "x"),
    ])))
    rels = sorted(rel for _, rel in pi.analyze_archive(zf))
    # dotfiles (.latexmkrc, .hidden) are project content now; only VCS/OS junk is dropped
    assert rels == [".hidden", "fig/a.png", "main.tex"]


def test_happy_path_main_tex_kept(client, tmp_path):
    data = make_zip([("proj/main.tex", "\\documentclass{article}"), ("proj/ch/one.tex", "one"), ("proj/img.png", b"\x89PNG")])
    r = post(client, data, name="My Paper.zip")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "My Paper"
    assert body["main_tex_path"] == "main.tex" and body["created_main_tex"] is False
    assert body["files_count"] == 2 and body["assets_count"] == 1
    root = project_storage.UPLOADS_BASE_DIR / body["project_id"]
    assert (root / "ch" / "one.tex").read_text() == "one"
    assert (root / "img.png").read_bytes() == b"\x89PNG"


def test_project_name_override(client):
    r = post(client, make_zip([("main.tex", "x")]), project_name="Custom Name")
    assert r.json()["name"] == "Custom Name"


def test_main_document_recorded_not_moved(client):
    data = make_zip([("sub/a.tex", "just a chapter"), ("paper.tex", "% c\n\\documentclass{article}\nbody"), ("z/b.tex", "\\documentclass{x}")])
    r = post(client, data)
    body = r.json()
    assert r.status_code == 200 and body["created_main_tex"] is False
    assert body["main_file"] == "paper.tex" and body["main_tex_path"] == "paper.tex"
    root = project_storage.UPLOADS_BASE_DIR / body["project_id"]
    assert "documentclass{article}" in (root / "paper.tex").read_text()  # kept at its archived path
    assert not (root / "main.tex").exists()  # no stray seeded main.tex
    assert (root / "sub" / "a.tex").exists() and (root / "z" / "b.tex").exists()
    assert project_storage.get_main_document(body["project_id"]) == "paper.tex"


def test_empty_main_tex_created_when_no_documentclass(client):
    r = post(client, make_zip([("notes.txt", "hello"), ("pic.png", b"p")]))
    body = r.json()
    assert r.status_code == 200 and body["created_main_tex"] is True
    root = project_storage.UPLOADS_BASE_DIR / body["project_id"]
    assert (root / "main.tex").read_text() == ""
