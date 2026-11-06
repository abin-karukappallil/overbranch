"""
tex_runner — the compile sandbox of the AI-rebuild pipeline.

Runs one LaTeX compile of a directory with shell escape off, paranoid kpathsea file access,
an allowlisted environment, rlimits and a process-group wall-clock kill. The same code runs
in-process (local dev, `pdf2latex.rebuild.sandbox` in `local` mode) and as the `tex-runner`
sidecar container (`python -m tex_runner`, HTTP API in `server.py`).

Import-light on purpose: the sidecar runs this package standalone, so nothing here imports the
rest of the backend. `compile.py` is stdlib only; `server.py` adds FastAPI/uvicorn.
"""

from .compile import ENGINES, run_compile

__all__ = ["ENGINES", "run_compile"]
