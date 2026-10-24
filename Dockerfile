FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1

# ============================================================
# 1. System Dependencies
# ============================================================

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    \
    # ========================================================
    # TeX Live
    # ========================================================
    texlive-base \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-bibtex-extra \
    texlive-extra-utils \
    texlive-pictures \
    texlive-science \
    texlive-publishers \
    texlive-xetex \
    texlive-luatex \
    texlive-lang-greek \
    \
    # ========================================================
    # TeX Fonts
    # ========================================================
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-fonts-extra-links \
    \
    # PostScript / Times / URW fonts
    fonts-urw-base35 \
    fonts-texgyre \
    fonts-lmodern \
    \
    # TeX-side metrics for the above. These are only *Recommends* of
    # texlive-fonts-recommended / texlive-base, so --no-install-recommends
    # drops them: fonts-texgyre ships the OTFs, tex-gyre ships the .tfm/.pfb
    # (ts1-qtmr.tfm etc.) that newtx needs under pdfLaTeX, and fonts-lmodern
    # ships the OTFs while lmodern ships lmodern.sty.
    tex-gyre \
    lmodern \
    tipa \
    \
    # Additional fonts
    cm-super \
    fonts-dejavu \
    fonts-liberation \
    fonts-liberation2 \
    fonts-noto-core \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    \
    # ========================================================
    # LaTeX Tools
    # ========================================================
    latexmk \
    biber \
    \
    # ========================================================
    # PDF Tools
    # ========================================================
    ghostscript \
    poppler-utils \
    \
    # ========================================================
    # General Utilities
    # ========================================================
    perl \
    ca-certificates \
    curl \
    unzip \
    fontconfig \
    xfonts-utils \
    \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# 2. Refresh Fonts + TeX Databases
# ============================================================

RUN fc-cache -f -v && \
    mktexlsr && \
    updmap-sys --force && \
    mktexlsr

# ============================================================
# 3. TeX Installation Verification
# ============================================================

RUN echo "============================================================" && \
    echo "TeX Live Version" && \
    echo "============================================================" && \
    pdflatex --version && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking TeX configuration" && \
    echo "============================================================" && \
    kpsewhich texmf.cnf && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking Beamer" && \
    echo "============================================================" && \
    kpsewhich beamer.cls && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking Focus Beamer" && \
    echo "============================================================" && \
    kpsewhich beamerthemefocus.sty && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking Fira Math" && \
    echo "============================================================" && \
    kpsewhich firamath-otf.sty && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking Unicode Math" && \
    echo "============================================================" && \
    kpsewhich unicode-math.sty && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking Fontspec" && \
    echo "============================================================" && \
    kpsewhich fontspec.sty && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking NewTX / Times packages" && \
    echo "============================================================" && \
    kpsewhich newtxtext.sty || true && \
    kpsewhich newtxmath.sty || true && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking Times font metrics" && \
    echo "============================================================" && \
    echo "ts1-qtmr (TS1 metric newtx needs for bullets, degree, euro):" && \
    kpsewhich ts1-qtmr.tfm && \
    echo "ec-qtmr (T1 metric):" && \
    kpsewhich ec-qtmr.tfm && \
    echo "qtmr.pfb:" && \
    kpsewhich qtmr.pfb && \
    echo "lmodern.sty:" && \
    kpsewhich lmodern.sty && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking PDFTeX font map" && \
    echo "============================================================" && \
    kpsewhich pdftex.map && \
    echo "" && \
    echo "============================================================" && \
    echo "TeX installation verification complete" && \
    echo "============================================================"

# ============================================================
# 4. Create a Real PDFTeX Font Test
# ============================================================

# Mirrors the shape of a dual-engine document compiled by pdfLaTeX: the
# \ifPDFTeX branch loads newtx, and the first itemize bullet is a TS1 glyph,
# which is what pulls in ts1-qtmr.tfm from tex-gyre. A test without an itemize
# passes even when that metric is missing, so keep the list and the log assert.
RUN mkdir -p /tmp/tex-test && \
    printf '%s\n' \
    '\documentclass[12pt]{report}' \
    '\usepackage{iftex}' \
    '\usepackage[T1]{fontenc}' \
    '\usepackage[utf8]{inputenc}' \
    '\usepackage{textcomp}' \
    '\usepackage{newtxtext}' \
    '\usepackage{newtxmath}' \
    '\usepackage{enumitem}' \
    '\begin{document}' \
    'Times font test: ABCDEFG abcdefg 1234567890 $x^2+\alpha$' \
    '\begin{itemize}[leftmargin=*]' \
    '  \item TS1 glyphs: \textbullet\ \textdegree\ \texteuro' \
    '\end{itemize}' \
    '\end{document}' \
    > /tmp/tex-test/test.tex && \
    cd /tmp/tex-test && \
    max_print_line=10000 pdflatex -interaction=nonstopmode -halt-on-error test.tex && \
    test -f test.pdf && \
    grep -q "TS1/ntxtlf" test.log && \
    ! grep -q "Metric (TFM) file not found" test.log && \
    echo "============================================================" && \
    echo "PDFTeX font test PASSED" && \
    echo "============================================================" && \
    rm -rf /tmp/tex-test
    
# ============================================================
# 5. Install Bun
# ============================================================

RUN npm install -g bun@latest

# ============================================================
# 6. Application Directory
# ============================================================

WORKDIR /app

# ============================================================
# 7. Install Node.js Dependencies
# ============================================================

COPY package.json bun.lock* ./

RUN bun install

# ============================================================
# 8. Install Python Dependencies
# ============================================================

COPY backend/requirements.txt ./backend/requirements.txt

RUN python3 -m pip install \
    --no-cache-dir \
    --break-system-packages \
    -r backend/requirements.txt

# ============================================================
# 9. Copy Application
# ============================================================

COPY . .

# ============================================================
# 10. Production Environment
# ============================================================

ENV NODE_ENV=production

# ============================================================
# 11. Build Next.js Application
# ============================================================

RUN bun run build

# ============================================================
# 12. Final TeX Verification
# ============================================================

RUN echo "============================================================" && \
    echo "Final production TeX verification" && \
    echo "============================================================" && \
    pdflatex --version && \
    echo "" && \
    echo "Beamer:" && \
    kpsewhich beamer.cls && \
    echo "" && \
    echo "Focus:" && \
    kpsewhich beamerthemefocus.sty && \
    echo "" && \
    echo "NewTX:" && \
    kpsewhich newtxtext.sty && \
    echo "" && \
    echo "Times metric:" && \
    kpsewhich ts1-qtmr.tfm && \
    echo "" && \
    echo "Final TeX verification complete."

# ============================================================
# 13. Runtime Configuration
# ============================================================

EXPOSE 3000
EXPOSE 8000

# ============================================================
# 14. Persistent Project Uploads
# ============================================================

VOLUME ["/app/uploads"]

# ============================================================
# 15. Health Check
# ============================================================

HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=30s \
    --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

# ============================================================
# 16. Entrypoint
# ============================================================

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]