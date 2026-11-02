"""
Warm the TeX caches of the tex-runner sidecar before it starts serving.

The runner keeps its fontconfig / luaotfload / TEXMFVAR caches in TEX_RUNNER_TMP (a tmpfs, so
empty on every container start). The first compile of a cold container rebuilds them: seconds
for xelatex, ~47 s measured for lualatex. This compiles one small document per engine in
TEX_RUNNER_WARMUP_ENGINES (default "xelatex") through the runner's own `run_compile`, so the
caches land in exactly the directories real jobs use.

Always exits 0: a failed warm-up only means the first real job pays the cold-start cost.
Run from the image: `python3 /app/docker/tex-runner-warmup.py` (see tex-runner-entrypoint.sh).
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(os.environ.get("TEX_RUNNER_BACKEND") or "/app/backend")))

from tex_runner.compile import ENGINES, run_compile  # noqa: E402

# The fonts the rebuild pipeline maps to (pdf2latex/rebuild/fonts.py) plus the packages a rebuilt
# page typically loads, so their font lookups are cached too.
DOC = r"""\documentclass[11pt]{article}
\usepackage{fontspec}
\IfFontExistsTF{Carlito}{\setmainfont{Carlito}}{}
\IfFontExistsTF{Liberation Sans}{\setsansfont{Liberation Sans}}{}
\IfFontExistsTF{Liberation Mono}{\setmonofont{Liberation Mono}}{}
\IfFontExistsTF{Caladea}{\newfontfamily\cal{Caladea}}{\let\cal\relax}
\IfFontExistsTF{TeX Gyre Termes}{\newfontfamily\gyre{TeX Gyre Termes}}{\let\gyre\relax}
\usepackage{amsmath,array,booktabs,graphicx,xcolor}
\begin{document}
Warm-up. {\sffamily Sans.} {\ttfamily Mono.} {\cal Caladea.} {\gyre TeX Gyre.}
$\sum_{i=1}^{n} x_i^2 = \frac{a}{b}$
\begin{tabular}{ll}\toprule a & b \\ \bottomrule\end{tabular}
\end{document}
"""


def main() -> int:
    wanted = [e.strip() for e in (os.environ.get("TEX_RUNNER_WARMUP_ENGINES") or "xelatex").split(",")]
    engines = [e for e in wanted if e in ENGINES]
    try:
        timeout = float(os.environ.get("TEX_RUNNER_WARMUP_TIMEOUT") or 120)
    except ValueError:
        timeout = 120.0
    root = Path(tempfile.mkdtemp(prefix="tex-warmup-"))
    try:
        for engine in engines:
            work = root / engine
            work.mkdir()
            (work / "main.tex").write_text(DOC, encoding="utf-8")
            result = run_compile(work, "main.tex", engine, timeout, root=root)
            state = "ok" if result.get("ok") else f"failed ({result.get('detail') or result.get('errors')})"
            print(f"tex-runner warm-up: {engine} {state} in {result.get('seconds')}s", flush=True)
    except Exception as exc:  # noqa: BLE001 - a warm-up must never keep the runner from starting
        print(f"tex-runner warm-up skipped: {exc!r}", flush=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
