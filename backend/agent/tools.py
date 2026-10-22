"""
agent/tools.py — Agent Tool Definitions & Executor
======================================================
Defines the tool suite for the OverBranch agent loop. Each tool is a plain
Python function that operates on a ShadowWorkspace. No LangChain dependency.

The TOOL_DEFINITIONS list provides JSON schemas for the LLM system prompt.
The execute_tool() dispatcher routes tool calls to the correct function.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("agent.tools")


# ============================================================================
# Tool Schema Definitions (injected into the LLM system prompt)
# ============================================================================

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "inspect_document",
        "description": (
            "Compact structural outline of the document: every chapter/section/frame/environment with its "
            "stable node_id, title and line range, plus metadata and a token estimate. node_ids stay valid "
            "while other parts of the document are edited — prefer them over line numbers and copied text."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_block",
        "description": (
            "Read one structural block by node_id (e.g. 'sec:introduction', 'frame:results', 'meta:title', "
            "'label:fig:arch', 'slide 3'). Optionally include its parent header and the preamble lines that "
            "style it (\\setbeamerfont/\\setbeamercolor/\\definecolor/macros it uses)."
        ),
        "parameters": {
            "node_id": {"type": "string", "description": "Stable node ID, label:<label>, or 'slide N' / 'section N'."},
            "include_parent": {"type": "boolean", "description": "Also return the parent node's header.", "default": False},
            "include_style": {"type": "boolean", "description": "Also return the relevant preamble style lines.", "default": False},
        },
        "required": ["node_id"],
    },
    {
        "name": "read_file_range",
        "description": (
            "Read exact line-numbered content ('<line_no>: <content>'), up to 300 lines per call. "
            "Content you already received and that has not changed since is not re-sent."
        ),
        "parameters": {
            "file": {"type": "string", "description": "File to read (default: main document).", "default": "main.tex"},
            "start_line": {"type": "integer", "description": "1-indexed start line (inclusive)."},
            "end_line": {"type": "integer", "description": "1-indexed end line (inclusive)."},
        },
        "required": ["start_line", "end_line"],
    },
    {
        "name": "search_document",
        "description": "Search a file for a literal string or regex. Returns matching lines with line numbers.",
        "parameters": {
            "query": {"type": "string", "description": "Search pattern (literal text or regex)."},
            "file": {"type": "string", "description": "Optional file to search (default: main document)."},
            "is_regex": {"type": "boolean", "description": "Treat query as a regex. Default: false.", "default": False},
        },
        "required": ["query"],
    },
    {
        "name": "replace_text",
        "description": (
            "Replace a piece of text with new text — the smallest edit; prefer it for changes inside a block. "
            "old_str should be copied from the document, but small drift (indentation, spacing, quotes) is "
            "tolerated: the target is located exactly, then normalised, then by close similarity. Pass node_id "
            "(and/or line_hint) to scope the search when the text may occur more than once. If the target "
            "cannot be found confidently, nothing is changed and the current region is returned."
        ),
        "parameters": {
            "old_str": {"type": "string", "description": "The text to replace, copied from the document."},
            "new_str": {"type": "string", "description": "The replacement text."},
            "node_id": {"type": "string", "description": "Optional: node the text lives in."},
            "line_hint": {"type": "integer", "description": "Optional: approximate line number of the text."},
            "file": {"type": "string", "description": "Optional file to modify (default: main document)."},
        },
        "required": ["old_str", "new_str"],
    },
    {
        "name": "replace_block",
        "description": (
            "Replace a whole structural block (section with its body, a frame, an environment, \\title{...}) "
            "by node_id. Use when most of the block changes; include the block's own heading or "
            "\\begin/\\end lines in new_content."
        ),
        "parameters": {
            "node_id": {"type": "string", "description": "Stable node ID of the block."},
            "new_content": {"type": "string", "description": "The complete replacement block."},
        },
        "required": ["node_id", "new_content"],
    },
    {
        "name": "insert_block",
        "description": (
            "Insert new LaTeX relative to a block: position 'after' / 'before' the block, or 'start' / 'end' "
            "of its body (inside \\begin..\\end, after a heading line). Use for new slides, sections, items, "
            "figures."
        ),
        "parameters": {
            "node_id": {"type": "string", "description": "Stable node ID of the reference block."},
            "content": {"type": "string", "description": "The LaTeX to insert (balanced environments)."},
            "position": {"type": "string", "description": "'after' (default), 'before', 'start' or 'end'.", "default": "after"},
        },
        "required": ["node_id", "content"],
    },
    {
        "name": "delete_block",
        "description": "Delete a whole structural block by node_id.",
        "parameters": {"node_id": {"type": "string", "description": "Stable node ID of the block to delete."}},
        "required": ["node_id"],
    },
    {
        "name": "rewrite_chunk",
        "description": (
            "FULL-REWRITE MODE: replace an entire chunk (chapter, section, or frame) by its chunk_id from the "
            "chunk list (e.g. 'section_2', 'frame_3'). Stable node IDs are accepted too."
        ),
        "parameters": {
            "chunk_id": {"type": "string", "description": "Chunk ID (e.g. 'chapter_1', 'section_1', 'frame_1') or node ID."},
            "new_content": {"type": "string", "description": "The complete replacement LaTeX content for this chunk."},
        },
        "required": ["chunk_id", "new_content"],
    },
    {
        "name": "insert_into_chunk",
        "description": (
            "Insert content into a chunk: position 'end' (default; before \\end{thebibliography} / the closing "
            "list or frame tag) or 'begin'. Use for \\bibitem entries and list items."
        ),
        "parameters": {
            "chunk_id": {"type": "string", "description": "Chunk ID or node ID (e.g. 'section_3', 'bibliography')."},
            "content": {"type": "string", "description": "The LaTeX content or \\bibitem entry to insert."},
            "position": {"type": "string", "description": "'end' (default) or 'begin'.", "default": "end"},
        },
        "required": ["chunk_id", "content"],
    },
    {
        "name": "compile_latex",
        "description": (
            "Compile the current buffer. Returns {success, errors, new_errors, overfull_boxes}. Errors the "
            "original document already had are reported separately — fix only new_errors."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "request_more_steps",
        "description": (
            "Ask for more reasoning steps when you can see the task needs them. Call this as soon as you "
            "realise the remaining steps will not cover the work — NOT on the last step. You are told your "
            "step number and budget on every turn. Granted only if the document has actually changed since "
            "your last request, so make progress between requests; if it is refused, finish what you have "
            "with done=true rather than continuing. Running out of steps mid-edit discards the entire run."
        ),
        "parameters": {
            "additional_steps": {"type": "integer", "description": "How many more steps you need (max 6 per request)."},
            "reason": {"type": "string", "description": "What is left to do that needs them."},
        },
        "required": ["reason"],
    },
    {
        "name": "validate_edit",
        "description": "Check the buffer's LaTeX structure (environments, braces, math) against the original, without compiling.",
        "parameters": {},
        "required": [],
    },
    {
        "name": "rollback_edit",
        "description": "Undo the most recent successful edit.",
        "parameters": {},
        "required": [],
    },
    {
        "name": "detect_overflow",
        "description": (
            "Compile and report text that runs past its container or the page: overfull boxes mapped to source "
            "lines, plus glyphs beyond the text area or page edge."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "inspect_pdf_geometry",
        "description": "Compile and return the text lines of one rendered page with position, width, font size and weight.",
        "parameters": {"page": {"type": "integer", "description": "1-based page number.", "default": 1}},
        "required": [],
    },
    {
        "name": "justify_content",
        "description": (
            "Repair the document's LAYOUT by inspecting the rendered PDF. Use this for any request about "
            "justification, formatting, alignment, overflow, text running past the margin, awkwardly broken "
            "file paths or identifiers, or tables that are too wide or run off the page — including "
            "'fix the justification/formatting of the whole document'. It compiles the document, measures "
            "every page, maps each defect back to the source, applies the smallest fix (break opportunities "
            "inside a long path or identifier, a flexible table column, looser spacing for one paragraph), "
            "recompiles and keeps the fix only if the page measurably improved. Text is never changed and "
            "type is never shrunk. Do NOT hand-insert \\\\ line breaks, \\small or margin changes for this."
        ),
        "parameters": {
            "scope": {"type": "string",
                      "description": "'document' (default — check and repair every page), 'page', "
                                     "'node' or 'text' (fit one block/phrase to a width)."},
            "page": {"type": "integer", "description": "1-based page, with scope='page'."},
            "max_fixes": {"type": "integer", "description": "Most repairs to apply (default 12)."},
            "dry_run": {"type": "boolean", "description": "Report the defects without changing anything."},
            "node_id": {"type": "string", "description": "Block to fit, with scope='node'."},
            "text": {"type": "string", "description": "Line/phrase to fit, with scope='text'."},
            "width_pt": {"type": "number", "description": "Target width in pt for scope='node'/'text'."},
            "alignment": {"type": "string", "description": "'left', 'right', 'center' or 'justify'."},
        },
        "required": [],
    },
    {
        "name": "generate_diagram",
        "description": (
            "Build a clean, compiling diagram, block diagram, figure or flowchart — do NOT hand-write TikZ for "
            "diagrams. Use it whenever a slide or section needs a process, pipeline, workflow, architecture, or "
            "relationship picture. TWO WAYS: (1) give a natural-language `description` and the diagram is DRAWN BY "
            "THE LLM, then compiled, repaired if needed, and verified before it is placed — best for rich or custom "
            "figures; (2) give a `nodes`/`edges` spec and it is laid out deterministically — best for standard "
            "flow/block charts. Give node_id to insert it into that block (e.g. a frame); omit it (or dry_run=true) "
            "to get the LaTeX back. It loads the right TikZ libraries and guarantees the result fits the slide."
        ),
        "parameters": {
            "description": {"type": "string",
                            "description": "Natural-language description of the diagram/figure to draw. When given, "
                                           "the LLM draws it (verified to compile). Best for rich or custom figures."},
            "nodes": {"type": "array",
                      "description": "Deterministic mode: list of {id, label, shape?}. shape: 'process' (default, box), "
                                     "'decision' (diamond), 'io' (parallelogram), 'terminal' (rounded) or 'data'."},
            "edges": {"type": "array",
                      "description": "Deterministic mode: list of {from, to, label?, style?}. from/to are node ids; "
                                     "style 'solid' (default) or 'dashed'. A feedback edge (a cycle) is fine."},
            "kind": {"type": "string", "description": "'flowchart' (default), 'block' or any figure kind (LLM mode)."},
            "direction": {"type": "string", "description": "'vertical' (default) or 'horizontal'."},
            "title": {"type": "string", "description": "Optional caption shown above the diagram."},
            "node_id": {"type": "string", "description": "Block to insert the diagram into, e.g. 'frame:architecture'."},
            "position": {"type": "string", "description": "Where, relative to node_id: 'end' (default), 'start', 'before', 'after'."},
            "dry_run": {"type": "boolean", "description": "Return the LaTeX without inserting it."},
        },
        "required": [],
    },
    {
        "name": "view_rendered_pages",
        "description": (
            "LOOK at the compiled document. Use this for any request about how something looks — alignment, "
            "spacing, overlapping text or images, text that is hard to see, content cut off or off the page — "
            "before editing, and again after editing to confirm the fix. It compiles the buffer, renders the "
            "page(s) and returns the page image together with MEASURED defects (overlap, off-page content, "
            "low contrast, overflow), each mapped to the source lines that produced it. Give a target: "
            "node_id (a frame/section/figure block), text (a phrase printed on the page) or pages."
        ),
        "parameters": {
            "node_id": {"type": "string", "description": "Block to look at, e.g. 'frame:results' or 'slide 3'."},
            "text": {"type": "string", "description": "A phrase printed on the page(s) to look at."},
            "pages": {"type": "string", "description": "1-based page(s): 3, '2-4' or '1,3' (at most 3 per call)."},
            "scan": {"type": "string", "description": "'document' measures every page and shows the two with the heaviest defects."},
        },
        "required": [],
    },
    {
        "name": "humanize_document",
        "description": (
            "Reword the document's bulk prose so it reads as a careful human author wrote it instead of "
            "reading as generated text \u2014 and nothing else. Titles, headings, author names, captions, "
            "labels, citations, references, math, tables, TikZ, listings, the preamble and the bibliography "
            "are never touched, and every command, number, acronym and name of a passage must come out "
            "identical or that passage keeps its original text. It covers EVERY prose passage of the "
            "document in one call. Each rewrite is measured: the AI-register score must fall, the length "
            "must stay within ~20%, and the result is verified and compiled after it is written. Use it for "
            "'humanize this', 'make it sound less like AI', 'remove the AI tone', 'remove the AI slop'. Do "
            "NOT hand-rewrite prose for this yourself."
        ),
        "parameters": {
            "scope": {"type": "string", "description": "'document' (every prose passage in the body) or 'node'.", "default": "document"},
            "node_id": {"type": "string", "description": "Restrict to one block (e.g. 'sec:introduction', 'frame:results')."},
            "dry_run": {"type": "boolean", "description": "Measure and report what would change; write nothing.", "default": False},
            "report_only": {"type": "boolean", "description": "Measure the document's current AI-register score without calling the model.", "default": False},
        },
        "required": [],
    },
    {
        "name": "elaborate_content",
        "description": (
            "ADD new material to a block (or to every block of the document) without replacing a word of "
            "what is there. Use it for 'elaborate this', 'expand this section', 'add more detail', 'explain "
            "this in more depth', 'make the document longer'. It writes at least the required amount of new "
            "substantive prose, inserts it after the existing text (and, on a slide, as follow-up frames so "
            "no frame overflows), then verifies that the original text survived byte for byte, that enough "
            "was really added, that it is not a restatement of what was there, that no citation or reference "
            "was invented, and that the document still compiles \u2014 rolling the insert back if not. "
            "Omit `content` to have the material written for you; pass `content` to insert your own."
        ),
        "parameters": {
            "target": {"type": "string", "description": "'section' (one block, with node_id), 'selection' (what the user highlighted), or 'document' (every block).", "default": "section"},
            "node_id": {"type": "string", "description": "The block to elaborate, e.g. 'sec:introduction' or 'frame:results'."},
            "content": {"type": "string", "description": "LaTeX to add. Omit to have it generated and verified for you."},
            "instruction": {"type": "string", "description": "What the elaboration should cover, if the request named something specific."},
            "dry_run": {"type": "boolean", "description": "Report what would be added; write nothing.", "default": False},
        },
        "required": [],
    },
    {
        "name": "list_attachment_figures",
        "description": (
            "List the figures (diagrams, charts, photographs) found in the files attached to this chat, with "
            "their figure_id, page, caption and size. Use it to choose which figures of an attached paper "
            "belong in the document (e.g. the system architecture for the architecture slide)."
        ),
        "parameters": {
            "filename": {"type": "string", "description": "Only this attached file (default: all of them)."},
        },
        "required": [],
    },
    {
        "name": "import_attachment_figure",
        "description": (
            "Copy one figure from an attached file into the project's assets/ folder so the document can show "
            "it. Returns the saved path and ready-to-use LaTeX (\\includegraphics with a caption). Then place "
            "that LaTeX in the slide or section that discusses the figure. Only reference image paths that this "
            "tool or list_project_files returned — never invent a filename."
        ),
        "parameters": {
            "figure_id": {"type": "string", "description": "ID from the figure list, e.g. '3f2a9c1b-p3-f1'."},
            "asset_name": {"type": "string", "description": "Optional file name without extension, e.g. 'system-architecture'."},
        },
        "required": ["figure_id"],
    },
    {
        "name": "search_uploaded_references",
        "description": (
            "Search previously uploaded reference files/PDFs attached to this session. "
            "Use this to look up specific benchmark numbers, equations, citations, or domain details from attached papers."
        ),
        "parameters": {
            "query": {
                "type": "string",
                "description": "Keywords or topic to search for in attached references.",
            },
        },
        "required": ["query"],
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
    {
        "name": "list_project_files",
        "description": (
            "List all files in the project workspace with metadata (line count, char count, modified status). "
            "Use this to discover multi-file project structure before editing auxiliary .tex files."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "list_attached_documents",
        "description": (
            "List all reference documents (PDFs, research papers, data files) attached by the user to this chat. "
            "Returns filenames, page counts, total character sizes, and text previews. "
            "Use this to discover what external source material is available to incorporate into the LaTeX document."
        ),
        "parameters": {},
        "required": [],
    },
    {
        "name": "read_attached_document",
        "description": (
            "Read pages or lines from an attached reference document (PDF or text file). "
            "Can read by page range (start_page, end_page) or line range (start_line, end_line). "
            "Use this to inspect specific sections, algorithms, theorems, data tables, or equations from the uploaded PDF."
        ),
        "parameters": {
            "filename": {
                "type": "string",
                "description": "Name of the attached document to read (optional, defaults to active attached document).",
            },
            "start_page": {
                "type": "integer",
                "description": "1-indexed starting page number to read (optional).",
            },
            "end_page": {
                "type": "integer",
                "description": "1-indexed ending page number to read (optional, max 5 pages per call).",
            },
            "start_line": {
                "type": "integer",
                "description": "1-indexed line number to start reading from (optional).",
            },
            "end_line": {
                "type": "integer",
                "description": "1-indexed line number to stop reading at (optional).",
            },
        },
        "required": [],
    },
    {
        "name": "convert_attached_pdf",
        "description": (
            "Convert a PDF the user attached to this chat into LaTeX for the current project (PDF import). "
            "Use ONLY when the user asks to convert / import / recreate / reproduce an attached PDF as LaTeX. "
            "The PDF is rebuilt as an ordinary, editable LaTeX document (headings, paragraphs, lists, tables and "
            "images in reading order) that keeps the source's fonts, colours, sizes and assets, then compiled and "
            "checked for text coverage and style fidelity. Starts a background job and returns its job_id; the user "
            "sees progress and a quality report and confirms before main.tex is replaced. Do not edit the document "
            "yourself after starting a conversion — finish with done=true."
        ),
        "parameters": {
            "filename": {
                "type": "string",
                "description": "Name of the attached PDF (optional, defaults to the most recent attached PDF).",
            },
        },
        "required": [],
    },
]


# Earlier tool names, still accepted from the model (and from older prompts).
TOOL_ALIASES: Dict[str, str] = {
    "str_replace": "replace_text",
    "grep_search": "search_document",
    "verify_compile": "compile_latex",
    "read_document_summary": "inspect_document",
    # The wording tool and the additive tool, under the names a model reaches
    # for. Both are canonical elsewhere in the codebase under the names below.
    "humanize_content": "humanize_document",
    "humanize_text": "humanize_document",
    "humanise_document": "humanize_document",
    "humanise_content": "humanize_document",
    "expand_content": "elaborate_content",
    "elaborate_section": "elaborate_content",
    "elaborate": "elaborate_content",
}

# Tools that change the document (used for transactions and tracing).
EDIT_TOOLS = frozenset({
    "replace_text", "replace_block", "insert_block", "delete_block", "rewrite_chunk",
    "insert_into_chunk", "justify_content", "generate_diagram",
    "humanize_document", "elaborate_content",
})


# Tools that stay EXECUTABLE (older prompts, worklists and the model's habits still
# call them) but are no longer described in the prompt: each duplicates a tool that
# is. They are deliberately NOT entries in TOOL_ALIASES — every one of them takes
# different arguments, or does something different, from its modern counterpart,
# so a rename would change behaviour (see the notes):
#   read_file_range            line ranges (start_line/end_line/file) vs get_block's node_id
#   rewrite_chunk              chunk_id namespace + touched-chunk coverage tracking;
#                              replace_block takes a node id only
#   insert_into_chunk          chunk_id, position 'end'/'begin' (bibliography/list/frame
#                              aware) vs insert_block's node id + before/after/start/end
#   detect_overflow,
#   inspect_pdf_geometry       measurements, not page images (view_rendered_pages)
#   list_assets                assets/ images only; list_project_files lists every file
#   list_attached_documents    chat attachments, not project files
#   search_uploaded_references searches attachments, not the document (search_document)
#   validate_edit              the loop validates after every write and before commit
#   rollback_edit              the run is one transaction; undo is the loop's job
HIDDEN_FROM_PROMPT = frozenset({
    "read_file_range", "rewrite_chunk", "insert_into_chunk", "detect_overflow",
    "inspect_pdf_geometry", "list_assets", "list_attached_documents",
    "search_uploaded_references", "validate_edit", "rollback_edit",
})

# What ask mode (answer a question, never edit) is shown: reading and searching only.
ASK_MODE_TOOLS = frozenset({
    "inspect_document", "get_block", "search_document", "view_rendered_pages",
    "list_attachment_figures", "get_template_theme", "list_project_files",
    "read_attached_document", "request_more_steps",
})


def canonical_tool_name(name: str) -> str:
    return TOOL_ALIASES.get(name, name)


def prompt_tool_definitions(mode: str = "edit") -> List[Dict[str, Any]]:
    """The tool definitions shown to the model in ``mode`` ('edit' or 'ask')."""
    tools = [t for t in TOOL_DEFINITIONS if t["name"] not in HIDDEN_FROM_PROMPT]
    if mode == "ask":
        tools = [t for t in tools if t["name"] in ASK_MODE_TOOLS]
    return tools


def get_tools_prompt_block(mode: str = "edit") -> str:
    """
    Generates the tool documentation block for the LLM system prompt.
    Formatted as a clear reference for the model to use in tool calls.
    Only the tools for ``mode`` are listed (see prompt_tool_definitions); hidden
    tools remain executable through ``execute_tool``.
    """
    lines = ["AVAILABLE TOOLS:"]
    for i, tool in enumerate(prompt_tool_definitions(mode), 1):
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
        main_file = getattr(workspace, "file_path", getattr(workspace, "_file_path", "main.tex"))

        tool_name = TOOL_ALIASES.get(tool_name, tool_name)

        if tool_name == "read_file_range":
            target_file = args.get("file")
            start = int(args.get("start_line", 1))
            end = int(args.get("end_line", start + 50))
            # Clamp range to prevent excessive context
            if end - start > 300:
                end = start + 300
            if target_file and target_file not in ("main.tex", main_file):
                content = workspace.read_file_lines(target_file, start, end)
                file_lines = len(workspace._aux_files.get(target_file, "").splitlines()) if hasattr(workspace, "_aux_files") and target_file in workspace._aux_files else 0
                return {
                    "file": target_file,
                    "content": content,
                    "lines_read": f"{start}-{end}",
                    "total_lines": file_lines,
                }
            content = workspace.read_lines(start, end)
            ledger = getattr(workspace, "context_ledger", None)
            if ledger is not None:
                content = ledger.filter(content)
            return {
                "file": main_file,
                "content": content,
                "lines_read": f"{start}-{end}",
                "total_lines": workspace.get_line_count(),
            }

        elif tool_name == "search_document":
            query = args.get("query", "")
            is_regex = bool(args.get("is_regex", False))
            target_file = args.get("file")
            def run(q: str, rx: bool):
                if target_file and target_file not in ("main.tex", main_file):
                    return workspace.grep_file(target_file, q, is_regex=rx)
                return workspace.grep(q, is_regex=rx)

            results = run(query, is_regex)
            ignore_case = False
            if not any("line_no" in r for r in results) and query:
                # Users name things in lower case ("change jacob ..."), documents do not
                # ("JACOB PRASANTH"): retry ignoring case rather than report nothing.
                results = run("(?i)" + (query if is_regex else re.escape(query)), True)
                ignore_case = any("line_no" in r for r in results)
            out = {
                "matches": results,
                "match_count": len([r for r in results if "line_no" in r]),
                "query": query,
            }
            if ignore_case:
                out["note"] = "No exact-case match; these lines match ignoring case."
            return out

        elif tool_name == "replace_text":
            from latex_error_fixer import sanitize_edit_latex
            old_str = args.get("old_str", args.get("old_text", ""))
            new_str = sanitize_edit_latex(args.get("new_str", args.get("new_text", "")))
            target_file = args.get("file")
            if target_file and target_file not in ("main.tex", main_file):
                return workspace.str_replace_file(target_file, old_str, new_str)
            line_hint = args.get("line_hint")
            try:
                line_hint = int(line_hint) if line_hint not in (None, "") else None
            except (TypeError, ValueError):
                line_hint = None
            return workspace.str_replace(old_str, new_str, line_hint=line_hint, node_id=args.get("node_id") or None)

        elif tool_name == "inspect_document":
            from .context_builder import build_outline
            from document_analyzer import analyze_document
            analysis = analyze_document(workspace.get_buffer())
            return {
                "outline": build_outline(workspace),
                "total_lines": analysis.total_lines,
                "estimated_tokens": analysis.estimated_tokens,
                "structure_type": analysis.primary_structure_type,
            }

        elif tool_name == "get_block":
            return workspace.get_block(
                str(args.get("node_id", "")).strip(),
                include_parent=bool(args.get("include_parent", False)),
                include_style=bool(args.get("include_style", False)),
            )

        elif tool_name == "replace_block":
            from latex_error_fixer import sanitize_edit_latex
            new_content = sanitize_edit_latex(args.get("new_content", ""))
            return workspace.replace_block(str(args.get("node_id", "")).strip(), new_content)

        elif tool_name == "insert_block":
            from latex_error_fixer import sanitize_edit_latex
            content = sanitize_edit_latex(args.get("content", ""))
            return workspace.insert_block(str(args.get("node_id", "")).strip(), content,
                                          str(args.get("position", "after")).strip().lower())

        elif tool_name == "delete_block":
            return workspace.delete_block(str(args.get("node_id", "")).strip())

        elif tool_name == "rewrite_chunk":
            from latex_error_fixer import sanitize_edit_latex
            chunk_id = str(args.get("chunk_id", "")).strip()
            new_content = sanitize_edit_latex(args.get("new_content", ""))
            result = workspace.rewrite_chunk(chunk_id, new_content)
            return result

        elif tool_name == "insert_into_chunk":
            from latex_error_fixer import sanitize_edit_latex
            chunk_id = str(args.get("chunk_id", "")).strip()
            content = sanitize_edit_latex(args.get("content", ""))
            position = args.get("position", "end")
            result = workspace.insert_into_chunk(chunk_id=chunk_id, content=content, position=position)
            return result

        elif tool_name == "compile_latex":
            from .shadow_compiler import compile_shadow_buffer
            return compile_shadow_buffer(workspace)

        elif tool_name == "validate_edit":
            from edit_validator import validate_edit
            ok, errors = validate_edit(workspace.get_original(), workspace.get_buffer())
            return {"success": ok, "valid": ok, "new_errors": errors[:10]}

        elif tool_name == "rollback_edit":
            return workspace.rollback_last()

        elif tool_name == "detect_overflow":
            from .layout_tools import detect_overflow_tool
            return detect_overflow_tool(workspace)

        elif tool_name == "inspect_pdf_geometry":
            from .layout_tools import inspect_pdf_geometry_tool
            return inspect_pdf_geometry_tool(workspace, int(args.get("page", 1) or 1))

        elif tool_name == "justify_content":
            from .layout_tools import justify_content_tool
            return justify_content_tool(workspace, args)

        elif tool_name == "generate_diagram":
            from .diagram_tools import generate_diagram_tool
            return generate_diagram_tool(workspace, args)

        elif tool_name == "view_rendered_pages":
            from .visual_tools import view_rendered_pages_tool
            return view_rendered_pages_tool(workspace, args)

        elif tool_name == "humanize_document":
            from .humanize import humanize_document_tool
            return humanize_document_tool(workspace, args)

        elif tool_name == "elaborate_content":
            from .elaborate import elaborate_content_tool
            return elaborate_content_tool(workspace, args)

        elif tool_name == "list_attachment_figures":
            from .attachment_tools import list_attachment_figures_tool
            return list_attachment_figures_tool(workspace, args)

        elif tool_name == "import_attachment_figure":
            from .attachment_tools import import_attachment_figure_tool
            return import_attachment_figure_tool(workspace, args)

        elif tool_name == "search_uploaded_references":
            from attached_context import attached_context_store
            query = args.get("query", "")
            results = attached_context_store.search_attachments(session_id=workspace.session_id, query=query)
            return {
                "query": query,
                "matches": results,
                "count": len(results),
            }

        elif tool_name == "list_assets":
            assets = workspace.list_assets()
            return {
                "assets": assets,
                "count": len(assets),
            }

        elif tool_name == "get_template_theme":
            from .template_registry import get_template_theme as fetch_theme
            cat = args.get("category", "ppt")
            theme = args.get("theme_name")
            extract_sec = args.get("extract_section", "all")
            return fetch_theme(category=cat, theme_name=theme, extract_section=extract_sec)

        elif tool_name == "list_project_files":
            files = workspace.get_file_list()
            return {
                "files": files,
                "count": len(files),
            }

        elif tool_name == "list_attached_documents":
            from attached_context import attached_context_store
            attachments = attached_context_store.get_attachments(session_id=workspace.session_id)
            doc_list = []
            for a in attachments:
                doc_list.append({
                    "filename": a.get("filename"),
                    "file_type": a.get("file_type"),
                    "page_count": a.get("page_count", 1),
                    "size_chars": a.get("size", len(a.get("content", ""))),
                    "is_pdf": a.get("is_pdf", False),
                    "kind": a.get("kind"),
                    "figures": len(a["figures"]) if isinstance(a.get("figures"), list) else None,
                    "preview": (a.get("content", "")[:300] + "...").replace("\n", " "),
                })
            # Also check workspace reference files
            ref_files = getattr(workspace, "get_reference_files", lambda: {})()
            for rname, rcontent in ref_files.items():
                if not any(d["filename"] == rname for d in doc_list):
                    doc_list.append({
                        "filename": rname,
                        "file_type": "reference",
                        "page_count": 1,
                        "size_chars": len(rcontent),
                        "is_pdf": rname.lower().endswith(".pdf"),
                        "preview": (rcontent[:300] + "...").replace("\n", " "),
                    })
            return {
                "attached_documents": doc_list,
                "documents": doc_list,
                "count": len(doc_list),
            }

        elif tool_name == "read_attached_document":
            from attached_context import attached_context_store
            filename = args.get("filename")
            start_page = args.get("start_page")
            end_page = args.get("end_page")
            start_line = args.get("start_line")
            end_line = args.get("end_line")

            # 1. Page-based reading
            if start_page is not None or end_page is not None:
                sp = int(start_page or 1)
                ep = int(end_page or (sp + 3))
                if ep - sp > 5:
                    ep = sp + 5
                text = attached_context_store.read_attachment_pages(
                    session_id=workspace.session_id,
                    filename=filename,
                    start_page=sp,
                    end_page=ep,
                )
                return {
                    "filename": filename or "attached_document",
                    "pages_read": f"{sp}-{ep}",
                    "content": text,
                }

            # 2. Line-based reading
            if start_line is not None or end_line is not None:
                sl = int(start_line or 1)
                el = int(end_line or (sl + 50))
                if el - sl > 200:
                    el = sl + 200
                text = attached_context_store.read_attachment_lines(
                    session_id=workspace.session_id,
                    filename=filename,
                    start_line=sl,
                    end_line=el,
                )
                return {
                    "filename": filename or "attached_document",
                    "lines_read": f"{sl}-{el}",
                    "content": text,
                }

            # 3. Default: read first 3 pages
            text = attached_context_store.read_attachment_pages(
                session_id=workspace.session_id,
                filename=filename,
                start_page=1,
                end_page=3,
            )
            return {
                "filename": filename or "attached_document",
                "pages_read": "1-3",
                "content": text,
            }

        elif tool_name == "convert_attached_pdf":
            return _convert_attached_pdf(args, workspace)

        else:
            return {
                "error": f"Unknown tool: '{tool_name}'. Available tools: {[t['name'] for t in prompt_tool_definitions()]}",
            }

    except Exception as e:
        logger.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
        return {
            "error": f"Tool '{tool_name}' failed: {str(e)}",
        }


def _convert_attached_pdf(args: Dict[str, Any], workspace: "ShadowWorkspace") -> Dict[str, Any]:
    """Starts a pdf2latex conversion job for an attached PDF (see TOOL_DEFINITIONS)."""
    from attached_context import attached_context_store
    from pdf2latex import jobs
    from pdf2latex.config import get_settings
    from pdf2latex.extract import PdfValidationError, open_pdf
    from pdf2latex.runner import start_job

    settings = get_settings()

    user_ctx = getattr(workspace, "user_context", None) or {}
    owner = user_ctx.get("user_id")
    project_id = getattr(workspace, "project_id", None) or getattr(workspace, "_project_id", None)
    if not owner or not project_id:
        return {"error": "PDF conversion needs a signed-in user and an open project."}

    pdfs = [a for a in attached_context_store.get_attachments(workspace.session_id) if a.get("is_pdf")]
    if not pdfs:
        return {"error": "No attached PDF found in this chat. Ask the user to attach the PDF file."}
    wanted = (args.get("filename") or "").lower()
    att = next((a for a in pdfs if wanted and a.get("filename", "").lower() == wanted), pdfs[-1])

    data = attached_context_store.read_bytes(att)
    if not data:
        return {"error": "The attached PDF is no longer available. Ask the user to attach it again."}
    try:
        doc = open_pdf(data)
        page_count = doc.page_count
        doc.close()
    except PdfValidationError as e:
        return {"error": str(e)}
    if page_count > settings.max_pages:
        return {"error": f"The PDF has {page_count} pages; the conversion limit is {settings.max_pages}."}
    existing = jobs.active_job_for(owner)
    if existing:
        return {"error": "A PDF conversion is already running for this user.", "job_id": existing["job_id"]}
    if user_ctx.get("is_guest"):
        from services.guest_quota import check_guest_conversion_quota, consume_guest_conversion
        from project_storage import get_supabase_client
        sid = owner.replace("guest_", "", 1)
        res = get_supabase_client().table("guest_sessions").select("*").eq("id", sid).limit(1).execute()
        if not res.data:
            return {"error": "Guest session not found."}
        allowed, _used, _resets, reason = check_guest_conversion_quota(res.data[0], "")
        if not allowed:
            return {"error": reason or "Guest conversion limit reached."}
        consume_guest_conversion(sid)

    state = start_job(owner, bool(user_ctx.get("is_guest")), project_id,
                      att.get("filename") or "document.pdf", data, page_count, overwrite=False,
                      mode="editable")
    return {
        "success": True,
        "job_id": state["job_id"],
        "filename": att.get("filename"),
        "page_count": page_count,
        "mode": "editable",
        "message": (
            "Conversion started (editable mode). The user sees live progress and a quality report "
            "(text coverage and style fidelity), and is asked before an existing main.tex is replaced. "
            "Results are best-effort editable LaTeX, not a guaranteed identical copy."
        ),
    }
