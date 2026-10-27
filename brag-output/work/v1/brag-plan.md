# Brag Plan: OverBranch

## What is this app?
A 100% free, open-source, self-hostable agentic LaTeX editor ("like Antigravity for LaTeX"): unlimited compiles, an AI agent that edits your .tex, unlimited co-authors, and a PDF → LaTeX decompiler that turns a finished paper back into editable source.

## The angle
**Neo-brutalist open-source manifesto.** The landing page is a loud green poster (#00CC68, Archivo Black caps, 2px black borders, hard offset shadows). The video alternates that poster energy with the dark editor doing real work. The poster makes the claims and the editor proves them. The pain is universal to anyone who has written a paper: re-typing a PDF into LaTeX by hand. OverBranch's own copy says it best ("STOP RE-TYPING PAPERS BY HAND." / "DECOMPILE PDFS INTO REAL LATEX."), so the video quotes it rather than inventing claims.

## Hook (first 2-3 seconds)
Black frame. A caret is mid-way through hand-typing `\documentclass{arti`, one painful key at a time (key ticks). On the beat, the project's own line SLAMS in, huge white Archivo Black: **"STOP RE-TYPING / PAPERS BY HAND."** with "BY HAND." in OverBranch green. Then the frame floods green.

## Key moments (the middle)
- **The decompile.** A real-looking paper (`ReportTemplate.pdf`, the landing page's own example) drops into the Import PDF dialog. The real conversion stages tick off one by one: *Extracting Assets → Generating → Compiling LaTeX → Checking coverage & style fidelity*. Meanwhile `main.tex` streams in beside it, ending on "[✓] Verified zero-error compilation" and an "ACTUALLY EDITABLE" stamp.
- **The agent edits your paper.** The editor (dark Monaco, green caret) with the copilot panel in **Edit** mode. A prompt is typed into "Ask agent to edit LaTeX…". The Agent Reasoning steps tick (*Finding target… → Applying patch… → Compiling… → Done*) and a green inline diff (+9 −0) lands in the .tex. Cursor clicks **Accept**.
- **The receipts.** Green poster: "100% FREE." and the four black declaration cards from the site slam in one by one: UNLIMITED COMPILATION / UNLIMITED CO-AUTHORS / AGENTIC AI ASSISTANCE / FASTER THAN OVERLEAF.

## Outro / punchline
Hard dip-cut to black on the strongest beat: **"FORK THE FUTURE."** ("FUTURE." in green), then the branching-document logo + OVERBRANCH wordmark + BETA chip, then `overbranch.app` and a ★ STAR ON GITHUB pill. Holds ≥ 2s.

## User flow worth showing
1. **Entry:** drop a PDF into Import PDF.
2. **Key action:** the conversion pipeline runs (stages tick, LaTeX streams, compile verified).
3. **Result + next action:** an editable project in the editor; ask the agent for a change, see the inline diff, accept it.

## Tone
- Preset: `default`
- Creative direction: neo-brutalist open-source manifesto: the green poster vs. the dark workbench
- Interpretation: punchy and playful, but never jokey about the product; claims are the site's own ALL-CAPS copy; motion is hard and confident (slams, floods, whips), and text lands then holds dead still.

## Format: landscape — 1920x1080, 30fps
## Duration: 21.8s

## Visual identity (from the project)
- Poster ground: `#00CC68` (landing hero / Free / CTA sections); ink `#000000`; paper `#FFFFFF`
- Workbench ground: `#0E0F12` (void-bg), surfaces `#141519` / `#1A1C22`, border `#282A30`, text `#E2E4E9` / `#9E9E9E`, accent `#10B981`
- Code editor (Monaco dark theme in EditorLayout): bg `#121b17`, line highlight `#1c2b25`, line numbers `#71717a`, caret `#10b981`; diff removed `#EB5757`; landing code panel `#0a0a0c`
- Logo gradient: `#10b981 → #059669 → #d97706` on `#090d16` (README/favicon SVG)
- Display font: Archivo Black (uppercase, tracking −0.04em, leading 0.88–0.9)
- Body/UI font: Space Mono 700 uppercase for labels; Inter for UI body text
- Strongest visual element: hard 5px offset shadows (black on green, white on black), 2px black rules, black pill buttons

## Share copy (draft)
Stop re-typing papers by hand. OverBranch decompiles a PDF into real, compilable LaTeX, then an AI agent edits it with you. 100% free, open source, self-hostable.

## Audio direction
- Role: dense-ish rhythmic layer, tight and percussive, under a punchy bed
- Music: `happy-beats-business-moves-vol-10-by-ende-dot-app.mp3` (compact punchy loop, ~110 BPM, beat 1 at 0.27s so the hook hits immediately)
- Music treatment: starts at 0 at ~0.32, no fade-in (the hook needs it), 1.2s fade-out under the final hold
- Music cue guidance: bundled preset read (`assets/music/cues/happy-beats-business-moves-vol-10-by-ende-dot-app.music-cues.json`), tempo 109.96 BPM, beat ≈ 0.545s.
  - Strong-cue locks: **15.82s** (first declaration card), **18.55s** (dip-cut → "FORK THE FUTURE." slam).
  - Beat-grid windows: hook slam 0.82; flood/OVERBRANCH 3.01; BETA 3.55; PDF drop 6.82; stages 7.35 / 7.79 / 8.22 / 8.73; verified 9.29; stamp 9.83; send 12.56; agent steps 12.56 / 13.11 / 13.64 / 14.20; accept 14.73; 100% FREE 15.28.
  - Readability note: the four stage labels and four cards are TEXT; they reveal quickly on consecutive beats/half-beats and then the full set holds ≥ 1.2s.
- Audio-reactive treatment: subtle; the outro logo's green glow and the "verified" badge glow breathe with bass energy (baked at build time). No waveform/EQ visuals.
- SFX posture: moderate, motion-matched, low-HF-risk picks; soft thuds for slams, quiet clicks for UI ticks, key ticks for typing, one bell for the outro.
- Audio-coupled moments: hand-typing keys (S1), headline slam, PDF drop, stage ticks, prompt typing, send click, Accept click, card slams, final bell.
- Restraint rule: UI ticks stay under the music; no stacked sounds on the same frame except a slam + its beat; nothing bright repeated.

## Storyboard

### Scene 1 — Hook "By hand" — 3.01s (0.00–3.01)
Black ground. Small mono line mid-frame being hand-typed: `\documentclass{arti` with a green caret. Keys tick irregularly (slow, painful). At 0.82 (beat) the headline slams in over it: "STOP RE-TYPING / PAPERS BY HAND." (verbatim landing copy, "BY HAND." green). The typed line dims behind it. Hold.
Sequential/interaction: yes, simulated hand-typing, character by character.
Audio intent: tension → release on the slam.
Audio-coupled idea: per-key keypress ticks; soft heavy thud on the slam.
Transition mood: colour flood (green rises from the bottom, 2.70–3.01) → Scene 2

### Scene 2 — Reveal "OVERBRANCH" — 3.27s (3.01–6.28)
Green poster (the real hero): "OVERBRANCH" in giant black Archivo Black slams letter by letter, the black BETA chip pops at 3.55, "AGENTIC LATEX CODE EDITOR" lands under it, mono kicker "FOR STUDENTS AND RESEARCHERS". Hold.
Sequential/interaction: per-letter wordmark, chip pop.
Audio intent: arrival, confidence.
Audio-coupled idea: thud on wordmark, small click on BETA chip.
Transition mood: object becomes the world (the black BETA chip grows past the frame into the dark workbench, 5.74–6.28) → Scene 3

### Scene 3 — Decompile — 5.19s (6.28–11.47)
Dark workbench. Top-left: green mono kicker "02 // PDF TO LATEX CODE" and white Archivo "DECOMPILE PDFS INTO REAL LATEX." Left: the Import PDF dialog; a paper page flies in and drops (6.82), file chip "ReportTemplate.pdf · 14 pages". Stages tick one per beat (7.35, 7.79, 8.22, 8.73), each turning green-checked, then the full list holds. Right: `main.tex` code panel with tabs (main.tex / refs.bib / assets/ (6)); decompiled LaTeX streams in. 9.29: "[✓] VERIFIED ZERO-ERROR COMPILATION" line glows green. 9.83: "ACTUALLY EDITABLE" stamp slaps on.
Sequential/interaction: yes, file drop, staged checklist, streaming code.
Audio intent: machinery working, satisfying ticks.
Audio-coupled idea: drop sound, quiet click per stage, warm bong on verified, thud on stamp.
Transition mood: whip left (10.93–11.47) → Scene 4

### Scene 4 — The agent — 3.81s (11.47–15.28)
Editor workspace: slim top bar (logo, "Seminar Report", "Live" presence with two avatars, green "Compile TeX"), Monaco-dark editor with the project's own sample report LaTeX, copilot panel on the right with the Ask | **Edit** toggle. Label chip top-left "01 // AGENTIC AI FOR LATEX". Prompt types into "Ask agent to edit LaTeX…": "add a results table". Send (12.56). Agent Reasoning steps tick per beat; at 13.11 a green inline diff (a `table` environment) inserts into the editor with the "+9 −0" review bar; cursor clicks **Accept** at 14.73.
Sequential/interaction: yes, typing, send, step ticks, diff insert, accept click.
Audio intent: quick, clever, productive.
Audio-coupled idea: light key ticks, send click, accept click.
Transition mood: iris from the Accept click opens onto green (14.80–15.28) → Scene 5

### Scene 5 — Receipts — 3.27s (15.28–18.55)
Green poster (the real Free section): mono "NO SUBSCRIPTION REQUIRED", giant "100% FREE." slams at 15.28. Four black cards with white hard shadows slam in quickly (15.82 strong cue, then half-beats), then the full set HOLDS ≥ 1.4s: UNLIMITED COMPILATION / UNLIMITED CO-AUTHORS / AGENTIC AI ASSISTANCE / FASTER THAN OVERLEAF.
Sequential/interaction: yes, 4 cards one by one.
Audio intent: stomping receipts.
Audio-coupled idea: thud per card, slightly varied.
Transition mood: dip cut (green darkens ~40% for 3 frames, hard cut on 18.55) → Scene 6

### Scene 6 — Fork the future — 3.25s (18.55–21.80)
Black. "FORK THE FUTURE." slams on the strong cue ("FUTURE." green). 19.10: logo mark + OVERBRANCH wordmark + BETA chip. 19.64: `overbranch.app` and a white "★ STAR ON GITHUB" pill with hard shadow. Logo glow breathes with the bass. Music fades out under the hold.
Sequential/interaction: brand row then CTA row.
Audio intent: final, ringing payoff.
Audio-coupled idea: bell on the slam; soft drop on the logo.
Transition mood: hold to end.

**Scene durations:** 3.01 + 3.27 + 5.19 + 3.81 + 3.27 + 3.25 = **21.80s** ✓ (15–25s)

**Music mood for this video:** upbeat, punchy
**Audio summary:** hand-typed tension snaps into a punchy loop; UI ticks ride the beat through the demo; slams stomp the receipts; a bell lands the manifesto and the loop fades under the logo.

## Notes on source material and privacy
- All on-screen LaTeX is project-authored sample content (`LatexEditorView.tsx` default project, the landing `PdfToLatexSection` example `ReportTemplate.pdf`). The real user documents under `uploads/projects/` are NOT used.
- Author names shown are the repo's own placeholders ("Alex Rivers, Sam Vance"). Presence avatars use initials only.
- The typed agent prompt ("add a results table") and the diff contents are illustrative UI text, not claims.
