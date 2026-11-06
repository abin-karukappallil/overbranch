import os
import re
import time
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("synctex_service")

SYNCTEX_CACHE_DIR = Path("/tmp/overbranch_synctex_cache")
SYNCTEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory LRU cache for forward and backward lookup results
_LOOKUP_CACHE: Dict[str, Any] = {}
MAX_CACHE_ENTRIES = 500

AUXILIARY_EXTENSIONS = frozenset({
    ".aux", ".lof", ".lot", ".toc", ".log", ".out", ".synctex", ".synctex.gz",
    ".fls", ".fdb_latexmk", ".nav", ".snm", ".vrb", ".bcf", ".run.xml",
    ".blg", ".bbl", ".idx", ".ind", ".ilg", ".glo", ".gls", ".glg",
    ".acn", ".acr", ".alg", ".nlo", ".nls", ".nlg", ".ist", ".dvi", ".xdv"
})


def is_auxiliary_file(file_path: str) -> bool:
    if not file_path:
        return False
    lower = file_path.strip().lower()
    if lower.endswith(".synctex.gz"):
        return True
    ext = Path(lower).suffix
    return ext in AUXILIARY_EXTENSIONS


def get_project_build_dir(project_id: Optional[str]) -> Path:
    """Return the persistent build directory for a project."""
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", (project_id or "default").strip())
    build_dir = SYNCTEX_CACHE_DIR / safe_id
    build_dir.mkdir(parents=True, exist_ok=True)
    return build_dir


def normalize_tex_file_path(raw_path: str, build_dir: Path) -> str:
    """
    Clean up file path from synctex output to be relative to project root.
    e.g. '/tmp/tmp1234/./sections/method.tex' -> 'sections/method.tex'
         '/tmp/overbranch_synctex_cache/proj_1/./sections/method.tex' -> 'sections/method.tex'
    """
    cleaned = raw_path.strip()
    build_dir_str = str(build_dir.resolve())

    if cleaned.startswith(build_dir_str):
        cleaned = cleaned[len(build_dir_str):].lstrip("/\\")

    # Strip any generic /tmp/tmp.../ temporary compilation directory prefix
    cleaned = re.sub(r"^/tmp/[^/]+/", "", cleaned)

    # Strip any leading ./ or .\ or /
    cleaned = re.sub(r"^(\./|/|\\)+", "", cleaned)

    return cleaned or "main.tex"


def resolve_synctex_source(raw_path: str, line_num: int, build_dir: Path) -> Tuple[str, int]:
    """
    Translates raw SyncTeX output into an editable project source file and line.
    
    1. System-wide TeX distribution files (/usr/..., /texmf...) and absolute paths outside
       the project are never returned to the editor; they fall back to main.tex.
    2. Generated auxiliary files (.lof, .toc, .lot) are translated back to the line in
       main.tex where \\listoffigures, \\tableofcontents, or \\listoftables was declared.
    3. Any other auxiliary file (.aux, .out, .bbl, etc.) falls back to main.tex:1.
    """
    raw_clean = raw_path.strip()

    # TeX distribution or system paths (e.g. /usr/share/texmf-dist/.../something.sty)
    if raw_clean.startswith(("/usr/", "/opt/", "/etc/", "/var/")) or "/texmf" in raw_clean.lower():
        return "main.tex", 1

    rel_norm = normalize_tex_file_path(raw_clean, build_dir)

    if not is_auxiliary_file(rel_norm):
        return rel_norm, line_num

    # It is an auxiliary file: map to the originating declaration in main.tex
    main_tex = build_dir / "main.tex"
    if main_tex.is_file():
        try:
            lines = main_tex.read_text(encoding="utf-8", errors="replace").splitlines()
            lower_name = Path(rel_norm).name.lower()
            target_pattern = None
            if lower_name.endswith(".lof"):
                target_pattern = re.compile(r"\\listoffigures\b")
            elif lower_name.endswith(".toc"):
                target_pattern = re.compile(r"\\tableofcontents\b")
            elif lower_name.endswith(".lot"):
                target_pattern = re.compile(r"\\listoftables\b")
            elif lower_name.endswith(".bbl"):
                target_pattern = re.compile(r"\\(?:printbibliography|bibliography)\b|\\begin\{thebibliography\}")

            if target_pattern:
                for idx, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("%"):
                        continue
                    if target_pattern.search(line):
                        return "main.tex", idx
        except Exception as e:
            logger.debug(f"Error mapping aux file to main.tex line: {e}")

    return "main.tex", 1


