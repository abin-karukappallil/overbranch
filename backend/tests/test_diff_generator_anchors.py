"""
test_diff_generator_anchors.py — the apply contract for AI edit items.

Guards the contract documented in ``opencode/diff_generator.py``: every emitted
edit item must have a non-empty, unique, structurally-closed, non-overlapping
anchor, and replaying all of them must reproduce ``proposed_code`` exactly.

Before this contract existed, raw ``difflib`` insert opcodes produced items with
``original_chunk == ""`` (``i1 == i2``), which the editor silently dropped — so
wrapping a bare ``\\item`` in a new ``itemize`` shipped ``\\begin{itemize}`` and
``\\end{itemize}`` as two separate droppable items and left unbalanced LaTeX in
the user's document.

``replay_edit_items`` below is a deliberate mirror of ``lib/latex-edit-apply.ts``.
Because there is no JS test runner in this repo, it is the only automated proof
that the client contract holds; keep the two in step.
"""

from __future__ import annotations

import itertools

import pytest

from edit_validator import validate_latex_pre_commit
from opencode.diff_generator import (
    APPLY_CONTRACT_VERSION,
    _structural_delta,
    compute_edit_items,
    compute_final_diff,
)


# ---------------------------------------------------------------------------
# Python mirror of lib/latex-edit-apply.ts
# ---------------------------------------------------------------------------

def replay_edit_items(original: str, items):
    """Resolve each anchor, reject overlaps, splice descending."""
    if len(items) == 1 and items[0].get("is_full_document"):
        return items[0]["proposed_chunk"], []

    resolved, skipped = [], []
    for it in items:
        anchor = it["original_chunk"]
        if not anchor:
            skipped.append((it, "no-anchor"))
            continue
        first = original.find(anchor)
        if first == -1:
            skipped.append((it, "not-found"))
            continue
        if original.find(anchor, first + 1) != -1:
            skipped.append((it, "not-unique"))
            continue
        resolved.append((first, first + len(anchor), it))

    resolved.sort(key=lambda r: -r[0])
    accepted, out = [], original
    for start, end, it in resolved:
        if any(not (end <= s or start >= e) for s, e, _ in accepted):
            skipped.append((it, "overlap"))
            continue
        accepted.append((start, end, it))
        out = out[:start] + it["proposed_chunk"] + out[end:]
    return out, skipped


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BEAMER_FRAME = "\\begin{frame}{A}\n\\item one\n\\end{frame}\n"
BEAMER_FRAME_WRAPPED = (
    "\\begin{frame}{A}\n\\begin{itemize}\n\\item one\n\\end{itemize}\n\\end{frame}\n"
)


def _deck(titles):
    frames = [
        "\\begin{frame}{%s}\n\\begin{itemize}\n\\item P1 %s\n\\item P2 %s\n"
        "\\end{itemize}\n\\end{frame}\n" % (t, t, t)
        for t in titles
    ]
    return (
        "\\documentclass{beamer}\n\\begin{document}\n"
        + "\n".join(frames)
        + "\\end{document}\n"
    )


_T = ["Topic %d" % i for i in range(40)]
_T_EDITED = list(_T)
_T_EDITED[3] = "Revised 3"
_T_EDITED[17] = "Revised 17"
_T_EDITED[31] = "Revised 31"

