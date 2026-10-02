"""
scope_classifier.py — Request Scope Classification (Targeted Edit vs Full Rewrite)
==================================================================================
Classifies user LaTeX editing requests into:
  - TARGETED_EDIT: Surgical, localized modifications to specific sections, equations,
    figures, metadata, or slides.
  - FULL_DOCUMENT_REWRITE: Comprehensive document overhaul, full topic replacement,
    multi-chapter replacement based on new source material, or rewriting all content.

Employs fast heuristic keyword matching first, falling back to LLM-based classification
for ambiguous requests.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from providers.router import provider_router

logger = logging.getLogger("scope_classifier")


class ScopeType(str, Enum):
    TARGETED_EDIT = "TARGETED_EDIT"
    FULL_DOCUMENT_REWRITE = "FULL_DOCUMENT_REWRITE"
    FULL_DOCUMENT_EXPANSION = "FULL_DOCUMENT_EXPANSION"


@dataclass
class ScopeClassificationResult:
    scope: str
    reason: str
    confidence: float = 1.0
    is_heuristic: bool = True
    forbidden_terms: List[str] = field(default_factory=list)

    @property
    def is_full_rewrite(self) -> bool:
        return self.scope == ScopeType.FULL_DOCUMENT_REWRITE.value or self.scope == ScopeType.FULL_DOCUMENT_REWRITE

    @property
    def is_expansion(self) -> bool:
        return self.scope == ScopeType.FULL_DOCUMENT_EXPANSION.value or self.scope == ScopeType.FULL_DOCUMENT_EXPANSION


# Heuristic keyword patterns indicating full document expansion / adding content across the document
EXPANSION_PATTERNS = [
    r"\badd\s+more\s+content\b",
    r"\bexpand\s+(?:the\s+)?(?:whole\s+|entire\s+)?(?:document|report|paper|all\s+sections?|all\s+chapters?)\b",
    r"\bexpand\s+all\b",
    r"\bexpand\s+all\s+(?:chapters?|sections?|subchapters?|topics?)\b",
    r"\bmake\s+(?:it\s+|the\s+document\s+|this\s+)?longer\b",
    r"\bmake\s+(?:the\s+)?document\s+\d+\s+pages\b",
    r"\bmore\s+pages\b",
    r"\bfill\s+out\s+(?:the\s+)?(?:document|all\s+sections?|all\s+chapters?)\b",
    r"\bflesh\s+out\b",
    r"\badd\s+more\s+detail(?:s)?\b",
    r"\belaborate\s+(?:on\s+)?all\b",
    r"\belaborate\s+throughout\b",
    r"\belaborate\s+(?:on\s+)?(?:all\s+)?(?:chapters?|sections?|subchapters?)\b",
    r"\bwrite\s+more\s+content\b",
    r"\bincrease\s+(?:the\s+)?(?:length|content|details?)\b",
    r"\bexpand\s+every\s+(?:chapter|section|topic)\b",
    r"\badd\s+depth\b",
    r"\bmake\s+(?:it\s+)?more\s+detailed\b",
    r"\bexpand\s+the\s+content\b",
    r"\bmore\s+content\s+across\b",
    r"\badd\s+content\s+to\s+all\b",
    r"\bextend\s+the\s+document\b",
]

# Heuristic keyword patterns indicating full document rewrite
FULL_REWRITE_PATTERNS = [
    r"\bchange\s+the\s+topic\b",
    r"\bchange\s+topic\b",
    r"\bswitch\s+(?:the\s+)?topic\b",
    r"\bnew\s+topic\b",
    r"\bchange\s+the\s+subject\b",
    r"\brewrite\s+everything\b",
    r"\brewrite\s+(?:the\s+)?(?:(?:entire|whole)\s+)?document\b",
    r"\brewrite\s+document\b",
    r"\brewrite\s+all\b",
    r"\brewrite\s+all\s+content\b",
    r"\brewrite\s+all\s+chapters?\b",
    r"\brewrite\s+every\s+chapter\b",
    r"\brewrite\s+each\s+chapter\b",
    r"\brewrite\s+all\s+sections?\b",
    r"\brewrite\s+every\s+section\b",
    r"\brewrite\s+each\s+section\b",
    r"\brewrite\s+from\s+scratch\b",
    r"\bfull\s+document\s+rewrite\b",
    r"\bfull\s+rewrite\b",
    r"\bbased\s+on\s+this\s+new\s+source\b",
    r"\bnew\s+source\s+material\b",
    r"\breplace\s+all\s+content\b",
    r"\breplace\s+all\s+chapters?\b",
    r"\breplace\s+all\s+sections?\b",
    r"\breplace\s+all\b",
    r"\breplace\s+everything\b",
    r"\breplace\s+(?:the\s+)?entire\s+content\b",
    r"\breplace\s+the\s+entire\b",
    r"\boverhaul\s+everything\b",
    r"\boverhaul\s+all\s+chapters?\b",
    r"\boverhaul\s+(?:the\s+)?(?:(?:entire|whole)\s+)?document\b",
    r"\bredo\s+the\s+entire\b",
    r"\brebuild\s+the\s+whole\b",
    r"\bconvert\s+everything\b",
    r"\bupdate\s+all\s+chapters?\b",
    r"\bconvert\s+(?:this\s+)?(?:pdf|document|paper|file)\b",
    r"\bturn\s+(?:this\s+)?(?:pdf|document|paper|file)\s+into\b",
    r"\bcreate\s+(?:a\s+)?(?:presentation|slides?|beamer|report|paper)\s+from\s+(?:this\s+)?(?:pdf|document|paper|file)\b",
    r"\bmake\s+(?:a\s+)?(?:presentation|slides?|beamer|report|paper)\s+from\s+(?:this\s+)?(?:pdf|document|paper|file)\b",
]

# Targeted edit patterns
TARGETED_PATTERNS = [
    r"\btypo\b",
    r"\bspelling\b",
    r"\brename\b",
    r"\bchange\s+author\b",
    r"\bchange\s+title\s+to\b",
    r"\bfix\s+date\b",
    r"\breplace\s+word\b",
    r"\bsingle\s+word\b",
    r"\bline\s+number\b",
    r"\bgrammar\b",
    r"\bonly\s+in\s+chapter\b",
    r"\bjust\s+section\b",
    r"\bfix\s+equation\b",
    r"\bchange\s+color\b",
    r"\badd\s+a\s+section\b",
    r"\bin\s+section\s+\d+\b",
    r"\bin\s+chapter\s+\d+\b",
    r"\bslide\s+\d+\b",
    r"\b(?:add|insert|append|cite)\s+.*(?:bibliography|references?|bibitem|citation|source)\b",
    r"\b(?:bibliography|references?)\b",
    r"\b(?:add|insert|append)\s+.*(?:bullet|item|point|highlight|line)\b",
    r"\b(?:add|insert|append)\s+.*(?:figure|table|equation|formula|paragraph|sentence|code|algorithm)\b",
    r"\b(?:in|to)\s+(?:section|chapter|slide|frame|abstract|conclusion|intro|introduction)\b",
    r"\bfix\b",
    r"\bchange\b",
    r"\bmodify\b",
    r"\bupdate\b",
    r"\bextract\b",
    r"\bsearch\b",
    r"\binclude\b",
    r"\bcite\b",
    r"\bcreate\b",
    r"\bgenerate\b",
    r"\bdraft\b",
]


def extract_topic_transition_terms(instruction: str, current_code: Optional[str] = None) -> List[str]:
    """
    Extracts terms from the prompt that indicate old topic content
    which should not remain after a full rewrite (e.g., 'from X to Y', 'replace X with Y').
    """
    forbidden: List[str] = []
    instr_lower = instruction.lower()

    # 1. Match patterns like "from X to Y" or "replace X with Y"
    from_to_matches = re.finditer(r'(?:from|replace)\s+["\']?([^"\',]+?)["\']?\s+(?:to|with)\s+["\']?([^"\',]+?)["\']?', instr_lower)
    for match in from_to_matches:
        old_topic = match.group(1).strip()
        clean = re.sub(r'^(?:the\s+topic\s+of|the\s+topic|the|this|all|old)\s+', '', old_topic).strip()
        if len(clean) > 2 and clean not in ("the", "this", "all", "everything"):
            forbidden.append(clean)

    # 2. Match patterns like "no longer about X" or "instead of X"
    instead_matches = re.finditer(r'(?:instead of|no longer about|remove all mentions of)\s+["\']?([^"\',]+?)["\']?(?:\.|\n|,|$)', instr_lower)
    for match in instead_matches:
        old_topic = match.group(1).strip()
        clean = re.sub(r'^(?:the\s+topic\s+of|the\s+topic|the|this|all|old)\s+', '', old_topic).strip()
        if len(clean) > 2:
            forbidden.append(clean)

    return list(dict.fromkeys(forbidden))


def classify_scope(
    user_instruction: str,
    current_code: Optional[str] = None,
    model: Optional[str] = None,
    api_keys: Optional[Dict[str, str]] = None,
) -> ScopeClassificationResult:
    """
    Classifies a user's LaTeX editing request as TARGETED_EDIT, FULL_DOCUMENT_REWRITE,
    or FULL_DOCUMENT_EXPANSION.

    1. Fast heuristic keyword matching
    2. LLM fallback for ambiguous cases
    """
    if not user_instruction or not user_instruction.strip():
        return ScopeClassificationResult(
            scope=ScopeType.TARGETED_EDIT.value,
            reason="Empty instruction defaulted to targeted edit",
            is_heuristic=True,
        )

    text_lower = user_instruction.lower().strip()
    forbidden_terms = extract_topic_transition_terms(user_instruction, current_code)

    # 1. Check Full Document Expansion Heuristics (e.g. "add more content", "expand document", "make longer")
    for pattern in EXPANSION_PATTERNS:
        if re.search(pattern, text_lower):
            logger.info(f"Scope classified as FULL_DOCUMENT_EXPANSION via heuristic: '{pattern}'")
            return ScopeClassificationResult(
                scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
                reason=f"Matched full document expansion pattern: '{pattern}'",
                confidence=0.95,
                is_heuristic=True,
                forbidden_terms=forbidden_terms,
            )

    # 2. Check Full Rewrite Heuristics (e.g. "rewrite entire document", "replace all content", "change topic")
    for pattern in FULL_REWRITE_PATTERNS:
        if re.search(pattern, text_lower):
            logger.info(f"Scope classified as FULL_DOCUMENT_REWRITE via heuristic: '{pattern}'")
            return ScopeClassificationResult(
                scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
                reason=f"Matched full document rewrite pattern: '{pattern}'",
                confidence=0.95,
                is_heuristic=True,
                forbidden_terms=forbidden_terms,
            )

    # 3. Check Targeted Edit Heuristics
    for pattern in TARGETED_PATTERNS:
        if re.search(pattern, text_lower):
            logger.info(f"Scope classified as TARGETED_EDIT via heuristic: '{pattern}'")
            return ScopeClassificationResult(
                scope=ScopeType.TARGETED_EDIT.value,
                reason=f"Matched targeted edit pattern: '{pattern}'",
                confidence=0.90,
                is_heuristic=True,
                forbidden_terms=forbidden_terms,
            )

    # 4. LLM Fallback for Ambiguous Cases
    try:
        classifier_prompt = (
            "You are a LaTeX request scope classifier. Classify the user's editing intent into EXACTLY ONE category:\n"
            "- FULL_DOCUMENT_REWRITE: The user wants to rewrite/replace all or most chapters/sections/slides, "
            "change the entire topic of the document, replace all content with new source material, or perform a full overhaul.\n"
            "- FULL_DOCUMENT_EXPANSION: The user wants to elaborate, expand, add more depth/content/pages, or detail all or multiple chapters/sections "
            "across the document without replacing the entire topic.\n"
            "- TARGETED_EDIT: The user wants to modify, fix, add, or refine a specific section, subsection, slide, equation, "
            "table, typo, metadata field, or single component without expanding the whole document.\n\n"
            f"User Prompt:\n\"{user_instruction}\"\n\n"
            "Respond with ONLY a JSON object with this schema:\n"
            '{"scope": "FULL_DOCUMENT_REWRITE" | "FULL_DOCUMENT_EXPANSION" | "TARGETED_EDIT", "confidence": float, "reason": string}'
        )

        target_model = model or provider_router.get_fast_model()
        response = provider_router.chat(
            messages=[{"role": "user", "content": classifier_prompt}],
            model=target_model,
            temperature=0.0,
            max_tokens=256,
            api_keys=api_keys,
        )
        content = response.get("content", "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content).strip()

        data = json.loads(content)
        parsed_scope = data.get("scope", "").upper()
        if parsed_scope in (
            ScopeType.FULL_DOCUMENT_REWRITE.value,
            ScopeType.FULL_DOCUMENT_EXPANSION.value,
            ScopeType.TARGETED_EDIT.value,
        ):
            return ScopeClassificationResult(
                scope=parsed_scope,
                reason=data.get("reason", "Classified by LLM fallback"),
                confidence=float(data.get("confidence", 0.8)),
                is_heuristic=False,
                forbidden_terms=forbidden_terms,
            )
    except Exception as e:
        logger.warning(f"LLM scope classification fallback failed: {e}")

    # Safe default: TARGETED_EDIT
    return ScopeClassificationResult(
        scope=ScopeType.TARGETED_EDIT.value,
        reason="Defaulted to targeted edit after ambiguity evaluation",
        confidence=0.7,
        is_heuristic=True,
        forbidden_terms=forbidden_terms,
    )
