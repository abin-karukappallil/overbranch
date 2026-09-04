"""
test_collections_and_anchors.py — Comprehensive tests for:
1. Shape-based collection matching without literal title overlap (Bug A).
2. Explicit title matching signal preserved.
3. Ambiguous collection clarification path.
4. Anchored relative insertion detection and resolve_anchor_target precision (Bug B).
5. Generic section pair insertion (Conclusion -> Future Scope, Introduction -> Related Work).
6. Content hash immutability check verifying anchor remains 100% byte-for-byte untouched.
7. Validator rejection and auto-repair for altered/duplicated anchor and wrong offset.
"""
import pytest
import hashlib
from backend.document_index import (
    parse_document_structure,
    detect_collections,
    resolve_collection,
    resolve_collection_with_candidates,
    classify_content_shape,
    get_collection_shape_signature,
    compute_next_ordinal,
    is_anchored_insert_instruction,
    parse_anchored_insert_instruction,
    resolve_anchor_target,
    CONTENT_SHAPE_PAPER,
    CONTENT_SHAPE_BIBITEM,
    CONTENT_SHAPE_LIST_ITEM,
    CONTENT_SHAPE_TABLE_ROW,
)
from backend.edit_validator import (
    validate_edit,
    auto_repair_edits,
    validate_anchor_integrity,
)


# ── Sample LaTeX documents ──────────────────────────────────────────────────

LITERATURE_SURVEY_7_PAPERS_BEAMER = r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Introduction}
Welcome to our presentation.
\end{frame}
\begin{frame}{Literature Survey (1/7)}
\textbf{Title:} Attention Is All You Need\\
\textbf{Authors:} Vaswani et al.\\
\textbf{Method:} Transformer\\
\textbf{Year:} 2017
\end{frame}
\begin{frame}{Literature Survey (2/7)}
\textbf{Title:} BERT: Pre-training of Deep Bidirectional Transformers\\
\textbf{Authors:} Devlin et al.\\
\textbf{Method:} Masked LM\\
\textbf{Year:} 2018
\end{frame}
\begin{frame}{Literature Survey (3/7)}
\textbf{Title:} GPT-3: Language Models are Few-Shot Learners\\
\textbf{Authors:} Brown et al.\\
\textbf{Method:} Autoregressive LM\\
\textbf{Year:} 2020
\end{frame}
\begin{frame}{Literature Survey (4/7)}
\textbf{Title:} LLaMA: Open and Efficient Foundation Language Models\\
\textbf{Authors:} Touvron et al.\\
\textbf{Method:} Pretrained Transformer\\
\textbf{Year:} 2023
\end{frame}
\begin{frame}{Literature Survey (5/7)}
\textbf{Title:} Deep Residual Learning for Image Recognition\\
\textbf{Authors:} He et al.\\
\textbf{Method:} ResNet\\
\textbf{Year:} 2016
\end{frame}
\begin{frame}{Literature Survey (6/7)}
\textbf{Title:} Denoising Diffusion Probabilistic Models\\
\textbf{Authors:} Ho et al.\\
\textbf{Method:} Diffusion Models\\
\textbf{Year:} 2020
\end{frame}
\begin{frame}{Literature Survey (7/7)}
\textbf{Title:} High-Resolution Image Synthesis with Latent Diffusion\\
\textbf{Authors:} Rombach et al.\\
\textbf{Method:} Latent Diffusion\\
\textbf{Year:} 2022
\end{frame}
\begin{frame}{Conclusion}
Summary of survey and future outlook.
\end{frame}
\end{document}
"""

ARTICLE_DOCUMENT = r"""\documentclass{article}
\begin{document}
\section{Introduction}
This paper explores autonomous coding assistants.
\section{Methodology}
We evaluate several agent architectures across benchmarks.
\section{Results}
Our system achieves 95% compilation accuracy.
\section{Conclusion}
In conclusion, the proposed system demonstrates superior performance.
\end{document}
"""

AMBIGUOUS_MULTI_COLLECTION_BEAMER = r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Computer Vision Survey (1/2)}
\textbf{Title:} ResNet Architecture\\
\textbf{Authors:} He et al.\\
\textbf{Method:} Residual blocks
\end{frame}
\begin{frame}{Computer Vision Survey (2/2)}
\textbf{Title:} Vision Transformer\\
\textbf{Authors:} Dosovitskiy et al.\\
\textbf{Method:} Self-attention
\end{frame}
\begin{frame}{NLP Survey (1/2)}
\textbf{Title:} Transformer Model\\
\textbf{Authors:} Vaswani et al.\\
\textbf{Method:} Attention mechanism
\end{frame}
\begin{frame}{NLP Survey (2/2)}
\textbf{Title:} BERT\\
\textbf{Authors:} Devlin et al.\\
\textbf{Method:} Masked language modeling
\end{frame}
\end{document}
"""


