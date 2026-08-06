import tempfile
import subprocess
import base64
import os
from pathlib import Path


def compile_latex(latex_code: str, engine: str = "pdflatex") -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            tex_path = Path(tmpdir) / "main.tex"
            tex_path.write_text(latex_code, encoding="utf-8")

            if engine == "tectonic":
                cmd = ["tectonic", "main.tex"]
            else:
                cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]

            result = subprocess.run(
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=12,
            )

            pdf_path = Path(tmpdir) / "main.pdf"

            if not pdf_path.exists():
                return {
                    "success": False,
                    "error_log": result.stdout + "\n" + result.stderr,
                }

            pdf_bytes = pdf_path.read_bytes()
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

            return {
                "success": True,
                "pdf_base64": pdf_base64,
                "compile_time_ms": 0,
                "log": result.stdout[-500:] if result.stdout else "",
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error_log": "Compilation timed out after 12 seconds.",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error_log": f"Engine '{engine}' not found. Install pdflatex (texlive) or tectonic.",
            }
        except Exception as e:
            return {
                "success": False,
                "error_log": str(e),
            }
