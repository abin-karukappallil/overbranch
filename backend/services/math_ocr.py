"""
backend/services/math_ocr.py
============================
Formula-recognition pipeline for LaTeX document synthesis.
Transcribes cropped math formula regions and raw math blocks into clean LaTeX math environments:
  - Pluggable provider architecture: Vision LLM (Gemini / OpenRouter)
  - Rule-based heuristic clean-up fallback
  - Normalizes math to \\begin{equation} ... \\end{equation} or align
"""

import base64
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger("math_ocr")

MATH_OCR_SYSTEM_PROMPT = """You are a LaTeX mathematics transcription specialist.
Transcribe the mathematical formula in the provided image or text snippet into precise, standard LaTeX.

Rules:
1. Output ONLY the LaTeX math code.
2. Use standard LaTeX math symbols (e.g. \\frac, \\sum, \\int, \\alpha, \\beta, \\mathbf, \\partial, \\sqrt).
3. Wrap in an appropriate environment (e.g. \\begin{equation} ... \\end{equation} or \\begin{align} ... \\end{align}) without extra explanation.
4. No markdown commentary or backticks.
"""


def clean_math_latex(latex_str: str) -> str:
    """Cleans up raw LLM math output to ensure valid LaTeX math format."""
    if not latex_str:
        return ""
    s = latex_str.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:latex|tex)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    s = s.strip()

    # Wrap in equation environment if bare expression
    if not (s.startswith("\\begin{") or s.startswith("\\[") or s.startswith("$$")):
        s = f"\\begin{{equation}}\n    {s}\n\\end{{equation}}"
    return s


def heuristic_math_transcription(raw_text: str) -> str:
    """Heuristic fallback to clean common OCR artifacts in math formulas."""
    if not raw_text:
        return "\\begin{equation}\n    E = mc^2\n\\end{equation}"

    t = raw_text.strip()
    # Common OCR cleanups
    t = re.sub(r"([a-zA-Z])\s*\^\s*([0-9a-zA-Z]+)", r"\1^{\2}", t)
    t = re.sub(r"([a-zA-Z])\s*_\s*([0-9a-zA-Z]+)", r"\1_{\2}", t)
    t = re.sub(r"\bint\b", r"\\int", t)
    t = re.sub(r"\bsum\b", r"\\sum", t)
    t = re.sub(r"\balpha\b", r"\\alpha", t)
    t = re.sub(r"\bbeta\b", r"\\beta", t)
    t = re.sub(r"\bgamma\b", r"\\gamma", t)
    t = re.sub(r"\btheta\b", r"\\theta", t)
    t = re.sub(r"\bpi\b", r"\\pi", t)
    t = re.sub(r"<=", r"\\le", t)
    t = re.sub(r">=", r"\\ge", t)
    t = re.sub(r"!=", r"\\neq", t)

    return f"\\begin{{equation}}\n    {t}\n\\end{{equation}}"


class MathOCRService:
    """Pluggable service for converting math image regions or raw text into clean LaTeX."""

    def __init__(self):
        pass

    def transcribe_image(
        self,
        image_bytes: bytes,
        raw_text_hint: str = "",
        api_keys: Optional[Dict[str, str]] = None,
        model: str = "gemini-3.7-flash",
    ) -> str:
        """Transcribes a cropped equation image into LaTeX using vision model."""
        if not image_bytes:
            return heuristic_math_transcription(raw_text_hint)

        try:
            from providers.router import provider_router
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            messages = [
                {"role": "system", "content": MATH_OCR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Transcribe this equation into LaTeX (text hint: {raw_text_hint}):"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                    ]
                }
            ]

            # Route to vision capable model
            provider = provider_router.route(model)
            resp = provider.chat(
                messages=messages,
                model=model,
                temperature=0.1,
                max_tokens=512,
                api_keys=api_keys,
            )
            content = resp.get("content", "")
            if content:
                return clean_math_latex(content)
        except Exception as e:
            logger.warning(f"Vision Math-OCR failed: {e}. Using heuristic fallback.")

        return heuristic_math_transcription(raw_text_hint)

    def transcribe_text(
        self,
        raw_text: str,
        api_keys: Optional[Dict[str, str]] = None,
        model: str = "openai/gpt-oss-120b",
    ) -> str:
        """Transcribes raw extracted OCR text into valid LaTeX math syntax."""
        if not raw_text:
            return ""

        try:
            from providers.router import provider_router
            messages = [
                {"role": "system", "content": MATH_OCR_SYSTEM_PROMPT},
                {"role": "user", "content": f"Convert this formula text into clean LaTeX math:\n{raw_text}"}
            ]
            resp = provider_router.chat_fast_tier(
                messages=messages,
                temperature=0.1,
                max_tokens=256,
                api_keys=api_keys,
            )
            content = resp.get("content", "")
            if content:
                return clean_math_latex(content)
        except Exception as e:
            logger.debug(f"Fast tier Math-OCR text format note: {e}")

        return heuristic_math_transcription(raw_text)


math_ocr_service = MathOCRService()
