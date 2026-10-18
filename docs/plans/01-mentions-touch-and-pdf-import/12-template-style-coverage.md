# 01/12 — Map coloured, bold and italic runs onto the semantic styles

Plan folder: [`00-README.md`](00-README.md) · Model: Opus · Prerequisites: 01/07 · Parallel with: 01/11 (frontend only). Added after acceptance row 15 failed.

## Why this slice exists
Acceptance row 15 FAILED on the real use case. On the user's own lecturer template
("Seminar Report - Report Format.pdf") template mode emits **435 body lines with inline `\fontsize`
against only 101 `\obBodyFont` uses**. The synthetic test PDF emits 0, which is why the unit tests pass.

Root cause, confirmed in `backend/pdf2latex/preamble.py:428-445`:

```python
if (abs(size - profile.body_size_pt) < 0.5 and not bold and not italic
        and family == _family(profile.body_font) and color == default_color):
    return "body"
```

A run that differs from the body style **only** in colour, weight or slant returns `None` and falls
back to a full inline `\fontsize{…}\selectfont\rmfamily\bfseries`. On the real document that is the
majority of runs: 107 at body size and font but blue (#0000FF), 50 bold and 46 italic at 12bp.
M13 wants those set with the semantic command plus a modifier, so a student can restyle the document
by editing the preamble. That is the whole point of template mode.

## Decisions you need
M13 (template mode and the semantic preamble) — run `grep -E '^\| M13 ' 00-README.md`.

Slice 07's `## Result` in `07-template-mode.md` documents `style_role`, `style_block`, `page_facts`,
`fallback_body` and the `st` facts key. Read it before changing any of them.

## Read first
- `backend/pdf2latex/preamble.py` — `style_role` (:428-445), `_font_switch` (:452), `style_block`, `HEADING_COMMANDS` (:185), and the `\obBodyFont` / `\obHeadingI..III` definitions (~:491-498).
- `backend/pdf2latex/facts.py` — `page_facts(..., profile=None)` and `fallback_body(..., profile=None, default_color="")`, specifically where a run gets `st` instead of `sz/c/b/i/f`, and where `font={...}` is built for the TikZ layout fallback.
- `backend/pdf2latex/prompts.py` — `TEMPLATE_PAGE_SYSTEM_PROMPT` and the documented `st` key, which you are extending.
- `backend/tests/test_pdf2latex_template_mode.py` — all 25 tests must keep passing.

## Tasks

1. **Extend the role to carry modifiers.** Change `style_role` to return a small structure (a dataclass or a tuple — your call, but name it clearly) of `(role, bold, italic, color)` where:
   - a run matches **`body`** when its size is within 0.5pt of `body_size_pt` **and** its family matches, *regardless of* bold, italic or colour;
   - a run matches a **heading level** when size and family match that level, regardless of colour and with bold/italic carried as modifiers;
   - `None` only when size or family genuinely differ from every style.
   Keep the existing 0.5pt tolerance and `_family` comparison.

2. **Compose instead of inlining.** Where a matched run is emitted, build the semantic command plus only the modifiers that differ from the style's own definition:
   - bold that the style lacks → append `\bfseries`; italic → `\itshape`;
   - a colour differing from the style's colour → wrap in `\textcolor{<name>}{…}` using the existing colour-name machinery (`color_name`, `collect_colors`), **not** a raw `\color{...}` redefinition;
   - a run identical to the style emits the bare command, exactly as today.
   The result for a blue bold body run should read like `{\obBodyFont\bfseries\textcolor{obcolorN}{…}}`, never a `\fontsize`.

3. **Keep the two consumers in step.** Both `page_facts` (the `st` key given to the LLM) and `fallback_body` (the deterministic TikZ layout, which uses `font={...}`) must use the new composition. The layout fallback is what produced the 435 inline uses on the real document, so verify your change there specifically.

4. **Document the `st` key.** Update `TEMPLATE_PAGE_SYSTEM_PROMPT` in `prompts.py` so the model knows `st` may now carry modifiers, and that it should use the command plus modifier rather than inline sizing. Keep `PAGE_SYSTEM_PROMPT` (exact mode) untouched.

5. **Exact mode stays frozen.** `mode="exact"` must remain byte-for-byte identical. `test_exact_preamble_is_unchanged` and the fidelity suite are the guards.

6. **Tests.** Extend `backend/tests/test_pdf2latex_template_mode.py`:
   - a body-size run in a non-body colour maps to `body` + `\textcolor`, with **no** `\fontsize`;
   - a body-size **bold** run maps to `body` + `\bfseries`, no `\fontsize`;
   - a body-size **italic** run maps to `body` + `\itshape`;
   - a bold **and** coloured body run composes both;
   - a run at a genuinely different size still returns `None` and keeps inline `\fontsize` (the escape hatch must survive);
   - a heading-size run in an unexpected colour maps to that heading plus `\textcolor`;
   - `fallback_body` produces `font={\obBodyFont...}` rather than `font={\fontsize...}` for all of the above;
   - exact mode output is unchanged (keep the existing literal-preamble pin).

7. **Prove it on the real document.** The user's template is already in the repo. Find it under `uploads/` (the acceptance run used "Seminar Report - Report Format.pdf"; `find uploads -name '*.pdf' | grep -i seminar` locates it, and previous job directories are under `uploads/pdf2latex_jobs/`). Run it through template mode with the LLM off and report the before/after counts of inline `\fontsize` versus `\obBodyFont` in your `## Result`. The target is that `\fontsize` on body-size runs becomes a small minority; state the number you actually reach rather than claiming success.

## Done when
- The new tests pass and all 25 pre-existing tests in `test_pdf2latex_template_mode.py` still pass.
- `tools/verify-slice.sh backend/tests/test_pdf2latex_template_mode.py` passes.
- `cd backend && .venv/bin/python -m pytest tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py tests/test_pdf2latex_jobs.py tests/test_pdf2latex_mode_wiring.py -q` passes (106 tests today).
- Your `## Result` reports the real-document before/after counts from Task 7.

## Result

- `backend/pdf2latex/preamble.py`: added `ROLE_COMMANDS` and a frozen `StyleMatch(role, bold, italic, color)` dataclass. A modifier set to `None` means "as the style". `bold`/`italic` True/False give `\bfseries`/`\mdseries` and `\itshape`/`\upshape`, and `color` is a preamble colour name applied with `\textcolor`. Its helpers are `font()`, `wrap()`, `latex()` and `plain`. `style_role` now returns `Optional[StyleMatch]`: size (within 0.5pt) and `_family` decide the style, while weight, slant and colour become modifiers. When several styles share a size and family, the one that needs the fewest modifiers wins, with body first on a tie. It returns `None` only when the size or family differs from every style.
- `backend/pdf2latex/facts.py`: in `page_facts`, a matched run carries `st` plus `b`/`i`/`c` only where it differs from the style (it never has `sz`/`f`). In `fallback_body` (the TikZ layout), a matched run gets `font={<command><weight/slant modifiers>}`, and a colour modifier goes on the text as `\textcolor{name}{...}`, because a heading command's own `\color` would override `text=`. The dead `_ROLE_FONT` was removed.
- `backend/pdf2latex/prompts.py`: in `TEMPLATE_PAGE_SYSTEM_PROMPT`, rule 3, rule 3b and the `st` facts note now say that `st` may carry `b`/`i`/`c` modifiers and must be written as command + modifier, never `\fontsize`. `PAGE_SYSTEM_PROMPT` is untouched (the diff has insertions only).
- `backend/tests/test_pdf2latex_template_mode.py`: 7 new tests, 32 in total. They cover: colour, bold, italic and bold+colour body runs mapping to `body` + modifiers; the 8pt, 11.6pt and mono escape hatch still returning `None`; a red bold 16pt run mapping to H2 + `\textcolor`; a regular 16pt run mapping to H2 + `\mdseries`; StyleMatch composition (`{\obBodyFont\bfseries\textcolor{c0000FF}{x}}`); the fewest-modifiers tie-break; the `st` facts; `fallback_body` writing `font={\obBodyFont...}` with no `\fontsize` for every case; exact-mode layout and facts staying inline for the same runs; and a real pdflatex compile that checks the red heading really comes out red (#FF0000).

Gate (`tools/verify-slice.sh backend/tests/test_pdf2latex_template_mode.py`):
```
PASS  typecheck
PASS  pytest tests/test_pdf2latex_template_mode.py
```
`pytest tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py tests/test_pdf2latex_jobs.py tests/test_pdf2latex_mode_wiring.py -q`: 81 passed. That is every test those four files collect; the "106" figure is these 81 plus the 25 old template-mode tests. Full backend suite: 816 passed, 6 failed, which are exactly the baseline failures (1 in `test_compile_gate_truth.py`, 5 in `test_provider_fallback.py`).

Real document (Task 7): "Seminar Report - Report Format.pdf" (`uploads/pdf2latex_jobs/8f02d2f0b10843ef8009fed3a1a27cfb/input.pdf`, 15 pages), run with `run_conversion(mode="template")`, the LLM off and real pdflatex. Output went to the scratchpad; `uploads/` was read only.

| template mode, body of main.tex | before | after |
|---|---|---|
| lines with inline `\fontsize` | 435 | **205** |
| of which at the 12bp body size | 212 | **0** |
| `\obBodyFont` uses | 101 | **313** (217 bare, 50 `\bfseries`, 46 `\itshape`) |
| `\obHeading*` uses | 11 | 29 |
| compiled | yes | yes |

- The rendered output is pixel-identical before and after on all 15 pages at 50 dpi: the blue and red runs are still blue and red.
- Exact mode on the same PDF is byte-identical to the acceptance run's exact output (job 74761446) after normalising the `pdf_<job8>` asset dir. It has 547 inline `\fontsize`.

The remaining 205 inline uses are all at sizes that really are different, which this slice deliberately leaves inline: 113 at 10bp, 40 at 12.5bp (0.5pt off the 12bp body, at the tolerance edge), 39 at 11bp and 13 at 7–8bp or 11.5bp. So inline `\fontsize` on body-size runs dropped to zero, but overall it is still about 37% of styled runs (205 against 342 semantic uses). Bringing the 10bp group (probably the template's small-print or instruction style) under a semantic command would need a fourth style in the profile and preamble. M13 does not define one, so that is left as a follow-up decision.
