"""
config.py — Environment-driven settings for the PDF → LaTeX pipeline.

Only non-LLM settings live here. The LLM client, base URL, keys and model are the
ones the agentic edit feature uses (providers.router / GEMINI_WEB2API_*).
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_root_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _root_env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_root_env, override=False)
    except ImportError:
        pass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Pdf2LatexSettings:
    concurrency: int
    page_timeout: float
    page_retries: int
    max_compile_repairs: int
    max_file_mb: int
    max_pages: int
    sim_threshold: float
    coverage_target: float
    visual_floor: float
    max_displacement: float
    quality_rerun: bool
    render_dpi: int
    job_dir: Path

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


def get_settings() -> Pdf2LatexSettings:
    """Reads settings from the environment on every call so tests can monkeypatch env vars."""
    job_dir = os.getenv("PDF2LATEX_JOB_DIR") or os.path.join(tempfile.gettempdir(), "overbranch_pdf2latex_jobs")
    return Pdf2LatexSettings(
        concurrency=max(1, _env_int("PDF2LATEX_CONCURRENCY", 4)),
        page_timeout=max(10.0, _env_float("PDF2LATEX_PAGE_TIMEOUT", 180.0)),
        page_retries=max(0, _env_int("PDF2LATEX_PAGE_RETRIES", 2)),
        max_compile_repairs=max(0, _env_int("PDF2LATEX_MAX_COMPILE_REPAIRS", 3)),
        max_file_mb=max(1, _env_int("PDF2LATEX_MAX_FILE_MB", 50)),
        max_pages=max(1, _env_int("PDF2LATEX_MAX_PAGES", 50)),
        # Reported target for the visual score. It is a diagnostic, not a gate: full-page SSIM
        # cannot tell a faithful reflow from a page with text missing (see verify.compare_pages).
        sim_threshold=_env_float("PDF2LATEX_SIM_THRESHOLD", 0.85),
        # The real quality gate: the share of the PDF's words that must survive into the output.
        coverage_target=min(1.0, max(0.0, _env_float("PDF2LATEX_COVERAGE_TARGET", 0.995))),
        # Backstop for a page that has all the words but looks nothing like the original.
        visual_floor=min(1.0, max(0.0, _env_float("PDF2LATEX_VISUAL_FLOOR", 0.55))),
        # How far, in pt, the median word may move from where it sits in the PDF. A faithful
        # re-setting lands around 8-13 pt; an interleaved or mis-spaced page around 40-65 pt.
        max_displacement=max(1.0, _env_float("PDF2LATEX_MAX_DISPLACEMENT", 25.0)),
        quality_rerun=_env_bool("PDF2LATEX_QUALITY_RERUN", True),
        render_dpi=max(36, _env_int("PDF2LATEX_RENDER_DPI", 100)),
        job_dir=Path(job_dir).resolve(),
    )
