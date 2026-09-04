import os
import re
import time
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("synctex_service")

SYNCTEX_CACHE_DIR = Path("/tmp/overbranch_synctex_cache")
SYNCTEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory LRU cache for forward and backward lookup results
_LOOKUP_CACHE: Dict[str, Any] = {}
MAX_CACHE_ENTRIES = 500


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
                text=True,
                timeout=5,
            )
            output = proc.stdout or ""

            input_match = re.search(r"^Input:(.+)$", output, re.MULTILINE)
            line_match = re.search(r"^Line:(\d+)$", output, re.MULTILINE)
            col_match = re.search(r"^Column:(-?\d+)$", output, re.MULTILINE)

            if line_match:
                raw_file = input_match.group(1) if input_match else "main.tex"
                rel_file = normalize_tex_file_path(raw_file, build_dir)
                line_num = int(line_match.group(1))
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
            text=True,
            timeout=5,
        )
        output = proc.stdout or ""

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

