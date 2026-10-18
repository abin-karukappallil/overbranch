# 01/07 — PDF→LaTeX template mode and rule detection

Plan folder: [`00-README.md`](00-README.md) · Model: Opus · Prerequisites: 01/05 · Parallel with: 01/02, 01/03 (frontend), 01/06 (`main.py`, `compiler.py`, `compile_queue.py`). **`routes/pdf_convert.py` belongs to slice 05 — see Task 1.**

## Decisions you need
M13 (template mode and `StyleProfile`), M14 (template-rule detection), M15 (asset parity) — run `grep -E '^\| M1(3|4|5) ' 00-README.md`.

Slice 05 added a `resume` parameter to the pipeline entry point and a done-page skip in the per-page loop. Read its `### For slice 07` note in `05-job-durability.md`'s `## Result` and build on that code rather than reverting it.

## Read first
- `backend/pdf2latex/extract.py` — `_extract_lines` at :129 (spans already carry font name, size, exact RGB, flags, bbox and baseline — this is the data the whole slice rests on), `extract_document` at :570, `_extract_images` at :475, `_rasterize_vector_art` at :529, `_is_scanned` at :513.
- `backend/pdf2latex/fontmap.py` — `font_class`, `span_weight`, `descriptor_bold_fonts`, `outline_stroke_bold`.
- `backend/pdf2latex/preamble.py` — `page_geometry` at :53, `collect_colors` at :69, `plan_fonts` at :88, `build_preamble` at :112.
- `backend/pdf2latex/models.py` — `Span`, `Line`, `PageExtract`.
- `backend/pdf2latex/prompts.py` — `PAGE_SYSTEM_PROMPT` and `page_user_prompt` at :100, and the documented `lines[]` keys `sz/c/f/b/i`.
- `backend/pdf2latex/llm.py` — `complete()` at :84. **It sends a page PNG today; your M14 detection call must be text-only** — the Web2API gateway rejects image parts (`CLAUDE.md`).
- `backend/pdf2latex/pipeline.py` — `_generate` :289, `_compile_page` :325, `_fallbacks` :358, `_polish` :404, `_process_page` :467, the merged compile ~:598, the `asyncio.gather` under a semaphore at :665, and the exception path at :620-695.
- `backend/tests/test_pdf2latex_fidelity.py` and `backend/tests/pdf2latex_fixtures.py` — the fixtures and assertions that **must stay green**.

## Scope (files you own)
- `backend/pdf2latex/pipeline.py`
- `backend/pdf2latex/extract.py`
- `backend/pdf2latex/fontmap.py`
- `backend/pdf2latex/preamble.py`
- `backend/pdf2latex/prompts.py`
- `backend/pdf2latex/models.py`
- `backend/pdf2latex/facts.py`
- `backend/pdf2latex/llm.py`
- `backend/tests/test_pdf2latex_template_mode.py` (new)

## Tasks

1. **Mode plumbing.** The pipeline entry point gains `mode: str = "exact"`. The HTTP field on `POST /api/convert/pdf` belongs to slice 05's file (`routes/pdf_convert.py`), which you do **not** own: state the exact parameter name and default in your `## Result` under `### For slice 08`, and the orchestrator will have slice 08 pass it from the dialog. If the route does not yet forward `mode`, your pipeline must still default cleanly to `"exact"`.
   **`mode="exact"` must be byte-for-byte today's behaviour.** `test_pdf2latex_fidelity.py` is the guard; it stays green.

2. **`StyleProfile` (M13).** Add to `models.py`:
   ```python
   @dataclass
   class HeadingStyle:
       name: str; font: str; size_pt: float; bold: bool; italic: bool
       color: str; spacing_before_pt: float

   @dataclass
   class StyleProfile:
       body_font: str; body_size_pt: float; line_spacing: float
       margins_mm: dict           # {"top","bottom","left","right"}
       colors: list               # ["#rrggbb", ...]
       heading_levels: list       # [HeadingStyle, ...]
       source: str = "measured"   # or "stated" / "merged" (M14)
   ```

3. **Derive the profile.** Write `build_style_profile(pages: list[PageExtract]) -> StyleProfile` in `preamble.py`, from data `extract.py` already captures — do not add a new extraction pass:
   - **body font/size**: the modal (font, rounded size) pair weighted by character count across all pages;
   - **headings**: cluster spans whose size exceeds the body size by ≥1pt or whose `font_class`/`span_weight` marks them bold; order the clusters by descending size and take at most **3** levels, named `H1`/`H2`/`H3`; `spacing_before_pt` is the median gap above a line in that cluster;
   - **margins**: reuse `page_geometry` (:53), converting to mm;
   - **colors**: reuse `collect_colors` (:69), deduplicated, most-used first;
   - **line_spacing**: the median baseline-to-baseline distance within a paragraph, divided by the body size.
   Pure and deterministic — no LLM, no I/O — so it is unit-testable against a synthetic `PageExtract`.

