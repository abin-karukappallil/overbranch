"""
overleaf_compat.py — does OverBranch build imported projects the way Overleaf does?

For every project in the corpus:

  reference  ``latexmk -pdf|-pdfxe -interaction=nonstopmode -file-line-error <main>`` run
             from the main file's directory (what Overleaf's CLSI does with ``-cd``), on a
             plain extraction of the project, with the caller's normal environment.
  overbranch the real import path (routes.project_import: analyze_archive -> split_projects
             -> _extract, which detects + records the main document) into a scratch
             UPLOADS_BASE_DIR, then compiler.compile_latex in PROJECT mode exactly as the
             editor will call it: active_file = some non-main .tex of the project (the
             open tab), active_text = its text. The compiler must build the MAIN document.

PASS   OverBranch succeeds wherever the reference does, with the same page count, and
       resolved the expected main document.
PASS+  the reference fails, OverBranch builds it (e.g. a missing system font substituted).
SKIP   the reference cannot run on this machine (biber is not installed here).
FAIL   anything else.

Corpus: the two real user zips (Prism multi-project export, "New Project.zip"), the six
projects in backend/bench/corpus, and synthetic projects for the import/compile cases
(main in a sub-folder, % !TeX root, glossaries/nomencl/index, missing fontspec family,
a class that loads hyperref itself, \\include chapters, a project .latexmkrc).

Usage (from backend/):  .venv/bin/python bench/overleaf_compat.py [--keep DIR]
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

ZIPS = [
    Path.home() / "Downloads" / "prism-projects-2026-10-24.zip",
    Path.home() / "Downloads" / "New Project.zip",
]
CORPUS = BACKEND / "bench" / "corpus"
RC_MARKER = "PROJECT-LATEXMKRC-EXECUTED"


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def synthetic_projects() -> Dict[str, Dict[str, object]]:
    """name -> {files: {rel: bytes|str}, main: expected main}"""
    png = _png()
    return {
        "syn-subdir-main": {"main": "thesis/thesis.tex", "files": {
            "thesis/thesis.tex": "\\documentclass{report}\n\\usepackage{graphicx}\n\\graphicspath{{figures/}}\n"
                                 "\\begin{document}\n\\tableofcontents\n\\input{chapters/one}\n\\input{chapters/two}\n"
                                 "\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n",
            "thesis/chapters/one.tex": "\\chapter{One}\\label{c1} See \\cite{knuth} and Fig.~\\ref{f}.\n"
                                       "\\begin{figure}\\centering\\includegraphics[width=4cm]{plot}"
                                       "\\caption{Plot}\\label{f}\\end{figure}\n",
            "thesis/chapters/two.tex": "\\chapter{Two} Back to Chapter~\\ref{c1}.\n",
            "thesis/refs.bib": "@book{knuth, author={D. Knuth}, title={The TeXbook}, year=1984, publisher={AW}}\n",
            "thesis/figures/plot.png": png,
            "README.md": "thesis lives in thesis/\n",
        }},
        "syn-texroot-magic": {"main": "src/paper.tex", "files": {
            "a-standalone-notes.tex": "\\documentclass{article}\\begin{document}Notes\\end{document}\n",
            "src/paper.tex": "\\documentclass{article}\n\\begin{document}\n\\input{sections/intro}\n\\newpage Two\n\\end{document}\n",
            "src/sections/intro.tex": "% !TeX root = ../paper.tex\nIntro text.\n",
        }},
        "syn-glossaries-index": {"main": "main.tex", "files": {
            "main.tex": "\\documentclass{article}\n\\usepackage[acronym]{glossaries}\n\\usepackage{nomencl}\n"
                        "\\usepackage{makeidx}\n\\makeglossaries\n\\makenomenclature\n\\makeindex\n"
                        "\\newacronym{tla}{TLA}{three letter acronym}\n"
                        "\\newglossaryentry{pi}{name={pi},description={a constant}}\n"
                        "\\begin{document}\n\\input{body}\n\\printglossaries\n\\printnomenclature\n"
                        "\\printindex\n\\end{document}\n",
            "body.tex": "\\gls{tla} and \\gls{pi}\\index{foo} \\nomenclature{$x$}{a variable}\n\\newpage\nMore\\index{bar}.\n",
        }},
        "syn-fontspec-calibri": {"main": "main.tex", "files": {
            "main.tex": "% !TEX program = xelatex\n\\documentclass{article}\n\\usepackage{fontspec}\n"
                        "\\setmainfont{Calibri}\n\\setmonofont{Consolas}\n\\begin{document}\n\\input{text}\n\\end{document}\n",
            "text.tex": ("Body text in Calibri, \\texttt{code in Consolas}. " * 40 + "\n\n") * 6,
        }},
        "syn-class-loads-hyperref": {"main": "main.tex", "files": {
            "main.tex": "\\documentclass{papertex}\n\\begin{document}\n\\input{content}\n\\end{document}\n",
            "content.tex": "Text \\cite{k}.\n\\begin{thebibliography}{9}\\bibitem{k} K. Ref.\\end{thebibliography}\n",
        }},
        "syn-include-chapters": {"main": "main.tex", "files": {
            "main.tex": "\\documentclass{book}\n\\begin{document}\n\\tableofcontents\n\\include{chapters/ch1}\n"
                        "\\include{chapters/ch2}\n\\end{document}\n",
            "chapters/ch1.tex": "\\chapter{First} Text.\n",
            "chapters/ch2.tex": "\\chapter{Second} Text, see p.~\\pageref{x}\\label{x}.\n",
            ".latexmkrc": f"print \"{RC_MARKER}\\n\";\n",
        }},
    }


def zip_bytes(files: Dict[str, object]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in files.items():
            zf.writestr(rel, data if isinstance(data, (bytes, str)) else str(data))
    return buf.getvalue()


def dir_zip_bytes(root: Path, prefix: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                zf.write(p, prefix + p.relative_to(root).as_posix())
    return buf.getvalue()


def page_count(pdf: Path) -> int:
    import compiler
    return compiler._pdf_page_count(pdf)


def reference_compile(project_root: Path, main_rel: str, outdir: Path) -> Tuple[str, int, float, str]:
    """(status ok|fail|skip, pages, seconds, note)"""
    import compiler
    main = project_root / main_rel
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in project_root.rglob("*.tex"))
    magic = compiler.detect_magic_engine(main.read_text(encoding="utf-8", errors="replace"))
    flag = {"xelatex": "-pdfxe", "lualatex": "-pdflua"}.get(magic or "", None)
    if flag is None:
        flag = "-pdfxe" if compiler.needs_unicode_engine(text) else "-pdf"
    cmd = ["latexmk", flag, "-interaction=nonstopmode", "-file-line-error", main.name]
    t = time.time()
    try:
        r = subprocess.run(cmd, cwd=main.parent, capture_output=True, timeout=600)
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return "fail", 0, time.time() - t, "timeout"
    dt = time.time() - t
    pdf = main.with_suffix(".pdf")
    note = flag
    if "biber" in out and ("not found" in out.lower() or "Could not run" in out) and shutil.which("biber") is None:
        return "skip", page_count(pdf) if pdf.exists() else 0, dt, "biber not installed here"
    if RC_MARKER in out:
        note += " (ran project latexmkrc)"
    if pdf.exists() and pdf.stat().st_size > 0:
        shutil.copy2(pdf, outdir / "reference.pdf")
        return "ok", page_count(pdf), dt, note
    return "fail", 0, dt, note + " no pdf"


def overbranch_import(data: bytes, name: str) -> List[Dict[str, object]]:
    from routes import project_import as pi
    import project_storage
    zf, members = pi._open_and_analyze(data)
    out = []
    try:
        for folder, group in pi.split_projects(zf, members):
            proj = project_storage.create_empty_project("bench-user", folder or name, None, "ZIP Import")
            res = pi._extract(zf, group, proj["project_id"], None)
            out.append({"project_id": proj["project_id"], "folder": folder, **res})
    finally:
        zf.close()
    return out


def overbranch_compile(project_id: str) -> Dict[str, object]:
    import compiler
    import project_storage
    pdir = project_storage.project_dir(project_id)
    main_rel = project_storage.get_main_document(project_id)
    tex = sorted(p.relative_to(pdir).as_posix() for p in pdir.rglob("*.tex"))
    others = [t for t in tex if t != main_rel]
    active = others[0] if others else main_rel
    active_text = (pdir / active).read_text(encoding="utf-8", errors="replace")
    t = time.time()
    res = compiler.compile_latex("", engine="pdfLaTeX", project_id=project_id, persist_synctex=False,
                                 active_file=active, active_text=active_text)
    res["_seconds"] = time.time() - t
    res["_active"] = active
    res["_stored_main"] = main_rel
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", help="keep the scratch directory here")
    ap.add_argument("--only", help="substring filter on project names")
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)

    scratch = Path(args.keep or tempfile.mkdtemp(prefix="ob-compat-"))
    scratch.mkdir(parents=True, exist_ok=True)
    uploads = scratch / "uploads"
    uploads.mkdir(exist_ok=True)
    os.environ["UPLOADS_BASE_DIR"] = str(uploads)

    import project_storage

    def _no_supabase():
        raise RuntimeError("bench runs disk-only")
    project_storage.UPLOADS_BASE_DIR = uploads.resolve()
    project_storage.get_supabase_client = _no_supabase

    # (label, zip bytes, {folder or None: expected main})
    cases: List[Tuple[str, bytes, Dict[Optional[str], str]]] = []
    for z in ZIPS:
        if not z.exists():
            print(f"!! missing {z}")
            continue
        data = z.read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
        tops = {n.split("/", 1)[0] for n in names if "/" in n}
        expected: Dict[Optional[str], str] = {}
        if all("/" in n for n in names) and len(tops) > 1:
            for t in tops:
                expected[t] = "main.tex"
        else:
            expected[None] = "main.tex"
        cases.append((z.name, data, expected))
    for d in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        cases.append((f"corpus/{d.name}", dir_zip_bytes(d, prefix=f"{d.name}/"), {None: "main.tex"}))
    for name, spec in synthetic_projects().items():
        cases.append((name, zip_bytes(spec["files"]), {None: spec["main"]}))

    rows = []
    for label, data, expected in cases:
        if args.only and args.only not in label:
            continue
        try:
            imported = overbranch_import(data, label)
        except Exception as e:  # pragma: no cover
            rows.append((label, "-", "-", "IMPORT ERROR", "", "", "", "", f"FAIL {e}"))
            continue
        if len(expected) > 1 and len(imported) != len(expected):
            rows.append((label, "-", "-", f"imported {len(imported)} != {len(expected)}", "", "", "", "", "FAIL"))
        for proj in imported:
            folder = proj["folder"]
            name = f"{label}:{folder}" if folder else label
            exp_main = expected.get(folder) if folder in expected else expected.get(None, "main.tex")
            pdir = project_storage.project_dir(proj["project_id"])
            # reference: a plain copy of what was imported (the import keeps archived paths)
            ref_root = scratch / "ref" / proj["project_id"]
            shutil.copytree(pdir, ref_root, ignore=shutil.ignore_patterns(project_storage.MAIN_MARKER))
            outdir = scratch / "out" / proj["project_id"]
            outdir.mkdir(parents=True, exist_ok=True)
            ref_status, ref_pages, ref_s, ref_note = reference_compile(ref_root, exp_main, outdir)
            res = overbranch_compile(proj["project_id"])
            ob_ok = bool(res.get("success"))
            ob_pages = 0
            if ob_ok:
                import base64
                pdf = outdir / "overbranch.pdf"
                pdf.write_bytes(base64.b64decode(res["pdf_base64"]))
                ob_pages = page_count(pdf)
            main_ok = res.get("main_file") == exp_main and proj["main_file"] == exp_main
            rc_kept = (pdir / ".latexmkrc").exists()
            notes = []
            if res.get("notices"):
                notes.append("; ".join(n.split(".")[0] for n in res["notices"]))
            if rc_kept:
                ran = RC_MARKER in (res.get("log") or "") + (res.get("raw_log") or "")
                notes.append(f".latexmkrc stored, {'EXECUTED' if ran else 'not executed'}")
            if not ob_ok:
                notes.append((res.get("error_log") or "")[:160].replace("\n", " | "))
            if not main_ok:
                verdict = "FAIL (main)"
            elif ref_status == "skip":
                verdict = "SKIP"
            elif ref_status == "ok":
                verdict = "PASS" if ob_ok and ob_pages == ref_pages else "FAIL"
            else:
                verdict = "PASS+" if ob_ok else "PASS (both fail)"
            rows.append((name, exp_main, res.get("main_file"),
                         f"{ref_status}/{ref_pages}p {ref_s:.1f}s {ref_note}",
                         f"{'ok' if ob_ok else 'fail'}/{ob_pages}p {res['_seconds']:.1f}s",
                         res.get("engine_used") or "-", res["_active"], "; ".join(notes), verdict))

    headers = ("project", "expected main", "OB main", "reference (latexmk)", "overbranch",
               "OB engine", "active tab sent", "notes", "verdict")
    widths = [max(len(str(r[i])) for r in rows + [headers]) for i in range(len(headers))]
    widths = [min(w, 60) for w in widths]

    def fmt(r):
        return " | ".join(str(c)[:widths[i]].ljust(widths[i]) for i, c in enumerate(r))
    print(fmt(headers))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(fmt(r))
    verdicts = [r[-1] for r in rows]
    fails = [v for v in verdicts if v.startswith("FAIL")]
    print(f"\n{len(rows)} projects: {sum(v == 'PASS' for v in verdicts)} PASS, "
          f"{sum(v == 'PASS+' for v in verdicts)} PASS+, {sum(v == 'SKIP' for v in verdicts)} SKIP, "
          f"{sum(v.startswith('PASS (both') for v in verdicts)} both-fail, {len(fails)} FAIL")
    print(f"scratch: {scratch}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
