"""
tests/test_ask_ai_to_fix.py
===========================
Integration and unit tests for the "Ask AI to Fix" / compilation error repair system.
Validates:
1. Exact user error log parsing & categorization.
2. Auto-healing of TikZ calc library, path semicolons, unclosed frames, and color palettes.
3. Scope classification properly recognizing compilation fix requests as TARGETED_EDIT.
4. Agent loop pre-healing and mandatory verify_compile enforcement before done=true.
"""

import pytest
import re
from unittest.mock import MagicMock, patch

from latex_error_fixer import (
    parse_compilation_errors,
    auto_heal_latex_code,
    balance_latex_environments,
    format_compilation_fix_prompt,
)
from scope_classifier import classify_scope, ScopeType
from opencode.shadow_workspace import ShadowWorkspace
from opencode.shadow_compiler import parse_latex_error_log


USER_REPORTED_ERROR_LOG = """./main.tex:66: LaTeX Error: Bad math environment delimiter.
./main.tex:66: LaTeX Error: Bad math environment delimiter.
./main.tex:66: Package tikz Error: Giving up on this path. Did you forget a sem
./main.tex:66: LaTeX Error: \\begin{tikzpicture} on input line 66 ended by \\end{frame}.
./main.tex:66: LaTeX Error: \\begin{tikzpicture} on input line 66 ended by \\end{frame}.
./main.tex:241: LaTeX Error: \\begin{frame} on input line 160 ended by \\end{document}.
./main.tex:241: LaTeX Error: \\begin{frame} on input line 160 ended by \\end{document}.
! Emergency stop.
!  ==> Fatal error occurred, no output PDF file produced!

these types of erros in after ai edits and the ask ai to fix is not working....think how to fix this in agentic flow and fix that and in ask ai to fix this feat also"""


def test_scope_classifier_recognizes_user_compilation_error():
    """Verify scope_classifier classifies the compilation fix prompt as TARGETED_EDIT."""
    result = classify_scope(
        user_instruction=USER_REPORTED_ERROR_LOG,
        current_code=r"\documentclass{beamer}\begin{document}\end{document}",
    )
    assert result.scope == ScopeType.TARGETED_EDIT.value
    assert not result.is_full_rewrite
    assert not result.is_expansion
    assert result.confidence == 1.0


def test_parse_exact_user_error_log():
    """Verify parse_compilation_errors extracts line 66 and line 160 with accurate types."""
    errors = parse_compilation_errors(USER_REPORTED_ERROR_LOG)
    assert len(errors) >= 3

    line_numbers = [e.line_number for e in errors]
    assert 66 in line_numbers
    assert 160 in line_numbers

    # Verify bad math delimiter on line 66
    bad_math = next((e for e in errors if e.error_type == "BAD_MATH_DELIMITER"), None)
    assert bad_math is not None
    assert bad_math.line_number == 66
    assert "calc" in bad_math.suggested_action

    # Verify unclosed frame on line 160
    unclosed_frame = next((e for e in errors if e.line_number == 160 and e.error_type == "UNCLOSED_ENVIRONMENT"), None)
    assert unclosed_frame is not None
    assert r"\end{frame}" in unclosed_frame.suggested_action


def test_shadow_compiler_error_log_parser():
    """Verify shadow_compiler parse_latex_error_log populates structured error diagnostics."""
    diagnostics = parse_latex_error_log(USER_REPORTED_ERROR_LOG)
    assert diagnostics["has_errors"] is True
    assert len(diagnostics["errors"]) >= 3
    first_err = diagnostics["errors"][0]
    assert "line" in first_err
    assert "suggested_action" in first_err
    assert "type" in first_err


def test_auto_heal_fixes_all_user_reported_issues():
    """
    Construct a document with the exact issues described by the user:
    - Line with TikZ coordinate math $(...) without \\usetikzlibrary{calc}
    - TikZ node/fill path without semicolon
    - Unclosed frame 2 ended by \\end{document}
    - Undefined Regalia palette colors
    """
    broken_latex = r"""\documentclass{beamer}
\usepackage{tikz}

\begin{document}

\begin{frame}{Slide 1}
\begin{tikzpicture}
\fill[navy] (0,0) rectangle ($(current page.north west)+(2,2)$)
\end{tikzpicture}
\end{frame}

\begin{frame}{Slide 2}
This is slide 2 content that is unclosed before document ends.
\end{document}"""

    healed_code, fixes = auto_heal_latex_code(broken_latex, USER_REPORTED_ERROR_LOG)

    # 1. calc library was injected
    assert r"\usetikzlibrary{calc}" in healed_code

    # 2. semicolon was added to TikZ path
    assert r"$(current page.north west)+(2,2)$);" in healed_code

    # 3. unclosed frame was closed before \end{document}
    assert healed_code.count(r"\begin{frame}") == healed_code.count(r"\end{frame}")
    assert healed_code.find(r"\end{frame}") < healed_code.rfind(r"\end{document}")

    # 4. Regalia colors were injected
    assert r"\definecolor{navy}" in healed_code

    # 5. Fixes were tracked
    assert len(fixes) >= 3


