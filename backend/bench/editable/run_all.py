"""Run the deterministic editable CLI on the acceptance PDFs in parallel and print one table.

    .venv/bin/python bench/editable/run_all.py OUTDIR [name-filter ...]

Each PDF's output goes to OUTDIR/<short name>/ (main.tex, main.pdf, gates.json, err.txt).
"""
import concurrent.futures as cf
import json
import pathlib
import re
import subprocess
import sys
import time

PDFS = [
    "/home/abin/Ryve_report.pdf",
    "/home/abin/Seminar Report - Report Format.pdf",
    "/home/abin/abelpaper.pdf",
    "/home/abin/resume.pdf",
    "/home/abin/CET362-QP.pdf",
    "/home/abin/newtest.pdf",
    "/home/abin/Explainable Artificial Intelligence (XAI) for Malware Analysis_ A Survey of "
    "Techniques, Applications, and Open Challenges - myreport.pdf",
    "/home/abin/atlastfinal.pdf",
]
BACKEND = pathlib.Path(__file__).resolve().parents[2]


def short(pdf: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", pathlib.Path(pdf).stem)[:24].strip("_")


def run(pdf: str, root: pathlib.Path):
    out = root / short(pdf)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = subprocess.run([str(BACKEND / ".venv/bin/python"), "-m", "pdf2latex.editable", pdf,
                        "--out", str(out), "--gates", "--max-pages", "120"],
                       cwd=str(BACKEND), capture_output=True, text=True, timeout=1800)
    (out / "err.txt").write_text(r.stderr)
    (out / "stdout.txt").write_text(r.stdout)
    res = None
    gj = out / "gates.json"
    if gj.exists():
        try:
            res = json.loads(gj.read_text())
        except Exception:
            res = None
    return pdf, res, time.time() - t0, r.returncode


def fmt(v):
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def main():
    root = pathlib.Path(sys.argv[1])
    flt = sys.argv[2:]
    pdfs = [p for p in PDFS if not flt or any(f.lower() in p.lower() for f in flt)]
    rows = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for pdf, res, dt, rc in ex.map(lambda p: run(p, root), pdfs):
            rows.append((pdf, res, dt, rc))
    print(f"{'pdf':24} {'pages':>9} {'pstart':>6} {'figpos':>7} {'cov':>6} {'extra':>6} {'order':>6} "
          f"{'style':>6} {'chrome':>6} {'cmp':>3} {'sec':>5}  failed / spills")
    for pdf, res, dt, rc in rows:
        name = short(pdf)
        if not res:
            print(f"{name:24} FAILED rc={rc} ({dt:.0f}s)")
            continue
        g = res.get("gates", {})
        ps = res.get("page_start", {}) or {}
        fp = res.get("figure_position", {}) or {}
        ch = res.get("chrome_style", {}) or {}
        pages = f"{g.get('pages_source')}->{g.get('pages_out')}"
        figs = f"{fp.get('ok', 0)}/{fp.get('total', 0)}" if fp else "-"
        spills = ps.get("misplaced", [])
        print(f"{name:24} {pages:>9} {fmt(g.get('page_start', '-')):>6} {figs:>7} "
              f"{fmt(g.get('coverage')):>6} {fmt(g.get('extra_ratio')):>6} {fmt(g.get('order')):>6} "
              f"{fmt(g.get('style')):>6} {fmt(ch.get('family', '-')):>6} "
              f"{res.get('compiles', '-'):>3} {dt:5.0f}  {res.get('failed')} {spills[:12]}")


if __name__ == "__main__":
    main()
