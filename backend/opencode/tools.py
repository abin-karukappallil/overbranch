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
            "Search a LaTeX file for a pattern. Returns matching lines with "
            "line numbers. Use this to find \\\\labels, \\\\includegraphics references, "
            "section headings, or any specific text. Supports literal strings and regex."
        ),
        "parameters": {
            "query": {
                "type": "string",
                "description": "Search pattern (literal text or regex).",
            },
            "file": {
                "type": "string",
                "description": "Optional file to search (default: main document file).",
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
            "file": {
                "type": "string",
                "description": "Optional file to modify (default: main document file).",
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
        "name": "insert_into_chunk",
        "description": (
            "Insert new content into a specific document chunk (e.g. bibliography, section, chapter, frame). "
            "Position can be 'end' (default) or 'begin'. "
            "For bibliography chunks (containing \\end{thebibliography}), 'end' automatically inserts the new \\bibitem entries "
            "BEFORE \\end{thebibliography}, preserving bibliography structure."
        ),
        "parameters": {
            "chunk_id": {
                "type": "string",
                "description": "The target chunk ID (e.g. 'chapter_1', 'section_3', 'frame_2', 'content_body').",
            },
            "content": {
                "type": "string",
                "description": "The LaTeX content or \\bibitem entry to insert.",
            },
            "position": {
                "type": "string",
                "description": "Where to insert within the chunk: 'end' (default, before closing tags like \\end{thebibliography}) or 'begin'.",
                "default": "end",
            },
        },
        "required": ["chunk_id", "content"],
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
        "name": "read_document_summary",
        "description": (
            "Get a compact structural analysis of the document: metadata (title, author, class), "
            "content inventory (figures, tables, equations, references), per-section breakdown "
            "with line counts and content markers. Use this instead of reading the entire file "
            "when you need a global understanding of the document structure."
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
            "Each page is reproduced as compilable LaTeX (same text, images, colors, font sizes, spacing and "
            "alignment as closely as possible), compiled and compared with the original. Starts a background job "
            "and returns its job_id; the user sees per-page progress and similarity scores and confirms before "
            "main.tex is replaced. Do not edit the document yourself after starting a conversion — finish with done=true."
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
        main_file = getattr(workspace, "file_path", getattr(workspace, "_file_path", "main.tex"))

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
            else:
                content = workspace.read_lines(start, end)
                return {
                    "file": main_file,
                    "content": content,
                    "lines_read": f"{start}-{end}",
                    "total_lines": workspace.get_line_count(),
                }

        elif tool_name == "grep_search":
            query = args.get("query", "")
            is_regex = bool(args.get("is_regex", False))
            target_file = args.get("file")
            if target_file and target_file not in ("main.tex", main_file):
                results = workspace.grep_file(target_file, query, is_regex=is_regex)
            else:
                results = workspace.grep(query, is_regex=is_regex)
            return {
                "matches": results,
                "match_count": len([r for r in results if "line_no" in r]),
                "query": query,
            }

        elif tool_name == "str_replace":
            old_str = args.get("old_str", "")
            new_str = args.get("new_str", "")
            target_file = args.get("file")
            if target_file and target_file not in ("main.tex", main_file):
                result = workspace.str_replace_file(target_file, old_str, new_str)
            else:
                result = workspace.str_replace(old_str, new_str)
            return result

        elif tool_name == "rewrite_chunk":
            chunk_id = str(args.get("chunk_id", "")).strip()
            new_content = args.get("new_content", "")
            result = workspace.rewrite_chunk(chunk_id, new_content)
            return result

        elif tool_name == "insert_into_chunk":
            chunk_id = str(args.get("chunk_id", "")).strip()
            content = args.get("content", "")
            position = args.get("position", "end")
            result = workspace.insert_into_chunk(chunk_id=chunk_id, content=content, position=position)
            return result

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

        elif tool_name == "list_project_files":
            files = workspace.get_file_list()
            return {
                "files": files,
                "count": len(files),
            }

        elif tool_name == "read_document_summary":
            from document_analyzer import analyze_document, generate_compact_summary
            buffer_content = workspace.get_buffer()
            analysis = analyze_document(buffer_content)
            summary = generate_compact_summary(analysis)
            return {
                "summary": summary,
                "total_lines": analysis.total_lines,
                "estimated_tokens": analysis.estimated_tokens,
                "structure_type": analysis.primary_structure_type,
                "structural_units": analysis.structural_unit_count,
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
                "error": f"Unknown tool: '{tool_name}'. Available tools: {[t['name'] for t in TOOL_DEFINITIONS]}",
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

    pdfs = [a for a in attached_context_store.get_attachments(workspace.session_id) if a.get("raw_bytes")]
    if not pdfs:
        return {"error": "No attached PDF found in this chat. Ask the user to attach the PDF file."}
    wanted = (args.get("filename") or "").lower()
    att = next((a for a in pdfs if wanted and a.get("filename", "").lower() == wanted), pdfs[-1])

    data: bytes = att["raw_bytes"]
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
                      att.get("filename") or "document.pdf", data, page_count, overwrite=False)
    return {
        "success": True,
        "job_id": state["job_id"],
        "filename": att.get("filename"),
        "page_count": page_count,
        "message": (
            "Conversion started. The user sees live progress and a similarity report, and is asked before "
            "an existing main.tex is replaced. Results are best-effort with measured similarity."
        ),
    }