# ── Tests for Bug A: Shape-based Collection Matching ────────────────────────

def test_shape_based_collection_matching_without_literal_title():
    """
    Acceptance Criteria 1:
    'add xai ieee paper' (with no mention of 'literature survey') correctly appends
    to the literature-survey collection, with 7 existing entries intact.
    """
    doc = parse_document_structure(LITERATURE_SURVEY_7_PAPERS_BEAMER)
    collections = detect_collections(doc, LITERATURE_SURVEY_7_PAPERS_BEAMER)
    assert len(collections) >= 1

    coll = resolve_collection(doc, LITERATURE_SURVEY_7_PAPERS_BEAMER, "add xai ieee paper")
    assert coll is not None, "resolve_collection failed without literal title phrase"
    assert coll.parent_title == "Literature Survey"
    assert coll.current_count == 7

    # Check next ordinal is 8
    next_ord, next_label = compute_next_ordinal(coll)
    assert next_ord == 8
    assert "8" in next_label

    # Verify zero changes to existing entries when appended after last member
    new_paper_frame = (
        r"\begin{frame}{Literature Survey (8/8)}" "\n"
        r"\textbf{Title:} Explainable AI for Healthcare in IEEE Transactions" "\n"
        r"\textbf{Authors:} Doe et al." "\n"
        r"\textbf{Method:} SHAP Analysis" "\n"
        r"\end{frame}"
    )

    insertion_offset = coll.last_member_end_offset
    modified_doc = (
        LITERATURE_SURVEY_7_PAPERS_BEAMER[:insertion_offset]
        + "\n\n"
        + new_paper_frame
        + LITERATURE_SURVEY_7_PAPERS_BEAMER[insertion_offset:]
    )

    # Verify all 7 original papers remain byte-for-byte identical
    for start, end in coll.member_offsets:
        original_slice = LITERATURE_SURVEY_7_PAPERS_BEAMER[start:end]
        assert original_slice in modified_doc, f"Original member at [{start}:{end}] was corrupted"


def test_explicit_literal_match_signal_still_works():
    """
    Acceptance Criteria 2:
    The same instruction phrased with the section named explicitly
    ('add xai ieee paper to the literature survey') still works.
    """
    doc = parse_document_structure(LITERATURE_SURVEY_7_PAPERS_BEAMER)
    coll = resolve_collection(
        doc,
        LITERATURE_SURVEY_7_PAPERS_BEAMER,
        "add xai ieee paper to the literature survey",
    )
    assert coll is not None
    assert coll.parent_title == "Literature Survey"
    assert coll.current_count == 7


def test_ambiguous_collection_clarification_path():
    """
    Acceptance Criteria 6 (part 2):
    When multiple collections match the shape equally plausibly, surface clarification
    candidates rather than guessing silently.
    """
    doc = parse_document_structure(AMBIGUOUS_MULTI_COLLECTION_BEAMER)
    collections = detect_collections(doc, AMBIGUOUS_MULTI_COLLECTION_BEAMER)
    assert len(collections) == 2

    # Instruction does not name either "computer vision" or "nlp", just "add new paper"
    best_match, is_ambiguous, candidates = resolve_collection_with_candidates(
        doc,
        AMBIGUOUS_MULTI_COLLECTION_BEAMER,
        "add a new deep learning paper",
    )

    assert is_ambiguous is True, "Expected ambiguous resolution when two survey collections match equally"
    assert best_match is None, "Should not silently guess a collection when ambiguous"
    assert len(candidates) == 2, f"Expected 2 candidate collections, got {len(candidates)}"
    candidate_titles = {c.parent_title for c in candidates}
    assert "Computer Vision Survey" in candidate_titles
    assert "NLP Survey" in candidate_titles