# (name, original, modified)
DIFF_CASES = [
    ("insert_mid", "\\begin{document}\na\nb\n\\end{document}\n",
     "\\begin{document}\na\nNEW\nb\n\\end{document}\n"),
    ("insert_bof", "a\nb\n", "NEW\na\nb\n"),
    ("insert_eof", "a\nb\n", "a\nb\nNEW\n"),
    ("pure_delete", "\\begin{document}\na\nDEL\nb\n\\end{document}\n",
     "\\begin{document}\na\nb\n\\end{document}\n"),
    ("replace", "\\begin{document}\nold\n\\end{document}\n",
     "\\begin{document}\nnew\n\\end{document}\n"),
    ("multi_region_small", "\\begin{document}\na\nx\nb\ny\nc\n\\end{document}\n",
     "\\begin{document}\nA\nx\nB\ny\nC\n\\end{document}\n"),
    ("duplicated_block", "\\item z\nQ\n\\item z\nR\n\\item z\n",
     "\\item z\nQ2\n\\item z\nR2\n\\item z\n"),
    ("single_line", "\\documentclass{article}", "\\documentclass{report}"),
    ("wrap_itemize", BEAMER_FRAME, BEAMER_FRAME_WRAPPED),
    ("add_align", "\\begin{document}\np\n\\end{document}\n",
     "\\begin{document}\n\\begin{align}\nx&=1\n\\end{align}\np\n\\end{document}\n"),
    ("nested_itemize", "\\begin{itemize}\n\\item a\n\\end{itemize}\n",
     "\\begin{itemize}\n\\item a\n\\begin{itemize}\n\\item b\n\\end{itemize}\n\\end{itemize}\n"),
    ("realistic_deck", _deck(_T), _deck(_T_EDITED)),
]

CASE_IDS = [c[0] for c in DIFF_CASES]


# ---------------------------------------------------------------------------
# Contract 1 & 2 — non-empty, unique anchors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,original,modified", DIFF_CASES, ids=CASE_IDS)
def test_every_edit_item_has_nonempty_unique_anchor(name, original, modified):
    items = compute_edit_items(original, modified, "x")
    assert items, f"{name}: expected at least one edit item"
    for it in items:
        anchor = it["original_chunk"]
        assert anchor, f"{name}: empty anchor would be dropped by the client"
        assert original.count(anchor) == 1, (
            f"{name}: anchor occurs {original.count(anchor)}x, must be unique"
        )


@pytest.mark.parametrize("name,original,modified", DIFF_CASES, ids=CASE_IDS)
def test_anchor_matches_its_declared_line_range(name, original, modified):
    orig_lines = original.splitlines(keepends=True)
    for it in compute_edit_items(original, modified, "x"):
        a = it["orig_start_line"] - 1
        b = it["orig_end_line"]
        window = "".join(orig_lines[a:b])
        anchor = it["original_chunk"]
        assert window in (anchor, anchor + "\n"), (
            f"{name}: line range {a + 1}-{b} does not match the anchor text"
        )


# ---------------------------------------------------------------------------
# Contract 3 — structural closure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,original,modified", DIFF_CASES, ids=CASE_IDS)
def test_every_item_is_structurally_closed(name, original, modified):
    for it in compute_edit_items(original, modified, "x"):
        assert _structural_delta(it["original_chunk"]) == _structural_delta(
            it["proposed_chunk"]
        ), f"{name}: item changes net environment/brace/math structure on its own"


def test_itemize_wrap_produces_single_structurally_closed_item():
    """The exact bug this contract exists to prevent."""
    items = compute_edit_items(BEAMER_FRAME, BEAMER_FRAME_WRAPPED, "wrap")
    assert len(items) == 1, (
        "a \\begin/\\end pair must never be split across items — "
        f"got {len(items)}: {[i['proposed_chunk'] for i in items]}"
    )
    item = items[0]
    assert "\\begin{itemize}" in item["proposed_chunk"]
    assert "\\end{itemize}" in item["proposed_chunk"]
    assert item["original_chunk"]


# ---------------------------------------------------------------------------
# Contract 4 — non-overlapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,original,modified", DIFF_CASES, ids=CASE_IDS)
def test_items_do_not_overlap(name, original, modified):
    ranges = sorted(
        (it["orig_start_line"], it["orig_end_line"])
        for it in compute_edit_items(original, modified, "x")
    )
    for (s1, e1), (s2, e2) in zip(ranges, ranges[1:]):
        assert s2 > e1, f"{name}: line ranges {s1}-{e1} and {s2}-{e2} overlap"