def backward_lookup(
    project_id: Optional[str],
    page: int,
    x: float,
    y: float,
) -> Optional[Dict[str, Any]]:
    """
    Perform reverse SyncTeX lookup (PDF point -> LaTeX source line & column).
    Coordinates (x, y) are in big points (72 dpi) from page top-left.
    """
    build_dir = get_project_build_dir(project_id)
    pdf_path = build_dir / "main.pdf"

    if not pdf_path.exists():
        # Fallback: Find the most recently compiled project cache
        recent_dirs = sorted(
            [
                d for d in SYNCTEX_CACHE_DIR.iterdir()
                if d.is_dir() and (d / "main.pdf").exists() and ((d / "main.synctex.gz").exists() or (d / "main.synctex").exists())
            ],
            key=lambda d: (d / "main.pdf").stat().st_mtime,
            reverse=True
        )
        if recent_dirs:
            build_dir = recent_dirs[0]
            pdf_path = build_dir / "main.pdf"
        else:
            logger.warning(f"No compiled main.pdf found in {build_dir}")
            return None

    cache_key = f"bwd:{project_id}:{page}:{round(x, 1)}:{round(y, 1)}"
    if cache_key in _LOOKUP_CACHE:
        return _LOOKUP_CACHE[cache_key]

    # Try exact coordinate first, then test small vertical offsets (SyncTeX line margin tolerance)
    test_coords = [(x, y), (x, y - 8), (x, y + 8), (x, y - 16), (x, y + 16), (x, y - 24), (x, y + 24)]
    
    for tx, ty in test_coords:
        if ty < 0:
            continue
        cmd = [
            "synctex",
            "edit",
            "-o",
            f"{page}:{tx}:{ty}:main.pdf",
            "-d",
            str(build_dir),
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(build_dir),
                capture_output=True,
                timeout=5,
            )
            raw = proc.stdout or b""
            output = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

            input_match = re.search(r"^Input:(.+)$", output, re.MULTILINE)
            line_match = re.search(r"^Line:(\d+)$", output, re.MULTILINE)
            col_match = re.search(r"^Column:(-?\d+)$", output, re.MULTILINE)

            if line_match:
                raw_file = input_match.group(1) if input_match else "main.tex"
                line_raw = int(line_match.group(1))
                rel_file, line_num = resolve_synctex_source(raw_file, line_raw, build_dir)
                col_num = int(col_match.group(1)) if col_match else 1
                if col_num < 1:
                    col_num = 1

                result = {
                    "file": rel_file,
                    "line": line_num,
                    "column": col_num,
                }

                if len(_LOOKUP_CACHE) >= MAX_CACHE_ENTRIES:
                    _LOOKUP_CACHE.clear()
                _LOOKUP_CACHE[cache_key] = result
                return result
        except Exception as err:
            logger.debug(f"SyncTeX backward coordinate try error: {err}")
            continue

    logger.debug(f"SyncTeX backward lookup found no match around ({x}, {y})")
    return None


