FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1

# ============================================================
# 1. System Dependencies
#    Node.js + Python + TeX Live + Fonts + Build Tools
# ============================================================

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    \
    # TeX Live core
    texlive-base \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-bibtex-extra \
    texlive-extra-utils \
    texlive-pictures \
    \
    # TeX fonts
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-fonts-extra-links \
    \
    # Science / publishing / language support
    texlive-science \
    texlive-publishers \
    texlive-lang-greek \
    \
    # XeLaTeX / LuaLaTeX
    texlive-xetex \
    texlive-luatex \
    \
    # Additional fonts
    cm-super \
    fonts-dejavu \
    fonts-lmodern \
    fonts-urw-base35 \
    fonts-liberation \
    fonts-liberation2 \
    fonts-noto-core \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    fonts-texgyre \
    \
    # LaTeX tooling
    latexmk \
    biber \
    \
    # PDF tools
    ghostscript \
    poppler-utils \
    \
    # General utilities
    perl \
    ca-certificates \
    curl \
    unzip \
    fontconfig \
    \
    && rm -rf /var/lib/apt/lists/* \
    \
    # Refresh font cache
    && fc-cache -f -v \
    \
    # Refresh TeX file database and synchronize font maps
    && mktexlsr \
    && updmap-sys

# ============================================================
# 2. Verify Critical LaTeX Packages
# ============================================================

RUN echo "============================================================" && \
    echo "Checking LaTeX installation..." && \
    echo "============================================================" && \
    pdflatex --version && \
    echo "" && \
    echo "Focus Beamer:" && \
    kpsewhich beamerthemefocus.sty && \
    echo "" && \
    echo "Fira Math:" && \
    kpsewhich firamath-otf.sty && \
    echo "" && \
    echo "Unicode Math:" && \
    kpsewhich unicode-math.sty && \
    echo "" && \
    echo "Fontspec:" && \
    kpsewhich fontspec.sty && \
    echo "" && \
    echo "Fira Math font files:" && \
    find /usr/share/texlive -iname '*FiraMath*' -o -iname '*firamath*' 2>/dev/null | head -20 && \
    echo "" && \
    echo "LaTeX environment verification complete."

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
# 10. Runtime Configuration
# ============================================================

EXPOSE 3000
EXPOSE 8000

# Persistent project uploads
VOLUME ["/app/uploads"]

# ============================================================
# 11. Health Check
# ============================================================

HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=30s \
    --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

# ============================================================
# 12. Entrypoint
# ============================================================

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
