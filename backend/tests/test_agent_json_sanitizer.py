r"""
Regressions for LaTeX corrupted on its way out of the model's JSON.

``_parse_agent_response`` has to decode JSON that may or may not escape LaTeX
backslashes. Two shapes are ambiguous, and both used to be resolved the wrong
way -- silently, inside the string the agent then wrote into the document:

* ``\nonumber`` decoded to a literal newline plus ``onumber``, an undefined
  control sequence. The rule was a hand-kept whitelist of ``\n`` commands and
  every macro missing from it broke the same way.
* ``\\`` decoded to a single backslash, so a tabular row break vanished and
  ``\\[0.3em]`` became ``\[0.3em]`` -- opening display math where a spaced line
  break was meant.
"""

from __future__ import annotations

import json

import pytest

from opencode.agent_loop import _parse_agent_response, sanitize_latex_json


def _unescaped_response(latex: str) -> str:
    """A response that writes LaTeX raw, the way models actually do."""
    return (
        '{"thought": "edit", "tool_call": {"name": "str_replace", '
        '"arguments": {"old_str": "PLACEHOLDER", "new_str": "' + latex + '"}}}'
    )


def _new_str(raw: str) -> str:
    parsed = _parse_agent_response(raw)
    assert parsed, f"response did not parse: {raw[:120]}"
    return parsed["tool_call"]["arguments"]["new_str"]


UNESCAPED_LATEX_CASES = [
    ("nonumber", r"\begin{align} x &= 1 \nonumber \end{align}", r"\nonumber"),
    ("notag", r"\begin{align} y \notag \end{align}", r"\notag"),
    ("nicefrac", r"\nicefrac{1}{2}", r"\nicefrac"),
    ("notin", r"$x \notin A$", r"\notin"),
    ("normalfont", r"{\normalfont text}", r"\normalfont"),
    ("noindent", r"\noindent Para", r"\noindent"),
    ("node", r"\node (a) at (0,0) {x};", r"\node"),
    ("newpage", r"\newpage", r"\newpage"),
    ("textbf", r"\textbf{bold}", r"\textbf"),
    ("frac", r"$\frac{1}{2}$", r"\frac"),
    ("begin_frame", r"\begin{frame}{T}\end{frame}", r"\begin{frame}"),
]


@pytest.mark.parametrize(
    "name,latex,expected", UNESCAPED_LATEX_CASES,
    ids=[c[0] for c in UNESCAPED_LATEX_CASES],
)
def test_unescaped_latex_macros_survive_decoding(name, latex, expected):
    out = _new_str(_unescaped_response(latex))
    assert expected in out, f"{name}: {expected!r} lost, got {out!r}"
    assert "\n" not in out, f"{name}: a macro was decoded into a newline: {out!r}"


def test_unescaped_double_backslash_stays_a_latex_line_break():
    latex = r"\begin{tabular}{ll} a & b \\ c & d \\[0.3em] \end{tabular}"
    out = _new_str(_unescaped_response(latex))
    assert r"a & b \\ c" in out, out
    # Not \[0.3em], which would open display math.
    assert r"\\[0.3em]" in out, out


def test_properly_escaped_response_keeps_newline_escapes():
    r"""
    The converse case: a model that escapes LaTeX correctly writes ``\\nonumber``
    and means a real line break by ``\n``. Nothing may be rewritten there.
    """
    payload = {
        "thought": "line one\nline two",
        "tool_call": {
            "name": "str_replace",
            "arguments": {
                "old_str": "a",
                "new_str": r"\begin{tabular}{ll} a & b \\ c \end{tabular} \nonumber",
            },
        },
    }
    raw = json.dumps(payload)
    parsed = _parse_agent_response(raw)
    assert parsed["thought"] == "line one\nline two"
    assert parsed["tool_call"]["arguments"]["new_str"] == payload["tool_call"]["arguments"]["new_str"]


def test_escaped_quotes_are_not_damaged():
    raw = '{"thought": "he said \\"hi\\"", "done": true, "explanation": "ok"}'
    parsed = _parse_agent_response(raw)
    assert parsed["thought"] == 'he said "hi"'


def test_sanitizer_is_idempotent():
    """Running the repair twice must not keep widening backslash runs."""
    raw = _unescaped_response(r"\begin{align} x \nonumber \\ y \end{align}")
    once = sanitize_latex_json(raw)
    assert sanitize_latex_json(once) == once


def test_sanitizer_leaves_backslash_free_text_alone():
    raw = '{"thought": "no latex here", "done": true}'
    assert sanitize_latex_json(raw) == raw
