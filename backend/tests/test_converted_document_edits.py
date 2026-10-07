"""
Agent edits on an imported PDF, and fake-bold PDFs.

A converted document has no sections or frames — just pages of positioned or
flowing text — so the request's own words are the only pointer to the target.
"change jacob to tims ittus" used to do nothing: the targeted context matched
no block, the model's search for "jacob" was case-sensitive against "JACOB",
and replace_text could not match a different case.
"""

import asyncio
import shutil

import pymupdf
import pytest

from conftest import final_buffer, result_event, run_agent
from pdf2latex_fixtures import ticket_pdf

from opencode.context_builder import build_targeted_context
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool

PREAMBLE = ("\\documentclass{article}\n\\usepackage[T1]{fontenc}\n\\usepackage{xcolor}\n"
            "\\definecolor{c000000}{RGB}{0,0,0}\n\\definecolor{c2961A6}{RGB}{41,97,166}\n")


def converted_doc(pages: int = 3) -> str:
    """Shaped like pdf2latex output: page markers, \\fontsize runs, \\vspace gaps, a tabular."""
    out = [PREAMBLE, "\\begin{document}"]
    for p in range(1, pages + 1):
        out.append(f"%% ==== OB-PAGE {p} ====")
        for i in range(30):
            out.append(f"{{\\fontsize{{8bp}}{{9.6bp}}\\selectfont Line {i} of page {p}: terms and conditions apply.}}\\\\")
            out.append("\\vspace{1.5pt}")
        if p == 1:
            out += ["\\begin{tabular}{@{}llll@{}}",
                    "\\textbf{\\# Name} & \\textbf{Age} & \\textbf{Gender} & \\textbf{Booking Status} \\\\",
                    "1. JACOB PRASANTH & 22 & M & CNF/S5/56/SIDE UPPER \\\\",
                    "2. ABIN THOMAS & 22 & M & CNF/S5/50/MIDDLE \\\\",
                    "\\end{tabular}"]
        out.append("\\newpage" if p < pages else "")
    out.append("\\end{document}")
    return "\n".join(out) + "\n"


def test_context_for_unstructured_document_contains_the_named_text():
    ws = ShadowWorkspace(converted_doc())
    assert ws.get_line_count() > 150
    text, info = build_targeted_context(ws, "change jacob to tims ittus")
    assert "1. JACOB PRASANTH" in text
    assert info["text_hits"] == ["jacob"]
    assert "Line 20 of page 3" not in text  # still targeted, not the whole file


def test_pages_are_nodes():
    ws = ShadowWorkspace(converted_doc())
    ids = [n.node_id for n in ws.get_nodes()]
    assert {"page:1", "page:2", "page:3"} <= set(ids)
    assert "Line 5 of page 2" in ws.get_block("page 2")["content"]


def test_search_falls_back_to_ignoring_case():
    ws = ShadowWorkspace(converted_doc())
    res = execute_tool("search_document", {"query": "jacob"}, ws)
    assert res["match_count"] == 1 and "note" in res


def test_replace_text_matches_a_different_case_when_unique():
    ws = ShadowWorkspace(converted_doc())
    res = ws.str_replace("jacob prasanth", "TIMS ITTUS")
    assert res["success"] and res["method"] == "normalized_ci"
    assert "1. TIMS ITTUS & 22" in ws.get_buffer()


def test_agent_renames_passenger_in_converted_document(scripted_llm, stub_compiler):
    doc = converted_doc()
    seen_context = {}

    def first(messages):
        seen_context["has_jacob"] = "JACOB PRASANTH" in messages[1]["content"]
        return {"thought": "Rename the passenger.", "tool_call": {"name": "replace_text", "arguments": {
            "old_str": "JACOB", "new_str": "TIMS ITTUS"}}, "done": True, "explanation": "Renamed."}

    scripted_llm([first])
    events = run_agent("change jacob to tims ittus", doc)
    assert seen_context["has_jacob"]
    buf = final_buffer(events, doc)
    assert "1. TIMS ITTUS PRASANTH & 22" in buf
    assert buf.replace("TIMS ITTUS", "JACOB") == doc            # nothing else changed
    assert result_event(events)["trace"]["edits"][0]["success"]


def test_agent_recovers_from_lowercase_search(scripted_llm, stub_compiler):
    """The model searches with the user's lower-case word, then edits from the hit."""
    doc = converted_doc()

    def edit_from_search(messages):
        last = messages[-1]["content"]
        assert "JACOB PRASANTH" in last
        return {"thought": "edit", "tool_call": {"name": "replace_text", "arguments": {
            "old_str": "1. JACOB PRASANTH", "new_str": "1. TIMS ITTUS"}}, "done": True}

    scripted_llm([{"thought": "find it", "tool_call": {"name": "search_document", "arguments": {"query": "jacob"}}},
                  edit_from_search])
    events = run_agent("change jacob to tims ittus", doc)
    assert "1. TIMS ITTUS & 22" in final_buffer(events, doc)


# --- fake bold by overprinting ---------------------------------------------------------

def test_overprinted_bold_is_extracted_once_and_bold():
    from pdf2latex.extract import _extract_lines
    doc = pymupdf.open(stream=ticket_pdf(fake_bold=True), filetype="pdf")
    lines = [ln.text.strip() for ln in _extract_lines(doc[0])]
    assert lines.count("Booked from") == 1
    assert lines.count("Passenger Details") == 1
    styles = {ln.text.strip(): ln.spans[0].bold for ln in _extract_lines(doc[0])}
    assert styles["Booked from"] is True and styles["Passenger Details"] is True
    assert styles["IR recovers only 57% of cost of travel on an average."] is False


@pytest.mark.skipif(not (shutil.which("pdflatex") and shutil.which("pdftoppm")), reason="needs TeX")
def test_fake_bold_ticket_converts_without_double_text(monkeypatch, tmp_path):
    from pdf2latex import jobs, pipeline
    from pdf2latex.facts import fallback_body

    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path))

    async def fake_generate(ctx, page, facts, png, pr, note="", allow_short_retry=True):
        pr.attempts += 1
        return fallback_body(page, ctx.geom, ctx.fonts).replace("\\bfseries", "")

    monkeypatch.setattr(pipeline, "_generate", fake_generate)
    monkeypatch.setattr(pipeline, "llm_available", lambda: True)
    monkeypatch.setattr(pipeline, "write_output_to_project", lambda *a, **k: {})
    st = jobs.create_job("tester", "proj-test", "t.pdf", 1)
    asyncio.run(pipeline.run_conversion(st["job_id"], ticket_pdf(fake_bold=True), "proj-test"))
    report = jobs.load_job(st["job_id"])["report"]["pages"][0]
    tex = (jobs.job_dir(st["job_id"]) / "output" / "main.tex").read_text()
    assert tex.count("Booked from") == 1 and tex.count("Passenger Details") == 1
    out = pymupdf.open(jobs.job_dir(st["job_id"]) / "output.pdf")[0].get_text("words")
    assert sum(1 for w in out if w[4] == "Booked") == 1
    assert report["text_coverage"] == 1.0 and report["style_mismatches"] == 0
    assert any(r == "bold restored: 'Booked from'" for r in report["geometry_repairs"])
