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
    echo "ts1-qtmr:" && \
    (kpsewhich ts1-qtmr.tfm || echo "WARNING: ts1-qtmr.tfm not found") && \
    echo "t1-qtmr:" && \
    (kpsewhich t1-qtmr.tfm || echo "WARNING: t1-qtmr.tfm not found") && \
    echo "qtmr:" && \
    (kpsewhich qtmr.tfm || echo "WARNING: qtmr.tfm not found") && \
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

RUN mkdir -p /tmp/tex-test && \
    printf '%s\n' \
    '\\documentclass{article}' \
    '\\usepackage[T1]{fontenc}' \
    '\\usepackage{textcomp}' \
    '\\usepackage{newtxtext}' \
    '\\begin{document}' \
    'Times font test: ABCDEFG abcdefg 1234567890' \
    '\\end{document}' \
    > /tmp/tex-test/test.tex && \
    cd /tmp/tex-test && \
    pdflatex -interaction=nonstopmode -halt-on-error test.tex && \
    test -f test.pdf && \
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
    (kpsewhich ts1-qtmr.tfm || echo "WARNING: ts1-qtmr.tfm unavailable") && \
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