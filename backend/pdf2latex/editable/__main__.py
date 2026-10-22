"""
CLI for editable-mode conversion, for acceptance runs and debugging:

    python -m pdf2latex.editable <pdf> [--out DIR] [--json] [--gates]

Deterministic only (no job system, no LLM polish). With --gates it compiles with pdflatex and
prints the measured gates.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

from ..extract import extract_document
from . import run as R


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pdf2latex.editable")
    ap.add_argument("pdf")
    ap.add_argument("--out", default=None, help="output directory (default: a temp dir)")
    ap.add_argument("--json", action="store_true", help="print the structure summary as JSON")
    ap.add_argument("--gates", action="store_true", help="compile and print the measured gates")
    ap.add_argument("--max-pages", type=int, default=50)
    args = ap.parse_args(argv)

    out = pathlib.Path(args.out) if args.out else pathlib.Path(tempfile.mkdtemp()) / "output"
    out.mkdir(parents=True, exist_ok=True)
    data = pathlib.Path(args.pdf).read_bytes()
    extract, doc = extract_document(data, out, "assets/pdf_cli", args.max_pages)
    tex, dm, lm = R._assemble_enriched(extract, doc, out, args.pdf)
    (out / "main.tex").write_text(tex, encoding="utf-8")
    summary = R.structure_summary(dm)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Wrote {out/'main.tex'}  ({summary['blocks']} blocks, "
              f"{summary['headings']} headings, {summary['lists']} lists, "
              f"{summary['tables']} tables, {summary['figures']} figures)")
    if args.gates:
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                           cwd=str(out), capture_output=True, text=True)
        pdf = out / "main.pdf"
        if not pdf.exists():
            print("COMPILE FAILED", file=sys.stderr)
            return 1
        if R.calibrate_heading_spacing(dm, pdf.read_bytes()):
            from .emit import emit_document
            tex, _lm = emit_document(dm)
            (out / "main.tex").write_text(tex, encoding="utf-8")
            subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                           cwd=str(out), capture_output=True, text=True)
        from ..config import get_settings
        from . import gates as G
        res = G.run_gates(extract, dm, tex, pdf.read_bytes(), get_settings())
        print(json.dumps({"gates": res["gates"], "style": res["style"], "lint": res["lint"],
                          "failed": res["failed"]}, indent=2))
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
