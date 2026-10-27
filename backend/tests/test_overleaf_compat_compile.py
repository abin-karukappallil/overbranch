"""
Overleaf-compatible project compiles and imports (real TeX where it matters).

- the editor's open file is overlaid at its own path and the project's MAIN document
  is compiled, never the open file (CompileRequest.active_file / active_text)
- a main document in a sub-folder compiles from its own directory (latexmk -cd):
  relative \\input, \\graphicspath figures, bibliography
- placeholder images never shadow or overwrite a real figure
- multi-project archives import as N projects; % !TeX root is honoured
- no service secret reaches the TeX process; \\input{|cmd} is refused
- fontspec families the server lacks are substituted in the compile copy only
- a class that loads hyperref itself gets no option clash from the injected hyperref
- a timeout kills the whole process group
"""

import base64
import io
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import compiler
import project_storage
import tex_sandbox
from auth import get_current_user_or_guest
from routes import project_import as pi

needs_tex = pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                               reason="needs latexmk + pdflatex")
B = "\\"


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    base = (tmp_path / "projects").resolve()
    base.mkdir()
    monkeypatch.setattr(project_storage, "UPLOADS_BASE_DIR", base)
    monkeypatch.setenv("UPLOADS_BASE_DIR", str(base))

    def no_supabase():
        raise RuntimeError("no supabase in tests")
    monkeypatch.setattr(project_storage, "get_supabase_client", no_supabase)
    return base


def make_project(base: Path, pid: str, files: dict) -> Path:
    root = base / pid
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            p.write_bytes(data)
        else:
            p.write_text(data, encoding="utf-8")
    return root


def png_bytes(color=(200, 30, 30)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="PNG")
    return buf.getvalue()


def pdf_text(res: dict) -> str:
    import fitz
    doc = fitz.open(stream=base64.b64decode(res["pdf_base64"]), filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


# --- active_file overlay -> main document ------------------------------------------------

@needs_tex
def test_active_file_overlay_compiles_the_main_document(uploads):
    root = make_project(uploads, "p-overlay", {
        "main.tex": B + "documentclass{article}\n" + B + "begin{document}\nMAINTITLE\n"
                    + B + "input{chapter1}\n" + B + "end{document}\n",
        "chapter1.tex": "DISKCHAPTER\n",
        # a second root document that must NOT be built just because it exists
        "reviews/review.tex": B + "documentclass{article}" + B + "begin{document}REVIEWDOC" + B + "end{document}\n",
    })
    res = compiler.compile_latex("ignored", engine="pdfLaTeX", project_id="p-overlay", persist_synctex=False,
                                 active_file="chapter1.tex", active_text="LIVEBUFFER edited text\n")
    assert res["success"], res.get("error_log")
    assert res["main_file"] == "main.tex"
    text = pdf_text(res)
    assert "MAINTITLE" in text and "LIVEBUFFER" in text
    assert "DISKCHAPTER" not in text and "REVIEWDOC" not in text
    assert (root / "chapter1.tex").read_text() == "DISKCHAPTER\n"  # the overlay is compile-only


@needs_tex
def test_active_file_that_is_itself_a_document_still_builds_main(uploads):
    make_project(uploads, "p-standalone", {
        "main.tex": B + "documentclass{article}" + B + "begin{document}THEMAIN" + B + "end{document}\n",
        "notes.tex": B + "documentclass{article}" + B + "begin{document}NOTES" + B + "end{document}\n",
    })
    res = compiler.compile_latex("", project_id="p-standalone", persist_synctex=False,
                                 active_file="notes.tex", active_text=B + "documentclass{article}"
                                 + B + "begin{document}NOTESEDIT" + B + "end{document}\n")
    assert res["success"] and res["main_file"] == "main.tex"
    assert "THEMAIN" in pdf_text(res) and "NOTES" not in pdf_text(res)


def test_compile_request_accepts_active_file_fields():
    import main
    fields = main.CompileRequest.model_fields
    assert "active_file" in fields and "active_text" in fields
    req = main.CompileRequest(latex_code="x")
    assert req.active_file is None and req.active_text is None


# --- main document in a sub-folder -------------------------------------------------------

@needs_tex
def test_subfolder_main_with_relative_input_figure_and_bib(uploads):
    real_png = png_bytes()
    root = make_project(uploads, "p-thesis", {
        "thesis/thesis.tex": B + "documentclass{article}\n" + B + "usepackage{graphicx}\n"
                             + B + "graphicspath{{figures/}}\n" + B + "begin{document}\n"
                             + B + "input{chapters/one}\n" + B + "includegraphics[width=2cm]{plot}\n"
                             + B + "cite{k}\n" + B + "bibliographystyle{plain}\n" + B + "bibliography{refs}\n"
                             + B + "end{document}\n",
        "thesis/chapters/one.tex": "CHAPTERONE text\n",
        "thesis/figures/plot.png": real_png,
        "thesis/refs.bib": "@book{k, title={BIBTITLE}, author={A. Author}, year=2020, publisher={P}}\n",
    })
    project_storage.set_main_document("p-thesis", "thesis/thesis.tex")
    res = compiler.compile_latex("", project_id="p-thesis", persist_synctex=False,
                                 active_file="thesis/chapters/one.tex", active_text="CHAPTERONE live\n")
    assert res["success"], res.get("error_log")
    assert res["main_file"] == "thesis/thesis.tex"
    assert res["engine_used"].startswith("latexmk")
    text = pdf_text(res)
    assert "CHAPTERONE live" in text and "BIBTITLE" in text
    assert "SAMPLE IMAGE" not in text
    assert not res["errors"], res["errors"]
    assert (root / "thesis/figures/plot.png").read_bytes() == real_png
    assert not (root / "plot.png").exists() and not (root / "thesis/plot.png").exists()


# --- placeholders never shadow real figures ----------------------------------------------

def test_placeholder_never_overwrites_or_shadows_a_real_figure(tmp_path):
    real = png_bytes()
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "plot.png").write_bytes(real)
    doc = (B + "graphicspath{{figures/}}" + B + "includegraphics{plot}\n"
           + B + "includegraphics{figures/plot}\n" + B + "includegraphics{figures/plot.png}\n")
    written = compiler.ensure_sample_images_exist(doc, tmp_path)
    assert written == []
    assert (tmp_path / "figures" / "plot.png").read_bytes() == real
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == \
        ["figures/plot.png"]