# ---------------------------------------------------------------------------
# Replay — the core regression test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,original,modified", DIFF_CASES, ids=CASE_IDS)
def test_edit_items_replay_reconstructs_proposed_code(name, original, modified):
    items = compute_edit_items(original, modified, "x")
    result, skipped = replay_edit_items(original, items)
    assert not skipped, f"{name}: client would skip {[s[1] for s in skipped]}"
    assert result == modified, f"{name}: replay did not reproduce proposed_code"


@pytest.mark.parametrize("name,original,modified", DIFF_CASES, ids=CASE_IDS)
def test_any_subset_of_items_remains_valid_latex(name, original, modified):
    """
    The invariant the structural-merge pass exists to provide: a user may accept
    any subset of the proposed edits without breaking the document.

    If someone later splits items more finely for nicer-looking diffs, this test
    is the tripwire — do not weaken it.
    """
    items = compute_edit_items(original, modified, "x")
    if len(items) > 8:
        pytest.skip("too many items to enumerate subsets")

    base_valid, _ = validate_latex_pre_commit(original)
    if not base_valid:
        pytest.skip("fixture is not valid LaTeX to begin with")

    for r in range(len(items) + 1):
        for combo in itertools.combinations(items, r):
            out, _ = replay_edit_items(original, list(combo))
            ok, errors = validate_latex_pre_commit(out)
            assert ok, (
                f"{name}: accepting {r}/{len(items)} edits produced invalid LaTeX: "
                f"{errors[:2]}"
            )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_insertion_at_bof_expands_forward_only():
    items = compute_edit_items("a\nb\n", "NEW\na\nb\n", "x")
    assert items[0]["context_before"] == 0


def test_insertion_at_eof_expands_backward_only():
    items = compute_edit_items("a\nb\n", "a\nb\nNEW\n", "x")
    assert items[-1]["context_after"] == 0


def test_empty_original_emits_full_document_item():
    modified = "\\documentclass{article}\n\\begin{document}\nhi\n\\end{document}\n"
    items = compute_edit_items("", modified, "create")
    assert len(items) == 1
    assert items[0]["is_full_document"] is True
    assert items[0]["anchor_unique"] is False
    assert items[0]["proposed_chunk"] == modified


def test_identical_documents_produce_no_items():
    assert compute_edit_items("same\n", "same\n", "x") == []


def test_full_document_item_is_not_newline_stripped():
    """A whole-document write must be byte-exact, trailing newline included."""
    modified = "\\documentclass{article}\n\\begin{document}\nhi\n\\end{document}\n"
    items = compute_edit_items("", modified, "x")
    assert items[0]["proposed_chunk"].endswith("\n")


# ---------------------------------------------------------------------------
# compute_final_diff payload
# ---------------------------------------------------------------------------

def test_compute_final_diff_includes_hashes_and_contract_version():
    payload = compute_final_diff(BEAMER_FRAME, BEAMER_FRAME_WRAPPED, "main.tex", "x")
    assert payload["apply_contract_version"] == APPLY_CONTRACT_VERSION
    assert len(payload["original_sha256"]) == 64
    assert len(payload["proposed_sha256"]) == 64
    assert payload["original_sha256"] != payload["proposed_sha256"]
    assert payload["proposed_code"] == BEAMER_FRAME_WRAPPED


def test_no_change_payload_still_carries_hashes():
    payload = compute_final_diff(BEAMER_FRAME, BEAMER_FRAME, "main.tex", "")
    assert payload["has_changes"] is False
    assert payload["edits"] == []
    assert payload["original_sha256"] == payload["proposed_sha256"]


def test_large_rewrite_collapses_to_single_full_document_item():
    """A near-total rewrite must not ship edits ~as large as proposed_code."""
    original = _deck(_T)
    modified = _deck(["Totally New %d" % i for i in range(40)])
    payload = compute_final_diff(original, modified, "main.tex", "x")
    assert len(payload["edits"]) == 1
    assert payload["edits"][0]["is_full_document"] is True
