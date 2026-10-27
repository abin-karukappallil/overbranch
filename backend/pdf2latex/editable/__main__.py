"""
CLI for editable-mode conversion, for acceptance runs and debugging:

    python -m pdf2latex.editable <pdf> [--out DIR] [--json] [--gates]

Deterministic only (no job system, no LLM polish). With --gates it runs the same compile passes as
the conversion job (compile with repair → heading calibration → page fit, ``pagefit.finish``)
through a local pdflatex, then prints the measured gates (also written to DIR/gates.json).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
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
        from . import pagefit as PF
        ctx = R.EditCtx(out_dir=out)
        tex, _lm, pdf, info = asyncio.run(PF.finish(ctx, extract, dm, tex, lm, PF.async_sync_compile))
        (out / "main.tex").write_text(tex, encoding="utf-8")
        if pdf is None:
            print("COMPILE FAILED", file=sys.stderr)
            return 1
        (out / "main.pdf").write_bytes(pdf)
        from ..config import get_settings
        from . import gates as G
        res = G.run_gates(extract, dm, tex, pdf, get_settings(), out_dir=out)
        res["compiles"] = info.get("compiles")
        res["fit"] = info.get("fit")
        summary = {k: v for k, v in res.items() if k != "page_coverage"}
        (out / "gates.json").write_text(json.dumps(summary, indent=2, default=str))
        print(json.dumps({"gates": res["gates"], "style": res["style"], "lint": res["lint"],
                          "page_start": {k: res["page_start"][k] for k in ("score", "misplaced", "spilled")},
                          "compiles": res["compiles"], "failed": res["failed"]}, indent=2, default=str))
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
