"""
Robust target resolution (tests A–D): stable node IDs, exact / normalised /
fuzzy text matching, ambiguity refusal and structured failure.
"""

import pytest

from document_index import find_node, index_nodes
from opencode.locator import Target, resolve
from opencode.shadow_workspace import ShadowWorkspace

DOC = r"""\documentclass{article}
\usepackage{xcolor}
\title{Graph Neural Networks}
\author{A. Author}
\begin{document}
\maketitle
\section{Introduction}\label{sec:intro}
    Graph neural networks generalise convolutions to irregular domains.
    They aggregate ``messages'' from   neighbouring nodes at every layer.
\begin{itemize}
  \item Message passing
  \item Readout
\end{itemize}
\section{Method}
We train a three-layer network with residual connections between layers.
Each layer normalises its input before the aggregation step.
\subsection{Training}
We use Adam with a learning rate of 0.001 for 200 epochs.
\section{Results}
The model improves accuracy by four points on every benchmark we tried.
\begin{table}
\begin{tabular}{cc}
a & b \\
\end{tabular}
\label{tab:main}
\end{table}
\end{document}
"""


# --- A. valid target ----------------------------------------------------------

def test_exact_target_resolves_and_applies():
    ws = ShadowWorkspace(DOC)
    res = ws.str_replace("for 200 epochs", "for 300 epochs")
    assert res["success"] and res["method"] == "exact"
    assert "for 300 epochs" in ws.get_buffer()
    assert res["node_id"] == "subsec:training"


def test_node_ids_cover_structure():
    ids = {n.node_id for n in index_nodes(DOC)}
    assert {"preamble", "meta:title", "meta:author", "maketitle", "sec:introduction", "sec:method",
            "subsec:training", "sec:results", "env:table:tab-main"} <= ids
    assert find_node(index_nodes(DOC), "label:sec:intro").node_id == "sec:introduction"
    assert find_node(index_nodes(DOC), "section 2").node_id == "sec:method"


# --- B. changed anchor --------------------------------------------------------

def test_anchor_with_whitespace_and_quote_drift_still_resolves():
    ws = ShadowWorkspace(DOC)
    # The model normalised the spacing and used typographic quotes.
    res = ws.str_replace("They aggregate “messages” from neighbouring nodes at every layer.",
                         "They aggregate messages from neighbouring nodes.")
    assert res["success"], res
    assert res["method"] == "normalized"
    buf = ws.get_buffer()
    assert "They aggregate messages from neighbouring nodes." in buf
    assert "``messages''" not in buf


def test_anchor_after_neighbouring_edit_resolves_by_similarity():
    ws = ShadowWorkspace(DOC)
    # An earlier edit changed one word inside the text the model later targets.
    assert ws.str_replace("three-layer", "four-layer")["success"]
    stale = ("We train a three-layer network with residual connections between layers.\n"
             "Each layer normalises its input before the aggregation step.")
    res = ws.str_replace(stale, "We train a four-layer network with skip connections.")
    assert res["success"], res
    assert res["method"] == "fuzzy"
    assert "skip connections" in ws.get_buffer()
    assert "residual connections" not in ws.get_buffer()


def test_node_id_survives_insertions_elsewhere():
    ws = ShadowWorkspace(DOC)
    assert ws.insert_block("sec:introduction", "\\section{Background}\nSome history.", "after")["success"]
    # Positional chunk IDs shifted; the stable ID still names the same section.
    block = ws.get_block("sec:results")
    assert "improves accuracy" in block["content"]


def test_renamed_block_keeps_its_old_id_as_alias():
    ws = ShadowWorkspace(DOC)
    res = ws.replace_block("sec:results", "\\section{Evaluation}\nThe model is better.\n")
    assert res["success"] and res["node_id"] == "sec:evaluation"
    assert "The model is better." in ws.get_block("sec:results")["content"]


# --- C. missing anchor --------------------------------------------------------

def test_missing_anchor_fails_structured_and_leaves_document_unchanged():
    ws = ShadowWorkspace(DOC)
    before = ws.get_buffer()
    res = ws.str_replace("This sentence does not exist anywhere in the document at all.", "x", line_hint=19)
    assert res["success"] is False
    assert res["document_unchanged"] is True
    assert res["failed_op"] == "replace_text"
    assert [a["method"] for a in res["attempts"]] == ["exact", "normalized", "normalized_ci", "fuzzy"]
    assert res["region_excerpt"].startswith("1: ")  # the re-read region around the hint
    assert ws.get_buffer() == before


def test_unknown_node_lists_available_nodes():
    ws = ShadowWorkspace(DOC)
    res = ws.replace_block("sec:conclusion", "x")
    assert res["success"] is False and "sec:results" in res["available_nodes"]


# --- D. structural / fuzzy recovery and ambiguity ---------------------------------

def test_ambiguous_text_is_refused_without_hint_and_resolved_with_node():
    doc = DOC.replace("\\section{Results}\n", "\\section{Results}\nWe use Adam with a learning rate of 0.001 for 200 epochs.\n")
    ws = ShadowWorkspace(doc)
    res = ws.str_replace("We use Adam with a learning rate of 0.001 for 200 epochs.", "X")
    assert res["success"] is False and res["reason"] == "ambiguous"
    res = ws.str_replace("We use Adam with a learning rate of 0.001 for 200 epochs.", "X", node_id="sec:results")
    assert res["success"] and res["node_id"] == "sec:results"
    assert ws.get_buffer().count("We use Adam") == 1


def test_line_hint_disambiguates():
    doc = "\\documentclass{article}\n\\begin{document}\nfoo bar\nmiddle\nfoo bar\n\\end{document}\n"
    r = resolve(doc, Target(text="foo bar", line_hint=5))
    assert r.ok and doc[:r.start].count("\n") + 1 == 5


def test_fuzzy_never_guesses_between_two_similar_regions():
    para = "The quick brown fox jumps over the lazy dog near the river bank today."
    doc = f"\\documentclass{{article}}\n\\begin{{document}}\n{para}\n\\section{{X}}\n{para.replace('today', 'again')}\n\\end{{document}}\n"
    r = resolve(doc, Target(text=para.replace("today", "now")))
    assert not r.ok
    assert any(a["outcome"] in ("ambiguous", "below_threshold") for a in r.attempts)


def test_short_snippets_are_not_fuzzy_matched():
    r = resolve(DOC, Target(text="Adem with"))
    assert not r.ok and r.attempts[-1]["outcome"] == "skipped_short"


def test_legacy_chunk_ids_still_work():
    ws = ShadowWorkspace(DOC)
    res = ws.rewrite_chunk("section_3", "\\section{Results}\nNew results.\n")
    assert res["success"]
    assert "New results." in ws.get_buffer()


@pytest.mark.parametrize("position,expect_before,expect_after", [
    ("end", "\\item Readout", "\\end{itemize}"),
    ("start", "\\begin{itemize}", "\\item Message passing"),
])
def test_insert_block_inside_environment(position, expect_before, expect_after):
    ws = ShadowWorkspace(DOC)
    res = ws.insert_block("env:itemize@sec:introduction#1", "  \\item Pooling", position)
    assert res["success"], res
    buf = ws.get_buffer()
    i = buf.index("\\item Pooling")
    assert buf.rfind(expect_before, 0, i) != -1
    assert buf.find(expect_after, i) != -1