def test_classify_content_shape():
    """Verify content shape classification detects paper, bibitem, list, and table shapes."""
    assert classify_content_shape("add xai ieee paper") == CONTENT_SHAPE_PAPER
    assert classify_content_shape("add another reference") == CONTENT_SHAPE_BIBITEM
    assert classify_content_shape("add a bullet point for scalability") == CONTENT_SHAPE_LIST_ITEM
    assert classify_content_shape("add a new table row with results") == CONTENT_SHAPE_TABLE_ROW


# ── Tests for Bug B: Anchored Relative Insertion ───────────────────────────

def test_is_anchored_insert_instruction():
    """Verify detection of anchored relative insertion phrasing."""
    assert is_anchored_insert_instruction("add a future scope section after conclusion") is True
    assert is_anchored_insert_instruction("insert related work before methodology") is True
    assert is_anchored_insert_instruction("after conclusion, add a future scope section") is True
    assert is_anchored_insert_instruction("insert X following the Y section") is True
    assert is_anchored_insert_instruction("edit conclusion section") is False
    assert is_anchored_insert_instruction("add xai ieee paper") is False


def test_parse_anchored_insert_instruction():
    """Verify parsing extracts new content description, position, and anchor description."""
    parsed1 = parse_anchored_insert_instruction("add a future scope section after conclusion")
    assert parsed1 is not None
    content, pos, anchor = parsed1
    assert "future scope" in content.lower()
    assert pos == "after"
    assert anchor.lower() == "conclusion"

    parsed2 = parse_anchored_insert_instruction("insert related work before methodology")
    assert parsed2 is not None
    content, pos, anchor = parsed2
    assert "related work" in content.lower()
    assert pos == "before"
    assert anchor.lower() == "methodology"

    parsed3 = parse_anchored_insert_instruction("after conclusion, add a future scope section")
    assert parsed3 is not None
    content, pos, anchor = parsed3
    assert "future scope" in content.lower()
    assert pos == "after"
    assert anchor.lower() == "conclusion"


def test_resolve_anchor_target_precision():
    """
    Acceptance Criteria 6 (part 3):
    resolve_anchor_target precisely locates the anchor section, boundaries, and content hash.
    """
    doc = parse_document_structure(ARTICLE_DOCUMENT)

    # Target "conclusion"
    anchor = resolve_anchor_target(doc, "conclusion")
    assert anchor is not None
    assert anchor.title == "Conclusion"
    assert anchor.start_offset > 0
    assert anchor.end_offset > anchor.start_offset

    expected_text = ARTICLE_DOCUMENT[anchor.start_offset:anchor.end_offset]
    assert "\\section{Conclusion}" in expected_text
    expected_hash = hashlib.sha256(expected_text.strip().encode("utf-8")).hexdigest()[:16]
    assert anchor.content_hash == expected_hash

    # Target "the introduction section"
    anchor_intro = resolve_anchor_target(doc, "the introduction section")
    assert anchor_intro is not None
    assert anchor_intro.title == "Introduction"


def test_anchored_insert_conclusion_future_scope_hash_preserved():
    """
    Acceptance Criteria 3:
    'add a future scope section after conclusion' results in:
    the existing Conclusion section byte-for-byte unchanged (verified via content hash before/after),
    and a new Future Scope section inserted immediately after it.
    """
    doc = parse_document_structure(ARTICLE_DOCUMENT)
    anchor = resolve_anchor_target(doc, "conclusion")
    assert anchor is not None

    hash_before = anchor.content_hash
    anchor_text_before = ARTICLE_DOCUMENT[anchor.start_offset:anchor.end_offset]

    future_scope_content = "\\section{Future Scope}\nWe plan to extend the agent with live compiler feedback."
    insertion_offset = anchor.end_offset  # Position 'after'

    modified_doc = (
        ARTICLE_DOCUMENT[:insertion_offset]
        + "\n\n"
        + future_scope_content
        + "\n"
        + ARTICLE_DOCUMENT[insertion_offset:]
    )

    # 1. Check anchor text in modified doc is byte-for-byte identical
    anchor_text_after = modified_doc[anchor.start_offset:anchor.end_offset]
    assert anchor_text_after == anchor_text_before
    hash_after = hashlib.sha256(anchor_text_after.strip().encode("utf-8")).hexdigest()[:16]
    assert hash_after == hash_before, "Conclusion section hash changed!"

    # 2. Check Future Scope is located directly after Conclusion
    assert modified_doc.find("\\section{Conclusion}") < modified_doc.find("\\section{Future Scope}")
    # 3. Check Conclusion is not duplicated
    assert modified_doc.count("\\section{Conclusion}") == 1


