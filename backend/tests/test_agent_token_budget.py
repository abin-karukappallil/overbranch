"""
Token efficiency: a targeted edit sends the blocks it concerns, not the whole
document, so the prompt does not grow with document length; unchanged lines
are not re-sent; a one-step edit costs one LLM call.
"""

from conftest import final_buffer, result_event, run_agent

from opencode.context_builder import ContextLedger, build_targeted_context, match_nodes
from opencode.shadow_workspace import ShadowWorkspace
from document_index import index_nodes


def make_doc(sections: int, lines_per_section: int = 20) -> str:
    parts = ["\\documentclass{article}", "\\usepackage{xcolor}", "\\definecolor{brand}{HTML}{1F4E79}",
             "\\title{\\textcolor{brand}{A Long Report}}", "\\begin{document}", "\\maketitle"]
    for s in range(1, sections + 1):
        parts.append(f"\\section{{Topic {s}}}")
        parts += [f"Sentence {k} of topic {s} discusses detail number {k} at some length." for k in range(lines_per_section)]
    parts.append("\\section{Conclusion}")
    parts.append("The conclusion summarises the findings.")
    parts.append("\\end{document}")
    return "\n".join(parts) + "\n"


EDIT = {"thought": "edit", "tool_call": {"name": "replace_text", "arguments": {
    "old_str": "The conclusion summarises the findings.", "new_str": "The conclusion restates the findings.",
    "node_id": "sec:conclusion"}}, "done": True, "explanation": "Reworded."}


def test_prompt_size_does_not_scale_with_document_length(scripted_llm, stub_compiler):
    sizes = {}
    for n_sections in (3, 250):  # ~70 lines vs ~5,300 lines
        doc = make_doc(n_sections)
        llm = scripted_llm([dict(EDIT)])
        events = run_agent("Reword the sentence in the Conclusion section", doc)
        assert "restates the findings" in final_buffer(events, doc)
        sizes[n_sections] = llm.prompt_chars[0]
    small, large = sizes[3], sizes[250]
    large_doc = len(make_doc(250))
    assert large < 2 * small, sizes
    assert large < large_doc / 5, (large, large_doc)


def test_one_step_targeted_edit_uses_one_llm_call(scripted_llm, stub_compiler):
    doc = make_doc(40)
    llm = scripted_llm([dict(EDIT)])
    events = run_agent("Reword the sentence in the Conclusion section", doc)
    trace = result_event(events)["trace"]
    assert len(llm.calls) == 1
    assert trace["llm_invocations"] == 1
    assert trace["context"]["strategy"] == "targeted"
    assert trace["context"]["nodes"] == ["sec:conclusion"]
    assert trace["edits"][0]["method"] == "exact"


def test_title_request_retrieves_title_and_its_styling():
    ws = ShadowWorkspace(make_doc(30))
    text, info = build_targeted_context(ws, "Make the title bigger")
    assert "meta:title" in info["nodes"]
    assert "\\title{" in text
    assert "\\definecolor{brand}" in text          # level 4: the colour the title uses
    assert "Sentence 3 of topic 17" not in text     # nothing unrelated


def test_slide_ordinal_and_quoted_text_are_matched():
    deck = "\\documentclass{beamer}\n\\begin{document}\n" + "\n".join(
        f"\\begin{{frame}}{{Slide {i}}}\nContent of slide number {i}.\n\\end{{frame}}" for i in range(1, 8)
    ) + "\n\\end{document}\n"
    nodes = index_nodes(deck)
    assert [n.node_id for n, _ in match_nodes(deck, nodes, "fix the typo on slide 3")] == ["frame:slide-3"]
    picked = match_nodes(deck, nodes, 'change "Content of slide number 5." to something better')
    assert picked[0][0].node_id == "frame:slide-5"


def test_ledger_does_not_resend_visible_unchanged_lines():
    ledger = ContextLedger()
    first = "\n".join(f"{i}: line {i}" for i in range(1, 11))
    ledger.mark_permanent(first)
    again = ledger.filter("\n".join(f"{i}: line {i}" for i in range(1, 13)))
    assert "[lines 1-10 unchanged" in again
    assert "11: line 11" in again and "12: line 12" in again
    changed = ledger.filter("5: line five (edited)")
    assert changed == "5: line five (edited)"
