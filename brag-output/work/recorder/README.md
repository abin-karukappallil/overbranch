Re-record the real /dashboard and /editor footage (needs `next dev` on :3000, chromium, pdflatex).

    npm i playwright-core@1.49.1   # in this folder
    node rec-dash.mjs && node rec-editor.mjs
    ffmpeg -framerate 30 -i frames/dash/%05d.jpg   -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p -g 15 -bf 0 -movflags +faststart ../../composition/assets/video/dashboard.mp4
    ffmpeg -framerate 30 -i frames/editor/%05d.jpg -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p -g 15 -bf 0 -movflags +faststart ../../composition/assets/video/editor-live.mp4

All backend/auth calls are stubbed in stubs.mjs (sample projects only); compiles run local pdflatex on the posted LaTeX.
