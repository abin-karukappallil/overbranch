"""
pdf_to_latex.py — PDF to Editable LaTeX Conversion Engine

Orchestrates:
1. Formatting extracted PDF text, layout blocks, and asset metadata into an LLM prompt.
2. Invoking LLM via provider_router (supporting Gemini, Groq, FreeLLM).
3. Parsing structured JSON response into project files:
   - main.tex
   - additional .tex files / sections
   - bibliography.bib (if references present)
   - assets mapping
4. Verifying compilation with compile_latex() and auto-retrying with compiler error feedback if compilation fails.
"""

import os
import re
import json
import base64
import logging
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field

from .pdf_parser import PDFParseResult, ExtractedImage
from providers import provider_router
from compiler import compile_latex

logger = logging.getLogger("pdf_to_latex")


@dataclass
class ProjectFile:
    path: str
    content: str


@dataclass
class AssetFile:
    filename: str
    data_bytes: bytes
    source_page: int
    ext: str = "png"
    mime_type: str = "image/png"


@dataclass
class ConversionResult:
    document_class: str
    engine: str
    files: List[ProjectFile]
    assets: List[AssetFile]
    compiled_successfully: bool = False
    compile_log: str = ""
    retry_count: int = 0


SYSTEM_PROMPT = r"""You are an elite LaTeX typographer and document engineer embedded in OverBranch.
Your task is to convert the extracted text, layout structure, and figures from a PDF document into a 100% editable, modular, and compilable LaTeX project.

CRITICAL ARCHITECTURAL RULES:
1. EDITABLE LATEX ONLY:
   - NEVER rasterize text into images.
   - All text, headers, paragraphs, lists, and tables must be native LaTeX.
   - Retain mathematical notation using standard LaTeX math environments ($...$, \begin{equation}, \begin{align*}).
   - Use semantic commands (\section, \subsection, \subsubsection, \paragraph).
   - Recreate tables using \begin{table}[h!] and \begin{tabular} with booktabs (\toprule, \midrule, \bottomrule).

2. DOCUMENT CLASS SELECTION:
   - NEVER use \documentclass{beamer} for portrait documents (research papers, reports, theses, articles, resumes). Beamer is ONLY for widescreen slide presentations.
   - If Report / Thesis / Chapter-based document -> Use \documentclass[11pt,a4paper,oneside]{report} with chapters or sections (the 'oneside' option is MANDATORY so odd and even pages have symmetric, centered margins!).
   - If Academic / Research Paper -> Use \documentclass[11pt,a4paper]{article} with \title, \author, \begin{abstract}, standard sections, and \bibliographystyle{plain}.
   - If Resume / CV -> Use \documentclass[10pt,letterpaper]{article} with \usepackage[margin=0.65in]{geometry}, clean sections, and enumitem.
   - If Widescreen Slide Deck (Landscape only) -> Use \documentclass[11pt,aspectratio=169]{beamer} with \begin{frame}{Title}... \end{frame}.

3. PAGE GEOMETRY, MARGINS & ALIGNMENT (CRITICAL TO PREVENT MISALIGNMENT):
   - ALWAYS include:
     \usepackage[margin=1in]{geometry}
     \usepackage{parskip} % ensures modern paragraph spacing without awkward accidental indentations
     \usepackage{amsmath,amssymb}
     \usepackage{booktabs}
     \usepackage{graphicx}
     \usepackage{hyperref}
   - NEVER use \MakeUppercase inside \titleformat (in modern LaTeX, \MakeUppercase inside \titleformat causes a fatal syntax crash). Use standard styles like \normalfont\bfseries\Large.
   - On title pages or vertical spacing, use \par\vspace{1.5cm} or empty lines with \vspace{1.5cm} instead of \\[1.5cm] (which can trigger Bad Math Delimiter errors).
   - ALL tables MUST be centered: \begin{table}[htbp] \centering \begin{tabular}{...} ... \end{tabular} \caption{...} \end{table}.
     If the table has many columns or wide text, wrap it with \resizebox{\textwidth}{!}{...} to prevent overflowing the right margin!
   - ALL figures MUST be centered: \begin{figure}[htbp] \centering \includegraphics[width=0.85\textwidth,keepaspectratio]{assets/filename} \caption{...} \end{figure}.
   - Math equations must be centered using standard \begin{equation} ... \end{equation} or \begin{align*} ... \end{align*}.

4. EMBEDDED IMAGES / ASSETS:
   - Available extracted images are placed in the 'assets/' folder.
   - When figures or logos are present, include them using \begin{figure}[htbp] \centering \includegraphics[width=...]{assets/filename} \caption{...} \end{figure}.
   - ONLY reference filenames that are listed in the AVAILABLE ASSETS list. Do not invent arbitrary image names.

5. SELF-CONTAINED SINGLE-DOCUMENT ARCHITECTURE (CRITICAL):
   - ALL document content must be written DIRECTLY inside main.tex between \begin{document} and \end{document}.
   - DO NOT split content into external section files (NEVER use \input{sections/...} or \include{sections/...}).
   - The user requires the entire document (title, abstract, table of contents, all chapters, sections, methodology, results, equations, tables, figures, conclusions) to be completely and fully written out directly inside main.tex.
   - Everything must be self-contained in main.tex so the user can immediately read, edit, and compile the entire project in one place.
   - For references/bibliography, either provide \begin{thebibliography}{99}...\end{thebibliography} directly inside main.tex, or provide bibliography.bib.

6. OUTPUT FORMAT:
   You MUST respond with a single, strictly valid JSON object. No Markdown code fences before or after the JSON, no surrounding commentary.

JSON Schema:
{
  "document_class": "article | beamer | report",
  "engine": "pdflatex",
  "files": [
    {
      "path": "main.tex",
      "content": "\\documentclass[11pt,a4paper,oneside]{report}\n\\usepackage[utf8]{inputenc}\n\\usepackage[margin=1in]{geometry}\n\\usepackage{parskip}\n\\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}\n...\n\\begin{document}\n\\chapter{Introduction}\n...\n\\chapter{Methodology}\n...\n\\chapter{Conclusion}\n...\n\\end{document}"
    },
    {
      "path": "bibliography.bib",
      "content": "@article{key,\n  author = {},\n  ...\n}"
    }
  ],
  "assets": [
    {
      "filename": "image_p1_1.png",
      "source_page": 1
    }
  ]
}

Ensure all backslashes in LaTeX strings are properly JSON-escaped (e.g. "\\\\documentclass", "\\\\section").
Ensure the document closes with \end{document}.
"""


