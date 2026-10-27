"""Font family/size usage (by character count) in source vs output."""
import sys, collections, pymupdf
def usage(path):
    c = collections.Counter(); d = pymupdf.open(path)
    for p in d:
        for b in p.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    f = s["font"].split("+")[-1]
                    c[(f, round(s["size"], 1))] += len(s["text"].strip())
    tot = sum(c.values()) or 1
    return [(k, round(100 * v / tot, 1)) for k, v in c.most_common(8)]
for path in sys.argv[1:]:
    print(path.split("/")[-1][:40]); [print("   ", k, v, "%") for k, v in usage(path)]