def forward_lookup(
    project_id: Optional[str],
    file_path: str,
    line: int,
    column: int = 1,
) -> Optional[Dict[str, Any]]:
    """
    Perform forward SyncTeX lookup (LaTeX source line & column -> PDF page & coords).
    """
    if is_auxiliary_file(file_path):
        return None

    build_dir = get_project_build_dir(project_id)
    pdf_path = build_dir / "main.pdf"

    if not pdf_path.exists():
        logger.warning(f"No compiled main.pdf found in {build_dir}")
        return None

    cache_key = f"fwd:{project_id}:{file_path}:{line}:{column}"
    if cache_key in _LOOKUP_CACHE:
        return _LOOKUP_CACHE[cache_key]

    clean_file = file_path.lstrip("./\\")
    cmd = [
        "synctex",
        "view",
        "-i",
        f"{line}:{column}:{clean_file}",
        "-o",
        "main.pdf",
        "-d",
        str(build_dir),
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(build_dir),
            capture_output=True,
            timeout=5,
        )
        raw = proc.stdout or b""
        output = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

        # Parse output
        # Page:1
        # x:159.505
        # y:156.585
        # h:133.768
        # v:158.522
        # W:343.711
        # H:8.855
        page_match = re.search(r"^Page:(\d+)$", output, re.MULTILINE)
        x_match = re.search(r"^x:([0-9.]+)$", output, re.MULTILINE)
        y_match = re.search(r"^y:([0-9.]+)$", output, re.MULTILINE)
        h_match = re.search(r"^h:([0-9.]+)$", output, re.MULTILINE)
        v_match = re.search(r"^v:([0-9.]+)$", output, re.MULTILINE)
        w_match = re.search(r"^W:([0-9.]+)$", output, re.MULTILINE)
        h_dim_match = re.search(r"^H:([0-9.]+)$", output, re.MULTILINE)

        if not page_match:
            logger.debug(f"SyncTeX forward lookup gave no page match for {file_path}:{line}")
            return None

        page_num = int(page_match.group(1))
        x_val = float(x_match.group(1)) if x_match else 0.0
        y_val = float(y_match.group(1)) if y_match else 0.0
        h_val = float(h_match.group(1)) if h_match else x_val
        v_val = float(v_match.group(1)) if v_match else y_val
        width_val = float(w_match.group(1)) if w_match else 200.0
        height_val = float(h_dim_match.group(1)) if h_dim_match else 14.0

        result = {
            "page": page_num,
            "x": x_val,
            "y": y_val,
            "h": h_val,
            "v": v_val,
            "width": width_val,
            "height": height_val,
        }

        if len(_LOOKUP_CACHE) >= MAX_CACHE_ENTRIES:
            _LOOKUP_CACHE.clear()
        _LOOKUP_CACHE[cache_key] = result

        return result
    except Exception as err:
        logger.error(f"Error during SyncTeX forward lookup: {err}", exc_info=True)
        return None


def invalidate_project_synctex_cache(project_id: Optional[str]) -> None:
    """Clear cached lookup entries when a project is recompiled."""
    prefix_bwd = f"bwd:{project_id}:"
    prefix_fwd = f"fwd:{project_id}:"
    keys_to_del = [k for k in _LOOKUP_CACHE if k.startswith(prefix_bwd) or k.startswith(prefix_fwd)]
    for k in keys_to_del:
        _LOOKUP_CACHE.pop(k, None)


def cleanup_stale_synctex_cache(max_age_hours: int = 24) -> int:
    """
    Remove synctex cache directories older than max_age_hours.
    Prevents /tmp/overbranch_synctex_cache from growing unbounded and filling disk.
    Returns number of purged directories.
    """
    purged = 0
    cutoff = time.time() - (max_age_hours * 3600)
    try:
        if not SYNCTEX_CACHE_DIR.exists():
            return 0
        for entry in SYNCTEX_CACHE_DIR.iterdir():
            if entry.is_dir():
                try:
                    if entry.stat().st_mtime < cutoff:
                        shutil.rmtree(entry, ignore_errors=True)
                        purged += 1
                except Exception as e:
                    logger.debug(f"Could not purge synctex cache entry {entry}: {e}")
    except Exception as e:
        logger.warning(f"Error scanning synctex cache directory: {e}")
    if purged > 0:
        logger.info(f"Purged {purged} stale synctex cache directories (> {max_age_hours}h old).")
    return purged

