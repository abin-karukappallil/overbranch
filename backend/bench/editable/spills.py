"""Per source page: which output pages it occupies and how far it overflows (pt of text on the
extra pages). Usage: spills.py OUTDIR [OUTDIR...] (each with gates.json + main.pdf)."""
import json
import pathlib
import sys

import pymupdf


def rows(pdf):
    out = {}
    with pymupdf.open(pdf) as d:
        for pg in d:
            h = pg.rect.height
            ys = []
            for b in pg.get_text("dict")["blocks"]:
                for ln in b.get("lines", []):
                    if any(sp["text"].strip() for sp in ln["spans"]):
                        ys.append((ln["bbox"][1], ln["bbox"][3]))
            imgs = [(i["bbox"][1], i["bbox"][3]) for i in pg.get_image_info()]
            out[pg.number + 1] = (ys + imgs, h)
    return out


for d in sys.argv[1:]:
    d = pathlib.Path(d)
    g = json.loads((d / "gates.json").read_text())
    land = {int(k): v for k, v in g["page_start"]["landing"].items() if "." not in k}
    n_out = g["gates"]["pages_out"]
    r = rows(d / "main.pdf")
    print(f"== {d.name}: {g['gates']['pages_source']} -> {n_out}; page_start {g['gates']['page_start']}")
    keys = sorted(land)
    for i, k in enumerate(keys):
        nxt = land[keys[i + 1]] if i + 1 < len(keys) else n_out + 1
        extra = list(range(land[k] + 1, nxt))
        if extra or land[k] != k:
            info = []
            for e in extra:
                ys, h = r.get(e, ([], 0))
                body = [y for y in ys if 60 < y[0] < h - 60]
                info.append(f"p{e}:{(max(y[1] for y in body) - min(y[0] for y in body)) if body else 0:.0f}pt")
            print(f"  src {k} -> out {land[k]}  extra {info}")