def auto_repair_json(text: str) -> str:
    """Repairs unclosed strings and brackets in truncated or malformed JSON."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.MULTILINE)
        s = re.sub(r"\s*```$", "", s, flags=re.MULTILINE)

    s = s.strip()
    if not s.endswith("}"):
        if not s.endswith('"'):
            s += '"'
        open_b = s.count('{')
        close_b = s.count('}')
        if open_b > close_b:
            s += '}' * (open_b - close_b)
    return s


def decode_json_string_value(s: str) -> str:
    """Safely decodes JSON string literal values without crashing on LaTeX commands."""
    if not s:
        return ""
    try:
        test_s = s
        if test_s.endswith("\\") and not test_s.endswith("\\\\"):
            test_s = test_s[:-1]
        return json.loads(f'"{test_s}"', strict=False)
    except Exception:
        pass
    def repl(m):
        esc = m.group(0)
        table = {r'\\': '\\', r'\"': '"', r'\/': '/', r'\n': '\n', r'\t': '\t', r'\r': '\r', r'\b': '\b', r'\f': '\f'}
        return table.get(esc, esc)
    return re.sub(r'\\(?:[\\"/bfnrt]|u[0-9a-fA-F]{4}|.)', repl, s)


def restore_latex_escapes(text: str) -> str:
    """Restores swallowed LaTeX commands from JSON control characters."""
    if not text or not isinstance(text, str):
        return text or ""
    s = text
    s = re.sub(r"[\x08](egin|fseries|ooktabs|ottomrule|ibliography)\b", r"\\b\1", s)
    s = re.sub(r"[\x0c](rac|ootnotesize|rame|igure)\b", r"\\f\1", s)
    s = re.sub(r"[\r](enewcommand|ef|ule|aisebox)\b", r"\\r\1", s)
    s = re.sub(r"[\t](extbf|extit|exttt|itle|able|oday)\b", r"\\t\1", s)
    s = re.sub(r"(?<![a-zA-Z\\])usepackage(?=\{|\s*\[)", r"\\usepackage", s)
    s = re.sub(r"(?<![a-zA-Z\\])begin(?=\{)", r"\\begin", s)
    s = re.sub(r"(?<![a-zA-Z\\])section(?=\{)", r"\\section", s)
    s = re.sub(r"(?<![a-zA-Z\\])textbf(?=\{)", r"\\textbf", s)
    return s


def parse_llm_json_response(raw_text: str) -> Dict[str, Any]:
    """Multi-stage robust JSON parser for LLM responses with LaTeX backslashes."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # Pass 1: Direct JSON parse
    try:
        data = json.loads(cleaned, strict=False)
        for f in data.get("files", []):
            if "content" in f:
                f["content"] = restore_latex_escapes(f["content"])
        return data
    except Exception:
        pass

    # Pass 2: Repair truncated brackets
    try:
        repaired = auto_repair_json(cleaned)
        data = json.loads(repaired, strict=False)
        for f in data.get("files", []):
            if "content" in f:
                f["content"] = restore_latex_escapes(f["content"])
        return data
    except Exception:
        pass

    # Pass 3: Escape lone unescaped backslashes (common in LaTeX inside JSON)
    try:
        escaped_slashes = re.sub(r'\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', cleaned)
        data = json.loads(auto_repair_json(escaped_slashes), strict=False)
        for f in data.get("files", []):
            if "content" in f:
                f["content"] = restore_latex_escapes(f["content"])
        return data
    except Exception:
        pass

    # Pass 4: Find JSON object boundaries via regex
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            raw_obj = json_match.group(0)
            data = json.loads(raw_obj, strict=False)
            for f in data.get("files", []):
                if "content" in f:
                    f["content"] = restore_latex_escapes(f["content"])
            return data
        except Exception:
            try:
                fixed = re.sub(r'\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_match.group(0))
                data = json.loads(auto_repair_json(fixed), strict=False)
                for f in data.get("files", []):
                    if "content" in f:
                        f["content"] = restore_latex_escapes(f["content"])
                return data
            except Exception:
                pass

    # Pass 5: Regex extraction of files if JSON is partially broken
    files = []
    main_tex_match = re.search(r'"path"\s*:\s*"main\.tex"[\s\S]*?"content"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
    if main_tex_match:
        content = decode_json_string_value(main_tex_match.group(1))
        content = restore_latex_escapes(content)
        files.append({"path": "main.tex", "content": content})
        return {
            "document_class": "article",
            "engine": "pdflatex",
            "files": files,
            "assets": []
        }

    # Pass 6: Check if response is raw LaTeX starting with \documentclass
    latex_doc_match = re.search(r"(\\documentclass[\s\S]*?\\end\{document\})", cleaned)
    if latex_doc_match:
        return {
            "document_class": "article",
            "engine": "pdflatex",
            "files": [{"path": "main.tex", "content": latex_doc_match.group(1)}],
            "assets": []
        }

    raise ValueError(f"Could not parse valid JSON or LaTeX from LLM response:\n{cleaned[:500]}...")


def build_conversion_prompt(parse_result: PDFParseResult) -> str:
    """Builds the comprehensive user prompt including page texts, layout hints, and asset manifests."""
    parts = []

    parts.append(f"DOCUMENT METADATA:")
    parts.append(f"- Total Pages: {parse_result.num_pages}")
    parts.append(f"- Detected Type: {parse_result.doc_type_hint.upper()}")
    parts.append(f"- Aspect Ratio: {parse_result.aspect_ratio_hint}")
    parts.append(f"- Suggested Geometry: {parse_result.page_size_hint}")
    parts.append("")

    # Available assets manifest
    if parse_result.embedded_images:
        parts.append("AVAILABLE ASSETS (Saved in 'assets/' directory):")
        for img in parse_result.embedded_images:
            parts.append(f"- assets/{img.filename} (From PDF Page {img.source_page}, Dimensions: {img.width}x{img.height} px)")
        parts.append("Instruction: Use \\includegraphics[width=...]{assets/filename} to include these figures at relevant locations.")
        parts.append("")
    else:
        parts.append("AVAILABLE ASSETS: None detected. Do not include external image files.")
        parts.append("")

    # Page-by-page text & layout breakdown
    parts.append("EXTRACTED PDF PAGES CONTENT:")
    for page in parse_result.pages:
        parts.append(f"=== PAGE {page.page_number} (Width: {int(page.width)}pt, Height: {int(page.height)}pt, AR: {page.aspect_ratio:.2f}) ===")
        page_text = page.text.strip()
        if page_text:
            parts.append(page_text)
        else:
            parts.append("[Page contains mostly graphics or scanned elements]")
        parts.append("")

    parts.append("TASK:")
    parts.append(
        "Generate the complete, editable LaTeX project replicating the layout, structure, and text of this document. "
        "CRITICAL: Write ALL document content, title, abstract, chapters, sections, paragraphs, tables, and equations "
        "DIRECTLY inside main.tex. DO NOT use \\input{sections/...} or \\include{} to split content into separate files. "
        "The entire document must be fully contained and editable directly within main.tex. "
        "Return ONLY the structured JSON with 'document_class', 'engine', 'files', and 'assets'."
    )

    return "\n".join(parts)


def resolve_and_inline_all_inputs(raw_files: List[Dict[str, Any]], parse_result: PDFParseResult) -> List[Dict[str, Any]]:
    """
    Ensures main.tex is 100% self-contained by inlining any \\input{} or \\include{}
    commands. If the referenced file exists in raw_files, its content is inlined.
    If not, it inlines relevant content from the PDF text to prevent missing file compilation errors.
    """
    files_map = {f.get("path", "").strip(): f.get("content", "") for f in raw_files if f.get("path")}
    main_tex = files_map.get("main.tex", "")
    if not main_tex or ("\\input" not in main_tex and "\\include" not in main_tex):
        return raw_files

    def replacer(match):
        raw_path = match.group(1).strip()
        candidates = [
            raw_path,
            f"{raw_path}.tex" if not raw_path.endswith(".tex") else raw_path,
            raw_path.replace("sections/", ""),
            f"sections/{raw_path}" if not raw_path.startswith("sections/") else raw_path,
        ]
        for c in candidates:
            if c in files_map and files_map[c].strip():
                logger.info(f"Inlining referenced section '{c}' directly into main.tex")
                return f"\n% --- Inlined section: {c} ---\n" + files_map[c].strip() + "\n"

        base_name = raw_path.rsplit("/", 1)[-1].replace(".tex", "")
        sec_title = base_name.replace("_", " ").title()

        # Check if text snippet for this section exists in PDF full text
        matched_text = ""
        kw = base_name.lower().replace("_", " ")
        if kw in parse_result.full_text.lower():
            idx = parse_result.full_text.lower().find(kw)
            snippet = parse_result.full_text[idx:idx + 800].strip()
            snippet = re.sub(r'--- PAGE \d+ ---', '', snippet).strip()
            if len(snippet) > 50:
                matched_text = snippet

        if matched_text:
            return f"\n\\section{{{sec_title}}}\n{matched_text}\n"
        elif any(k in base_name.lower() for k in ["title", "certificate", "abbreviation", "symbol", "acknowledgement"]):
            return f"\n% [{sec_title}]\n"
        else:
            return f"\n\\section{{{sec_title}}}\n"

    new_main_tex = re.sub(r'\\(?:input|include)\{([^}]+)\}', replacer, main_tex)

    # Sanitize titlesec \MakeUppercase bug in modern LaTeX & bad math delimiter on spacing
    sanitized_lines = []
    for line in new_main_tex.split("\n"):
        if "titleformat" in line and "\\MakeUppercase" in line:
            line = line.replace("\\MakeUppercase", "")
        elif "\\MakeUppercase" in line and any(k in line for k in ["centering", "normalfont", "bfseries"]):
            line = line.replace("\\MakeUppercase", "")
        if "\\\\" in line and any(unit in line for unit in ["cm]", "in]", "mm]", "pt]", "em]"]):
            line = re.sub(r'\\\\\s*\[(\d+(?:\.\d+)?(?:cm|in|mm|pt|em|ex))\]', r'\\par\\vspace{\1}', line)
        sanitized_lines.append(line)
    new_main_tex = "\n".join(sanitized_lines)

    result_files = []
    for f in raw_files:
        if f.get("path") == "main.tex":
            result_files.append({"path": "main.tex", "content": new_main_tex})
        else:
            result_files.append(f)

    return result_files


def test_and_auto_repair_compilation(
    conversion_data: Dict[str, Any],
    parse_result: PDFParseResult,
    model: str,
    progress_callback: Optional[Callable[[str, str], None]] = None,
    max_retries: int = 2,
) -> Tuple[Dict[str, Any], bool, str]:
    """
    Tests compilation of the generated LaTeX files.
    If compilation fails, queries LLM with the compiler error log to fix issues (up to max_retries).
    Returns (repaired_conversion_data, success, log).
    """
    current_data = conversion_data
    if "files" in current_data:
        current_data["files"] = resolve_and_inline_all_inputs(current_data["files"], parse_result)

    for attempt in range(max_retries + 1):
        files = current_data.get("files", [])
        main_tex = next((f["content"] for f in files if f.get("path") == "main.tex"), "")
        if not main_tex:
            return current_data, False, "No main.tex file found in conversion result."

        # Prepare images and extra files payload for compiler
        extra_files = []
        for f in files:
            if f.get("path") != "main.tex":
                extra_files.append({
                    "filename": f.get("path"),
                    "data": base64.b64encode(f.get("content", "").encode("utf-8")).decode("utf-8")
                })

        images_payload = []
        for img in parse_result.embedded_images:
            # We provide both "assets/filename" and "filename" for robust graphicx resolution
            b64_data = base64.b64encode(img.data_bytes).decode("utf-8")
            images_payload.append({"filename": f"assets/{img.filename}", "data": b64_data})
            images_payload.append({"filename": img.filename, "data": b64_data})

        engine = current_data.get("engine", "latexmk")

        if progress_callback:
            if attempt == 0:
                progress_callback("compiling", "Verifying LaTeX compilation...")
            else:
                progress_callback("compiling", f"Verifying corrected LaTeX (attempt {attempt}/{max_retries})...")

        comp_result = compile_latex(
            latex_code=main_tex,
            engine=engine,
            images=images_payload,
            files=extra_files,
            project_id="pdf_verify_temp"
        )

        if comp_result.get("success"):
            logger.info(f"PDF LaTeX compilation verified successfully on attempt {attempt}.")
            return current_data, True, comp_result.get("log", "Compilation successful")

        log = comp_result.get("log", "Compilation failed with unknown error.")
        logger.warning(f"Compilation failed on attempt {attempt}: {log[:300]}")

        # If retries left, ask LLM to fix the compilation error
        if attempt < max_retries:
            if progress_callback:
                progress_callback("repairing", f"Fixing compilation error (attempt {attempt + 1}/{max_retries})...")

            repair_prompt = (
                f"The generated LaTeX project failed to compile with the following error log:\n\n"
                f"```\n{log[-1500:]}\n```\n\n"
                f"CURRENT main.tex:\n"
                f"```latex\n{main_tex[:4000]}\n```\n\n"
                f"Please fix all LaTeX compilation errors, missing packages, syntax errors, or unclosed environments. "
                f"Return the complete corrected JSON object according to the original schema."
            )

            try:
                repair_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": repair_prompt},
                ]
                provider = provider_router.route(model)
                res = provider.chat(repair_messages, model=model, temperature=0.1, max_tokens=4096)
                new_raw = res.get("content", "")
                parsed_repair = parse_llm_json_response(new_raw)
                if parsed_repair.get("files"):
                    current_data = parsed_repair
            except Exception as repair_err:
                logger.error(f"Auto-repair LLM call failed: {repair_err}")
                break

    return current_data, False, log


def convert_pdf_to_latex(
    parse_result: PDFParseResult,
    model: Optional[str] = None,
    progress_callback: Optional[Callable[[str, str], None]] = None,
    auto_repair: bool = True,
) -> ConversionResult:
    """
    Main conversion orchestrator:
    - Builds LLM prompt from parse_result
    - Calls LLM via provider_router
    - Parses structured files and assets
    - Automatically tests compilation and repairs if needed
    """
    target_model = model or provider_router.get_default_model()

    if progress_callback:
        progress_callback("generating_latex", f"Synthesizing editable LaTeX via {target_model}...")

    user_prompt = build_conversion_prompt(parse_result)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    provider = provider_router.route(target_model)
    logger.info(f"Converting PDF with provider {provider.get_provider_name()} (model={target_model})...")

    llm_resp = provider.chat(
        messages=messages,
        model=target_model,
        temperature=0.1,
        max_tokens=4096,
    )

    raw_content = llm_resp.get("content", "")
    if not raw_content:
        raise RuntimeError("LLM returned empty response during PDF conversion.")

    parsed_json = parse_llm_json_response(raw_content)
    if "files" in parsed_json:
        parsed_json["files"] = resolve_and_inline_all_inputs(parsed_json["files"], parse_result)

    # Auto-repair verification pass
    compiled_ok = False
    comp_log = ""
    if auto_repair:
        parsed_json, compiled_ok, comp_log = test_and_auto_repair_compilation(
            conversion_data=parsed_json,
            parse_result=parse_result,
            model=target_model,
            progress_callback=progress_callback,
            max_retries=2,
        )

    # Build ProjectFiles list
    raw_files = resolve_and_inline_all_inputs(parsed_json.get("files", []), parse_result)
    project_files: List[ProjectFile] = []
    has_main_tex = False

    for f in raw_files:
        p = f.get("path", "").strip()
        c = f.get("content", "")
        if p == "main.tex":
            has_main_tex = True
        if p and c:
            project_files.append(ProjectFile(path=p, content=c))

    # Fallback if main.tex was missing
    if not has_main_tex:
        logger.warning("No main.tex in parsed files, using default document wrapper.")
        default_tex = (
            "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb,graphicx}\n"
            "\\begin{document}\n" + (parse_result.full_text or "Converted Document") + "\n\\end{document}"
        )
        project_files.insert(0, ProjectFile(path="main.tex", content=default_tex))

    # Map asset files
    assets: List[AssetFile] = [
        AssetFile(
            filename=img.filename,
            data_bytes=img.data_bytes,
            source_page=img.source_page,
            ext=img.ext,
            mime_type=img.mime_type,
        )
        for img in parse_result.embedded_images
    ]

    return ConversionResult(
        document_class=parsed_json.get("document_class", parse_result.doc_type_hint),
        engine=parsed_json.get("engine", "pdflatex"),
        files=project_files,
        assets=assets,
        compiled_successfully=compiled_ok,
        compile_log=comp_log,
    )
