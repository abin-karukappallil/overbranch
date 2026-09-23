import json
import pytest
from unittest.mock import MagicMock, patch
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool
from opencode.shadow_compiler import compile_shadow_buffer, parse_latex_error_log
from opencode.agent_loop import _parse_agent_response, stream_opencode_agent


def test_read_file_range_clamps_at_300_lines():
    """Verify that read_file_range clamps line requests at 300 lines (previously 200)."""
    # Create a workspace with 500 lines
    code = "\n".join([f"Line {i}" for i in range(1, 501)])
    workspace = ShadowWorkspace(original_code=code)

    result = execute_tool(
        tool_name="read_file_range",
        args={"start_line": 1, "end_line": 450},
        workspace=workspace,
    )
    assert result["lines_read"] == "1-301"
    # 301 lines inclusive (1 to 301 is 301 lines)
    assert len(result["content"].strip().split("\n")) == 301


def test_shadow_compiler_infra_skip_on_missing_compiler():
    """Verify that shadow compiler returns infra_skip: True when pdflatex is missing."""
    workspace = ShadowWorkspace(original_code="\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}")

    # Mock compile_latex returning infrastructure failure (no LaTeX error markers)
    with patch("compiler.compile_latex") as mock_compile:
        mock_compile.return_value = {
            "success": False,
            "error_log": "LaTeX compilation failed.",
            "raw_log": "LaTeX compilation failed.",
        }

        res = compile_shadow_buffer(workspace)
        assert res["success"] is True
        assert res["infra_skip"] is True
        assert res["errors"] == []
        assert "skipped" in res["summary"].lower()


def test_shadow_compiler_infra_skip_on_os_error():
    """Verify that shadow compiler handles command not found / no such file."""
    workspace = ShadowWorkspace(original_code="\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}")

    with patch("compiler.compile_latex") as mock_compile:
        mock_compile.return_value = {
            "success": False,
            "error_log": "/bin/sh: pdflatex: command not found",
            "raw_log": "/bin/sh: pdflatex: command not found",
        }

        res = compile_shadow_buffer(workspace)
        assert res["success"] is True
        assert res["infra_skip"] is True
        assert res["errors"] == []


def test_shadow_compiler_preserves_real_latex_syntax_errors():
    """Verify that real LaTeX syntax errors are NOT treated as infra errors."""
    workspace = ShadowWorkspace(original_code="\\documentclass{article}\n\\begin{document}\n\\badcmd\n\\end{document}")

    with patch("compiler.compile_latex") as mock_compile:
        mock_compile.return_value = {
            "success": False,
            "error_log": "! Undefined control sequence.\nl.3 \\badcmd",
            "raw_log": "! Undefined control sequence.\nl.3 \\badcmd",
        }

        res = compile_shadow_buffer(workspace)
        assert res["success"] is False
        assert res.get("infra_skip") is not True
        assert len(res["errors"]) > 0
        assert "Undefined control sequence" in res["errors"][0]["error"]


def test_shadow_compiler_passes_assets(tmp_path):
    """Verify that assets from workspace._assets_dir are read and forwarded to compiler."""
    # Create dummy asset file in tmp_path
    asset_file = tmp_path / "diagram.png"
    asset_file.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    workspace = ShadowWorkspace(
        original_code="\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}",
        assets_dir=str(tmp_path),
    )

    with patch("compiler.compile_latex") as mock_compile:
        mock_compile.return_value = {
            "success": True,
            "log": "Compiled successfully",
            "compile_time_ms": 150,
        }

        res = compile_shadow_buffer(workspace)
        assert res["success"] is True
        mock_compile.assert_called_once()
        call_kwargs = mock_compile.call_args.kwargs
        assert call_kwargs.get("files") is not None
        assert len(call_kwargs["files"]) == 1
        assert call_kwargs["files"][0]["filename"] == "diagram.png"


def test_agent_loop_truncation_continuation():
    """Verify that when finish_reason is 'length', continuation is requested and combined."""
    # Truncated response:
    part1 = '{"thought": "Writing chapter 1", "tool_call": {"name": "str_replace", "arguments": {"old_str": "Old", "new_str": "Long '
    part2 = 'replacement text"}}}'

    mock_router = MagicMock()
    # First call returns truncated part1 with finish_reason="length"
    # Second call returns part2 with finish_reason="stop"
    # Third call returns done=true
    mock_router.chat.side_effect = [
        {"content": part1, "finish_reason": "length"},
        {"content": part2, "finish_reason": "stop"},
        {"content": json.dumps({"thought": "Done", "done": True}), "finish_reason": "stop"},
    ]

    with patch("opencode.agent_loop.provider_router", mock_router):
        code = "Preamble\nOld\nPostamble"
        events = list(stream_opencode_agent(
            user_instruction="Expand content",
            project_id="test-project",
            current_code=code,
            max_steps=5,
        ))

        # Check that tool_call was parsed successfully after continuation
        tool_call_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_call_events) >= 1
        assert tool_call_events[0]["tool"] == "str_replace"
        assert tool_call_events[0]["args"]["new_str"] == "Long replacement text"


