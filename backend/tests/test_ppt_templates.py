"""
tests/test_ppt_templates.py — Tests for Default Regalia PPT Template & Template Switch Tool Calls
==================================================================================================
Tests:
1. Regalia is the default PPT template in template_registry (both explicit and fallback).
2. list_available_themes annotates Regalia with is_default=True.
3. Other PPT templates ('nordlight', 'prism', 'minimalist', 'basic', 'sorbonne', 'uwm') resolve correctly.
4. get_template_theme tool execution via execute_tool.
5. stream_opencode_agent sets Regalia as the default template for Beamer/PPT creation.
6. stream_opencode_agent detects "change design" / "change template" and mandates get_template_theme tool call.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from opencode.template_registry import get_template_theme, list_available_themes
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool
from opencode.agent_loop import stream_opencode_agent


def test_regalia_is_default_ppt_template():
    """Verify that Regalia is returned when requesting 'default' or 'regalia' theme for PPT."""
    # 1. Explicit 'regalia'
    res_regalia = get_template_theme(category="ppt", theme_name="regalia", extract_section="all")
    assert res_regalia["success"] is True
    assert "Regalia" in res_regalia["theme_name"]
    assert "navy" in res_regalia["content"]
    assert "gold" in res_regalia["content"]
    assert "cream" in res_regalia["content"]

    # 2. 'default' keyword
    res_default = get_template_theme(category="ppt", theme_name="default", extract_section="all")
    assert res_default["success"] is True
    assert "Regalia" in res_default["theme_name"]

    # 3. Preamble extraction for Regalia
    res_preamble = get_template_theme(category="ppt", theme_name="regalia", extract_section="preamble")
    assert res_preamble["success"] is True
    assert "\\begin{document}" not in res_preamble["content"]
    assert "\\setbeamercolor{background canvas}{bg=cream}" in res_preamble["content"]


def test_list_ppt_themes_highlights_default_regalia():
    """Verify list_available_themes for ppt includes all themes and marks Regalia as default."""
    themes = list_available_themes("ppt")
    assert len(themes) >= 5

    theme_ids = [t["id"] for t in themes]
    assert "regalia-presentation-template" in theme_ids
    assert "nordlight-presentation-template" in theme_ids
    assert "prism-presentation-template" in theme_ids

    regalia_entry = next(t for t in themes if "regalia" in t["id"])
    assert regalia_entry.get("is_default") is True
    assert "Default PPT Template" in regalia_entry.get("description", "")


def test_alternative_ppt_themes_resolve():
    """Verify alternative PPT themes can be retrieved for redesigning."""
    alternatives = ["nordlight", "prism", "minimalist", "basic", "uwm"]
    for alt in alternatives:
        res = get_template_theme(category="ppt", theme_name=alt, extract_section="preamble")
        assert res["success"] is True, f"Failed to retrieve theme '{alt}'"
        assert len(res["content"]) > 100, f"Theme '{alt}' preamble is empty"


def test_get_template_theme_via_execute_tool():
    """Verify get_template_theme tool works through the execute_tool dispatcher."""
    ws = ShadowWorkspace(
        original_code=r"\documentclass{beamer}\begin{document}\end{document}",
        project_id="proj-theme-test",
    )

    # 1. Fetch Regalia
    res = execute_tool("get_template_theme", {"category": "ppt", "theme_name": "regalia"}, ws)
    assert res.get("success") is True
    assert "Regalia" in res.get("theme_name", "")

    # 2. Fetch alternative 'nordlight' preamble
    res_nord = execute_tool("get_template_theme", {
        "category": "ppt",
        "theme_name": "nordlight",
        "extract_section": "preamble",
    }, ws)
    assert res_nord.get("success") is True
    assert "Nordlight" in res_nord.get("theme_name", "")
    assert res_nord.get("section_type") == "preamble"


def test_agent_loop_mandates_regalia_for_ppt_creation():
    """Verify agent loop instructs LLM to use Regalia template by default when creating slides."""
    mock_router = MagicMock()
    mock_router.chat.return_value = {
        "content": json.dumps({"thought": "Generating Regalia deck", "done": True}),
        "finish_reason": "stop",
    }

    code = r"\documentclass{beamer}\begin{document}\end{document}"

    with patch("opencode.agent_loop.provider_router", mock_router):
        events = list(stream_opencode_agent(
            user_instruction="Create a presentation on Quantum Computing",
            project_id="proj-create-ppt",
            current_code=code,
            mode="edit",
            max_steps=1,
        ))

        # Check prompt sent to LLM
        last_call_messages = mock_router.chat.call_args[1]["messages"]
        user_msg = next((m["content"] for m in last_call_messages if m["role"] == "user"), "")
        system_msg = next((m["content"] for m in last_call_messages if m["role"] == "system"), "")

        # System prompt must mandate Regalia
        assert "Regalia" in system_msg
        # User message archetype hint must mandate Regalia
        assert "DEFAULT TEMPLATE: REGALIA" in user_msg
        assert "0B2545" in user_msg  # Navy hex color
        assert "C9A24B" in user_msg  # Gold hex color
        assert "F7F4EC" in user_msg  # Cream hex color


def test_agent_loop_mandates_tool_call_for_design_change():
    """Verify agent loop recognizes 'change design' / 'change template' and mandates get_template_theme tool call."""
    mock_router = MagicMock()
    mock_router.chat.return_value = {
        "content": json.dumps({"thought": "Done", "done": True}),
        "finish_reason": "stop",
    }

    # Sample existing presentation
    code = r"""\documentclass{beamer}
\usetheme{Madrid}
\begin{document}
\begin{frame}{Slide 1}
\begin{itemize}\item Point 1\end{itemize}
\end{frame}
\end{document}"""

    prompts_to_test = [
        "change the design of this presentation",
        "switch template to nordlight",
        "change template to a different ppt design",
    ]

    for p in prompts_to_test:
        with patch("opencode.agent_loop.provider_router", mock_router):
            events = list(stream_opencode_agent(
                user_instruction=p,
                project_id="proj-redesign",
                current_code=code,
                mode="edit",
                max_steps=1,
            ))

            last_call_messages = mock_router.chat.call_args[1]["messages"]
            user_msg = next((m["content"] for m in last_call_messages if m["role"] == "user"), "")

            assert "REDESIGN / TEMPLATE CHANGE MANDATE (MANDATORY TOOL CALL)" in user_msg
            assert "YOU MUST MAKE A TOOL CALL TO `get_template_theme`" in user_msg
            assert "Start by calling `get_template_theme`" in user_msg
