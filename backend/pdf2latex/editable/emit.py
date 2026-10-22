"""
emit.py — Blocks → ordinary, editable LaTeX (pdfLaTeX).

The style is defined once in the preamble (document class, fonts, geometry, colours, size ladder,
heading formats, page styles). The body is plain reading-order LaTeX: paragraphs, \\section,
itemize/enumerate, tabular, \\includegraphics, with inline \\textbf/\\textit/\\textcolor only where
a run deviates from its surrounding style. No tikz, \\put, textpos, measured \\fontsize or
coordinate \\hspace/\\vspace.
"""

from __future__ import annotations

from contextlib import contextmanager

import re
from typing import Dict, List, Optional, Tuple

from ..texutil import fmt, latex_text
from .hyphen import keep_hyphen
from .model import (HFILL, LINEBREAK, Block, BBox, Box, EditProfile, Figure, Heading, Item, LineMap,
                    ListBlock, Math, Note, Para, RGB, Rule, Run, Table, TitlePage)

_SECTION_CMD = {0: "chapter", 1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph"}


def _cname(profile: EditProfile, rgb: RGB) -> str:
    for name, c in profile.colors:
        if c == rgb:
            return name
    return "obBlack"


class Emitter:
    def __init__(self, profile: EditProfile, source_name: str = "", furniture=None, backgrounds=None,
                 deck: bool = False):
        self.p = profile
        self.deck = deck
        self.furniture = furniture
        self.backgrounds: Dict[int, str] = dict(backgrounds or {})
        self.source = source_name
        self.notes = False
        self.multicol = False
        self.boxes = False
        self.body_color = profile.body_color
        # the size the surrounding text is already set in (the body, or a paragraph/list whose whole
        # text is one smaller size and is wrapped at paragraph level); runs only wrap a different size
        self._base_size = profile.body_size
        self._list_x: Optional[float] = None    # text edge of the list being written (nesting)

    # ------------------------------------------------------------------ preamble
    def preamble(self, has_notes: bool, has_tables: bool) -> str:
        p = self.p
        L: List[str] = []
        if self.source:
            L.append(f"% Converted by OverBranch from {self.source!r} (editable mode).")
        L.append("% The style is defined once below; the body is ordinary, editable LaTeX.")
        base = min((10, 11, 12), key=lambda c: abs(c - p.body_size))
        docclass = "report" if p.has_chapters else "article"
        paper = p.paper if not p.paper.startswith("custom") else ""
        opts = f"{base}pt" + (f",{paper}" if paper else "")
        L.append(f"\\documentclass[{opts}]{{{docclass}}}")
        L.append("\\usepackage[T1]{fontenc}")
        L.append("\\usepackage[utf8]{inputenc}")
        L.append("\\usepackage{textcomp}")
        L.extend(self._font_lines())
        L.append(self._geometry_line())
        L.append("\\usepackage{amsmath}")
        L.append("\\usepackage{amssymb}")
        L.append("\\usepackage[table]{xcolor}")
        L.append("\\usepackage{graphicx}")
        L.append("\\usepackage{array}")
        if has_tables:
            L.append("\\usepackage{tabularx}")
            L.append("\\usepackage{multirow}")
            L.append("\\usepackage{booktabs}")
        L.append("\\usepackage{enumitem}")
        L.append("\\usepackage{setspace}")
        L.append("\\usepackage{titlesec}")
        L.append("\\usepackage{changepage}")
        if self.backgrounds:
            L.append("\\usepackage{eso-pic}   % page decoration (template background) behind the text")
        if self.boxes:
            L.append("\\usepackage{tcolorbox}")
        if self.deck:
            L.append("\\usepackage{adjustbox}")
            L.append("% One slide per page: the slide's content in a box the height of the page, scaled down")
            L.append("% only if it would not fit.")
            L.append("\\newenvironment{slide}{\\noindent\\begin{adjustbox}{max totalheight=\\textheight}"
                     "\\begin{minipage}{\\linewidth}}{\\end{minipage}\\end{adjustbox}\\clearpage}")
        if self.multicol:
            L.append("\\usepackage{multicol}")
            L.append(f"\\setlength{{\\columnsep}}{{{fmt(max(8.0, self.p.columnsep or 18.0))}bp}}")
        L.append("\\usepackage{url}")
        L.append("\\usepackage[hidelinks]{hyperref}")
        L.append("")
        # colours
        L.append("% Colours (exact RGB from the PDF)")
        for name, rgb in p.colors:
            L.append(f"\\definecolor{{{name}}}{{RGB}}{{{rgb[0]},{rgb[1]},{rgb[2]}}}")
        L.append("")
        # size redefinitions
        if p.size_redefs:
            # \\@setfontsize, as the class files define sizes: it also records the current size,
            # which \\setstretch and footnotes re-select (a bare \\fontsize would fall back to
            # \\normalsize there)
            L.append("% Font sizes measured in the PDF that have no standard command")
            L.append("\\makeatletter")
            for cmd, sz in sorted(p.size_redefs, key=lambda t: t[1]):
                verb = "newcommand" if cmd.startswith("\\obsize") else "renewcommand"
                L.append(f"\\{verb}{{{cmd}}}{{\\@setfontsize{cmd}{{{fmt(sz)}}}{{{fmt(sz*1.2)}}}}}  "
                         f"% {fmt(sz)}pt in the PDF")
            L.append("\\makeatother")
            L.append("")
        # spacing
        if abs(p.line_stretch - 1.0) > 0.05:
            L.append(f"\\usepackage{{setspace}}" if "setspace" not in "".join(L) else "")
            L.append(f"\\setstretch{{{fmt(p.line_stretch)}}}")
        L.append(f"\\setlength{{\\parindent}}{{{fmt(p.parindent)}pt}}")
        # a line TeX cannot justify within its tolerance is set a little loose rather than run
        # into the margin (the PDF has no overfull lines)
        L.append("\\setlength{\\emergencystretch}{1.5em}")
        L.append(f"\\setlength{{\\parskip}}{{{fmt(p.parskip)}pt}}")
        L.append("")
        # page numbers
        L.extend(self._page_style_lines())
        # headings
        L.extend(self._heading_formats())
        # notes
        if has_notes:
            L.append("% A note set beside the text, as in the PDF")
            L.append("% \\obnote{<from left margin>}{<raise>}{<width>}{<text>}: a zero-height line, so the")
            L.append("% note sits beside the next paragraph without moving it")
            L.append("\\newcommand{\\obnote}[4]{\\par\\edef\\obprevdepth{\\the\\prevdepth}%")
            L.append("  {\\raggedright\\parskip=0pt\\nointerlineskip\\noindent")
            L.append("  \\makebox[0pt][l]{\\hspace{#1}\\raisebox{#2}[0pt][0pt]{\\parbox[t]{#3}{\\raggedright\\setstretch{1}#4}}}\\par}%")
            L.append("  \\prevdepth=\\obprevdepth\\relax}")
            L.append("")
        return "\n".join(x for x in L if x is not None)

    def _chrome_text(self, it: Dict) -> str:
        if it.get("image"):
            return f"\\raisebox{{-0.3\\height}}{{\\includegraphics[height={fmt(it['height'])}bp]{{{it['image']}}}}}"
        if it.get("page_number"):
            body = _tex(it.get("prefix", "")) + "\\thepage{}" + _tex(it.get("suffix", ""))
        else:
            body = _tex(it["text"])
        if it.get("italic"):
            body = f"\\textit{{{body}}}"
        if it.get("bold"):
            body = f"\\textbf{{{body}}}"
        col = tuple(it.get("color") or (0, 0, 0))
        if col != self.body_color and col != (0, 0, 0) or (col == (0, 0, 0) and self.body_color != (0, 0, 0)):
            body = f"\\textcolor{{{_cname(self.p, col)}}}{{{body}}}"
        sz = round((it.get("size") or self.p.body_size) * 2) / 2
        size = self.p.size_cmds.get(sz)
        if size and size != "\\normalsize":
            body = f"{size} {body}"
        elif not size and abs(sz - self.p.body_size) > 0.75:
            # a size only the header/footer uses (in the preamble, so the body stays free of \\fontsize)
            body = f"\\fontsize{{{fmt(sz)}}}{{{fmt(sz * 1.2)}}}\\selectfont {body}"
        return body

    def _page_style_lines(self) -> List[str]:
        """
        The running header and footer as the PDF prints them, as a fancyhdr page style: the header
        text and logo, the footer text, the rules under the header and over the footer, the page
        number where and how it appears. \\obnumberedtrue/false and \\obchrometrue/false switch the
        number and the running text on and off between parts (an unnumbered front matter, roman
        then arabic numbering). Chapter-opening pages use 'plain', empty when the PDF prints
        nothing on them.
        """
        f = self.furniture
        L = ["% Running header and footer, page numbers", "\\usepackage{fancyhdr}",
             "\\newif\\ifobnumbered", "\\newif\\ifobchrome"]
        parts: Dict[Tuple[str, str], List[Dict]] = {}
        rules = {"top": 0.0, "bottom": 0.0}
        for it in (f.items if f else []):
            if it.get("rule"):
                rules[it["band"]] = it["rule"]
                continue
            parts.setdefault((it["band"], it["align"]), []).append(it)
        cmds = []
        for (band, align), its in sorted(parts.items()):
            its.sort(key=lambda t: t["y"])
            lines = []
            anchor = {"L": "l", "C": "c", "R": "r"}.get(align, "c")
            for it in its:
                txt = self._chrome_text(it)
                if not it.get("image") and not it.get("page_number"):
                    # one PDF line stays one line, even when it is wider than the text (a
                    # publisher's notice across the page foot)
                    txt = f"\\makebox[0pt][{anchor}]{{{txt}}}"
                flag = "\\ifobnumbered" if it.get("page_number") else "\\ifobchrome"
                lines.append(f"{flag} {txt}\\fi")      # the space ends the control word
            where = "head" if band == "top" else "foot"
            cmds.append(f"\\fancy{where}[{align}]{{{'\\\\'.join(lines)}}}")
        head_rule = f"\\ifobchrome{fmt(rules['top'])}pt\\else0pt\\fi" if rules["top"] else "0pt"
        foot_rule = f"\\ifobchrome{fmt(rules['bottom'])}pt\\else0pt\\fi" if rules["bottom"] else "0pt"
        L.append("\\fancypagestyle{obmain}{\\fancyhf{}%")
        for c in cmds:
            L.append("  " + c + "%")
        L.append(f"  \\renewcommand{{\\headrulewidth}}{{{head_rule}}}\\renewcommand{{\\footrulewidth}}{{{foot_rule}}}}}")
        if f and f.plain_empty:
            L.append("\\fancypagestyle{plain}{\\fancyhf{}\\renewcommand{\\headrulewidth}{0pt}"
                     "\\renewcommand{\\footrulewidth}{0pt}}   % chapter-opening pages print nothing")
        else:
            L.append("\\fancypagestyle{plain}{\\pagestyle{obmain}}")
        L.append("")
        return L

    def _numbering_start(self) -> List[str]:
        f = self.furniture
        init = getattr(f, "initial_numbering", None) if f else None
        if not init or init[0] == "none":
            return ["\\obnumberedfalse", "\\obchromefalse"]
        style, value, chrome = init
        out = ["\\obnumberedtrue", "\\obchrometrue" if chrome else "\\obchromefalse",
               f"\\pagenumbering{{{style}}}"]
        if value and value != 1:
            out.append(f"\\setcounter{{page}}{{{value}}}")
        return out

    def _font_lines(self) -> List[str]:
        """The body font package, plus the default-family switch when the body is sans or mono but
        the package only provides it as a secondary family (Latin Modern Sans comes from the
        lmodern package, whose default is the serif)."""
        from ..fontmap import FONT_LINES
        out = _exact_font_lines(self.p.body_font) or list(FONT_LINES.get(self.p.body_cls, FONT_LINES["times"]))
        joined = "".join(out)
        if self.p.body_family == "sans" and "sfdefault" not in joined:
            out.append("\\renewcommand{\\familydefault}{\\sfdefault}")
        elif self.p.body_family == "mono" and "ttdefault" not in joined:
            out.append("\\renewcommand{\\familydefault}{\\ttdefault}")
        return out

    def _geometry_line(self) -> str:
        m = self.p.margins
        if self.p.paper.startswith("custom"):
            w, h = self.p.paper_pt
            size = f"paperwidth={fmt(w)}bp,paperheight={fmt(h)}bp,"
        else:
            size = ""
        foot = f",footskip={fmt(max(12, self.p.footskip))}bp" if self.p.footskip else ""
        f = self.furniture
        if f and f.items:
            heads = [it for it in f.items if it["band"] == "top" and not it.get("rule")]
            if heads:
                hh = max((it.get("height") or (it.get("size") or 8) * 1.2) for it in heads) + 2
                hsep = max(6.0, m["top"] - f.header_bottom)
                foot += f",headheight={fmt(hh)}bp,headsep={fmt(hsep)}bp"
            if f.footer_baseline:
                text_bottom = self.p.paper_pt[1] - m["bottom"]
                foot = f",footskip={fmt(max(12.0, f.footer_baseline - text_bottom))}bp" + foot.replace(
                    f",footskip={fmt(max(12, self.p.footskip))}bp", "")
        return (f"\\usepackage[{size}left={fmt(m['left'])}bp,right={fmt(m['right'])}bp,"
                f"top={fmt(m['top'])}bp,bottom={fmt(m['bottom'])}bp{foot}]{{geometry}}")

    def _heading_formats(self) -> List[str]:
        out: List[str] = []
        if not self.p.heading_levels:
            return out
        out.append("% Heading styles. Each level sets its usual alignment; \\leftheading, \\centerheading or")
        out.append("% \\rightheading before a heading changes the alignment of that one heading.")
        out.append("\\newcommand{\\obnextalign}{}")
        out.append("\\newcommand{\\obheadalign}{\\obnextalign\\global\\let\\obnextalign\\relax}")
        out.append("\\newcommand{\\leftheading}{\\gdef\\obnextalign{\\leftskip=0pt\\rightskip=0pt plus 1fil\\relax}}")
        out.append("\\newcommand{\\centerheading}{\\gdef\\obnextalign{\\filcenter}}")
        out.append("\\newcommand{\\rightheading}{\\gdef\\obnextalign{\\filleft}}")
        for lv in self.p.heading_levels:
            cmd = _SECTION_CMD.get(lv["level"], "paragraph")
            fmt_parts = ["\\filcenter"] if lv["align"] == "center" else []
            fmt_parts.append("\\obheadalign")
            # the size is carried by the heading text itself (so each heading keeps its own size),
            # not fixed per level here — only weight/slant/family/alignment are set.
            fmt_parts.append("\\bfseries" if lv["bold"] else "\\mdseries")
            if lv["italic"]:
                fmt_parts.append("\\itshape")
            if lv["family"] == "sans":
                fmt_parts.append("\\sffamily")
            # starred headings carry their number literally in the title, so no \the... format;
            # an underlined level draws its rule after the title, where the PDF has it
            after_code = ""
            if lv.get("rule"):
                r = lv["rule"]
                depth = 0.2 * (lv.get("size") or self.p.body_size)
                gap = max(0.0, r["gap"] - r["thickness"] / 2 - depth)
                after_code = (f"[\\vspace{{{fmt(round(gap, 1))}pt}}{{\\color{{{_cname(self.p, r['color'])}}}"
                              f"\\titlerule[{fmt(r['thickness'])}pt]}}]")
            out.append(f"\\titleformat{{\\{cmd}}}[block]{{{''.join(fmt_parts)}}}{{}}{{0pt}}{{}}{after_code}")
            # the space the PDF leaves above and below this level's headings (measured), else a
            # moderate default
            if lv.get("space_before") is not None:
                before = f"{fmt(lv['space_before'])}pt"
                after = f"{fmt(lv['space_after'])}pt"
            else:
                before = "1.3ex" if lv["level"] <= 1 else "1ex"
                after = "0.5ex"
            out.append(f"\\titlespacing*{{\\{cmd}}}{{0pt}}{{{before}}}{{{after}}}")
        out.append("")
        return out

    # ------------------------------------------------------------------ body
    def document(self, blocks: List[Block], has_notes: bool) -> Tuple[str, LineMap]:
        self.multicol = any(getattr(b, "cols", 1) == 2 for b in blocks)
        self.boxes = contains_kind(blocks, "box")
        has_notes = has_notes or contains_kind(blocks, "note")
        has_tables = any(isinstance(b, Table) for b in blocks) or \
            any(isinstance(b, Box) and any(isinstance(c, Table) for c in b.content) for b in blocks)
        pre = self.preamble(has_notes, has_tables)
        body_lines: List[Tuple[str, int]] = []
        in_cols = False
        in_slide = False
        bg_done: set = set()
        for b in blocks:
            if self.deck and b.kind == "pagemark":
                if in_cols:
                    body_lines.append(("\\end{multicols}", b.id))
                    in_cols = False
                if in_slide:
                    body_lines.append(("\\end{slide}", b.id))
                    body_lines.append(("", b.id))
                    in_slide = False
                continue        # the slide environment already ends the page
            if b.kind != "pagemark" and b.page in self.backgrounds and b.page not in bg_done:
                from ..preamble import background_command
                bg_done.add(b.page)
                body_lines.append((background_command(self.backgrounds[b.page]), b.id))
            if self.deck and not in_slide:
                body_lines.append(("\\begin{slide}", b.id))
                in_slide = True
            hard_mark = b.kind == "pagemark" and getattr(b, "hard", False)
            want_cols = getattr(b, "cols", 1) == 2 and b.kind != "pagemark"
            if in_cols and (hard_mark or (not want_cols and b.kind != "pagemark")):
                body_lines.append(("\\end{multicols}", b.id))
                body_lines.append(("", b.id))
                in_cols = False
            if want_cols and not in_cols:
                body_lines.append(("\\begin{multicols}{2}", b.id))
                in_cols = True
            self._emit(b, body_lines, top=True)
        if in_cols:
            body_lines.append(("\\end{multicols}", 0))
        if in_slide:
            body_lines.append(("\\end{slide}", 0))
        # assemble and build the line map
        start = ["", "\\begin{document}", "\\pagestyle{obmain}"] + self._numbering_start()
        if self.body_color != (0, 0, 0):
            # the document's body text is not black; set it as the default so unwrapped text matches
            start.append(f"\\color{{{_cname(self.p, self.body_color)}}}")
        head = pre.split("\n") + start
        lm = LineMap()
        all_lines: List[str] = list(head)
        base = len(all_lines)
        for i, (text, bid) in enumerate(body_lines):
            for sub in text.split("\n"):
                all_lines.append(sub)
                if bid:
                    lm.line_to_block[len(all_lines)] = bid
        all_lines.append("\\end{document}")
        all_lines.append("")
        return "\n".join(all_lines), lm

    def _emit(self, b: Block, out: List[Tuple[str, int]], top: bool = False) -> None:
        if isinstance(b, TitlePage):
            self._emit_titlepage(b, out)
        elif isinstance(b, Heading):
            out.append((self._heading(b), b.id))
            out.append(("", b.id))
        elif isinstance(b, Para):
            out.append((self._para(b), b.id))
            out.append(("", b.id))
        elif isinstance(b, ListBlock):
            out.append((self._list(b), b.id))
            out.append(("", b.id))
        elif isinstance(b, Figure):
            out.append((self._figure(b), b.id))
            out.append(("", b.id))
        elif isinstance(b, Table):
            out.append((self._table(b), b.id))
            out.append(("", b.id))
        elif isinstance(b, Math):
            out.append((self._math(b), b.id))
            out.append(("", b.id))
        elif isinstance(b, Rule):
            out.append((self._rule(b), b.id))
            out.append(("", b.id))
        elif isinstance(b, Note):
            out.append((self._note(b), b.id))
        elif isinstance(b, Box):
            out.append((self._box(b), b.id))
            out.append(("", b.id))
        elif b.kind == "pagemark":
            out.append((self._pagemark(b), b.id))

    # -- inline runs -------------------------------------------------------
    def _runs(self, runs: List[Run]) -> str:
        parts = [self._run(r) for r in runs]
        return "".join(parts)

    def _run(self, r: Run, heading: bool = False, h_bold: Optional[bool] = None,
             h_size: Optional[float] = None) -> str:
        """``heading`` emits a run inside a heading: the heading's \\titleformat sets the weight and
        family and the heading carries its own size, so only deviations from *that* (h_bold,
        h_size) are wrapped — e.g. a plain date beside a bold entry title."""
        if r.text == HFILL:
            return "\\hfill "
        if r.text == LINEBREAK:
            return "\\\\ "
        txt = _tex(r.text)
        if not txt:
            return ""
        lead = txt[: len(txt) - len(txt.lstrip())]
        trail = txt[len(txt.rstrip()):]
        core = txt.strip()
        if not core:
            return txt  # whitespace only
        inner = core
        # innermost → outermost wrapping (link, underline, color, shape, weight, family, size, script)
        if r.link:
            inner = f"\\href{{{_url(r.link)}}}{{{inner}}}"
        if r.underline:
            inner = f"\\underline{{{inner}}}"
        if r.color != self.body_color:
            inner = f"\\textcolor{{{_cname(self.p, r.color)}}}{{{inner}}}"
        if r.italic:
            inner = f"\\textit{{{inner}}}"
        if heading:
            if h_bold is not None and r.bold != h_bold:
                inner = f"\\textbf{{{inner}}}" if r.bold else f"\\textmd{{{inner}}}"
        if not heading:
            if r.bold:
                inner = f"\\textbf{{{inner}}}"
            if r.family == "sans" and self.p.body_family != "sans":
                inner = f"\\textsf{{{inner}}}"
            elif r.family == "mono" and self.p.body_family != "mono":
                inner = f"\\texttt{{{inner}}}"
            elif r.family == "serif" and self.p.body_family != "serif":
                inner = f"\\textrm{{{inner}}}"
        if r.script == 1:
            inner = f"\\textsuperscript{{{inner}}}"
        elif r.script == -1:
            inner = f"\\textsubscript{{{inner}}}"
        if heading and h_size and abs(r.size - h_size) > 0.75 and r.script == 0:
            cmd = self.p.size_cmds.get(round(r.size * 2) / 2)
            if cmd:
                inner = f"{{{cmd} {inner}}}"
        if not heading and abs(r.size - self._base_size) > 0.75 and r.script == 0:
            cmd = self.p.size_cmds.get(round(r.size * 2) / 2)
            if cmd and cmd != "\\normalsize":
                inner = f"{{{cmd} {inner}}}"
        return lead + inner + trail

    def _merge_runs_text(self, runs: List[Run]) -> str:
        # join runs, collapsing an inter-line nothing; runs already carry their own spacing
        return self._runs(runs)

    # -- paragraph ---------------------------------------------------------
    def _para_lines_text(self, p: Para, keep_breaks: bool = False) -> str:
        """Join a paragraph's lines into one flowing run list: de-hyphenate line breaks, put a space
        between segments (a tab gap), and move a short right-aligned field (marks "(3)", a date) to
        the end of the paragraph behind \\hfill, where it sits on the right as in the PDF. With
        keep_breaks (centred or right-aligned lines: a signature, an address) each PDF line ends
        in \\\\ instead, as set."""
        from .blocks import hfill_run, is_right_field
        runs_acc: List[Run] = []
        right_fields: List[List[Run]] = []

        def add_space():
            if runs_acc and runs_acc[-1].text and not runs_acc[-1].text.endswith((" ", "\u00a0")):
                runs_acc[-1] = Run(**{**runs_acc[-1].__dict__, "text": runs_acc[-1].text + " "})

        for i, line in enumerate(p.lines):
            n = len(line.segments)
            for si, seg in enumerate(line.segments):
                if p.right and is_right_field(seg, n, si, p.left, p.right):
                    right_fields.append(list(seg.runs))
                    continue
                if si > 0:
                    add_space()
                runs_acc.extend(seg.runs)
            if keep_breaks and i < len(p.lines) - 1 and runs_acc:
                runs_acc[-1] = Run(**{**runs_acc[-1].__dict__, "text": runs_acc[-1].text.rstrip()})
                runs_acc.append(Run(**{**runs_acc[-1].__dict__, "text": LINEBREAK}))
            elif i < len(p.lines) - 1 and runs_acc and runs_acc[-1].text.rstrip().endswith("-"):
                # a line-end hyphen: the word continues on the next line. A compound's own hyphen
                # ("high-" / "dimensional") stays; a hyphenation is dropped. Either way no space.
                left = runs_acc[-1].text.rstrip().split()[-1] if runs_acc[-1].text.split() else ""
                right = p.lines[i + 1].text.lstrip().split()[0] if p.lines[i + 1].text.split() else ""
                keep = keep_hyphen(left, right, self.p.words, self.p.compounds)
                runs_acc[-1] = Run(**{**runs_acc[-1].__dict__,
                                      "text": runs_acc[-1].text.rstrip()[:None if keep else -1]})
            elif i < len(p.lines) - 1:
                add_space()   # soft line break → a space
        if right_fields and runs_acc:
            runs_acc.append(hfill_run(runs_acc[-1]))
            for k, f in enumerate(right_fields):
                if k:
                    add_space()
                runs_acc.extend(f)
        return self._runs(runs_acc)

    def _local_stretch(self, p: Para) -> Optional[float]:
        """A \\setstretch for a paragraph whose measured line pitch differs from what the global
        stretch would give at its size (e.g. tight 10pt notes in a 1.5-spaced document)."""
        from .profile import tex_baselineskip
        sizes = [r.size for ln in p.lines for r in ln.runs if r.text.strip()]
        if not sizes or not p.leading:
            return None
        size = max(set(sizes), key=sizes.count)
        if abs(size - self.p.body_size) <= 0.6:
            # a body-size paragraph set wider or tighter than the rest (a certificate's text at
            # double spacing): its own measured pitch, from three or more lines
            steps = sorted(b.baseline - a.baseline for a, b in zip(p.lines, p.lines[1:])
                           if 0 < b.baseline - a.baseline < 3 * size)
            lead = self.p.leading or 0.0
            if len(steps) < 2 or not lead:
                return None
            pitch = steps[len(steps) // 2]
            if abs(pitch - lead) <= 0.08 * lead:
                return None
            want = pitch / tex_baselineskip(self.p, size)
        else:
            want = p.leading / (1.2 * size)
        have = self.p.line_stretch if abs(self.p.line_stretch - 1.0) > 0.05 else 1.0
        return round(want, 2) if abs(want - have) > 0.08 else None

    def _uniform_size(self, runs: List[Run]) -> Optional[float]:
        """The size ≥90% of the text is set in, when that differs from the body; else None."""
        w: Dict[float, int] = {}
        for r in runs:
            if r.script == 0:
                w[r.size] = w.get(r.size, 0) + len(r.text.strip())
        total = sum(w.values())
        if not total:
            return None
        size = max(w, key=w.get)
        if w[size] / total < 0.9 or abs(size - self.p.body_size) <= 0.75:
            return None
        return size if self.p.size_cmds.get(round(size * 2) / 2, "\\normalsize") != "\\normalsize" else None

    def _para(self, p: Para) -> str:
        """A paragraph. When its whole text is one smaller/larger size, the size switch wraps the
        paragraph *including* its \\par, so LaTeX spaces the lines for that size (a size switch
        inside the text, closed before \\par, would keep the body's line spacing)."""
        size = self._uniform_size([r for ln in p.lines for r in ln.runs])
        prev = self._base_size
        if size is not None:
            self._base_size = size
        try:
            body = self._para_lines_text(p, keep_breaks=self._keeps_breaks(p)).strip()
        finally:
            self._base_size = prev
        if not body:
            return "%"
        st = self._local_stretch(p)
        if size is None and not st:
            return self._para_aligned(p, body)
        lead = (self.p.size_cmds[round(size * 2) / 2] + " ") if size is not None else ""
        lead += f"\\setstretch{{{fmt(st)}}}" if st else ""
        # the space above is measured in body lines, so it stays outside the size switch
        pre = self._space(p)
        inner = self._para_aligned(p, body, space=False)
        if pre:
            return pre + self._wrap_sized(lead, inner)
        return self._wrap_sized(lead, inner)

    @staticmethod
    def _wrap_sized(lead: str, inner: str) -> str:
        if inner.endswith("\\par}"):          # {\\centering …\\par} already ends its paragraph
            return "{" + lead + inner + "}"
        if inner.endswith("\\end{adjustwidth}"):
            return "{" + lead + inner + "\\par}"
        return "{" + lead + inner + "\\par}"

    @staticmethod
    def _keeps_breaks(p: Para) -> bool:
        """Centred or right-aligned lines keep their breaks: re-wrapped, a name over its register
        number or a two-line address would run together on one line."""
        return p.align in ("center", "right") and len(p.lines) > 1

    def _para_aligned(self, p: Para, body: str, space: bool = True) -> str:
        pre = self._space(p) if space else ""
        if (self.p.parindent or 0) > 0 and p.align in ("left", "justify") and p.first_indent < 4 \
                and p.indent_l <= 6:
            body = "\\noindent " + body      # this paragraph's first line is not indented
        # {\centering …\par} / {\raggedleft …\par} rather than the center/flushright environments,
        # which add \topsep above and below and inflate the page count on reflow.
        if p.align == "center":
            return pre + "{\\centering " + body + "\\par}"
        if p.align == "right":
            return pre + "{\\raggedleft " + body + "\\par}"
        if p.align == "offset":
            return pre + "\\begin{adjustwidth}{0.5\\linewidth}{0pt}\n" + body + "\n\\end{adjustwidth}"
        if p.align == "left":
            # ragged right (not justified)
            if p.indent_l > 6:
                return (pre + f"\\begin{{adjustwidth}}{{{fmt(p.indent_l)}pt}}{{0pt}}\n"
                        + body + "\n\\end{adjustwidth}")
        return pre + body

    def _space(self, b: Block) -> str:
        if b.space_exact and b.space_before and abs(b.space_before) >= 2.0:
            return f"\\vspace{{{fmt(round(b.space_before * 2) / 2)}pt}}\n"
        if b.space_before and abs(b.space_before) >= max(4.0, 0.4 * (self.p.leading or 12)):
            k = round(b.space_before / max(1.0, self.p.leading) * 2) / 2
            if abs(k) >= 0.5:
                return f"\\vspace{{{fmt(k)}\\baselineskip}}\n"
        return ""

    # -- heading -----------------------------------------------------------
    def _heading(self, h: Heading) -> str:
        level = h.level
        lv = None
        if level == 0 and not h.starts_page:
            # \\chapter always starts a new page; a heading in that style standing mid-page in the
            # PDF ("CERTIFICATE" under the college name) takes the next level's command and keeps
            # its own size, weight and alignment.
            level = 1
            lv = next((x for x in self.p.heading_levels if x["level"] == 1), None)
        cmd = _SECTION_CMD.get(level, "section")
        # the heading keeps its own measured size (titleformat sets only weight/family/align);
        # size and weight are character-weighted so a short plain date doesn't decide them
        weights: Dict[float, int] = {}
        for r in h.runs:
            weights[r.size] = weights.get(r.size, 0) + len(r.text.strip())
        h_size = max(weights, key=weights.get) if weights else self.p.body_size
        h_bold = bool(h.style_key[1]) if h.style_key else True
        if lv is not None:
            fmt_bold = bool(lv["bold"])
            title = "".join(self._run(r, heading=True, h_bold=fmt_bold, h_size=h_size)
                            for r in h.runs).strip() or "~"
            if h_bold and not fmt_bold:
                title = f"\\bfseries {title}"
        else:
            title = "".join(self._run(r, heading=True, h_bold=h_bold, h_size=h_size)
                            for r in h.runs).strip() or "~"
        cmdsize = self.p.size_cmds.get(round(h_size * 2) / 2)
        if cmdsize and cmdsize != "\\normalsize":
            title = f"{cmdsize} {title}"
        level_align = ("center" if lv["align"] == "center" else "left") if lv is not None else (
            "center" if (h.style_key and h.style_key[4] == "center") else "left")
        own = h.align if h.align in ("left", "center", "right") else "left"
        prefix = "" if own == level_align else {"left": "\\leftheading", "center": "\\centerheading",
                                                 "right": "\\rightheading"}[own]
        return f"{self._heading_kern(h, level)}{prefix}\\{cmd}*{{{title}}}"

    def _heading_kern(self, h: Heading, level: int) -> str:
        """A heading whose own space above differs from its level's (it follows a rule or a
        picture, not text) is moved by the difference. A \\kern, because the space titlesec puts
        above a heading (\\addvspace) would swallow a \\vspace before it."""
        lv = next((x for x in self.p.heading_levels if x["level"] == level), None)
        d = h.kern
        if not h.starts_page and h.before_measured is not None and lv and lv.get("space_before_measured") is not None:
            d += h.before_measured - lv["space_before_measured"]
        if abs(d) < 4:
            return ""
        # under another heading no page break may fall between the two
        return f"\\kern{fmt(round(d, 1))}pt" + ("\\nobreak\n" if h.stacked else "\\relax\n")

    # -- list --------------------------------------------------------------
    def _list(self, lb: ListBlock) -> str:
        runs = [r for it in lb.items for b in it.body if isinstance(b, Para) for ln in b.lines for r in ln.runs]
        size = self._uniform_size(runs)
        if size is None:
            return self._list_inner(lb)
        prev = self._base_size
        self._base_size = size
        try:
            inner = self._list_inner(lb)
        finally:
            self._base_size = prev
        sizes_para = Para(lines=[ln for it in lb.items for b in it.body if isinstance(b, Para) for ln in b.lines],
                          leading=self._leading_of_list(lb))
        st = self._local_stretch(sizes_para)
        lead = self.p.size_cmds[round(size * 2) / 2] + (f"\\setstretch{{{fmt(st)}}}" if st else "")
        return "{" + lead + "\n" + inner + "\n}"

    def _leading_of_list(self, lb: ListBlock) -> float:
        for it in lb.items:
            for b in it.body:
                if isinstance(b, Para) and b.leading:
                    return b.leading
        return 0.0

    def _list_inner(self, lb: ListBlock) -> str:
        W_opt = []
        if lb.ordered and lb.label_kind in ("decimal", "alpha", "roman", "ref") and lb.items:
            fmt_label = _label_format(lb.items[0].label, lb.label_kind)
            lc = lb.items[0].label_color
            if lc is not None and lc != self.body_color:
                fmt_label = f"\\textcolor{{{_cname(self.p, lc)}}}{{{fmt_label}}}"
            opts = f"label={{{fmt_label}}}, start={lb.start}, {self._list_geometry(lb)}"
            lines = [f"\\begin{{enumerate}}[{opts}]"]
            with self._in_list(lb):
                for it in lb.items:
                    lines.append("  \\item " + self._item_body(it))
            lines.append("\\end{enumerate}")
            return self._space(lb) + "\n".join(lines)
        labels = [self._label(it) for it in lb.items]
        base_opts = self._list_geometry(lb)
        with self._in_list(lb):
            if lb.label_kind == "bullet" and len(set(labels)) == 1:
                # one bullet glyph for every item: set it once, plain \item (easiest to extend)
                lines = [f"\\begin{{itemize}}[label={{{labels[0]}}}, {base_opts}]"]
                for it in lb.items:
                    lines.append("  \\item " + self._item_body(it))
            else:
                # itemize with explicit literal labels (matches irregular PDF markers exactly)
                lines = [f"\\begin{{itemize}}[{base_opts}]"]
                for it, label in zip(lb.items, labels):
                    lines.append(f"  \\item[{label}] " + self._item_body(it))
        lines.append("\\end{itemize}")
        return self._space(lb) + "\n".join(lines)

    def _list_geometry(self, lb: ListBlock) -> str:
        """enumitem options that put the markers and the text where the PDF has them: the text
        indent (leftmargin) from the enclosing text's left edge, each marker at the start of a
        label box reaching to the text; item and list spacing as measured."""
        left = self._list_x if self._list_x is not None else (lb.left or self.p.margins.get("left", 0.0))
        indent = lb.text_x - left
        label_w = lb.text_x - lb.marker_x
        if lb.text_x and lb.marker_x and indent >= 4 and label_w >= 2:
            geo = (f"leftmargin={fmt(round(indent, 1))}pt, labelwidth={fmt(round(label_w, 1))}pt, "
                   f"labelsep=0pt, align=left")
        else:
            geo = "leftmargin=*"
        top = fmt(round(lb.topsep, 1)) if lb.topsep is not None else "2"
        return f"{geo}, itemsep={fmt(max(0, lb.itemsep))}pt, parsep=0pt, topsep={top}pt, partopsep=0pt"

    @contextmanager
    def _in_list(self, lb: ListBlock):
        """Inside a list, a nested list's indents count from this list's text."""
        prev = self._list_x
        self._list_x = lb.text_x or prev
        try:
            yield
        finally:
            self._list_x = prev

    def _label(self, it: Item) -> str:
        """A list marker in its own colour when that differs from the body text (an orange ▶)."""
        text = _tex(it.label)
        if it.label_color is not None and it.label_color != self.body_color:
            return f"\\textcolor{{{_cname(self.p, it.label_color)}}}{{{text}}}"
        return text

    def _item_body(self, it: Item) -> str:
        parts = []
        for b in it.body:
            if isinstance(b, Para):
                parts.append(self._para_lines_text(b).strip())
            elif isinstance(b, ListBlock):
                parts.append("\n" + self._list(b))
        return " ".join(x for x in parts if x)

    # -- figure ------------------------------------------------------------
    def _figure(self, f: Figure) -> str:
        """An image in the flow ({\\centering …\\par} rather than the center environment, whose
        \\topsep above and below would add space the PDF doesn't have)."""
        align = {"center": "\\centering", "right": "\\raggedleft"}.get(f.align, "\\noindent")
        lines = [self._space(f).rstrip("\n")] if self._space(f) else []
        imgs = " ".join(f"\\includegraphics[width={fmt(min(1.0, frac))}\\linewidth]{{{img}}}"
                        for img, frac in zip(f.images, f.width_frac))
        cap = ("\\\\\n" + self._para_lines_text(f.caption).strip()) if f.caption else ""
        lines.append("{" + align + " " + imgs + cap + "\\par}")
        return "\n".join(x for x in lines if x)

    # -- rule --------------------------------------------------------------
    def _rule(self, r: Rule) -> str:
        cname = _cname(self.p, r.color)
        body = f"\\textcolor{{{cname}}}{{\\rule{{{fmt(r.width_frac)}\\linewidth}}{{{fmt(r.thickness)}pt}}}}"
        pre = self._space(r)
        if r.align == "center":
            return pre + "{\\centering " + body + "\\par}"
        if r.align == "right":
            return pre + "{\\raggedleft " + body + "\\par}"
        return pre + "\\noindent" + body + "\\par"

    # -- math --------------------------------------------------------------
    def _math(self, m: Math) -> str:
        """A displayed equation: real LaTeX maths when the polish pass reconstructed it (and it was
        verified against the PDF's glyphs), otherwise the equation kept as its image."""
        if m.latex:
            if m.number:
                tag = m.number.strip("()")
                return f"\\begin{{equation}}\n{m.latex}\n\\tag{{{tag}}}\n\\end{{equation}}"
            return f"\\[\n{m.latex}\n\\]"
        img = (f"\\includegraphics[width={fmt(min(1.0, m.width_frac or 0.5))}\\linewidth]{{{m.image}}}"
               if m.image else "")
        num = f"\\hfill {_tex(m.number)}" if m.number else ""
        return self._space(m) + "{\\centering " + img + num + "\\par}"

    # -- table -------------------------------------------------------------
    def _table(self, t: Table) -> str:
        return self._space(t) + render_table(self, t)

    # -- note --------------------------------------------------------------
    def _note(self, n: Note) -> str:
        self.notes = True
        parts = []
        for c in n.content:
            if not isinstance(c, Para):
                continue
            text = self._para_lines_text(c).strip()
            hang = (c.lines[1].x0 - c.lines[0].x0) if len(c.lines) > 1 else 0.0
            if 4 <= hang <= 40:   # "- item" whose continuation lines are indented under the text
                text = f"\\hangindent={fmt(hang)}pt\\hangafter=1 " + text
            parts.append(text)
        content = "\\par ".join(parts)
        return f"\\obnote{{{fmt(n.dx)}pt}}{{{fmt(-n.dy)}pt}}{{{fmt(n.width)}pt}}{{{content}}}"

    # -- box ---------------------------------------------------------------
    def _box(self, b: Box) -> str:
        """A shaded box (a Beamer block, a coloured call-out) as a tcolorbox: background colour,
        title-bar colour and title as in the PDF; the content is ordinary LaTeX."""
        inner: List[Tuple[str, int]] = []
        for c in b.content:
            self._emit(c, inner)
        body = "\n".join(t for t, _ in inner if t).strip() or "~"
        fill = _cname(self.p, b.fill) if b.fill else "white"
        frame = _cname(self.p, b.title_fill) if b.title_fill else fill
        opts = [f"colback={fill}", f"colframe={frame}", "boxrule=0pt", "arc=2pt",
                "left=4pt", "right=4pt", "top=2pt", "bottom=2pt"]
        if self.body_color != (0, 0, 0):
            # tcolorbox resets the text colour to black; keep the document's body colour
            opts.append(f"coltext={_cname(self.p, self.body_color)}")
        if b.width_frac and b.width_frac < 0.97:
            opts.append(f"width={fmt(b.width_frac)}\\linewidth")
        if b.title_runs:
            title = "".join(self._run(r) for r in b.title_runs).strip()
            opts.append(f"title={{{title}}}")
            opts.append("toptitle=1pt, bottomtitle=1pt")
        return f"\\begin{{tcolorbox}}[{', '.join(opts)}]\n{body}\n\\end{{tcolorbox}}"

    # -- titlepage ---------------------------------------------------------
    def _emit_titlepage(self, tp: TitlePage, out: List[Tuple[str, int]]) -> None:
        """
        A title page: centred, single-spaced, no paragraph skip, each item placed where the PDF has
        it. The space before an item is the measured baseline distance minus what LaTeX puts there
        by itself (the item's \\baselineskip, or \\lineskip next to a picture); an item whose own
        lines sit closer or wider than LaTeX would set them keeps the PDF's line pitch. The largest
        gap may shrink, so a page filled to its foot never spills onto a second page.
        """
        from .profile import class_size, tex_baselineskip
        for c in tp.content:
            c.space_before = 0.0          # the gaps below place every item
        flow = [i for i, c in enumerate(tp.content) if c.kind != "note"]
        top = self.p.margins.get("top", 72.0)
        topskip = class_size(self.p.body_size)
        before: Dict[int, float] = {}
        prev = None
        for i in flow:
            c = tp.content[i]
            first, size = _tp_first(c, self.p.body_size)
            pitch = self._tp_pitch(c)
            if prev is None:
                # the page opens with \\null (an empty line \\topskip below the top, depth 0) and
                # the space, then this item: a text line one \\baselineskip lower, a picture
                # \\lineskip (1pt) lower
                # (an item already within 2pt of where LaTeX puts a page's first line needs neither)
                if first is None:
                    plain = c.bbox[1] - top
                    before[i] = c.bbox[1] - (top + topskip + 1.0)
                else:
                    plain = first - (top + max(topskip, 0.72 * size))
                    before[i] = first - (top + topskip + (pitch or tex_baselineskip(self.p, size)))
                if plain < 2:
                    del before[i]
            else:
                last, depth = _tp_last(prev)
                if first is None:
                    # a picture: \\lineskip (1pt) below the previous line's descenders
                    before[i] = c.bbox[1] - last - depth - 1.0
                else:
                    bs = pitch or tex_baselineskip(self.p, size)
                    h = 0.72 * size
                    natural = bs if bs - depth - h >= 0 else depth + 1.0 + h
                    before[i] = first - last - natural
            prev = c
        shrink_at = max(flow[1:], key=lambda i: before[i], default=None)
        out.append(("\\begin{titlepage}", tp.id))
        out.append(("\\centering\\setstretch{1}\\setlength{\\parskip}{0pt}", tp.id))
        for i, c in enumerate(tp.content):
            g = before.get(i)
            if g is not None and flow and i == flow[0]:
                amount = fmt(round(g, 1))
                out.append(("\\null" + (f"\\vspace{{{amount}bp}}" if abs(g) >= 0.5 else ""), tp.id))
            elif g is not None and abs(g) >= 2:
                amount = fmt(round(g, 1))
                if i == shrink_at and g >= 12:
                    out.append((f"\\vspace{{{amount}bp minus {amount}bp}}", tp.id))
                else:
                    out.append((f"\\vspace{{{amount}bp}}", tp.id))
            if isinstance(c, Note):
                out.append((self._note(c), c.id or tp.id))
            elif isinstance(c, Para):
                out.append((self._tp_line(c, self._tp_pitch(c)), c.id or tp.id))
            elif isinstance(c, Figure):
                out.append((self._figure(c), c.id or tp.id))
            elif isinstance(c, Heading):
                out.append(("{" + self._heading_inline(c, _pitch_cmd(self._tp_pitch(c))) + "\\par}",
                            c.id or tp.id))
            elif isinstance(c, ListBlock):
                out.append((self._list(c), c.id or tp.id))
        out.append(("\\end{titlepage}", tp.id))

    def _tp_pitch(self, c: Block) -> Optional[float]:
        """The PDF's line pitch inside a multi-line title-page item, when LaTeX's baselineskip for
        its size would set the lines more than 1pt closer or wider; else None."""
        from .profile import tex_baselineskip
        bases = c.baselines if isinstance(c, Heading) else (
            [ln.baseline for ln in c.lines] if isinstance(c, Para) else [])
        if len(bases) < 2:
            return None
        steps = sorted(b - a for a, b in zip(bases, bases[1:]))
        pitch = steps[len(steps) // 2]
        _first, size = _tp_first(c, self.p.body_size)
        return round(pitch, 1) if abs(pitch - tex_baselineskip(self.p, size)) > 1.0 else None

    def _heading_inline(self, h: Heading, after_size: str = "") -> str:
        """A heading's text set inline (title page): its own size and weight, colours per run."""
        weights: Dict[float, int] = {}
        for r in h.runs:
            weights[r.size] = weights.get(r.size, 0) + len(r.text.strip())
        h_size = max(weights, key=weights.get) if weights else self.p.body_size
        h_bold = bool(h.style_key[1]) if h.style_key else True
        title = "".join(self._run(r, heading=True, h_bold=h_bold, h_size=h_size) for r in h.runs).strip()
        cmd = self.p.size_cmds.get(round(h_size * 2) / 2, "")
        size = (cmd + " ") if cmd and cmd != "\\normalsize" else ""
        # after_size (a measured line pitch) follows the size switch, which resets \\baselineskip
        return size + after_size + ("\\bfseries " if h_bold else "") + title

    def _tp_line(self, p: Para, pitch: Optional[float] = None) -> str:
        """A title-page line: its size switch at paragraph level, so LaTeX spaces it for that size."""
        size = self._uniform_size([r for ln in p.lines for r in ln.runs])
        prev = self._base_size
        if size is not None:
            self._base_size = size
        try:
            body = self._para_lines_text(p, keep_breaks=self._keeps_breaks(p)).strip()
        finally:
            self._base_size = prev
        if not body:
            return "%"
        lead = (self.p.size_cmds[round(size * 2) / 2] + " ") if size is not None else ""
        # the pitch goes before the text: \\\\ under \\centering ends a paragraph per line
        return "{" + lead + _pitch_cmd(pitch) + body + "\\par}"

    # -- page mark ---------------------------------------------------------
    def _pagemark(self, pm) -> str:
        """A page boundary. The page is cleared *before* the numbering changes, so the change
        applies to the next page, not to the one being finished."""
        if not getattr(pm, "hard", False):
            return "%"           # the source page turned here; the text just flows on
        parts = ["\\clearpage"]
        if pm.numbering:
            style, start = pm.numbering
            if style == "none":
                parts.append("\\obnumberedfalse\\obchromefalse")
            else:
                parts.append("\\obnumberedtrue" + ("\\obchrometrue" if getattr(pm, "chrome", False)
                                                      else "\\obchromefalse"))
                parts.append(f"\\pagenumbering{{{style}}}")
                if start and start != 1:
                    parts.append(f"\\setcounter{{page}}{{{start}}}")
        return "\n".join(parts)


# TeX Gyre fonts the PDF names, which pdfLaTeX has as such: the same glyphs and widths, so the
# same line breaks (a metric look-alike such as mathptmx for TeX Gyre Termes is close, not equal)
_GYRE = (("texgyretermes", "tgtermes", ""), ("texgyrepagella", "tgpagella", ""),
         ("texgyrebonum", "tgbonum", ""), ("texgyreschola", "tgschola", ""),
         ("texgyreheros", "tgheros", "\\renewcommand{\\familydefault}{\\sfdefault}"),
         ("texgyreadventor", "tgadventor", "\\renewcommand{\\familydefault}{\\sfdefault}"),
         ("texgyrecursor", "tgcursor", "\\renewcommand{\\familydefault}{\\ttdefault}"))


def _exact_font_lines(body_font: str) -> List[str]:
    from latex_layout.metrics import tex_package_available
    n = (body_font or "").lower().replace(" ", "")
    for key, pkg, default in _GYRE:
        if n.startswith(key) and tex_package_available(pkg):
            return [f"\\usepackage{{{pkg}}}"] + ([default] if default else [])
    return []


# Symbols texutil.latex_text drops (it is shared with exact mode, which stays as it is): the variant
# Greek letters TeX's math fonts set ("g(x) → ϕ") and a few delimiters.
_EXTRA_SYMBOLS = {
    "\u03d5": "\\phi", "\u03d1": "\\vartheta", "\u03f5": "\\epsilon", "\u03d6": "\\varpi",
    "\u03f1": "\\varrho", "\u03d2": "\\Upsilon", "\u2225": "\\parallel", "\u27e8": "\\langle",
    "\u27e9": "\\rangle",
}
_EXTRA_RE = re.compile("[" + "".join(_EXTRA_SYMBOLS) + "]")


def _tex(text: str) -> str:
    """latex_text, plus the symbols it would drop."""
    if not _EXTRA_RE.search(text or ""):
        return latex_text(text)
    out, pos = [], 0
    for m in _EXTRA_RE.finditer(text):
        out.append(latex_text(text[pos:m.start()]))
        out.append(f"\\ensuremath{{{_EXTRA_SYMBOLS[m.group(0)]}}}")
        pos = m.end()
    out.append(latex_text(text[pos:]))
    return "".join(out)


def _pitch_cmd(pitch: Optional[float]) -> str:
    return f"\\setlength{{\\baselineskip}}{{{fmt(pitch)}bp}}" if pitch else ""


def _tp_first(c: Block, body_size: float) -> Tuple[Optional[float], float]:
    """A title-page item's first baseline in the PDF and its text size; (None, 0) for a picture."""
    from .blocks import _first_baseline
    if isinstance(c, Heading):
        size = _block_size(c) or body_size
        return (c.baselines[0] if c.baselines else c.bbox[1] + 0.8 * size), size
    if isinstance(c, (Para, ListBlock)):
        fb = _first_baseline(c)
        if fb is not None:
            return fb, (_block_size(c) or body_size)
    return None, 0.0


def _tp_last(c: Block) -> Tuple[float, float]:
    """A title-page item's last baseline in the PDF and the depth LaTeX gives that line (descenders),
    or a picture's bottom edge (depth 0)."""
    from .blocks import _last_baseline, _last_para
    if isinstance(c, Heading):
        size = max((r.size for r in c.runs if r.text.strip()), default=10.0)
        last = c.baselines[-1] if c.baselines else c.bbox[3] - 0.22 * size
        text = "".join(r.text for r in c.runs).split(LINEBREAK)[-1]
        return last, _depth(text, size)
    lb = _last_baseline(c)
    tail = _last_para(c)
    if lb is not None and tail is not None and tail.lines:
        ln = tail.lines[-1]
        return lb, _depth(ln.text, ln.size)
    return c.bbox[3], 0.0


def _depth(text: str, size: float) -> float:
    if any(ch in text for ch in "gjpqy"):
        return 0.22 * size
    if any(ch in text for ch in "(),;[]{}Q|/"):
        return 0.18 * size
    return 0.0


def _url(s: str) -> str:
    return s.replace("%", "\\%").replace("#", "\\#").replace("{", "\\{").replace("}", "\\}")


# ---------------------------------------------------------------------------
# Table rendering (kept here so the emitter owns all LaTeX text)
# ---------------------------------------------------------------------------

def render_table(em: "Emitter", t: Table) -> str:
    ncol = max((len(row) for row in t.rows), default=0)
    if ncol == 0:
        return "%"
    if not t.ruled and not t.booktabs:
        return _render_borderless(em, t, ncol)
    colspec = _colspec(t, ncol)
    lines = ["\\begin{center}"]
    if t.caption:
        lines.append(em._para_lines_text(t.caption).strip() + "\\par\\smallskip")
    lines.append(f"\\begin{{tabular}}{{{colspec}}}")
    if t.ruled and not t.booktabs:
        lines.append("\\hline")
    elif t.booktabs:
        lines.append("\\toprule")
    for ri, row in enumerate(t.rows):
        lines.append(" & ".join(_cell_text(em, t, cell) for cell in row) + " \\\\")
        if t.booktabs and ri + 1 == t.header_rows:
            lines.append("\\midrule")
        elif t.ruled and not t.booktabs:
            lines.append("\\hline")
    if t.booktabs:
        lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{center}")
    return "\n".join(lines)


def _cell_text(em: "Emitter", t: Table, cell) -> str:
    txt = " ".join(em._para_lines_text(p).strip() for p in cell.paras) if cell.paras else ""
    if cell.bold and txt:
        txt = f"\\textbf{{{txt}}}"
    if cell.colspan > 1:
        a = t.col_align[0] if t.col_align else "l"
        txt = f"\\multicolumn{{{cell.colspan}}}{{{a}}}{{{txt}}}"
    return txt


def _render_borderless(em: "Emitter", t: Table, ncol: int) -> str:
    """An aligned list without rules (abbreviations, symbols, contents): flush with the text margin
    (@{} edges), columns as wide as in the PDF, rows as far apart as in the PDF; a field that spans
    several columns is a \\multicolumn, a page-number column is right-aligned."""
    if getattr(t, "centered", False) and len(t.rows) == 1 and t.rows[0] \
            and all(getattr(c, "stack", False) for c in t.rows[0]):
        return _render_signatures(em, t)
    fracs = list(t.col_frac) + [0.2] * (ncol - len(t.col_frac))
    aligns = list(t.col_align) + ["p"] * (ncol - len(t.col_align))

    def col(k: int, frac: float) -> str:
        a = {"r": "\\raggedleft", "c": "\\centering"}.get(aligns[k], "\\raggedright")
        return f">{{{a}\\arraybackslash}}p{{{fmt(frac)}\\linewidth}}"

    cols = "".join(col(k, fracs[k]) for k in range(ncol))
    sep = (12.0 / t.width_pt) if t.width_pt else 0.02     # two \\tabcolsep, as a share of the line
    body = [f"\\begin{{tabular}}{{@{{}}{cols}@{{}}}}"]
    for row in t.rows:
        cells = []
        k = 0
        for cell in row:
            sep_txt = "\\newline " if getattr(cell, "stack", False) else " "
            txt = sep_txt.join(em._para_lines_text(p).strip() for p in cell.paras) if cell.paras else ""
            if cell.colspan > 1:
                span = min(cell.colspan, ncol - k)
                w = sum(fracs[k:k + span]) + (span - 1) * sep
                txt = f"\\multicolumn{{{span}}}{{{col(k, round(w, 3))}}}{{{txt}}}"
                k += span
            else:
                k += 1
            cells.append(txt)
        while k < ncol:
            cells.append("")
            k += 1
        body.append(" & ".join(cells) + " \\\\")
    body.append("\\end{tabular}")
    inner = "\n".join(body)
    if t.stretch and t.stretch > 1.0:
        inner = f"{{\\renewcommand{{\\arraystretch}}{{{fmt(t.stretch)}}}\n{inner}\\par}}"
    if getattr(t, "centered", False):
        return "{\\centering " + inner + "\\par}"
    if t.indent and t.indent > 6:
        return f"\\begin{{adjustwidth}}{{{fmt(t.indent)}pt}}{{0pt}}\n\\noindent{inner}\n\\end{{adjustwidth}}"
    return "\\noindent" + inner


def _render_signatures(em: "Emitter", t: Table) -> str:
    """Signatures side by side (a name over a role over a department): each stack is a tabular of
    its own lines, as wide as its longest line, so nothing re-wraps; \\hfill spreads them as in
    the PDF (edge to edge, or with equal space around a narrower group)."""
    stacks = []
    for cell in t.rows[0]:
        lines = [em._para_lines_text(p).strip() for p in cell.paras]
        stacks.append("\\begin{tabular}[t]{@{}c@{}}\n" + " \\\\\n".join(lines) + "\n\\end{tabular}")
    ends = "" if getattr(t, "spread", False) else "\\hspace*{\\fill}"
    return "\\noindent" + ends + "\n\\hfill\n".join(stacks) + ends + "\\par"


def _colspec(t: Table, ncol: int) -> str:
    aligns = list(t.col_align) + ["l"] * (ncol - len(t.col_align))
    fracs = list(t.col_frac) + [0.0] * (ncol - len(t.col_frac))
    parts = []
    vrule = "|" if (t.ruled and not t.booktabs) else ""
    parts.append(vrule)
    for i in range(ncol):
        a = aligns[i]
        if a == "p" and fracs[i] > 0:
            parts.append(f">{{\\raggedright\\arraybackslash}}p{{{fmt(fracs[i])}\\linewidth}}")
        elif a in ("l", "c", "r"):
            parts.append(a)
        else:
            parts.append("l")
        if i < ncol - 1 and i in t.vrules:
            parts.append("|")
    parts.append(vrule)
    return "".join(parts)


def _label_format(label: str, kind: str) -> str:
    """enumitem label mirroring the source's label shape: "1" → \\arabic*, "1." → \\arabic*.,
    "(a)" → (\\alph*), "IV." → \\Roman*., "[3]" → [\\arabic*]."""
    m = re.search(r"\d+|[A-Za-z]+", label)
    if not m:
        return "\\arabic*."
    core = m.group(0)
    if kind in ("decimal", "ref"):
        counter = "\\arabic*"
    elif kind == "roman":
        counter = "\\Roman*" if core.isupper() else "\\roman*"
    else:
        counter = "\\Alph*" if core.isupper() else "\\alph*"
    return _tex(label[:m.start()]) + counter + _tex(label[m.end():])


def contains_kind(blocks, kind: str) -> bool:
    """Whether any block, at any depth (title page, box, list item), is of ``kind``."""
    for b in blocks:
        if b.kind == kind:
            return True
        for attr in ("content", "body"):
            inner = getattr(b, attr, None)
            if inner and contains_kind(inner, kind):
                return True
        for it in getattr(b, "items", []) or []:
            if contains_kind(it.body, kind):
                return True
    return False


def _block_size(b) -> float:
    """Dominant run size of a block (0 when it has no text)."""
    if b is None:
        return 0.0
    runs = []
    if isinstance(b, Heading):
        runs = b.runs
    elif isinstance(b, Para):
        runs = [r for ln in b.lines for r in ln.runs]
    w: Dict[float, int] = {}
    for r in runs:
        w[r.size] = w.get(r.size, 0) + len(r.text.strip())
    return max(w, key=w.get) if w else 0.0


def emit_document(doc) -> Tuple[str, LineMap]:
    """Re-emit a whole EditDoc (after a compile repair or a polish edit) with its own settings."""
    em = Emitter(doc.profile, source_name=doc.title, furniture=doc.furniture,
                 backgrounds=getattr(doc, "backgrounds", {}) or {}, deck=getattr(doc, "deck", False))
    return em.document(doc.blocks, contains_kind(doc.blocks, "note"))