def test_workspace_ensure_document_structure_repairs_shadow_buffer():
    """Verify ShadowWorkspace.ensure_document_structure automatically heals the buffer."""
    ws = ShadowWorkspace(
        original_code=r"""\documentclass{beamer}
\usepackage{tikz}
\begin{document}
\begin{frame}{Intro}
\node at (0,0) {Title}
\end{frame}
\begin{frame}{Broken Frame}
Unclosed frame
\end{document}""",
        file_path="main.tex",
    )

    ws.ensure_document_structure()
    repaired = ws.get_buffer()

    assert repaired.count(r"\begin{frame}") == repaired.count(r"\end{frame}")
    assert repaired.rfind(r"\end{frame}") < repaired.rfind(r"\end{document}")


def test_format_compilation_fix_prompt_generation():
    """Verify format_compilation_fix_prompt creates actionable instructions for LLM."""
    ws = ShadowWorkspace(
        original_code=r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Title}
Test line 4
\end{frame}
\end{document}""",
        file_path="main.tex",
    )
    errors = parse_compilation_errors(USER_REPORTED_ERROR_LOG)
    prompt = format_compilation_fix_prompt(
        raw_error=USER_REPORTED_ERROR_LOG,
        parsed_errors=errors,
        workspace=ws,
        fixes_applied=["Injected \\usetikzlibrary{calc}", "Closed unclosed \\begin{frame}"],
    )

    assert "COMPILATION ERROR SURGICAL REPAIR MANDATE" in prompt
    assert "Injected \\usetikzlibrary{calc}" in prompt
    assert "Line 66" in prompt
    assert "Line 160" in prompt
    assert "verify_compile" in prompt


def test_agent_loop_compilation_fix_flow():
    """Verify that agent loop enforces verify_compile and pre-heals the workspace."""
    from opencode.agent_loop import stream_opencode_agent
    import json

    broken_code = r"""\documentclass{beamer}
\usepackage{tikz}
\begin{document}
\begin{frame}{Slide 1}
\fill[navy] (0,0) rectangle ($(current page.north west)+(2,2)$)
\end{frame}
\begin{frame}{Slide 2}
Broken frame
\end{document}"""

    # Step 1: Agent tries premature done=true without verify_compile
    response_1 = json.dumps({"thought": "I will conclude without compiling.", "done": True})
    # Step 2: Agent runs verify_compile
    response_2 = json.dumps({
        "thought": "I will verify compilation now.",
        "tool_call": {"name": "verify_compile", "arguments": {}},
    })
    # Step 3: Agent concludes after successful compile
    response_3 = json.dumps({
        "thought": "Verified cleanly.",
        "done": True,
        "explanation": "Compilation verified and errors repaired.",
    })

    with patch("providers.router.provider_router.chat") as mock_chat, \
         patch("opencode.shadow_compiler.compile_shadow_buffer") as mock_compile:
        mock_compile.return_value = {
            "success": True,
            "stderr": "",
            "errors": [],
            "summary": "Compilation passed",
            "compile_time_ms": 150,
        }
        mock_chat.side_effect = [
            {"content": response_1},
            {"content": response_2},
            {"content": response_3},
        ]

        events = list(stream_opencode_agent(
            user_instruction=USER_REPORTED_ERROR_LOG,
            current_code=broken_code,
            project_id="test_proj",
            max_steps=5,
        ))

    event_types = [e.get("type") for e in events]
    # Check that status event reported pre-healing
    assert any("Pre-healed" in e.get("message", "") for e in events if e.get("type") == "status")
    # Check that tool_call for verify_compile happened
    assert "tool_call" in event_types
    # Check that result was yielded
    assert "result" in event_types
    result_event = next(e for e in events if e.get("type") == "result")
    assert result_event["data"]["compile_verified"] is True
    # Verify final buffer has unclosed frame healed and calc library injected
    proposed = result_event["data"]["proposed_chunk"]
    assert r"\usetikzlibrary{calc}" in proposed
    assert proposed.count(r"\begin{frame}") == proposed.count(r"\end{frame}")


def test_auto_heal_fixes_and_compiles_cleanly_in_pdflatex():
    """Verify that auto_heal_latex_code turns a severely defective document into one that compiles cleanly."""
    from compiler import compile_latex

    broken_code = r"""\documentclass{beamer}
\usepackage{tikz}
\begin{document}
\begin{frame}{Slide 1: Architecture}
\begin{tikzpicture}
\coordinate (A) at (0,0);
\draw (A) -- ($(A) + (2,2)$);
\node (B) at (1,1) {Label}
\node (C) at (2,2) {Sublabel}
\end{tikzpicture}
\end{frame}
\begin{frame}{Slide 2: Bullet Points}
\item Lonely point 1
\item Lonely point 2
\end{frame}
\begin{frame}{Slide 3: Conclusions}
Concluding remarks without closing frame tag
\end{document}"""

    healed, fixes = auto_heal_latex_code(broken_code, USER_REPORTED_ERROR_LOG)
    assert len(fixes) >= 3

    # Compile the healed code with pdflatex
    res = compile_latex(healed)
    assert res.get("success") is True, f"Compilation failed: {res.get('error_log')}"


