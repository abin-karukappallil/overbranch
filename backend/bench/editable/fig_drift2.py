"""Match figures source->output by intrinsic pixel size; report page and y drift."""
import sys, pymupdf
def figs(path):
    d = pymupdf.open(path); out = []
    for p in d:
        for info in p.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            if x1 - x0 >= 40 and y1 - y0 >= 25:
                out.append(dict(page=p.number + 1, y=round(y0), w=round(x1 - x0), h=round(y1 - y0), px=(info["width"], info["height"])))
    return out, d.page_count
src, ns = figs(sys.argv[1]); dst, nd = figs(sys.argv[2])
used = set(); rows = []
for a in src:
    for i, b in enumerate(dst):
        if i not in used and b["px"] == a["px"]:
            used.add(i); rows.append((a, b)); break
    else:
        # the converter may have cropped the picture to its ink (*_trim.png): a different pixel
        # size, so fall back to the nearest unmatched picture on the same page
        cand = [(abs(b["y"] - a["y"]), i) for i, b in enumerate(dst) if i not in used and b["page"] == a["page"]]
        if cand:
            i = min(cand)[1]
            used.add(i); rows.append((a, dict(dst[i], trimmed=True)))
        else:
            rows.append((a, None))
print(f"pages {ns}->{nd}; src figs {len(src)}, matched {sum(1 for _, b in rows if b)}")
for a, b in rows:
    if b is None:
        print(f"  src p{a['page']} y{a['y']} {a['w']}x{a['h']}  -> NOT FOUND in output"); continue
    flag = "" if b["page"] == a["page"] and abs(b["y"] - a["y"]) <= 20 and abs(b["h"] - a["h"]) <= 8 else "  <-- drift"
    if b.get("trimmed"):
        flag = "  (ink crop: size is the ink box's)" if b["page"] == a["page"] and abs(b["y"] - a["y"]) <= 120 else "  <-- drift"
    print(f"  src p{a['page']} y{a['y']} {a['w']}x{a['h']}  -> out p{b['page']} y{b['y']} {b['w']}x{b['h']}{flag}")