def test_agent_loop_handles_infra_skip_compilation():
    """Verify agent loop handles infra_skip correctly and sets compile_verified."""
    mock_router = MagicMock()
    mock_router.chat.side_effect = [
        # Step 1: LLM calls verify_compile
        {
            "content": json.dumps({
                "thought": "Let's compile",
                "tool_call": {"name": "verify_compile", "arguments": {}}
            }),
            "finish_reason": "stop",
        },
        # Step 2: LLM sets done=true
        {
            "content": json.dumps({"thought": "Finished", "done": True}),
            "finish_reason": "stop",
        }
    ]

    with patch("opencode.agent_loop.provider_router", mock_router), \
         patch("opencode.shadow_compiler.compile_shadow_buffer") as mock_compile:

        mock_compile.return_value = {
            "success": True,
            "infra_skip": True,
            "errors": [],
            "stderr": "",
            "compile_time_ms": 0,
            "summary": "Shadow compilation skipped",
        }

        code = "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}"
        events = list(stream_opencode_agent(
            user_instruction="Check compilation",
            project_id="test-project",
            current_code=code,
            mode="chat",
            max_steps=3,
        ))

        # Verify status event emitted with infra skip message
        status_events = [e for e in events if e.get("type") == "status" and "Shadow compilation skipped" in e.get("message", "")]
        assert len(status_events) == 1

        # Check final result event has compile_verified = True
        result_events = [e for e in events if e.get("type") == "result"]
        assert len(result_events) == 1
        assert result_events[0]["data"]["compile_verified"] is True


def test_compact_conversation_history_prunes_older_tool_outputs():
    """Verify that conversation history older than recent turns is compacted."""
    from opencode.agent_loop import _compact_conversation_history

    messages = [
        {"role": "system", "content": "You are OpenCode assistant."},
        {"role": "user", "content": "Initial user instruction"},
        # Turn 1 (Old)
        {"role": "assistant", "content": json.dumps({"thought": "reading", "tool_call": {"name": "read_file_range", "arguments": {"start_line": 1, "end_line": 50}}})},
        {"role": "user", "content": "TOOL RESULT from `read_file_range`:\n" + ("1: \\documentclass{report}\n" * 50)},
        # Turn 2 (Old)
        {"role": "assistant", "content": json.dumps({"thought": "getting theme", "tool_call": {"name": "get_template_theme", "arguments": {"category": "ppt"}}})},
        {"role": "user", "content": "TOOL RESULT from `get_template_theme`:\n" + ("\\usepackage{xcolor}\n" * 50)},
        # Turn 3 (Recent)
        {"role": "assistant", "content": json.dumps({"thought": "replacing", "tool_call": {"name": "str_replace", "arguments": {"old_str": "a", "new_str": "b"}}})},
        {"role": "user", "content": "TOOL RESULT from `str_replace`:\n{\"success\": true}"},
        # Turn 4 (Recent)
        {"role": "assistant", "content": json.dumps({"thought": "verifying", "tool_call": {"name": "verify_compile", "arguments": {}}})},
        {"role": "user", "content": "TOOL RESULT from `verify_compile`:\n{\"success\": true}"},
    ]

    compacted = _compact_conversation_history(messages, keep_recent_turns=2)

    # Total message count preserved
    assert len(compacted) == len(messages)
    # System and initial user prompt are untouched
    assert compacted[0]["content"] == "You are OpenCode assistant."
    assert compacted[1]["content"] == "Initial user instruction"

    # Old Turn 1 & 2 user tool outputs are compacted
    assert "Lines read and processed" in compacted[3]["content"]
    assert "Template theme retrieved" in compacted[5]["content"]

    # Recent turns (Turn 3 & 4) remain completely intact
    assert "{\"success\": true}" in compacted[7]["content"]
    assert "{\"success\": true}" in compacted[9]["content"]


def test_build_document_outline_indexes_structure():
    """Verify that _build_document_outline accurately indexes chapters, sections, and frames."""
    from opencode.agent_loop import _build_document_outline

    code = (
        "\\documentclass{report}\n"
        "\\usepackage{amsmath}\n"
        "\\begin{document}\n"
        "\\chapter{Introduction to AI}\n"
        "Text here\n"
        "\\section{Background & History}\n"
        "More text\n"
        "\\subsection{Early Neural Nets}\n"
        "\\chapter{Methodology}\n"
        "\\section{Architecture Design}\n"
        "\\end{document}\n"
    )
    workspace = ShadowWorkspace(original_code=code)
    outline = _build_document_outline(workspace)

    assert "DOCUMENT STRUCTURE OUTLINE" in outline
    assert "Preamble & Setup" in outline
    assert "[CHAPTER] \\chapter{Introduction to AI}" in outline
    assert "[SECTION] \\section{Background & History}" in outline
    assert "[SUBSECTION] \\subsection{Early Neural Nets}" in outline
    assert "[CHAPTER] \\chapter{Methodology}" in outline


def test_router_chat_fallback_on_primary_failure():
    """Verify that ProviderRouter.chat falls back to OpenRouter when primary provider fails."""
    from providers.router import ProviderRouter

    router = ProviderRouter()

    # Mock primary gemini provider to raise error
    mock_gemini = MagicMock()
    mock_gemini.get_provider_name.return_value = "Gemini"
    mock_gemini.chat.side_effect = Exception("Gemini Web2API 504 Gateway Timeout")

    # Mock openrouter fallback
    mock_openrouter = MagicMock()
    mock_openrouter.get_provider_name.return_value = "OpenRouter"
    mock_openrouter.candidates = [{"name": "Server Key 1", "key": "test-key"}]
    mock_openrouter.chat.return_value = {
        "content": "{\"thought\": \"Fallback succeeded\", \"done\": true}",
        "model_used": "meta-llama/llama-3.3-70b-instruct",
        "finish_reason": "stop",
    }

    router.gemini = mock_gemini
    router.openrouter = mock_openrouter

    resp = router.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gemini-3.7-flash",
    )

    assert resp.get("is_fallback") is True
    assert "Fallback succeeded" in resp.get("content", "")
    mock_openrouter.chat.assert_called_once()

