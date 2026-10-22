"""
model.py — Data structures for editable (reflowed) PDF → LaTeX conversion.

The extractor (``pdf2latex.extract``) gives us ``PageExtract`` with ``Line``/``Span`` laid out by
PDF coordinate. Editable mode rebuilds that into a *document*: a flat list of semantic ``Block``s
(paragraphs, headings, lists, tables, figures…) in reading order, which ``emit`` writes as ordinary
LaTeX. Nothing here positions text by coordinate; coordinates survive only as hints (alignment,
spacing, which column a line was in) that the emitter turns into semantic LaTeX.

All coordinates are PDF points, PyMuPDF convention (origin top-left, y downwards).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

BBox = Tuple[float, float, float, float]
RGB = Tuple[int, int, int]

# Text of a Run that stands for "push what follows to the right margin" (emitted as \hfill).
HFILL = "\x00HFILL\x00"
# Text of a Run that stands for a line break the PDF has inside a heading (emitted as \\).
LINEBREAK = "\x00BR\x00"


# ---------------------------------------------------------------------------
# Text pieces
# ---------------------------------------------------------------------------

@dataclass
class Run:
    """One style-uniform piece of text."""
    text: str                 # raw extracted text, NOT LaTeX-escaped
    size: float               # rounded to 0.5pt
    family: str               # "serif" | "sans" | "mono"
    font_cls: str             # times | carlito | lmodern | helvetica | …
    bold: bool
    italic: bool
    color: RGB
    script: int = 0           # +1 superscript, -1 subscript, 0 baseline
    link: Optional[str] = None
    underline: bool = False
    math: bool = False        # math font or private-use glyph

    def style_key(self) -> Tuple:
        return (self.size, self.family, self.bold, self.italic, self.color, self.script,
                self.underline, bool(self.link))


@dataclass
class Segment:
    """Same-baseline runs merged across small horizontal gaps."""
    runs: List[Run]
    x0: float
    x1: float

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class TLine:
    """One rebuilt visual row inside one column zone."""
    segments: List[Segment]
    x0: float
    x1: float
    top: float
    bottom: float
    baseline: float
    page: int
    size: float               # dominant size by character count
    src: List[int] = field(default_factory=list)   # indices into the source PageExtract.lines

    @property
    def runs(self) -> List[Run]:
        out: List[Run] = []
        for s in self.segments:
            out.extend(s.runs)
        return out

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)

    @property
    def bbox(self) -> BBox:
        return (self.x0, self.top, self.x1, self.bottom)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

@dataclass
class Block:
    """Base class. ``kind`` identifies the subclass for the emitter and the lint gate; each
    subclass sets it in ``__post_init__`` so callers never pass it."""
    kind: str = ""
    page: int = 0
    bbox: BBox = (0.0, 0.0, 0.0, 0.0)
    id: int = 0
    space_before: float = 0.0     # measured extra gap beyond LaTeX's natural spacing, in pt
    space_exact: bool = False     # write space_before in points (next to a picture), not in lines
    scope: Optional[str] = None   # id of a shared size/colour/leading style scope
    polish: Optional[str] = None  # "math" | "table" | "list" | "titlepage" when flagged for the LLM
    confidence: float = 1.0
    cols: int = 1                 # 2 when the block sits in a two-column band (emitted in multicols)


@dataclass
class Para(Block):
    lines: List[TLine] = field(default_factory=list)
    align: str = "left"           # justify | left | center | right | offset
    indent_l: float = 0.0
    indent_r: float = 0.0
    first_indent: float = 0.0
    leading: float = 0.0
    joins_prev: bool = False      # continues the paragraph that ended the previous page
    left: float = 0.0             # left edge of the column it sits in
    right: float = 0.0            # right edge of the column it sits in (for right-aligned fields)

    def __post_init__(self):
        self.kind = "para"


@dataclass
class Heading(Block):
    level: int = 1                # 0 = chapter-like, 1..3 section levels
    number: Optional[str] = None  # "1", "1.2", "II" … or None
    runs: List[Run] = field(default_factory=list)
    style_key: Tuple = ()
    align: str = "left"           # this heading's own alignment (left | center | right)
    starts_page: bool = False
    baselines: List[float] = field(default_factory=list)   # each of its lines' baseline in the PDF
    before_measured: Optional[float] = None   # its own space above, as its level's is measured
    kern: float = 0.0             # measured correction of its place (calibration), pt
    stacked: bool = False         # it follows another heading directly

    def __post_init__(self):
        self.kind = "heading"

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class Item:
    label: str                    # the literal marker text ("1.", "a)", "-", "•", "[3]")
    body: List[Block] = field(default_factory=list)
    label_color: Optional[RGB] = None   # the marker's colour when it differs from the text's


@dataclass
class ListBlock(Block):
    ordered: bool = False
    label_kind: str = "bullet"    # bullet | decimal | alpha | roman | compound
    start: int = 1
    items: List[Item] = field(default_factory=list)
    marker_x: float = 0.0
    text_x: float = 0.0
    itemsep: float = 0.0
    left: float = 0.0             # left edge of the column the list sits in
    topsep: Optional[float] = None    # measured space above (and below) the list, beyond \parskip

    def __post_init__(self):
        self.kind = "list"


@dataclass
class Cell:
    paras: List["Para"] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1
    stack: bool = False           # several lines set one under another (a signature: name, role, unit)
    fill: Optional[RGB] = None
    bold: bool = False

    @property
    def text(self) -> str:
        return " ".join(p_text(p) for p in self.paras)


@dataclass
class Table(Block):
    col_x: List[float] = field(default_factory=list)       # column left edges
    col_align: List[str] = field(default_factory=list)     # l | c | r | p
    col_frac: List[float] = field(default_factory=list)    # width as a fraction of \linewidth (for p)
    rows: List[List[Cell]] = field(default_factory=list)
    hrules: Set[int] = field(default_factory=set)          # row indices with a rule above
    vrules: Set[int] = field(default_factory=set)          # column-boundary indices with a vertical rule
    header_rows: int = 0
    ruled: bool = False
    booktabs: bool = False
    caption: Optional["Para"] = None
    indent: float = 0.0           # borderless: offset of the first column from the text margin, pt
    stretch: float = 1.0          # borderless: row pitch relative to the body leading
    width_pt: float = 0.0         # borderless: width of the column the table sits in, pt
    centered: bool = False        # set the table centred on the line (a group of signatures)
    spread: bool = False          # a signature group spanning the line edge to edge

    def __post_init__(self):
        self.kind = "table"


@dataclass
class Figure(Block):
    images: List[str] = field(default_factory=list)        # project-relative asset paths
    width_frac: List[float] = field(default_factory=list)  # one per image, fraction of \linewidth
    align: str = "center"
    caption: Optional["Para"] = None

    def __post_init__(self):
        self.kind = "figure"


@dataclass
class Math(Block):
    image: str = ""               # cropped PNG asset path
    number: Optional[str] = None  # equation number, e.g. "(3)"
    width_frac: float = 0.0
    glyphs: List[Dict] = field(default_factory=list)  # for the polish pass (x,y,size,font,char)
    latex: Optional[str] = None   # accepted LaTeX math (polish); replaces the image when set

    def __post_init__(self):
        self.kind = "math"


@dataclass
class Rule(Block):
    width_frac: float = 1.0
    thickness: float = 0.4
    color: RGB = (0, 0, 0)
    align: str = "left"

    def __post_init__(self):
        self.kind = "rule"


@dataclass
class Box(Block):
    stroke: Optional[RGB] = None
    fill: Optional[RGB] = None
    content: List[Block] = field(default_factory=list)
    title_runs: List[Run] = field(default_factory=list)   # a title bar's text (a Beamer block title)
    title_fill: Optional[RGB] = None
    width_frac: float = 1.0       # share of the text width

    def __post_init__(self):
        self.kind = "box"


@dataclass
class Note(Block):
    """A margin / side callout that cannot flow; anchored beside a main-flow block."""
    anchor: int = 0               # id of the block it sits beside
    dx: float = 0.0               # horizontal offset from the text-block left, in pt
    dy: float = 0.0               # vertical offset from that block's first baseline, in pt
    width: float = 0.0            # note width in pt
    anchor_top: float = 0.0       # top of the anchor block (to place the note's rows for the gates)
    content: List[Block] = field(default_factory=list)

    def __post_init__(self):
        self.kind = "note"


@dataclass
class TitlePage(Block):
    content: List[Block] = field(default_factory=list)
    gaps: List[float] = field(default_factory=list)  # measured vertical gaps between content items

    def __post_init__(self):
        self.kind = "titlepage"


@dataclass
class PageMark(Block):
    """A page boundary. ``hard`` forces \\newpage/\\clearpage; soft marks are advisory."""
    hard: bool = False
    reasons: List[str] = field(default_factory=list)
    numbering: Optional[Tuple[str, int]] = None  # ("arabic"|"roman"|"none", start value) at a reset
    chrome: bool = False          # running header/footer shown from here (with numbering)
    pagestyle: Optional[str] = None               # fancyhdr style id active from here

    def __post_init__(self):
        self.kind = "pagemark"


def p_text(p: "Para") -> str:
    return " ".join(l.text for l in p.lines)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    """A reading-order region on a page: a full-width band or one column of a two-column band."""
    page: int
    bbox: BBox
    column: int = 0               # 0 = single/left, 1 = right column
    of_columns: int = 1           # how many columns this band has


@dataclass
class StyledWord:
    """One word with its measured style, for the coverage/style gates."""
    norm: str                     # normalised comparison token
    size: float
    bold: bool
    italic: bool
    color: RGB
    family: str
    page: int


@dataclass
class EditProfile:
    body_cls: str
    body_family: str
    body_size: float
    body_color: RGB
    leading: float                # baseline-to-baseline within a body paragraph
    line_stretch: float           # leading / natural LaTeX baselineskip
    parskip: float
    parindent: float
    margins: Dict[str, float]     # top/bottom/left/right in pt
    paper: str                    # "letterpaper" | "a4paper" | "custom:WxH"
    paper_pt: Tuple[float, float]
    colors: List[Tuple[str, RGB]]              # (name, rgb) ordered by use
    size_cmds: Dict[float, str]                # rounded size → LaTeX command (\small, \large…)
    size_redefs: List[Tuple[str, float]]       # (command, size) commands to redefine in the preamble
    heading_levels: List[Dict]                 # per level: size, bold, italic, family, align, color…
    has_chapters: bool = False
    # measured baseline pitch inside paragraphs for each size class (a 10pt note block is often
    # set much tighter than the 1.5-spaced body)
    leading_by_size: Dict[float, float] = field(default_factory=dict)
    columnsep: float = 0.0
    two_column: bool = False
    footskip: float = 0.0
    body_font: str = ""           # the body text's PDF font name, without subset prefix or style
    # the document's words and hyphenated compounds (from whole lines), to tell a compound broken
    # at its own hyphen ("high-" / "dimensional") from a hyphenated word
    words: Set[str] = field(default_factory=set)
    compounds: Set[str] = field(default_factory=set)


@dataclass
class Furniture:
    header_sig: Optional[str] = None
    footer_sig: Optional[str] = None
    page_number_band: Optional[str] = None     # "top" | "bottom" | None
    page_number_align: str = "C"               # L | C | R
    page_number_size: float = 0.0
    numbering_segments: List[Dict] = field(default_factory=list)  # per segment: first_page, style, start
    furniture_line_ids: Set[Tuple[int, int]] = field(default_factory=set)  # (page, line index) to skip
    # The running header/footer to reproduce: items {band, align, text, size, color, bold, italic,
    # y, image (file) | page_number (True), height}, and the pages that carry them.
    items: List[Dict] = field(default_factory=list)
    header_pages: Set[int] = field(default_factory=set)
    footer_pages: Set[int] = field(default_factory=set)
    image_keys: Set[Tuple[int, str]] = field(default_factory=set)   # (page, file) of repeated pictures
    rule_keys: Set[Tuple[int, int]] = field(default_factory=set)    # (page, round(y)) of repeated rules
    page_numbers: Dict[int, Tuple[str, int]] = field(default_factory=dict)  # page → (style, value)
    header_bottom: float = 0.0     # lowest edge of the header, pt from the top
    footer_top: float = 0.0        # highest edge of the footer, pt from the top
    footer_baseline: float = 0.0   # first footer line's baseline
    initial_numbering: Optional[Tuple] = None   # (style, value, chrome) on page 1, from the plan
    plain_empty: bool = False      # chapter-opening pages print no header, footer or number


@dataclass
class EditDoc:
    blocks: List[Block]
    profile: EditProfile
    furniture: Furniture
    zones: Dict[int, List[Zone]] = field(default_factory=dict)
    pinned: Set[int] = field(default_factory=set)       # page numbers kept 1:1 (title/scan/slide)
    scanned: Set[int] = field(default_factory=set)
    source_words: List[StyledWord] = field(default_factory=list)
    # rebuilt rows per page in reading order (zone by zone, furniture removed); the gates read the
    # source from these so a two-column page is measured column by column, as it reads
    rows_by_page: Dict[int, List[TLine]] = field(default_factory=dict)
    backgrounds: Dict[int, str] = field(default_factory=dict)   # page → background picture
    deck: bool = False            # a slide deck: one slide environment per page
    page_count: int = 0
    title: str = ""
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LineMap: maps emitted .tex line numbers back to blocks, for compile-error repair
# ---------------------------------------------------------------------------

@dataclass
class LineMap:
    """Which block produced each emitted body line. Built by the emitter, kept out of the .tex."""
    # line number (1-based, in the full document) -> block id
    line_to_block: Dict[int, int] = field(default_factory=dict)

    def block_for_line(self, line: int) -> Optional[int]:
        best = None
        for ln in sorted(self.line_to_block):
            if ln <= line:
                best = self.line_to_block[ln]
            else:
                break
        return best
