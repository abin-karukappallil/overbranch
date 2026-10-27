"""Compare figure placements: source PDF vs editable output (page, top y, width), matched in order."""
import sys, pymupdf
def figs(path, min_w=60):
    d = pymupdf.open(path); out = []
    for p in d:
        for info in p.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            if x1 - x0 >= min_w and y1 - y0 >= 30:
                out.append((p.number + 1, round(y0), round(x1 - x0), round(y1 - y0)))
    return sorted(out), d.page_count
src, n_s = figs(sys.argv[1]); dst, n_d = figs(sys.argv[2])
print(f"pages {n_s}->{n_d}  figures {len(src)}->{len(dst)}")
same = 0; drift = []
for a, b in zip(src, dst):
    if a[0] == b[0]: same += 1
    drift.append((a, b, b[0] - a[0], b[1] - a[1], b[3] - a[3]))
print(f"same page: {same}/{min(len(src), len(dst))}")
for a, b, dp, dy, dh in drift:
    if dp or abs(dy) > 20 or abs(dh) > 10:
        print(f"  src p{a[0]} y{a[1]} {a[2]}x{a[3]}  ->  out p{b[0]} y{b[1]} {b[2]}x{b[3]}  (dpage {dp:+d}, dy {dy:+d}, dh {dh:+d})")
