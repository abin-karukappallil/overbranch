# Hyperframes Composition Brief: OverBranch

## Objective
Create a short launch-style brag video for OverBranch, the free, open-source agentic LaTeX editor.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080, 30fps
- Duration: 21.8 seconds

## Source Material
- Project root: `/home/abin/overbranch`
- Primary files read: `README.md`, `app/layout.tsx`, `app/globals.css`, `components/landing/{Hero,Features,FreeSection,CTASection,PdfToLatexSection}.tsx`, `app/convert/page.tsx`, `components/pdf-import/ImportPdfDialog.tsx`, `components/editor/{EditorLayout,LatexEditorView,CompileToolbar,CollabPresenceBar,AgentReasoningWindow,ChatModeToggle}.tsx`; rendered landing reference `brag-output/work/landing-reference.png`
- Product name: OverBranch (wordmark "OVERBRANCH" + "BETA" chip)
- Tagline / strongest claim: "STOP RE-TYPING PAPERS BY HAND." / "DECOMPILE PDFS INTO REAL LATEX."
- Key UI to recreate: Import PDF dialog + conversion stages + `main.tex` code panel; editor (Monaco dark) + copilot panel (Ask|Edit, Agent Reasoning steps, inline diff review bar with Accept); landing hero; Free section cards.
- Copy that must appear verbatim (re-casing / trimming allowed):
  - STOP RE-TYPING PAPERS BY HAND.
  - OVERBRANCH · BETA · AGENTIC LATEX CODE EDITOR · FOR STUDENTS AND RESEARCHERS
  - 02 // PDF TO LATEX CODE · DECOMPILE PDFS INTO REAL LATEX.
  - Import PDF · Extracting Assets · Generating · Compiling LaTeX · Checking coverage & style fidelity
  - [✓] Verified zero-error compilation (with pdflatex) · Actually Editable
  - AGENTIC AI FOR LATEX · Ask / Edit · Ask agent to edit LaTeX... · Agent Reasoning · Finding target… · Applying patch… · Compiling… · Done · Accept · Compile TeX · Live
  - NO SUBSCRIPTION REQUIRED · 100% FREE. · UNLIMITED COMPILATION · UNLIMITED CO-AUTHORS · AGENTIC AI ASSISTANCE · FASTER THAN OVERLEAF
  - FORK THE FUTURE. · STAR ON GITHUB · overbranch.app

## Creative Direction
- Tone preset: default
- Creative direction: neo-brutalist open-source manifesto: the green poster vs. the dark workbench
- Interpretation: punchy, confident, hard-edged motion; titles slam then hold dead still; the poster states, the editor proves.
- Angle: alternate the landing page's loud green poster with the dark editor actually doing the work; every claim is the site's own copy.
- Hook: hand-typing `\documentclass{arti` key by key on black, then "STOP RE-TYPING / PAPERS BY HAND." slams on the beat.
- Outro / punchline: "FORK THE FUTURE." on black, logo + wordmark, overbranch.app + STAR ON GITHUB.
- Avoid: generic SaaS language; abstract filler; redesigning the brand; invented numbers (no similarity %, no speed figures); real user documents.

## Visual Identity
- Poster ground `#00CC68`, ink `#000000`, paper `#FFFFFF`
- Workbench `#0E0F12`; surfaces `#141519`, `#1A1C22`; border `#282A30`; text `#E2E4E9`, secondary `#9E9E9E`; accent `#10B981`; diff red `#EB5757`
- Code: Monaco bg `#121b17`, line highlight `#1c2b25`, line numbers `#71717a`; landing code panel `#0a0a0c`
- Logo: branching-document SVG, gradient `#10b981 → #059669 → #d97706` on `#090d16`
- Display: Archivo Black (bundled). Labels: Space Mono 700 (bundled). UI body: Inter (bundled).
- Treatments: hard offset shadows (5–8px at video scale), 2–3px black rules, black pill buttons, uppercase mono labels with wide tracking.

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.
1. Hook "By hand": 3.01s: hand-typing → headline slam → green flood out
2. Reveal "OVERBRANCH": 3.27s: wordmark, BETA, subtitle; BETA chip grows into the dark world
3. Decompile: 5.19s: PDF drop, 4 stages, main.tex streams, verified, ACTUALLY EDITABLE; whip out
4. The agent: 3.81s: prompt, steps, inline diff, Accept click; iris to green
5. Receipts: 3.27s: 100% FREE. + 4 cards; dip cut
6. Fork the future: 3.25s: manifesto line, brand, CTA

## Audio
- Audio role: punchy rhythmic layer
- Audio arc: typing tension → loop kicks in → UI ticks ride the beat → slams → bell → fade
- Music: `assets/music/happy-beats-business-moves-vol-10-by-ende-dot-app.mp3`, volume ~0.32, no fade-in, ~1.2s fade-out at the end
- Music cue guidance: `brag/assets/music/cues/happy-beats-business-moves-vol-10-by-ende-dot-app.music-cues.json` (109.96 BPM). Lock 15.82 (first card) and 18.55 (outro slam). Beat grid for sequential items per the plan.
- Audio-reactive treatment: subtle; outro logo glow + verified badge glow from bass energy, baked at build time via media-use `extract-audio-data.py`.
- Audio-coupled moments: hand-typing keys; headline slam; flood/wordmark; BETA pop; PDF drop; stage ticks; verified; stamp; whip; prompt keys; send; accept; iris; 100% FREE; 4 cards; outro bell; logo.
- SFX selection guidance: low-HF-risk picks from `sfx-analysis.md` (impactSoft_medium_*, interface/click_00{2,3,5}, ui/click2, interface/bong_001, interface/drop_00*), keyboard keypresses for typing, impactBell_heavy_000 for the outro. Quiet UI ticks (0.4–0.55), slams 0.7–0.8.
- Exact SFX choice: chosen after the animation exists.
- Audio files: copied into `brag-output/composition/assets/`.

## Hyperframes Instructions
Follow the `hyperframes` contract (format.md, motion.md, look.md), `hyperframes-registry`, `media-use`, `hyperframes-cli`. /brag replaces the storyline/SPEC/REVIEW/usage/history/feedback steps; `check` is the gate. One scene per sub-composition; seam transitions are built as matching end/start states in adjacent scenes. Keep creation and rendering local.

## Extended cut (38.2s)
- New scenes: `compositions/dashboard.html` (6.28–11.73) and `compositions/editor.html` (16.92–27.83), each a window (1680x770 at 120,236, the agent scene's frame) holding a frame-by-frame recording of the real app page at 2x (`assets/video/dashboard.mp4`, `assets/video/editor-live.mp4`). Camera moves are tweens on a wrapper inside the window, never on the `<video>`.
- Later scenes shift by whole beats (decompile +10, agent/receipts/outro +30), so their internal beat locks still hold; the outro slam sits on 34.91s, the hit after the track's 33.8–34.4s break.
- Seams: BETA chip grows into the dashboard's ground; zoom through the "PDF to LaTeX" card into decompile; decompile whips into the editor; the editor pushes into its agent input and the agent scene lands slightly large and settles.
- Kickers raised to 28px in every scene (type floor).