def test_generic_section_pair_insertion():
    """
    Acceptance Criteria 4:
    The anchored-insert mechanism is generic (not hardcoded to Conclusion/Future Scope):
    inserting 'Related Work' after 'Introduction'.
    """
    doc = parse_document_structure(ARTICLE_DOCUMENT)
    anchor = resolve_anchor_target(doc, "introduction")
    assert anchor is not None
    assert anchor.title == "Introduction"

    hash_before = anchor.content_hash
    related_work_content = "\\section{Related Work}\nPrior literature in automated LaTeX editing."
    insertion_offset = anchor.end_offset

    modified_doc = (
        ARTICLE_DOCUMENT[:insertion_offset]
        + "\n\n"
        + related_work_content
        + "\n"
        + ARTICLE_DOCUMENT[insertion_offset:]
    )

    # Verify Introduction remains untouched
    anchor_text_after = modified_doc[anchor.start_offset:anchor.end_offset]
    hash_after = hashlib.sha256(anchor_text_after.strip().encode("utf-8")).hexdigest()[:16]
    assert hash_after == hash_before

    # Verify Related Work appears before Methodology and after Introduction
    intro_pos = modified_doc.find("\\section{Introduction}")
    rel_pos = modified_doc.find("\\section{Related Work}")
    method_pos = modified_doc.find("\\section{Methodology}")
    assert intro_pos < rel_pos < method_pos, "Related Work not inserted between Introduction and Methodology"


def test_validator_rejects_altered_or_duplicated_anchor():
    """
    Acceptance Criteria 5:
    edit_validator.py correctly rejects when:
    1. The anchor section is altered or duplicated.
    2. The new content lands at the wrong offset.
    And auto_repair corrects fixable issues.
    """
    doc = parse_document_structure(ARTICLE_DOCUMENT)
    anchor = resolve_anchor_target(doc, "conclusion")
    assert anchor is not None

    # Case 1: Wrong offset
    bad_offset_edit = {
        "action": "insert_relative",
        "anchor_page_id": anchor.page_id,
        "position": "after",
        "insertion_offset": 5,  # Wrong offset!
        "original_chunk": "",
        "proposed_chunk": "\\section{Future Scope}\nSome text.",
        "explanation": "Added Future Scope",
    }
    val_res = validate_edit(
        original_code=ARTICLE_DOCUMENT,
        proposed_edits=[bad_offset_edit],
        anchor_target=anchor,
        expected_position="after",
    )
    assert val_res.passed is False
    assert any("does not match expected anchor boundary" in i.message for i in val_res.issues)

    # Case 2: Proposed chunk duplicates anchor section heading/content
    duplicate_edit = {
        "action": "insert_relative",
        "anchor_page_id": anchor.page_id,
        "position": "after",
        "insertion_offset": anchor.end_offset,
        "original_chunk": "",
        "proposed_chunk": "\\section{Conclusion}\nDuplicated conclusion.\n\\section{Future Scope}\nNew text.",
        "explanation": "Added Future Scope",
    }
    val_res2 = validate_edit(
        original_code=ARTICLE_DOCUMENT,
        proposed_edits=[duplicate_edit],
        anchor_target=anchor,
        expected_position="after",
    )
    assert val_res2.passed is False
    assert any("re-emits anchor heading" in i.message or "duplicates anchor" in i.message for i in val_res2.issues)

    # Case 3: Auto-repair repairs the re-emitted anchor heading
    repaired_edits, repairs = auto_repair_edits(
        proposed_edits=[duplicate_edit],
        original_code=ARTICLE_DOCUMENT,
        anchor_target=anchor,
        expected_position="after",
    )
    assert len(repairs) >= 1
    val_res3 = validate_edit(
        original_code=ARTICLE_DOCUMENT,
        proposed_edits=repaired_edits,
        anchor_target=anchor,
        expected_position="after",
    )
    assert val_res3.passed is True
