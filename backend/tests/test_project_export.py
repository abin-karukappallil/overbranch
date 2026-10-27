"""GET /api/projects/{id}/export.zip and /api/projects/export-all.zip."""
import base64
import io
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import compiler
import project_storage
from auth import get_current_user_or_guest
from routes import project_export as pe
from routes import project_import as pi

needs_tex = pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                               reason="needs latexmk + pdflatex")
B = "\\"
CORPUS = Path(__file__).resolve().parents[1] / "bench" / "corpus"
DOC = B + "documentclass{article}\n" + B + "begin{document}\nHello\n" + B + "end{document}\n"


# ---------------------------------------------------------------------------
# A tiny in-memory Supabase: just the select/eq/limit/execute chain the routes use.
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, rows):
        self.rows, self.filters, self.n = rows, [], None

    def select(self, *_):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def insert(self, row):
        self.rows.append(dict(row))
        return self

    def update(self, _values):
        return self

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        out = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]
        if self.n is not None:
            out = out[: self.n]
        return type("R", (), {"data": out})()


class FakeSB:
    def __init__(self):
        self.tables = {"projects": [], "project_members": [], "guest_projects": [], "latex_documents": []}

    def table(self, name):
        return _Query(self.tables[name])

    def add_project(self, pid, name, owner):
        self.tables["projects"].append({"id": pid, "name": name, "owner_id": owner})


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = (tmp_path / "projects").resolve()
    base.mkdir()
    monkeypatch.setattr(project_storage, "UPLOADS_BASE_DIR", base)
    monkeypatch.setenv("UPLOADS_BASE_DIR", str(base))
    sb = FakeSB()
    monkeypatch.setattr(project_storage, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(pi, "_supabase", lambda: None)  # the importer stays disk-only
    caller = {"user_id": "u1", "is_guest": False, "session_id": "s1"}

    app = FastAPI()
    app.include_router(pi.router, prefix="/api/projects")
    app.include_router(pe.router, prefix="/api/projects")
    app.dependency_overrides[get_current_user_or_guest] = lambda: caller
    app.dependency_overrides[pi._rate_limit] = lambda: None
    app.dependency_overrides[pe._rate_limit] = lambda: None
    return type("Env", (), {"base": base, "sb": sb, "caller": caller, "client": TestClient(app)})()


def make_project(env, pid, files, name=None, owner="u1"):
    root = env.base / pid
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    env.sb.add_project(pid, name or pid, owner)
    return root


def as_bytes(files: dict) -> dict:
    return {k: v if isinstance(v, bytes) else v.encode("utf-8") for k, v in files.items()}


def disk_files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and p.name != project_storage.MAIN_MARKER}


def zip_names(content: bytes):
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return zf.namelist()


def import_zip(env, content: bytes, name="x.zip"):
    r = env.client.post("/api/projects/import-zip", files={"file": (name, content, "application/zip")})
    assert r.status_code == 200, r.text
    return r.json()


