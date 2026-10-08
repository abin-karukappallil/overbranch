"""
LaTeX inside the agent's JSON replies (opencode.agent_loop._parse_agent_response).

Models escape LaTeX for JSON inconsistently. The parser used to guess one style
for the whole reply, and a single `\\u0026` or a newline before "e.g." made it
re-escape a correctly escaped reply: every `\\begin` decoded to a line break
followed by the word "begin" and every newline to a literal `\\n`. These tests
pin the decoded LaTeX for each style.
"""

import json

import pytest

from opencode.agent_loop import OPENCODE_SYSTEM_PROMPT, _parse_agent_response, sanitize_latex_json

B = "\\"
NL = "\n"
ITEMIZE = B + "begin{itemize}" + NL + B + "item A & B" + NL + B + "end{itemize}"
TABULAR_ROWS = "a & b " + B + B + " " + B + "hline" + NL + "c & d " + B + B + B + "hline"


def _dumps(new_str: str, ensure_ascii: bool = False) -> str:
    """A correctly escaped reply, exactly as json.dumps writes it."""
    return json.dumps({"thought": "t", "tool_call": {"name": "replace_text",
                       "arguments": {"old_str": "x", "new_str": new_str}}}, ensure_ascii=ensure_ascii)


def _raw(new_str_json_text: str) -> str:
    """A reply whose new_str is given as the literal JSON-string text the model typed."""
    return ('{"thought":"t","tool_call":{"name":"replace_text","arguments":'
            '{"old_str":"x","new_str":"' + new_str_json_text + '"}}}')


def _new_str(reply: str) -> str:
    return _parse_agent_response(reply)["tool_call"]["arguments"]["new_str"]


@pytest.mark.parametrize("latex", [
    ITEMIZE,
    TABULAR_ROWS,
    B + "section{Steps}" + NL + "i) first" + NL + B + "textbf{ok}",          # newline before "i)"
    B + "section{A}" + NL + "e.g. this" + NL + B + "item b",                 # newline before "e.g."
    B + "begin{align}" + NL + "a " + B + "ne b " + B + B + NL + B + "nu = 1" + NL + B + "end{align}",
    "\t" + B + "item indented with a tab",
])
def test_correctly_escaped_reply_round_trips(latex):
    assert _new_str(_dumps(latex)) == latex


def test_json_unicode_escape_does_not_flip_a_correctly_escaped_reply():
    assert _new_str(_dumps(ITEMIZE).replace("&", B + "u0026")) == ITEMIZE
    s = B + "textbf{Note} \u2014 see " + B + "ref{a}"
    assert _new_str(_dumps(s, ensure_ascii=True)) == s


def test_solidus_escapes_are_json_not_latex():
    s = "Path C:/x/y " + B + "url{http://a.b/c}"
    assert _new_str(_dumps(s).replace("/", B + "/")) == s


@pytest.mark.parametrize("typed, expected", [
    # raw LaTeX with real newline characters
    (B + "begin{itemize}" + NL + B + "item A" + NL + B + "end{itemize}",
     B + "begin{itemize}" + NL + B + "item A" + NL + B + "end{itemize}"),
    # raw LaTeX, \n used for newlines (the most common style)
    (B + "begin{itemize}" + B + "n" + B + "item A" + B + "n" + B + "end{itemize}",
     B + "begin{itemize}" + NL + B + "item A" + NL + B + "end{itemize}"),
    # raw \\ line break followed by a \n newline, and a newline before "a"
    (B + "begin{tabular}{ll}" + B + "na & b " + B + B + B + "n" + B + "end{tabular}",
     B + "begin{tabular}{ll}" + NL + "a & b " + B + B + NL + B + "end{tabular}"),
    # raw \\\hline is a line break and then \hline
    (B + "begin{tabular}{l}a " + B + B + B + "hline" + B + "n" + B + "end{tabular}",
     B + "begin{tabular}{l}a " + B + B + B + "hline" + NL + B + "end{tabular}"),
    # \textbf and \frac are valid JSON escapes (tab, form feed) but mean LaTeX here
    (B + "textbf{x} $" + B + "frac{a}{b}$", B + "textbf{x} $" + B + "frac{a}{b}$"),
    # raw LaTeX with & written as \u0026
    (B + "begin{tabular}{ll}a " + B + "u0026 b " + B + B + B + "n" + B + "end{tabular}",
     B + "begin{tabular}{ll}a & b " + B + B + NL + B + "end{tabular}"),
    # \newline is a valid \n escape followed by "ewline"
    ("line one" + B + "newline two", "line one" + B + "newline two"),
])
def test_raw_latex_reply_is_repaired(typed, expected):
    assert _new_str(_raw(typed)) == expected


@pytest.mark.parametrize("typed, expected", [
    # the only raw macro is \neq: a valid JSON "\n" escape followed by "eq"
    ("$a " + B + "neq b$", "$a " + B + "neq b$"),
    # the only raw macro is \node: "\n" + "ode at"
    (B + "node at (0,0) {A};", B + "node at (0,0) {A};"),
    # a raw \\ row break followed by a real newline character
    ("a & b " + B + B + NL + "c & d " + B + B, "a & b " + B + B + NL + "c & d " + B + B),
])
def test_raw_replies_that_happen_to_be_valid_json(typed, expected):
    assert _new_str(_raw(typed)) == expected


def test_mixed_escaping_in_one_reply():
    assert _new_str(_raw(B + B + "section{A}" + B + "n" + B + "noindent Text")) == \
        B + "section{A}" + NL + B + "noindent Text"
    assert _new_str(_raw(B + B + "begin{equation}" + B + "frac{1}{2}" + B + B + "end{equation}")) == \
        B + "begin{equation}" + B + "frac{1}{2}" + B + "end{equation}"


def test_envelopes_and_batches():
    assert _new_str("```json\n" + _dumps(ITEMIZE) + "\n```") == ITEMIZE
    assert _new_str("Here is the edit:\n" + _dumps(ITEMIZE) + "\nDone.") == ITEMIZE
    batch = json.dumps({"thought": "t", "tool_calls": [
        {"name": "replace_text", "arguments": {"old_str": "a", "new_str": ITEMIZE}},
        {"name": "replace_text", "arguments": {"old_str": "b", "new_str": TABULAR_ROWS}}]})
    parsed = _parse_agent_response(batch.replace("&", B + "u0026"))
    assert [c["arguments"]["new_str"] for c in parsed["tool_calls"]] == [ITEMIZE, TABULAR_ROWS]
    assert _parse_agent_response('{"thought":"ok","done":true,"explanation":"Updated."}')["done"] is True
    assert _parse_agent_response("not json at all") == {}


def test_sanitize_default_mode_unchanged_for_raw_latex():
    assert sanitize_latex_json('{"a":"' + B + 'begin"}') == '{"a":"' + B + B + 'begin"}'


def test_system_prompt_states_the_escaping_rule():
    rendered = OPENCODE_SYSTEM_PROMPT.format(tools_block="TOOLS")
    assert ("write EVERY LaTeX backslash as two backslashes (`" + B + B + "begin{itemize}`") in rendered
    assert "a LaTeX line break `" + B + B + "` as `" + B * 4 + "`" in rendered
    assert "never use `" + B + "uXXXX` escapes" in rendered
