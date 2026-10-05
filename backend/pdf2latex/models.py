"""
models.py — Data structures shared by extraction, generation, verification and reporting.

All coordinates are PDF points (1/72 in) in the PyMuPDF convention: origin at the
top-left of the page, y growing downwards.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

BBox = Tuple[float, float, float, float]
RGB = Tuple[int, int, int]

# PyMuPDF span flag bits
FLAG_SUPERSCRIPT = 1
FLAG_ITALIC = 2
FLAG_SERIF = 4
FLAG_MONO = 8
FLAG_BOLD = 16


@dataclass
class Span:
    text: str
    font: str  # raw PDF font name (may carry a subset prefix like ABCDEF+)
    size: float
    color: RGB
    flags: int
    bbox: BBox
    origin: Tuple[float, float]  # baseline start

    @property
    def bold(self) -> bool:
        return bool(self.flags & FLAG_BOLD) or "bold" in self.font.lower() or "black" in self.font.lower()

    @property
    def italic(self) -> bool:
        low = self.font.lower()
        return bool(self.flags & FLAG_ITALIC) or "italic" in low or "oblique" in low

    @property
    def superscript(self) -> bool:
        return bool(self.flags & FLAG_SUPERSCRIPT)


@dataclass
class Line:
    spans: List[Span]
    bbox: BBox
    block: int = 0
    invisible: bool = False  # OCR text layered invisibly over a scanned image
    column: int = 0  # reading-order region (see extract.order_lines); a change starts a new flow

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def baseline(self) -> float:
        return max(s.origin[1] for s in self.spans)


@dataclass
class Drawing:
    rect: BBox
    kind: str  # "hrule" | "vrule" | "rect" | "path"
    stroke: Optional[RGB] = None
    fill: Optional[RGB] = None
    width: float = 0.0
    n_items: int = 1
    complex: bool = False  # curves, diagonals or polylines that LaTeX rules cannot express


@dataclass
class ImageRef:
    file: str  # project-relative path, e.g. assets/pdf_ab12cd34/page1_img1.png
    bbox: BBox
    width_px: int = 0
    height_px: int = 0
    kind: str = "image"  # "image" | "figure" (rasterized vector region) | "scan"


@dataclass
class PageExtract:
    number: int  # 1-based
    width: float
    height: float
    margins: BBox  # left, top, right, bottom (content extents)
    lines: List[Line] = field(default_factory=list)
    drawings: List[Drawing] = field(default_factory=list)
    images: List[ImageRef] = field(default_factory=list)
    background: Optional[str] = None  # full-page raster of vector art (no text), placed behind the text
    is_scanned: bool = False
    ocr_text: bool = False  # lines come from an invisible OCR layer
    warnings: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    @property
    def has_content(self) -> bool:
        return bool(self.lines or self.images or self.drawings or self.background)


@dataclass
class DocExtract:
    pages: List[PageExtract]
    asset_prefix: str  # e.g. assets/pdf_ab12cd34
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PageReport:
    number: int
    status: str = "pending"  # pending | generating | compiling | repairing | verifying | rerunning | done | below_threshold | failed
    similarity: Optional[float] = None
    ssim: Optional[float] = None
    pixel_diff: Optional[float] = None
    text_coverage: Optional[float] = None
    extra_ratio: Optional[float] = None  # words in the output that are not in the PDF
    shift_pt: Optional[float] = None     # vertical offset of the render against the original
    displacement: Optional[float] = None  # median pt a word moved from its place in the PDF
    attempts: int = 0  # LLM generation calls for this page
    compile_repairs: int = 0
    fallback: Optional[str] = None  # None | "layout" (deterministic positioned text) | "image"
    overflow: bool = False
    warnings: List[str] = field(default_factory=list)


@dataclass
class ConversionReport:
    page_count: int
    pages: List[PageReport] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    threshold: float = 0.0          # reported visual-similarity target (a diagnostic)
    coverage_target: float = 0.0    # the gate: share of the PDF's words the output must carry
    max_displacement: float = 0.0   # the gate: median pt a word may move from its place in the PDF
    compiled: bool = False
    compiled_page_count: Optional[int] = None
    model: str = ""
    llm_used: bool = True
    disclaimer: str = (
        "Best-effort conversion. A page is accepted when it compiles to a single page carrying "
        "every word of the source; the similarity figure is a visual comparison (SSIM + pixel "
        "difference) reported alongside it, and a faithful page that re-sets the type differently "
        "scores well below 100%. The output is not guaranteed to be identical to the PDF."
    )

    @property
    def mean_similarity(self) -> Optional[float]:
        vals = [p.similarity for p in self.pages if p.similarity is not None]
        return sum(vals) / len(vals) if vals else None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mean_similarity"] = self.mean_similarity
        return d