4. **Semantic preamble (M13).** Extend `build_preamble` (:112) with a `profile: StyleProfile | None` argument. When given, emit a **commented** block defining `\obBodyFont`, `\obHeadingI`, `\obHeadingII`, `\obHeadingIII` and `\obAccentColor`, plus `geometry` margins and the line spacing, with one comment line per definition saying what it was derived from (measured, or stated per M14) so a student can see what to change. In template mode the page bodies must use these commands; they must **not** emit per-span inline `\fontsize`/`\color` for text matching the body or a heading style. Inline formatting is still correct for genuinely one-off spans.

5. **Prompt changes (M13).** Add a template-mode variant to `prompts.py`. It instructs the model to use the semantic commands for body and heading text and to reserve inline formatting for exceptions, and it receives the `StyleProfile` through `facts.py` alongside the existing `lines[]` facts. Keep the exact-mode prompt unchanged.

6. **Template-rule detection (M14).** Add `detect_template_rules(page_texts: list[str]) -> dict | None`, calling `llm.complete()` over the **text of the first ≤3 pages only** — **text-only, no image part.** Ask for strict JSON `{"is_template": bool, "rules": {...}, "evidence": [str]}`, where `rules` is a `StyleProfile` subset (any of `body_font`, `body_size_pt`, `line_spacing`, `margins_mm`, `heading_levels`). Parse defensively: a non-JSON reply, a missing key or a failed call logs a warning and returns `None` — **it must never fail the job.** When `is_template` is true, merge: **stated rules override measured values**, set `profile.source = "merged"`, and store the whole result at `report["template_rules"]`. Run it once per job, not per page.

7. **Asset parity (M15).** Template mode reuses `_extract_images` (:475), `_rasterize_vector_art` (:529) and the same `assets/pdf_<job8>/` output path with no change to `storage.write_output_to_project`. Changing the asset path or count is a failure of this slice.

8. **`backend/tests/test_pdf2latex_template_mode.py`.** Pytest, no live LLM (stub `llm.complete`). Cover:
   - `build_style_profile` on a synthetic `PageExtract` returns the expected modal body font/size and orders heading levels by descending size, capped at 3;
   - `build_preamble(profile=...)` emits `\obBodyFont` and `\obHeadingI`, and a body paragraph renders via the command with no inline `\fontsize`;
   - `build_preamble(profile=None)` output is **identical** to today's for the same input (the exact-mode guard);
   - `detect_template_rules` returns `None` for a non-JSON reply, for a reply missing `is_template`, and when `complete()` raises;
   - a stated `{"body_size_pt": 12, "body_font": "Times New Roman"}` overrides a measured 11pt Arial and sets `source == "merged"`;
   - the detection call's payload contains **no image part** (assert on what the stub received);
   - mode defaults to `"exact"` when not supplied.

## Done when
- `tools/verify-slice.sh backend/tests/test_pdf2latex_template_mode.py` passes.
- `cd backend && pytest tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py -v` passes unchanged (or skips cleanly with no TeX engine) — exact mode must not move.
- `cd backend && pytest tests/test_provider_fallback.py -v` still passes.
- Append `## Result`, with the `### For slice 08` note from Task 1 naming the request field and its default.

## Result

