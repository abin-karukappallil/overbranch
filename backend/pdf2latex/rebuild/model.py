"""
model.py — the contracts between the stages of the AI-rebuild pipeline.

Coordinates are PDF points in PyMuPDF page space: origin top-left, y grows downward, `Rect` is
(x0, y0, x1, y1). Pages are 1-based everywhere. Extend a dataclass only by adding fields with
defaults; never rename or retype an existing field (other stages depend on it).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

Rect = Tuple[float, float, float, float]

DOC_TYPES = ("paper", "slides", "form", "report")

# Job-level `stage` values, in order. generating / compiling / verifying overlap in time because
# pages run in parallel; per-page progress is `PageResult.status`.
STAGES = ("queued", "inspecting", "ocr", "extracting", "rasterizing", "assets", "generating",
          "compiling", "verifying", "packaging", "done")

PAGE_STATUSES = ("pending", "generating", "compiling", "verifying", "done", "fallback", "failed")

BLOCK_ROLES = ("title", "heading", "body", "list_item", "caption", "footnote", "header", "footer",
               "page_number", "table", "figure", "math", "other")

ASSET_KINDS = ("image", "vector", "math", "background")


def _rect(r: Rect) -> List[float]:
    return [round(float(v), 2) for v in r]


# ---------------------------------------------------------------------------
# Inspect / OCR
# ---------------------------------------------------------------------------

@dataclass
class PageInfo:
    number: int
    width_pt: float
    height_pt: float
    chars: int = 0              # visible extractable characters
    scanned: bool = False       # no extractable text and a page-sized image
    ocr: bool = False           # its text layer came from OCR
    hidden_chars: int = 0       # characters drawn invisibly (render mode 3 / transparent): a pre-existing OCR layer


@dataclass
class Inspection:
    page_count: int
    pages: List[PageInfo]
    doc_type: str = "report"    # one of DOC_TYPES
    ocr_applied: bool = False
    warnings: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)   # what the doc_type decision was based on

    @property
    def scanned_pages(self) -> List[int]:
        return [p.number for p in self.pages if p.scanned]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["scanned_pages"] = self.scanned_pages
        return d


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

@dataclass
class Asset:
    filename: str               # relative to the output dir, spelled exactly as \includegraphics must
    kind: str                   # one of ASSET_KINDS
    page: int
    bbox: Rect                  # where it sits on the source page
    fmt: str = "png"            # "png" | "jpg" | "pdf"
    width_pt: float = 0.0       # size on the source page (suggested \includegraphics width)
    height_pt: float = 0.0
    caption: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.width_pt:
            self.width_pt = round(self.bbox[2] - self.bbox[0], 2)
        if not self.height_pt:
            self.height_pt = round(self.bbox[3] - self.bbox[1], 2)

    def to_prompt(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"file": self.filename, "kind": self.kind, "bbox": _rect(self.bbox),
                             "width_pt": self.width_pt, "height_pt": self.height_pt}
        if self.caption:
            d["caption"] = self.caption
        return d


@dataclass
class TableData:
    id: str                     # "p3t1"
    page: int
    bbox: Rect
    rows: List[List[str]]       # cell text, row-major, ragged rows padded with ""
    col_edges: List[float] = field(default_factory=list)   # x of the column boundaries, pt
    row_edges: List[float] = field(default_factory=list)   # y of the row boundaries, pt
    style: str = "ruled"        # "ruled" | "booktabs" | "borderless"
    header_rows: int = 0
    caption: str = ""

    def to_prompt(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.id, "bbox": _rect(self.bbox), "style": self.style,
                             "header_rows": self.header_rows, "rows": self.rows,
                             "col_edges": [round(v, 1) for v in self.col_edges]}
        if self.caption:
            d["caption"] = self.caption
        return d


@dataclass
class AssetManifest:
    assets: List[Asset] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)

    def for_page(self, n: int) -> List[Asset]:
        return [a for a in self.assets if a.page == n]

    def tables_for_page(self, n: int) -> List[TableData]:
        return [t for t in self.tables if t.page == n]

    def filenames(self, n: Optional[int] = None) -> List[str]:
        return [a.filename for a in (self.assets if n is None else self.for_page(n))]

    def to_dict(self) -> Dict[str, Any]:
        return {"assets": [asdict(a) for a in self.assets], "tables": [asdict(t) for t in self.tables]}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

@dataclass
class PageLayout:
    """
    One page of structured extraction, in reading order.

    Each entry of `blocks` is a plain dict (it goes straight into the prompt JSON):
      id            "p3b7"
      role          one of BLOCK_ROLES
      bbox          [x0, y0, x1, y1] pt
      text          the block's text, verbatim, lines joined by a space ("\n" only at forced breaks)
      level         heading level 1..3, or list nesting depth (0 otherwise)
      font          {"family": str, "size": pt, "bold": bool, "italic": bool, "color": "#rrggbb"}
      runs          style runs that differ from `font`: [{"text", "bold", "italic", "color", "size", "script"}]
      align         "left" | "center" | "right" | "justify"
      column        0-based column index (0 for single column)
      gap_before    measured vertical gap to the previous block, pt
      marker        list marker text ("•", "1.") when role == "list_item"
    """
    number: int
    width_pt: float
    height_pt: float
    margins: Dict[str, float] = field(default_factory=dict)   # top/bottom/left/right, pt
    columns: int = 1
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)  # TableData.to_prompt() of this page
    assets: List[Dict[str, Any]] = field(default_factory=list)  # Asset.to_prompt() of this page
    warnings: List[str] = field(default_factory=list)

    def to_prompt_dict(self) -> Dict[str, Any]:
        return {"page": self.number, "width_pt": round(self.width_pt, 1), "height_pt": round(self.height_pt, 1),
                "margins": {k: round(v, 1) for k, v in self.margins.items()}, "columns": self.columns,
                "blocks": self.blocks, "tables": self.tables, "assets": self.assets}


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

@dataclass
class SandboxResult:
    ok: bool                    # a PDF was produced AND there are no TeX errors
    pdf_path: Optional[Path] = None
    log: str = ""               # tail of the log (<= 32 000 chars)
    errors: List[str] = field(default_factory=list)   # "file:line: message" strings
    timed_out: bool = False
    engine: str = "xelatex"
    pages: int = 0
    seconds: float = 0.0
    detail: str = ""            # sandbox-level failure (runner unreachable, path rejected, ...)


# ---------------------------------------------------------------------------
# Per-page outcome
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    number: int
    status: str = "pending"     # one of PAGE_STATUSES
    body: str = ""              # best page body (no preamble, no \begin{document})
    pdf_path: Optional[Path] = None   # best standalone compile of that body
    score: Optional[float] = None     # 0..1 match score of the best attempt
    ssim: Optional[float] = None
    coverage: Optional[float] = None  # share of source words present
    displacement_pt: Optional[float] = None
    overflow: bool = False      # the body needed more than one page
    rounds: int = 0             # correction rounds used
    repairs: int = 0            # compile-fix LLM calls used
    fallback: str = ""          # "" | "image" (page embedded as a picture)
    vision_used: bool = False   # the model actually saw the page image
    low_confidence: List[str] = field(default_factory=list)   # reasons, e.g. "ocr", "table", "math", "score"
    warnings: List[str] = field(default_factory=list)

    def public(self) -> Dict[str, Any]:
        """The per-page row the UI shows (no bodies, no paths)."""
        return {"number": self.number, "status": self.status,
                "similarity": None if self.score is None else round(self.score, 4),
                "text_coverage": None if self.coverage is None else round(self.coverage, 4),
                "attempts": self.rounds + 1, "fallback": self.fallback or None,
                "low_confidence": self.low_confidence, "warnings": self.warnings[:5]}


# ---------------------------------------------------------------------------
# Shared job context
# ---------------------------------------------------------------------------

@dataclass
class RebuildCtx:
    """Everything a stage needs about one job. Stages add fields with defaults, never rename."""
    job_id: str
    job_dir: Path                       # <job_dir>/<job_id>
    out_dir: Path                       # <job_dir>/output  (main.tex, assets/, output.pdf live here)
    source_pdf: Path                    # normalised copy used for extraction (OCR'd when OCR ran)
    inspection: Inspection
    layouts: List[PageLayout] = field(default_factory=list)
    manifest: AssetManifest = field(default_factory=AssetManifest)
    page_pngs: Dict[int, Path] = field(default_factory=dict)   # page number → pages/page_N.png
    vision: bool = False                # the gateway accepted an image in the start-of-job probe
    preamble: str = ""                  # validated preamble (fixed once generated)
    results: Dict[int, PageResult] = field(default_factory=dict)

    @property
    def work_dir(self) -> Path:
        """Scratch for sandbox builds; lives under the job dir so the runner sidecar can see it."""
        return self.job_dir / "build"

    @property
    def rebuild_dir(self) -> Path:
        return self.job_dir / "rebuild"
