"""
OverBranch Standard presentation style — the built-in DEFAULT for Beamer decks.

This is deliberately NOT a template from `backend/templates/`. The agent uses it
when the user asks for a presentation WITHOUT naming a template, so a plain
"make a ppt on X" produces a clean, modern, LIGHT deck inline (no template
dependency). A named template (regalia, nordlight, …) is still fetched with
`get_template_theme` and reproduced verbatim — see `template_registry.py`.

Design goals (why this exists):
  * The old default forced the Regalia template, whose title slide is cream text
    on a dark navy banner — the "dark themed title page" users disliked.
  * This standard is light-on-white with a slim accent sidebar and a light title
    slide (no dark banner), high contrast, max ~6 bullets per slide.

Robustness: every positioned element is single-pass safe.
  * The sidebar is drawn by the `background` template with `[overlay]` only —
    NOT `remember picture` — so it renders on the first pdflatex pass (the direct
    engine path only runs a second pass for refs/cites/TOC, not for pgf's
    remember-picture aux round-trip).
  * The title slide uses ordinary flow inside a `minipage`, so a two-line title
    pushes the accent rule down with it instead of colliding with it.
Both were verified by rendering with real pdflatex before shipping.
"""

# Preamble only (\documentclass … last \setbeamertemplate), no \begin{document}.
STANDARD_PPT_PREAMBLE = r"""\documentclass[aspectratio=169]{beamer}
\usetheme{default}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{tikz}
\usepackage{booktabs}
\usepackage{amsmath,amssymb}
\usetikzlibrary{calc}
% --- OverBranch Standard palette (light) ---
\definecolor{accent}{HTML}{2A5DB0}
\definecolor{accentdark}{HTML}{1C3D73}
\definecolor{ink}{HTML}{1A1A1A}
\definecolor{muted}{HTML}{5C6270}
\definecolor{paper}{HTML}{FFFFFF}
% --- Light background, dark text ---
\setbeamercolor{background canvas}{bg=paper}
\setbeamercolor{normal text}{fg=ink,bg=paper}
\setbeamercolor{frametitle}{fg=accentdark,bg=paper}
\setbeamercolor{title}{fg=accentdark}
\setbeamercolor{itemize item}{fg=accent}
\setbeamercolor{itemize subitem}{fg=muted}
\setbeamercolor{block title}{fg=paper,bg=accent}
\setbeamercolor{block body}{fg=ink,bg=paper}
\setbeamerfont{frametitle}{series=\bfseries,size=\Large}
\setbeamerfont{title}{series=\bfseries,size=\huge}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{itemize item}{\textcolor{accent}{\textbf{--}}}
% Slim accent sidebar on every frame (single-pass safe: overlay, no remember picture)
\setbeamertemplate{background}{\begin{tikzpicture}[overlay]\fill[accent] (0,0) rectangle (0.18,-\paperheight);\end{tikzpicture}}
% Frametitle clear of the sidebar, with an accent underline rule
\setbeamertemplate{frametitle}{\vspace{3mm}\hspace{3mm}%
  {\usebeamerfont{frametitle}\usebeamercolor[fg]{frametitle}\insertframetitle}\par
  \hspace{3mm}{\color{accent}\rule{0.25\paperwidth}{1pt}}\vspace{1mm}}
% Muted page number footer
\setbeamertemplate{footline}{\hfill{\color{muted}\scriptsize\insertframenumber/\inserttotalframenumber}\hspace{3mm}\vspace{2mm}}"""

# The light title slide (ordinary flow + minipage; no overlay collision).
STANDARD_PPT_TITLE_SLIDE = r"""\begin{frame}[plain]
  \vspace*{1.4cm}\hspace*{1.1cm}%
  \begin{minipage}{0.84\textwidth}
    {\usebeamercolor[fg]{title}\bfseries\huge PRESENTATION TITLE}\\[3mm]
    {\color{accent}\rule{0.32\textwidth}{1.2pt}}\\[4mm]
    {\color{muted}\large Subtitle / one-line description}\\[6mm]
    {\color{ink}\normalsize Author Name}\\[1mm]
    {\color{muted}\small Affiliation \textbullet\ \today}
  \end{minipage}
\end{frame}"""

# Prose spec injected verbatim into the agent's creation message (the PPT
# archetype hint) when NO template was named by the user.
STANDARD_PPT_SPEC = (
    "DOCUMENT TARGET: BEAMER PRESENTATION (SLIDES) — DEFAULT: OVERBRANCH STANDARD (light, accent sidebar)\n"
    "- Do NOT pull a template. The user did not ask for one, so build the deck inline with the clean, "
    "modern, LIGHT OverBranch Standard below. Never a dark title page.\n"
    "- Use this preamble EXACTLY (it is light-on-white with a slim accent sidebar and compiles in a single pass):\n"
    "```latex\n" + STANDARD_PPT_PREAMBLE + "\n```\n"
    "- Title slide — light, no dark banner. Fill in the real title, subtitle, author and affiliation:\n"
    "```latex\n" + STANDARD_PPT_TITLE_SLIDE + "\n```\n"
    "- Structure:\n"
    "  * Title slide ([plain]) as above.\n"
    "  * An Outline slide (`\\begin{frame}{Outline}`) listing the key topics.\n"
    "  * 6-12 content frames (`\\begin{frame}{Title}`): clear bullets (MAX 5-6 per slide), "
    "`block` environments for highlights, `booktabs` tables, and `$…$`/`equation` math. Never place text outside a frame.\n"
    "- DIAGRAMS: when a slide needs a diagram, block diagram, figure or flowchart, call `generate_diagram` "
    "instead of hand-writing TikZ — pass a natural-language `description` (the LLM draws it, verified to compile) "
    "or a `nodes`/`edges` spec (laid out deterministically). Either way it returns clean, compiling, slide-fitting TikZ.\n"
    "- The accent colour is `accent` (#2A5DB0). To restyle later, the user only has to ask; then switch palette or template freely."
)