- `backend/pdf2latex/models.py`: added `HeadingStyle` and `StyleProfile` with the M13 fields, plus `stated_fields` (default `[]`) so the preamble comments can say which values were stated. `ConversionReport` gained `template_rules` and `style_profile`. Both are `None` by default, and `to_dict()` drops them when unset, so the exact-mode report has the same keys as before.
- `backend/pdf2latex/preamble.py`: added `build_style_profile(pages)` (pure), `clean_template_rules`, `merge_template_rules` (stated values override measured ones, `source="merged"`), `template_geometry`, `template_fonts`, `style_role` and `style_block`. `build_preamble(..., profile=None)` is unchanged when `profile` is None. When given a profile it writes the margins in mm under a comment line, adds the commented block (`\obBodyFont`, `\obHeadingI..III`, `\obAccentColor`, one comment per definition saying "measured from the PDF" or "stated in the document"), and uses `\AtBeginDocument{\obBodyFont}`.
- `backend/pdf2latex/facts.py`: `page_facts(..., profile=None)`. With a profile, a run that matches the body or a heading style gets `st` instead of `sz/c/b/i/f`, a body line's `gap` uses the document's own leading, and `facts["style"]` lists the commands. `fallback_body(..., profile=None, default_color="")` uses `font={\obBodyFont}` / `{\obHeadingI}` for runs that match. One-off runs keep inline `\fontsize`.
- `backend/pdf2latex/prompts.py`: added `TEMPLATE_PAGE_SYSTEM_PROMPT`, built from `PAGE_SYSTEM_PROMPT` by swapping rules 3 and 3b and adding a note about the `st` key; import-time asserts check the source text it replaces. Also added `TEMPLATE_RULES_SYSTEM` / `TEMPLATE_RULES_USER`. `PAGE_SYSTEM_PROMPT` itself is unchanged.
- `backend/pdf2latex/llm.py`: added `async detect_template_rules(page_texts) -> dict | None`. It makes one `complete(system, user, None, ...)` call over the first 3 pages or fewer (at most 6000 characters each). The call is text-only: no image part ever reaches the provider. It parses fenced or embedded JSON and requires a boolean `is_template`. On any failure it logs a warning and returns None, and it never raises (except on cancellation).
- `backend/pdf2latex/pipeline.py`: built on slice 05's `resume` code without reverting it. `run_conversion(..., resume=False, mode="exact")`, with `MODES = ("exact", "template")`. An unknown mode logs a warning and runs as exact. A resumed job keeps the `mode` recorded in its state. `_template_style` runs once per job: it measures the profile, runs detection once (on resume it reuses the stored `template_rules` and does not call again), merges, and builds the semantic preamble. `Ctx.style` holds the measured profile, which decides which runs match a style. The `_layout()` helper replaces the four `fallback_body` calls, and `_generate` picks the template prompt. Template mode writes `mode` and `template_rules` to the job state; exact mode writes nothing new. Asset extraction and paths are untouched (M15).
- `backend/tests/test_pdf2latex_template_mode.py` (new, gitignored as expected): 25 tests. Every case listed in Task 8 is covered, plus: detection through the real `complete()` with `_chat` stubbed (asserting the messages are plain strings with no `image_url`), once-per-job detection, resume, an unknown mode, asset parity (same files under `assets/pdf_<job8>/` in both modes), and a real-pdflatex compile in template mode.

Gate (`tools/verify-slice.sh backend/tests/test_pdf2latex_template_mode.py`):
```
PASS  typecheck
PASS  pytest tests/test_pdf2latex_template_mode.py
```
(25 passed.) `pytest tests/test_pdf2latex_fidelity.py tests/test_converted_document_edits.py tests/test_pdf2latex_jobs.py`: all pass (63). Exact mode was also compared against the HEAD copies of `preamble.py` / `facts.py` on the ticket, synthetic-bold and a generated PDF: the preamble, every page's facts and the layout body are identical.

`tests/test_provider_fallback.py`: 22 passed, 5 failed (`test_primary_failure_falls_back_to_openrouter_minimax_m3[*]`, `test_minimax_m3_aliases_do_not_map_to_text_01`). These failures don't come from this slice: the root `.env` sets `OPENROUTER_FALLBACK_MODEL="minimax/minimax-m3:free"`, the tests expect `minimax/minimax-m3`, and they do not import any file this slice touched. Full backend suite: 791 passed, 6 failed (those 5 plus the known `test_compile_gate_truth.py::test_recovery_success_still_reports_errors`).

Deliberate choices and deviations:
- Body font/size is the modal pair over regular upright spans, falling back to all spans when none are regular. Without this, a form made mostly of bold labels (the ticket fixture) made `Carlito-Bold` the body font of a `\mdseries` command.
- The bold-only heading criterion requires size >= body size, so small bold labels and footnotes don't become headings.
- A stated `line_spacing` is read as a multiple of single spacing (1 / 1.5 / 2) and converted to the profile's baseline/size ratio as stated × 1.2.
- Heading commands are font switches (`{\obHeadingI text\par}`), not macros that take an argument, so the TikZ layout fallback can use them as `font=`. `spacing_before_pt` appears in the comment and in `style_profile`, but the vertical space itself still comes from each line's `gap`.
- Heading levels the PDF lacks are still defined (as bold body text), so the prompt can always refer to `\obHeadingI..III`.
- When stated margins differ from the measured ones, the facts' coordinate origin follows the stated margins.

### For slice 08
- Request field: `mode` on `POST /api/convert/pdf`, a form field `mode: str = Form("exact")`. Values `"exact" | "template"`, default `"exact"`. The pipeline treats anything else as exact.
- It has to be threaded `route -> runner.start_job(..., mode=...) -> _spawn -> run_conversion(..., mode=mode)`. `runner.py` does not forward it yet; it isn't owned by this slice. On resume, `run_conversion` reads the mode from the job state (it is written there in template mode), so the resume path needs no `mode` argument.
- The preview can show "Template rules detected" from `report["template_rules"]` = `{"is_template": true, "rules": {...}, "evidence": [str]}`. That key is present only when rules were detected. `report["style_profile"]` (the merged profile; `source` is `"measured"` or `"merged"`) is present in every template-mode run.