def test_recursive_search_finds_figure_without_graphicspath(tmp_path):
    (tmp_path / "assets" / "img").mkdir(parents=True)
    (tmp_path / "assets" / "img" / "logo.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "eps").mkdir()
    (tmp_path / "eps" / "diagram.eps").write_bytes(b"%!PS")
    assert compiler.ensure_sample_images_exist(B + "includegraphics{logo}" + B + "includegraphics{diagram}",
                                               tmp_path) == []


def test_placeholder_only_for_truly_missing_target(tmp_path):
    written = compiler.ensure_sample_images_exist(B + "includegraphics[width=3cm]{missing/fig}", tmp_path)
    assert written == ["missing/fig.png"]
    assert (tmp_path / "missing" / "fig.png").is_file()
    # macros in the path are left to TeX
    assert compiler.ensure_sample_images_exist(B + "includegraphics{" + B + "figdir/x}", tmp_path) == []


# --- import: multi-project, % !TeX root, files stay put -----------------------------------

@pytest.fixture
def client(uploads):
    app = FastAPI()
    app.include_router(pi.router, prefix="/api/projects")
    app.dependency_overrides[get_current_user_or_guest] = lambda: {"user_id": "u1", "is_guest": False}
    app.dependency_overrides[pi._rate_limit] = lambda: None
    return TestClient(app)


def zip_of(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for rel, data in files.items():
            zf.writestr(rel, data)
    return buf.getvalue()


DOC = B + "documentclass{article}\n" + B + "begin{document}\nx\n" + B + "end{document}\n"


def test_multi_project_zip_imports_each_folder(client, uploads):
    data = zip_of({
        "Proj A/main.tex": DOC, "Proj A/conversations/c.json": "{}",
        "Proj B/main.tex": DOC, "Proj B/reviews/review.tex": DOC,
        "Proj C/paper.tex": DOC,
    })
    r = client.post("/api/projects/import-zip", files={"file": ("export.zip", data, "application/zip")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["projects_count"] == 3 and len(body["projects"]) == 3
    by_folder = {p["folder"]: p for p in body["projects"]}
    assert set(by_folder) == {"Proj A", "Proj B", "Proj C"}
    assert by_folder["Proj B"]["main_file"] == "main.tex"  # a root main.tex beats reviews/review.tex
    assert by_folder["Proj C"]["main_file"] == "paper.tex"
    assert body["project_id"] == body["projects"][0]["project_id"]  # back-compat top level
    rootc = uploads / by_folder["Proj C"]["project_id"]
    assert (rootc / "paper.tex").is_file() and not (rootc / "main.tex").exists()
    assert (uploads / by_folder["Proj A"]["project_id"] / "conversations" / "c.json").is_file()


def test_single_project_with_subfolder_main_is_not_moved(client, uploads):
    data = zip_of({"thesis/thesis.tex": DOC.replace("x", B + "input{ch}"), "thesis/ch.tex": "c",
                   "figures/a.png": b"png", ".latexmkrc": "$pdf_mode=1;\n", ".git/config": "x",
                   ".DS_Store": "x", "__MACOSX/._thesis.tex": "x"})
    body = client.post("/api/projects/import-zip", files={"file": ("p.zip", data, "application/zip")}).json()
    assert body["projects_count"] == 1 and body["main_file"] == "thesis/thesis.tex"
    root = uploads / body["project_id"]
    assert (root / "thesis" / "thesis.tex").is_file() and not (root / "main.tex").exists()
    assert (root / ".latexmkrc").is_file()  # stored (never executed)
    assert not (root / ".git").exists() and not (root / ".DS_Store").exists()
    assert project_storage.get_main_document(body["project_id"]) == "thesis/thesis.tex"


def test_tex_root_magic_comment_is_honoured(client):
    data = zip_of({
        "a-notes.tex": DOC,                                   # shallower, alphabetical first
        "src/paper.tex": DOC.replace("x", B + "input{sections/intro}"),
        "src/sections/intro.tex": "% !TeX root = ../paper.tex\nIntro\n",
    })
    body = client.post("/api/projects/import-zip", files={"file": ("p.zip", data, "application/zip")}).json()
    assert body["main_file"] == "src/paper.tex"


def test_detect_main_prefers_root_main_then_shallowest_real_document():
    heads = {"main.tex": DOC, "z/x.tex": DOC, "b.tex": "chapter only", "a/b.tex": DOC}
    assert project_storage.detect_main_document(heads.get, list(heads)) == "main.tex"
    heads.pop("main.tex")
    assert project_storage.detect_main_document(heads.get, list(heads)) == "a/b.tex"
    commented = {"x.tex": "% " + B + "documentclass{article}\n% " + B + "begin{document}\n", "y/y.tex": DOC}
    assert project_storage.detect_main_document(commented.get, list(commented)) == "y/y.tex"


def test_main_document_storage_marker(uploads):
    make_project(uploads, "p-main", {"sub/doc.tex": DOC, "main.tex": DOC})
    assert project_storage.get_main_document("p-main") == "main.tex"
    project_storage.set_main_document("p-main", "sub/doc.tex")
    assert project_storage.get_main_document("p-main") == "sub/doc.tex"
    project_storage.set_main_document("p-main", "main.tex")
    assert not (uploads / "p-main" / project_storage.MAIN_MARKER).exists()
    with pytest.raises(Exception):
        project_storage.set_main_document("p-main", "../escape.tex")


# --- secrets / sandbox -------------------------------------------------------------------

def test_tex_env_is_an_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk-canary-123")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-canary-456")
    env = tex_sandbox.project_tex_env(tmp_path, tmp_path / "sub")
    assert "SUPABASE_SERVICE_ROLE_KEY" not in env and "OPENROUTER_API_KEY" not in env
    assert env["openout_any"] == "p" and env["openin_any"] == "p"
    assert env["TEXINPUTS"].startswith(".:") and env["TEXINPUTS"].endswith(":")
    assert f"{tmp_path}//" in env["TEXINPUTS"] and f"{tmp_path}//" in env["BIBINPUTS"]
    assert "shell_escape" not in env  # TeX Live's default restricted mode, like Overleaf


@needs_tex
def test_secrets_never_reach_the_tex_log(monkeypatch):
    canary = "CANARYSECRETVALUE9137"
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", canary)
    monkeypatch.setenv("BETTER_AUTH_SECRET", canary)
    doc = (B + "documentclass{article}\n" + B + "begin{document}\n"
           + B + "newread" + B + "f " + B + "openin" + B + "f=/proc/self/environ\n"
           + B + "ifeof" + B + "f NOENV" + B + "else" + B + "read" + B + "f to" + B + "l "
           + B + "typeout{ENV=" + B + "detokenize" + B + "expandafter{" + B + "l}}" + B + "fi\n"
           + B + "input{|\"cat /proc/self/environ\"}\n"
           + B + "end{document}\n")
    res = compiler.compile_latex(doc, engine="pdfLaTeX", persist_synctex=False, allow_recovery=False,
                                 pre_heal=False)
    blob = " ".join(str(res.get(k) or "") for k in ("log", "error_log", "raw_log", "errors"))
    assert "ENV=" in blob and "PATH=" in blob  # the read happened and IS in the log (TL 2026
    #   ignores openin_any) — only the allowlist keeps the secrets out of it
    assert canary not in blob
    # restricted shell escape refuses the pipe: TeX looks for a FILE literally named |"cat ..."
    assert "cat /proc/self/environ" in blob


def test_timeout_kills_the_whole_process_group(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        tex_sandbox.run_tex_process(["sh", "-c", "sleep 300 & echo $! > child.pid; wait"],
                                    cwd=tmp_path, timeout=1, env=tex_sandbox.build_tex_env())
    child = int((tmp_path / "child.pid").read_text())
    time.sleep(0.3)
    try:
        os.kill(child, 0)
        alive = Path(f"/proc/{child}/stat").read_text().split()[2] != "Z"
    except ProcessLookupError:
        alive = False
    assert not alive


# --- fonts / hyperref --------------------------------------------------------------------

def test_font_substitution_rewrites_compile_copy_only_and_keeps_lines():
    src = (B + "documentclass{article}\n" + B + "usepackage{fontspec}\n"
           + B + "setmainfont{Calibri}[Ligatures=TeX]\n" + B + "setmonofont{Consolas}\n"
           + B + "newfontfamily" + B + "lato{Lato}[Path=./fonts/, Extension=.ttf]\n"
           + "% " + B + "setsansfont{Cambria}\n" + B + "begin{document}x" + B + "end{document}\n")
    out, subs = compiler.substitute_missing_fonts(src)
    if not subs:
        pytest.skip("Calibri/Consolas installed on this host")
    assert ("Calibri", "Carlito") in subs
    assert out.count("\n") == src.count("\n")
    assert "Path=./fonts/" in out and "{Lato}" in out          # project font files untouched
    assert "% " + B + "setsansfont{Cambria}" in out            # comments untouched


@needs_tex
def test_missing_fontspec_family_compiles_with_notice(uploads):
    if shutil.which("xelatex") is None:
        pytest.skip("needs xelatex")
    make_project(uploads, "p-font", {
        "main.tex": "% !TEX program = xelatex\n" + B + "documentclass{article}\n" + B + "usepackage{fontspec}\n"
                    + B + "setmainfont{Calibri}\n" + B + "begin{document}\n" + B + "input{body}\n"
                    + B + "end{document}\n",
        "body.tex": "Visible body text. " * 80,
    })
    res = compiler.compile_latex("", project_id="p-font", persist_synctex=False,
                                 active_file="body.tex", active_text="Visible body text. " * 80)
    assert res["success"], res.get("error_log")
    assert "Visible body text" in pdf_text(res)
    if res.get("notices"):
        assert "Calibri" in res["notices"][0]


@needs_tex
def test_injected_hyperref_does_not_clash_with_a_class_that_loads_it(tmp_path):
    if not shutil.which("kpsewhich") or not subprocess.run(["kpsewhich", "papertex.cls"],
                                                          capture_output=True).stdout.strip():
        pytest.skip("papertex.cls not installed")
    doc = (B + "documentclass{papertex}\n" + B + "begin{document}\nText " + B + "cite{k}.\n"
           + B + "begin{thebibliography}{9}" + B + "bibitem{k} K." + B + "end{thebibliography}\n"
           + B + "end{document}\n")
    res = compiler.compile_latex(doc, engine="pdfLaTeX", persist_synctex=False, allow_recovery=False,
                                 pre_heal=False)
    assert res["success"]
    assert not any("Option clash" in e for e in res.get("errors") or []), res.get("errors")


@needs_tex
def test_compile_route_honours_active_file(uploads, monkeypatch):
    import main
    from collab import room_manager
    monkeypatch.setattr(room_manager, "get", lambda pid: None)
    make_project(uploads, "p-route", {
        "main.tex": B + "documentclass{article}" + B + "begin{document}ROUTEMAIN " + B + "input{ch}" + B + "end{document}\n",
        "ch.tex": "OLDCH\n",
    })
    main.app.dependency_overrides[get_current_user_or_guest] = lambda: {}
    try:
        r = TestClient(main.app).post("/api/compile", json={
            "latex_code": "NEWCH from the editor\n", "project_id": "p-route", "engine": "pdfLaTeX",
            "active_file": "ch.tex", "active_text": "NEWCH from the editor\n"})
    finally:
        main.app.dependency_overrides.pop(get_current_user_or_guest, None)
    body = r.json()
    assert r.status_code == 200 and body["success"], body.get("error_log")
    assert body["main_file"] == "main.tex"
    text = pdf_text(body)
    assert "ROUTEMAIN" in text and "NEWCH" in text and "OLDCH" not in text
