"""
opencode/tools.py — Agent Tool Definitions & Executor
======================================================
Defines the tool suite for the OpenCode agent loop. Each tool is a plain
Python function that operates on a ShadowWorkspace. No LangChain dependency.

The TOOL_DEFINITIONS list provides JSON schemas for the LLM system prompt.
The execute_tool() dispatcher routes tool calls to the correct function.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.tools")


# ============================================================================
# Tool Schema Definitions (injected into the LLM system prompt)
# ============================================================================

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "read_file_range",
        "description": (
            "Read exact line-numbered content from the LaTeX file. "
            "Returns lines in the format '<line_no>: <content>'. "
            "Use this to inspect the target section or surrounding context (up to 200-300 lines in one call). "
            "Always read the target area first to get the exact text for str_replace."
        ),
        "parameters": {
            "file": {
                "type": "string",
                "description": "File to read (default: 'main.tex'). Usually 'main.tex'.",
                "default": "main.tex",
            },
            "start_line": {
                "type": "integer",
                "description": "1-indexed start line (inclusive).",
            },
            "end_line": {
                "type": "integer",
                "description": "1-indexed end line (inclusive). Can read up to 200-300 lines in one call.",
            },
        },
        "required": ["start_line", "end_line"],
    },
    {
        "name": "grep_search",
        "description": (
            "Search the LaTeX file for a pattern. Returns matching lines with "
            "line numbers. Use this to find \\\\labels, \\\\includegraphics references, "
            "section headings, or any specific text. Supports literal strings and regex."
        ),
        "parameters": {
            "query": {
                "type": "string",
                "description": "Search pattern (literal text or regex).",
            },
            "is_regex": {
                "type": "boolean",
                "description": "If true, treat query as a regex pattern. Default: false.",
                "default": False,
            },
        },
        "required": ["query"],
    },
    {
        "name": "str_replace",
        "description": (
            "Replace an exact string in the shadow buffer. The old_str MUST match "
            "the file content character-for-character (including whitespace and newlines). "
            "If the match fails, you will receive an error — read the file again to get "
            "the exact text. Only one occurrence must exist; include surrounding context "
            "to disambiguate if needed."
        ),
        "parameters": {
            "old_str": {
                "type": "string",
                "description": "The exact string to find and replace. Must match verbatim.",
            },
            "new_str": {
                "type": "string",
                "description": "The replacement string.",
            },
        },
        "required": ["old_str", "new_str"],
    },
    {
        "name": "rewrite_chunk",
        "description": (
            "Replace an entire document chunk (chapter, section, or frame) by its chunk_id. "
            "Uses structural byte/character offsets rather than requiring exact string matching. "
            "This is the PREFERRED tool in FULL_DOCUMENT_REWRITE mode to guarantee full section replacement."
        ),
        "parameters": {
            "chunk_id": {
                "type": "string",
                "description": "The ID of the chunk to replace (e.g. 'chapter_1', 'chapter_2', 'section_1', 'frame_1').",
            },
            "new_content": {
                "type": "string",
                "description": "The complete replacement LaTeX content for this entire chunk.",
            },
        },
        "required": ["chunk_id", "new_content"],
    },
    {
        "name": "list_assets",
        "description": (
            "List all files in the project's assets/ directory. Use this to discover "
            "available images, PDFs, and other files for \\\\includegraphics{} references."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "verify_compile",
        "description": (
            "Compile the current shadow buffer with the LaTeX engine to check for errors. "
            "Returns {success: true/false, errors: [...], stderr: '...'}. "
            "Call this after applying your edits to verify the document compiles cleanly before signaling done=true. "
            "If compilation fails, read the error, fix it with str_replace, and verify again."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_template_theme",
        "description": (
            "Retrieve LaTeX templates, Beamer presentation themes, IEEE paper layouts, thesis chapters, "
            "resumes/CVs, letters, and lab assignments from the template library. "
            "Use extract_section='preamble' to get theme colors and styling to redesign existing documents without erasing content. "
            "Use extract_section='all' to get the full source for new document creation."
        ),
        "parameters": {
            "category": {
                "type": "string",
                "description": "Category: 'ppt' (Beamer), 'papers' (IEEE/articles), 'thesis' (reports/thesis), 'resume' (CV), 'letters' (formal letters), 'assignments' (lab reports).",
            },
            "theme_name": {
                "type": "string",
                "description": "Theme name or keyword (e.g. 'nordlight', 'prism', 'regalia', 'minimalist', 'basic', 'ieee-conference', 'thesis', 'medium-length-professional-cv', 'letter1', 'navy-gold'). Omit or set to 'list' to see available themes.",
                "default": "list",
            },
            "extract_section": {
                "type": "string",
                "description": "'preamble' (styling/colors/packages for redesigns), 'structure' (skeleton), or 'all' (complete template source). Default: 'all'.",
                "default": "all",
            },
        },
        "required": ["category"],
    },
]


def get_tools_prompt_block() -> str:
    """
    Generates the tool documentation block for the LLM system prompt.
    Formatted as a clear reference for the model to use in tool calls.
    """
    lines = ["AVAILABLE TOOLS:"]
    for i, tool in enumerate(TOOL_DEFINITIONS, 1):
        params_desc = []
        params = tool.get("parameters", {})
        required = tool.get("required", [])
        for pname, pspec in params.items():
            req_marker = " (REQUIRED)" if pname in required else " (optional)"
            params_desc.append(f"    - {pname}: {pspec.get('type', 'string')}{req_marker} — {pspec.get('description', '')}")

        params_block = "\n".join(params_desc) if params_desc else "    (no parameters)"
        lines.append(f"\n{i}. `{tool['name']}`")
        lines.append(f"   {tool['description']}")
        lines.append(f"   Parameters:\n{params_block}")

    return "\n".join(lines)


# ============================================================================
# Tool Executor
# ============================================================================

def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    workspace: "ShadowWorkspace",
) -> Dict[str, Any]:
    """
    Dispatches a tool call to the appropriate workspace method.

    Args:
        tool_name: Name of the tool to execute.
        args: Tool arguments as a dict.
        workspace: The active ShadowWorkspace instance.

    Returns:
        Dict with the tool result (always JSON-serializable).
    """
    try:
        if tool_name == "read_file_range":
            start = int(args.get("start_line", 1))
            end = int(args.get("end_line", start + 50))
            # Clamp range to prevent excessive context
            if end - start > 300:
                end = start + 300
            content = workspace.read_lines(start, end)
            return {
                "content": content,
                "lines_read": f"{start}-{end}",
                "total_lines": workspace.get_line_count(),
            }

        elif tool_name == "grep_search":
            query = args.get("query", "")
            is_regex = bool(args.get("is_regex", False))
            results = workspace.grep(query, is_regex=is_regex)
            return {
                "matches": results,
                "match_count": len([r for r in results if "line_no" in r]),
                "query": query,
            }

        elif tool_name == "str_replace":
            old_str = args.get("old_str", "")
            new_str = args.get("new_str", "")
            result = workspace.str_replace(old_str, new_str)
            return result

        elif tool_name == "rewrite_chunk":
            chunk_id = str(args.get("chunk_id", "")).strip()
            new_content = args.get("new_content", "")
            result = workspace.rewrite_chunk(chunk_id, new_content)
            return result

        elif tool_name == "list_assets":
            assets = workspace.list_assets()
            return {
                "assets": assets,
                "count": len(assets),
            }

        elif tool_name == "verify_compile":
            # Delegate to shadow_compiler module
            from .shadow_compiler import compile_shadow_buffer
            result = compile_shadow_buffer(workspace)
            return result

        elif tool_name == "get_template_theme":
            from .template_registry import get_template_theme as fetch_theme
            cat = args.get("category", "ppt")
            theme = args.get("theme_name")
            extract_sec = args.get("extract_section", "all")
            return fetch_theme(category=cat, theme_name=theme, extract_section=extract_sec)

        else:
            return {
                "error": f"Unknown tool: '{tool_name}'. Available tools: {[t['name'] for t in TOOL_DEFINITIONS]}",
            }

    except Exception as e:
        logger.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
        return {
            "error": f"Tool '{tool_name}' failed: {str(e)}",
        }
