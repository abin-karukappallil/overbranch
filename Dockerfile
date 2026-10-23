FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1

# ============================================================
# 1. System Dependencies
#    Node.js + Python + TeX Live + Fonts + Build Tools
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
    # TeX Live Core
    # ========================================================
    texlive-base \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-bibtex-extra \
    texlive-extra-utils \
    texlive-pictures \
    \
    # ========================================================
    # TeX Fonts
    # ========================================================
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-fonts-extra-links \
    fonts-urw-base35 \
    fonts-texgyre \
    fonts-lmodern \
    cm-super \
    \
    # ========================================================
    # Science / Publishing / Language Support
    # ========================================================
    texlive-science \
    texlive-publishers \
    texlive-lang-greek \
    \
    # ========================================================
    # XeLaTeX / LuaLaTeX
    # ========================================================
    texlive-xetex \
    texlive-luatex \
    \
    # ========================================================
    # Additional System Fonts
    # ========================================================
    fonts-dejavu \
    fonts-liberation \
    fonts-liberation2 \
    fonts-noto-core \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    \
    # ========================================================
    # LaTeX Tooling
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
    \
    # ========================================================
    # Font / TeX Utilities
    # ========================================================
    xfonts-utils \
    \
    && rm -rf /var/lib/apt/lists/* \
    \
    # ========================================================
    # Refresh System Font Cache
    # ========================================================
    && fc-cache -f -v \
    \
    # ========================================================
    # Refresh TeX Filename Database
    # ========================================================
    && mktexlsr \
    \
    # ========================================================
    # Rebuild PDFTeX / TeX Font Maps
    # ========================================================
    && updmap-sys --force \
    \
    # ========================================================
    # Refresh TeX Database Again
    # ========================================================
    && mktexlsr

# ============================================================
# 2. Verify LaTeX Installation
# ============================================================

RUN echo "============================================================" && \
    echo "Checking LaTeX installation..." && \
    echo "============================================================" && \
    pdflatex --version && \
    echo "" && \
    echo "Checking TeX Live..." && \
    kpsewhich texmf.cnf && \
    echo "" && \
    echo "Checking Beamer..." && \
    kpsewhich beamer.cls && \
    echo "" && \
    echo "Checking Focus Beamer..." && \
    kpsewhich beamerthemefocus.sty && \
    echo "" && \
    echo "Checking Fira Math..." && \
    kpsewhich firamath-otf.sty && \
    echo "" && \
    echo "Checking Unicode Math..." && \
    kpsewhich unicode-math.sty && \
    echo "" && \
    echo "Checking Fontspec..." && \
    kpsewhich fontspec.sty && \
    echo "" && \
    echo "============================================================" && \
    echo "Checking Times / Nimbus font metrics..." && \
    echo "============================================================" && \
    kpsewhich ts1-qtmr.tfm && \
    kpsewhich t1-qtmr.tfm && \
    kpsewhich qtmr.tfm && \
    echo "" && \
    echo "Checking PDFTeX font map..." && \
    kpsewhich pdftex.map && \
    echo "" && \
    echo "Checking Fira Math font files..." && \
    find /usr/share/texlive \
        -iname '*FiraMath*' \
        -o -iname '*firamath*' \
        2>/dev/null | head -20 && \
    echo "" && \
    echo "============================================================" && \
    echo "LaTeX environment verification complete." && \
    echo "============================================================"

# ============================================================
# 3. Install Bun
# ============================================================

RUN npm install -g bun@latest

# ============================================================
# 4. Application Directory
# ============================================================

WORKDIR /app

# ============================================================
# 5. Install Node.js Dependencies
# ============================================================

COPY package.json bun.lock* ./

RUN bun install

# ============================================================
# 6. Install Python Dependencies
# ============================================================

COPY backend/requirements.txt ./backend/requirements.txt

RUN python3 -m pip install \
    --no-cache-dir \
    --break-system-packages \
    -r backend/requirements.txt

# ============================================================
# 7. Copy Application
# ============================================================

COPY . .

# ============================================================
# 8. Production Environment
# ============================================================

ENV NODE_ENV=production

# ============================================================
# 9. Build Next.js Application
# ============================================================

RUN bun run build

# ============================================================
# 10. Final TeX Verification
#     Make sure copying the application didn't alter TeX setup
# ============================================================

RUN echo "============================================================" && \
    echo "Final production TeX verification..." && \
    echo "============================================================" && \
    kpsewhich ts1-qtmr.tfm && \
    kpsewhich t1-qtmr.tfm && \
    kpsewhich qtmr.tfm && \
    kpsewhich beamerthemefocus.sty && \
    echo "============================================================" && \
    echo "Production TeX environment OK." && \
    echo "============================================================"

# ============================================================
# 11. Runtime Configuration
# ============================================================

EXPOSE 3000
EXPOSE 8000

# ============================================================
# 12. Persistent Project Uploads
# ============================================================

VOLUME ["/app/uploads"]

# ============================================================
# 13. Health Check
# ============================================================

HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=30s \
    --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

# ============================================================
# 14. Entrypoint
# ============================================================

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]