def page_count(res) -> int:
    import fitz
    doc = fitz.open(stream=base64.b64decode(res["pdf_base64"]), filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()


def png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------

def test_single_export_shape_and_headers(env):
    make_project(env, "p1", {"main.tex": DOC, "chapters/a.tex": "A", "fig.png": b"\x89PNG-bytes",
                             ".obmain": "main.tex", ".DS_Store": "x", ".git/config": "x",
                             "__MACOSX/._main.tex": "x"}, name="My: Thesis/2024")
    r = env.client.get("/api/projects/p1/export.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    assert "My_ Thesis_2024.zip" in r.headers["content-disposition"]
    assert int(r.headers["content-length"]) == len(r.content)
    names = sorted(zip_names(r.content))
    assert names == ["My_ Thesis_2024/chapters/a.tex", "My_ Thesis_2024/fig.png", "My_ Thesis_2024/main.tex"]


def test_non_member_gets_403(env):
    make_project(env, "secret", {"main.tex": DOC}, owner="someone-else")
    r = env.client.get("/api/projects/secret/export.zip")
    assert r.status_code == 403
    # a member is let in
    env.sb.tables["project_members"].append({"id": "m", "project_id": "secret", "user_id": "u1", "role": "Editor"})
    assert env.client.get("/api/projects/secret/export.zip").status_code == 200


def test_unknown_project_is_404(env):
    assert env.client.get("/api/projects/nope/export.zip").status_code == 404


def test_db_only_text_rows_and_placeholders(env):
    make_project(env, "p2", {"main.tex": DOC, "real.png": png_bytes()})
    env.sb.tables["latex_documents"] += [
        {"project_id": "p2", "file_path": "notes/only-in-db.tex", "raw_code": "from the database"},
        {"project_id": "p2", "file_path": "ghost.png", "raw_code": "[Binary Asset: ghost.png, Size: 99 bytes]"},
        # a row for a file that exists on disk: disk wins, no duplicate member
        {"project_id": "p2", "file_path": "main.tex", "raw_code": "STALE DB COPY"},
        {"project_id": "p2", "file_path": "../evil.tex", "raw_code": "x"},
        {"project_id": "p2", "file_path": "empty.tex", "raw_code": None},
    ]
    r = env.client.get("/api/projects/p2/export.zip")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert len(names) == len(set(names))
        assert sorted(names) == ["p2/empty.tex", "p2/main.tex", "p2/notes/only-in-db.tex", "p2/real.png"]
        assert zf.read("p2/notes/only-in-db.tex") == b"from the database"
        assert zf.read("p2/main.tex") == DOC.encode()
        assert zf.read("p2/real.png") == png_bytes()
        assert zf.testzip() is None


def test_template_class_files_are_included(env):
    tmpl = Path(compiler.__file__).parent / "templates" / "resume" / "63b810f378d656009cf7a813"
    assert (tmpl / "res.cls").is_file()
    make_project(env, "p3", {"main.tex": B + "documentclass{res}\n" + B + "begin{document}\nx\n" + B + "end{document}\n"})
    names = zip_names(env.client.get("/api/projects/p3/export.zip").content)
    assert "p3/res.cls" in names and "p3/main.tex" in names
    assert not any(n.endswith(("metadata.json", "thumbnail.png")) for n in names)
    # a class the project already carries is not overwritten by the template copy
    make_project(env, "p4", {"main.tex": B + "documentclass{res}\n" + B + "begin{document}\nx\n" + B + "end{document}\n",
                             "res.cls": "MY OWN CLASS"})
    with zipfile.ZipFile(io.BytesIO(env.client.get("/api/projects/p4/export.zip").content)) as zf:
        assert zf.read("p4/res.cls") == b"MY OWN CLASS"


def test_flush_runs_before_reading_files(env, monkeypatch):
    root = make_project(env, "p5", {"main.tex": "OLD"})
    calls = []

    async def fake_flush(pid):
        calls.append(pid)
        (root / "main.tex").write_text("FLUSHED EDIT")

    monkeypatch.setattr(pe, "_flush_collab_room", fake_flush)
    r = env.client.get("/api/projects/p5/export.zip")
    assert calls == ["p5"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.read("p5/main.tex") == b"FLUSHED EDIT"


def test_flush_prefers_main_py_helper(env, monkeypatch):
    import sys, types
    calls = []

    async def helper(pid):
        calls.append(pid)

    fake_main = types.SimpleNamespace(_flush_collab_room_before_compile=helper)
    monkeypatch.setitem(sys.modules, "main", fake_main)
    make_project(env, "p6", {"main.tex": DOC})
    assert env.client.get("/api/projects/p6/export.zip").status_code == 200
    assert calls == ["p6"]


def test_round_trip_same_files(env):
    files = {
        "main.tex": B + "documentclass{article}\n" + B + "usepackage{graphicx}\n" + B + "begin{document}\n"
                    + B + "input{chapters/one}\n" + B + "includegraphics{fig.png}\n" + B + "end{document}\n",
        "chapters/one.tex": "Chapter one text.\n",
        "refs.bib": "@book{k,title={T},author={A},year={2020},publisher={P}}\n",
        "fig.png": png_bytes(),
    }
    make_project(env, "orig", files, name="Round Trip")
    exported = env.client.get("/api/projects/orig/export.zip").content
    body = import_zip(env, exported, "Round Trip.zip")
    assert body["projects_count"] == 1
    new_root = env.base / body["project_id"]
    assert disk_files(new_root) == as_bytes(files)
    assert body["main_file"] == "main.tex"


@needs_tex
def test_round_trip_compiles_to_same_page_count(env):
    files = {p.name: p.read_bytes() for p in (CORPUS / "bibliography").iterdir() if p.is_file()}
    make_project(env, "bib", files, name="Bib Corpus")
    main_text = files["main.tex"].decode()
    before = compiler.compile_latex("", project_id="bib", persist_synctex=False,
                                    active_file="main.tex", active_text=main_text)
    assert before["success"], before.get("error_log")

    exported = env.client.get("/api/projects/bib/export.zip").content
    body = import_zip(env, exported)
    assert disk_files(env.base / body["project_id"]) == as_bytes(files)
    after = compiler.compile_latex("", project_id=body["project_id"], persist_synctex=False,
                                   active_file="main.tex", active_text=main_text)
    assert after["success"], after.get("error_log")
    assert page_count(after) == page_count(before)


def test_subfolder_main_round_trips_and_stays_in_place(env):
    files = {"thesis/thesis.tex": DOC, "thesis/ch.tex": "c", "figures/a.png": png_bytes()}
    make_project(env, "th", files, name="Thesis")
    body = import_zip(env, env.client.get("/api/projects/th/export.zip").content)
    assert body["main_file"] == "thesis/thesis.tex"
    assert disk_files(env.base / body["project_id"]) == as_bytes(files)


def test_export_all_reimports_as_n_projects(env):
    make_project(env, "a", {"main.tex": DOC, "x/y.tex": "y"}, name="Alpha")
    make_project(env, "b", {"paper.tex": DOC}, name="Beta")
    make_project(env, "c", {"main.tex": DOC}, name="Alpha")  # duplicate name
    make_project(env, "other", {"main.tex": DOC}, name="Not Mine", owner="someone-else")
    env.sb.tables["project_members"].append({"id": "m", "project_id": "c", "user_id": "u1", "role": "Editor"})
    env.sb.tables["projects"][2]["owner_id"] = "someone-else"  # c is mine only as a member

    r = env.client.get("/api/projects/export-all.zip")
    assert r.status_code == 200
    assert "overbranch-projects.zip" in r.headers["content-disposition"]
    names = zip_names(r.content)
    tops = {n.split("/")[0] for n in names}
    assert tops == {"Alpha", "Beta", "Alpha (2)"}
    assert not any(n.startswith("Not Mine") for n in names)

    body = import_zip(env, r.content, "all.zip")
    assert body["projects_count"] == 3
    assert {p["folder"] for p in body["projects"]} == {"Alpha", "Beta", "Alpha (2)"}
    beta = next(p for p in body["projects"] if p["folder"] == "Beta")
    assert beta["main_file"] == "paper.tex"


def test_export_all_without_projects_is_404(env):
    assert env.client.get("/api/projects/export-all.zip").status_code == 404


def test_guest_export_all_lists_only_its_projects(env):
    env.caller.update({"user_id": "guest_g1", "is_guest": True, "session_id": "g1"})
    make_project(env, "g-a", {"main.tex": DOC}, name="Mine", owner="guest_g1")
    make_project(env, "g-b", {"main.tex": DOC}, name="Theirs", owner="guest_g2")
    env.sb.tables["guest_projects"] += [
        {"project_id": "g-a", "guest_session_id": "g1"}, {"project_id": "g-b", "guest_session_id": "g2"}]
    names = zip_names(env.client.get("/api/projects/export-all.zip").content)
    assert {n.split("/")[0] for n in names} == {"Mine"}


def test_safe_name():
    assert pe.safe_name("a/b\\c:d") == "a_b_c_d"
    assert pe.safe_name("  .. ") == "project"
    assert pe.safe_name("Résumé 日本") == "Résumé 日本"
