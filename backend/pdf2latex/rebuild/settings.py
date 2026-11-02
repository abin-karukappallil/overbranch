"""
settings.py — Environment-driven settings of the AI-rebuild pipeline.

Re-read on every call (like `pdf2latex.config`) so tests can monkeypatch env vars. Secrets are
never read here: the LLM key comes from `providers.web2api_keys`, the runner token only from
TEX_RUNNER_TOKEN.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import _env_bool, _env_float, _env_int, get_settings


@dataclass(frozen=True)
class RebuildSettings:
    engine: str                 # "rebuild" | "deterministic" (ops switch; deterministic = old editable engine)
    raster_dpi: int             # page PNGs sent to the model / used as the visual reference
    refine_rounds: int          # measure-and-correct rounds per page (1..5)
    max_active_jobs: int        # rebuild jobs running at once in this process; the rest stay queued
    probe_ttl_s: int            # how long a gateway text/vision probe result is trusted
    sandbox_mode: str           # "local" (in-process, same code) | "runner" (HTTP sidecar)
    runner_url: str             # TEX_RUNNER_URL, e.g. http://tex-runner:8001
    runner_token: str           # TEX_RUNNER_TOKEN shared secret
    runner_root: str            # where the runner sees the job directory (compose mounts it at /work)
    compile_timeout_s: int      # per-compile wall clock inside the sandbox
    compile_cpu_s: int          # RLIMIT_CPU per compile
    compile_mem_mb: int         # RLIMIT_AS per compile
    compile_fsize_mb: int       # RLIMIT_FSIZE per compile
    ocr_enabled: bool
    ocr_language: str           # tesseract language(s), e.g. "eng"
    ocr_timeout_s: int
    page_pass_score: float      # match score at/above which a page needs no more correction rounds
    low_confidence_score: float # below this a page is listed in the report as low confidence
    min_gain: float             # a correction round must raise the score by this much to continue
    max_failed_page_share: float  # more failed pages than this → hand the job to the deterministic engine

    @property
    def local_root(self) -> Path:
        """The job directory as seen by this process (confinement root for local compiles)."""
        return get_settings().job_dir


def get_rebuild_settings() -> RebuildSettings:
    engine = (os.getenv("PDF2LATEX_EDITABLE_ENGINE") or "rebuild").strip().lower()
    mode = (os.getenv("TEX_SANDBOX_MODE") or "local").strip().lower()
    return RebuildSettings(
        engine=engine if engine in ("rebuild", "deterministic") else "rebuild",
        raster_dpi=min(200, max(100, _env_int("PDF2LATEX_RASTER_DPI", 150))),
        refine_rounds=min(5, max(1, _env_int("PDF2LATEX_REFINE_ROUNDS", 3))),
        max_active_jobs=max(1, _env_int("PDF2LATEX_MAX_ACTIVE_JOBS", 2)),
        probe_ttl_s=max(30, _env_int("PDF2LATEX_PROBE_TTL", 600)),
        sandbox_mode=mode if mode in ("local", "runner") else "local",
        runner_url=(os.getenv("TEX_RUNNER_URL") or "").strip().rstrip("/"),
        runner_token=os.getenv("TEX_RUNNER_TOKEN") or "",
        runner_root=(os.getenv("TEX_RUNNER_ROOT") or "/work").rstrip("/") or "/work",
        compile_timeout_s=max(10, _env_int("TEX_RUNNER_TIMEOUT", 120)),
        compile_cpu_s=max(10, _env_int("TEX_RUNNER_CPU_SECONDS", 150)),
        compile_mem_mb=max(256, _env_int("TEX_RUNNER_MEMORY_MB", 2048)),
        compile_fsize_mb=max(8, _env_int("TEX_RUNNER_FSIZE_MB", 128)),
        ocr_enabled=_env_bool("PDF2LATEX_OCR", True),
        ocr_language=(os.getenv("PDF2LATEX_OCR_LANG") or "eng").strip(),
        ocr_timeout_s=max(30, _env_int("PDF2LATEX_OCR_TIMEOUT", 600)),
        page_pass_score=min(1.0, max(0.0, _env_float("PDF2LATEX_PAGE_PASS_SCORE", 0.93))),
        low_confidence_score=min(1.0, max(0.0, _env_float("PDF2LATEX_LOW_CONFIDENCE_SCORE", 0.80))),
        min_gain=max(0.0, _env_float("PDF2LATEX_MIN_GAIN", 0.005)),
        max_failed_page_share=min(1.0, max(0.0, _env_float("PDF2LATEX_MAX_FAILED_SHARE", 0.5))),
    )
