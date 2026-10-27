# Brag Plan: OverBranch

## What is this app?
A 100% free, open-source, self-hostable agentic LaTeX editor ("like Antigravity for LaTeX"): unlimited compiles, an AI agent that edits your .tex, unlimited co-authors, and a PDF → LaTeX decompiler that turns a finished paper back into editable source.

## The angle
**Neo-brutalist open-source manifesto.** The landing page is a loud green poster (#00CC68, Archivo Black caps, 2px black borders, hard offset shadows). The video alternates that poster energy with the dark editor doing real work. The poster makes the claims and the editor proves them. The pain is universal to anyone who has written a paper: re-typing a PDF into LaTeX by hand. OverBranch's own copy says it best ("STOP RE-TYPING PAPERS BY HAND." / "DECOMPILE PDFS INTO REAL LATEX."), so the video quotes it rather than inventing claims.

## Hook (first 2-3 seconds)
Black frame. A caret is mid-way through hand-typing `\documentclass{arti`, one painful key at a time (key ticks). On the beat, the project's own line SLAMS in, huge white Archivo Black: **"STOP RE-TYPING / PAPERS BY HAND."** with "BY HAND." in OverBranch green. Then the frame floods green.

## Key moments (the middle)
- **The real dashboard.** The actual `/dashboard` (recorded live from the app with sample projects): the project grid scrolls by, then the cursor lands on the **PDF to LaTeX** card and the camera zooms through it.
- **The decompile.** A real-looking paper (`ReportTemplate.pdf`, the landing page's own example) drops into the Import PDF dialog. The real conversion stages tick off one by one: *Extracting Assets → Generating → Compiling LaTeX → Checking coverage & style fidelity*. Meanwhile `main.tex` streams in beside it, ending on "[✓] Verified zero-error compilation" and an "ACTUALLY EDITABLE" stamp.
- **The real editor, live.** The actual `/editor/[id]` page: Compile → the PDF renders. The presence bar flips to **Live**, Sam Vance and Mia Chen join; their name-flagged carets select and type in `main.tex` at the same time; recompile and the PDF carries both edits ("Mia Chen" in the author line, a new "3 Conclusion").
- **The agent edits your paper.** The editor (dark Monaco, green caret) with the copilot panel in **Edit** mode. A prompt is typed into "Ask agent to edit LaTeX…". The Agent Reasoning steps tick (*Finding target… → Applying patch… → Compiling… → Done*) and a green inline diff (+9 −0) lands in the .tex. Cursor clicks **Accept**.
- **The receipts.** Green poster: "100% FREE." and the four black declaration cards from the site slam in one by one: UNLIMITED COMPILATION / UNLIMITED CO-AUTHORS / AGENTIC AI ASSISTANCE / FASTER THAN OVERLEAF.

## Outro / punchline
Hard dip-cut to black on the strongest beat: **"FORK THE FUTURE."** ("FUTURE." in green), then the branching-document logo + OVERBRANCH wordmark + BETA chip, then `overbranch.app` and a ★ STAR ON GITHUB pill. Holds ≥ 2s.

## User flow worth showing
1. **Entry:** the dashboard → PDF to LaTeX → drop a PDF into Import PDF.
2. **Key action:** the conversion pipeline runs (stages tick, LaTeX streams, compile verified).
3. **Result + next action:** an editable project in the real editor; compile, co-author live with teammates, ask the agent for a change, accept it.

## Tone
- Preset: `default`
- Creative direction: neo-brutalist open-source manifesto: the green poster vs. the dark workbench
- Interpretation: punchy and playful, but never jokey about the product; claims are the site's own ALL-CAPS copy; motion is hard and confident (slams, floods, whips), and text lands then holds dead still.

## Format: landscape — 1920x1080, 30fps
## Duration: 38.2s
Extended past the 25s default on request: the cut now also shows `/dashboard`, `/editor` and real-time multi-author editing.

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
  - Full-track beat grid from `hyperframes beats` (108 beats, fit 0.582 + 0.5446·k); per-beat bass energy measured over the whole 60s track.
  - Strong-cue locks: **32.18s** (first declaration card), **34.91s** (the hit right after the track's 33.8–34.4s break → "FORK THE FUTURE." slam).
  - Every inserted scene is a whole number of beats (dashboard 10, editor 20), so the earlier scenes keep their beat phase: hook slam 0.82; flood/OVERBRANCH 3.01; BETA 3.55; dashboard click 10.37; PDF drop 12.27; verified 14.74; stamp 15.28; editor compile 18.00 / PDF 18.55; Live 19.09; recompile 24.00 / PDF 24.55; send 28.92; accept 31.09; 100% FREE 31.64.
  - Readability note: the four stage labels and four cards are TEXT; they reveal quickly on consecutive beats/half-beats and then the full set holds ≥ 1.2s.
- Audio-reactive treatment: subtle; the outro logo's green glow and the "verified" badge glow breathe with bass energy (baked at build time). No waveform/EQ visuals.
- SFX posture: moderate, motion-matched, low-HF-risk picks; soft thuds for slams, quiet clicks for UI ticks, key ticks for typing, one bell for the outro.
- Audio-coupled moments: hand-typing keys (S1), headline slam, PDF drop, stage ticks, prompt typing, send click, Accept click, card slams, final bell.
- Restraint rule: UI ticks stay under the music; no stacked sounds on the same frame except a slam + its beat; nothing bright repeated.

## Storyboard
### Scene 1 — Hook "By hand" — 3.01s (0.00–3.01)
Black ground, `\documentclass{arti` hand-typed with key ticks; "STOP RE-TYPING / PAPERS BY HAND." slams on the beat (0.82), then the frame floods green. (Unchanged.)
Transition mood: colour flood → Scene 2

### Scene 2 — Reveal "OVERBRANCH" — 3.27s (3.01–6.28)
Green poster: OVERBRANCH letter-drop, BETA chip pop (3.55), "AGENTIC LATEX CODE EDITOR", "FOR STUDENTS AND RESEARCHERS". (Unchanged.)
Transition mood: object becomes the world (the BETA chip grows into the dark ground, 5.74–6.28) → Scene 3

### Scene 3 — The dashboard — 5.45s (6.28–11.73)
Kicker "/DASHBOARD // DOCUMENT PROJECTS", headline "REPORTS. THESES. SLIDES." (from the dashboard's own subtitle). A window holds the real `/dashboard`, recorded frame by frame: Document Projects banner and the three quick-action cards, then the page scrolls to "Your Document Projects (6)" (owned + shared), the cursor hovers Seminar Report, scrolls back and lands on **Import PDF & Convert** (real hover state). Click on the beat (10.37).
Audio-coupled idea: click, then a whoosh into the zoom.
Transition mood: zoom through the button (camera tracks to the card 10.44–11.06, card scales past the frame 11.20–11.70, fill becomes the dark ground) → Scene 4

### Scene 4 — Decompile — 5.19s (11.73–16.92)
As before: Import PDF dialog, paper drop (12.27), four stages on the beat, `main.tex` streams in, verified glow (14.74), ACTUALLY EDITABLE stamp (15.28).
Transition mood: whip left (16.38–16.92) → Scene 5

### Scene 5 — The editor, live — 10.91s (16.92–27.83)
Kicker "/EDITOR // MAIN.TEX", headline "LIGHTNING-FAST COMPILATION." The real `/editor/[id]` page, recorded frame by frame: Project Files, `main.tex` in Monaco, PDF PREVIEW, agent panel. Cursor clicks **Compile** (18.00) → "Compiling LaTeX document…" → the real pdflatex PDF renders (18.52).
19.09: presence bar goes **Live**; Sam Vance (amber) and Mia Chen (cyan) avatars pop in. Headline swaps to "/EDITOR // REAL-TIME PRESENCE" + "CO-AUTHOR WITH LIVE CURSORS." (the landing's own "live selection cursors" line).
Camera punches into the code (19.47–20.22): Mia's caret selects the title (live selection highlight), then types ", Mia Chen" into `\author`; at the same time Sam types `\section{Conclusion}` and "Co-authors see every keystroke live." Name flags ride both carets.
Camera pulls back; Compile again (24.00); the PDF re-renders (24.52) and the camera pushes onto the page: "Alex Rivers, Sam Vance, Mia Chen" and "3 Conclusion" are there. The cursor heads for "Ask agent to edit LaTeX…".
Audio-coupled idea: compile clicks, soft drop on the first PDF, pops for each co-author joining, a light scatter of key ticks under the typing, warm bong when the recompiled PDF lands.
Transition mood: camera pushes into the agent input (27.27–27.83, ease-in + blur) → Scene 6 lands slightly large around its agent input and settles

### Scene 6 — The agent — 3.81s (27.83–31.64)
As before: "add a results table" typed, Send (28.92), Agent Reasoning ticks, +9 −0 inline diff, Accept (31.09).
Transition mood: iris from the Accept click opens onto green → Scene 7

### Scene 7 — Receipts — 3.27s (31.64–34.91)
"100% FREE." slam (31.64), four declaration cards from 32.18 on half-beats, hold, 40% dip.
Transition mood: dip cut on the 34.91 hit → Scene 8

### Scene 8 — Fork the future — 3.29s (34.91–38.20)
"FORK THE FUTURE." slam with the bell (34.91), logo + OVERBRANCH + BETA (35.45), overbranch.app + ★ STAR ON GITHUB; music fades under the hold.

**Scene durations:** 3.01 + 3.27 + 5.45 + 5.19 + 10.91 + 3.81 + 3.27 + 3.29 = **38.20s** (extended on request)

**Music mood for this video:** upbeat, punchy
**Audio summary:** hand-typed tension snaps into a punchy loop; UI ticks ride the beat through the dashboard, decompile and live editor; co-author typing scatters soft key ticks; slams stomp the receipts; a bell lands the manifesto on the track's re-entry hit and the loop fades under the logo.

## Notes on source material and privacy
- All on-screen LaTeX is project-authored sample content (`LatexEditorView.tsx` default project, the landing `PdfToLatexSection` example `ReportTemplate.pdf`). The real user documents under `uploads/projects/` are NOT used.
- Author names shown are the repo's own placeholders ("Alex Rivers, Sam Vance"). Presence avatars use initials only.
- The typed agent prompt ("add a results table") and the diff contents are illustrative UI text, not claims.
- `/dashboard` and `/editor` are the real app (local `next dev`), driven by a headless browser with every backend and auth call stubbed: sample projects, the repo's sample report LaTeX (from `LatexEditorView.tsx`, switched to `article` so edits show on page 1), compiled by local pdflatex. No real account, project or upload is read.
- Remote carets use the exact decoration classes and CSS from `lib/collab/monaco-binding.ts`; the presence bar is `CollabPresenceBar`'s own markup in its Live state. "Mia Chen" is an added placeholder co-author name.
- The recordings live in `composition/assets/video/` (dashboard.mp4, editor-live.mp4, 3360x1534 = the 1680x767 window at 2x).
