# ============================================================
# OverBranch application image (Multi-stage)
# ============================================================
# Supports two build workflows:
# 1. Standard build from scratch:
#      docker compose up --build -d
#    Builds the TeX Live base stage automatically, then layers the application.
# 2. Fast app-only build (using a pre-built TeX base image):
#      docker build --build-arg TEX_BASE=overbranch-texlive:2026.1 -t overbranch:latest .
#    (or set TEX_BASE in .env / docker-compose.yml to skip rebuilding TeX Live)
# ============================================================

ARG TEX_BASE=texlive-base

# ============================================================
# Stage 1: TeX Live & Fonts Base Image
# (Only evaluated when TEX_BASE=texlive-base; skipped if external image provided)
# ============================================================
FROM node:22-bookworm-slim AS texlive-base

ENV DEBIAN_FRONTEND=noninteractive
ARG TEXLIVE_YEAR=2026

# System dependencies + system fonts
RUN sed -i 's/ main$/ main contrib/' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/ main$/ main contrib/' /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ghostscript \
    poppler-utils \
    perl \
    ca-certificates \
    curl \
    wget \
    unzip \
    xz-utils \
    fontconfig \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    fonts-croscore \
    fonts-liberation \
    fonts-liberation2 \
    fonts-urw-base35 \
    fonts-dejavu \
    fonts-freefont-ttf \
    fonts-freefont-otf \
    fonts-linuxlibertine \
    fonts-ebgaramond \
    fonts-ebgaramond-extra \
    fonts-open-sans \
    fonts-roboto-unhinted \
    fonts-lato \
    fonts-cantarell \
    fonts-inconsolata \
    fonts-hack \
    fonts-firacode \
    fonts-jetbrains-mono \
    fonts-ibm-plex \
    fonts-stix \
    fonts-symbola \
    fonts-noto-cjk \
    fonts-ipafont-gothic \
    fonts-ipafont-mincho \
    fonts-nanum \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    fonts-arphic-uming \
    fonts-arphic-ukai \
    fonts-noto-core \
    fonts-noto-extra \
    fonts-noto-ui-core \
    fonts-noto-color-emoji \
    fonts-indic \
    fonts-smc \
    fonts-hosny-amiri \
    fonts-thai-tlwg \
    fonts-sil-charis \
    fonts-sil-gentium \
    fonts-sil-gentiumplus \
    fonts-sil-doulos \
    fonts-sil-scheherazade \
    fonts-sil-padauk \
    && rm -rf /var/lib/apt/lists/*

# Microsoft core fonts
RUN sed -i 's/ main$/ main contrib/' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/ main$/ main contrib/' /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update && \
    echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" \
        | debconf-set-selections && \
    for attempt in 1 2 3; do \
        apt-get install -y --no-install-recommends ttf-mscorefonts-installer && break; \
        echo "mscorefonts attempt $attempt failed; retrying" >&2; sleep 5; \
    done && \
    rm -rf /var/lib/apt/lists/*

# TeX Live (upstream installer, scheme-full)
RUN set -eux; \
    mkdir -p /tmp/install-tl; \
    cd /tmp/install-tl; \
    curl -fsSL https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz \
        -o install-tl-unx.tar.gz; \
    tar -xzf install-tl-unx.tar.gz --strip-components=1; \
    grep -q "version ${TEXLIVE_YEAR}\$" release-texlive.txt; \
    printf '%s\n' \
        "selected_scheme scheme-full" \
        "TEXDIR /usr/local/texlive/${TEXLIVE_YEAR}" \
        "TEXMFLOCAL /usr/local/texlive/texmf-local" \
        "TEXMFSYSCONFIG /usr/local/texlive/${TEXLIVE_YEAR}/texmf-config" \
        "TEXMFSYSVAR /usr/local/texlive/${TEXLIVE_YEAR}/texmf-var" \
        "TEXMFCONFIG ~/.texlive${TEXLIVE_YEAR}/texmf-config" \
        "TEXMFVAR ~/.texlive${TEXLIVE_YEAR}/texmf-var" \
        "TEXMFHOME ~/texmf" \
        "instopt_adjustpath 0" \
        "instopt_adjustrepo 1" \
        "instopt_letter 0" \
        "instopt_portable 0" \
        "instopt_write18_restricted 1" \
        "tlpdbopt_autobackup 0" \
        "tlpdbopt_create_formats 1" \
        "tlpdbopt_desktop_integration 0" \
        "tlpdbopt_file_assocs 0" \
        "tlpdbopt_install_docfiles 0" \
        "tlpdbopt_install_srcfiles 0" \
        "tlpdbopt_post_code 1" \
        > texlive.profile; \
    ./install-tl --profile=texlive.profile; \
    cd /; \
    rm -rf /tmp/install-tl; \
    mkdir -p /usr/local/bin /usr/local/man/man1 /usr/local/share/info; \
    "$(echo /usr/local/texlive/${TEXLIVE_YEAR}/bin/*)"/tlmgr path add; \
    pdflatex --version | head -1 | grep -q "TeX Live ${TEXLIVE_YEAR}"

# Refresh fonts + TeX databases
RUN printf '%s\n' \
    '<?xml version="1.0"?>' \
    '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">' \
    '<fontconfig>' \
    "  <dir>/usr/local/texlive/${TEXLIVE_YEAR}/texmf-dist/fonts/opentype</dir>" \
    "  <dir>/usr/local/texlive/${TEXLIVE_YEAR}/texmf-dist/fonts/truetype</dir>" \
    "  <dir>/usr/local/texlive/${TEXLIVE_YEAR}/texmf-dist/fonts/type1</dir>" \
    '</fontconfig>' \
    > /etc/fonts/conf.d/09-texlive-fonts.conf && \
    fc-cache -f && \
    mktexlsr && \
    updmap-sys --force && \
    mktexlsr

# Font coverage gate
COPY docker/check-fonts.sh /usr/local/bin/ob-check-fonts
RUN chmod +x /usr/local/bin/ob-check-fonts && ob-check-fonts

# Build-time smoke compiles
COPY docker/smoke-tests /usr/local/share/overbranch/smoke-tests
RUN set -eux; cd /usr/local/share/overbranch/smoke-tests; \
    echo "== pdflatex + newtx (TS1 metrics) =="; \
    max_print_line=10000 pdflatex -interaction=nonstopmode -halt-on-error pdflatex_newtx.tex; \
    test -f pdflatex_newtx.pdf; \
    grep -q "TS1/ntxtlf" pdflatex_newtx.log; \
    ! grep -q "Metric (TFM) file not found" pdflatex_newtx.log; \
    echo "== xelatex + fontspec (Times New Roman, Arial, Noto CJK) =="; \
    xelatex -interaction=nonstopmode -halt-on-error xelatex_fontspec.tex; \
    test -f xelatex_fontspec.pdf; \
    ! grep -qi "cannot find\|not found\|no font" xelatex_fontspec.log; \
    echo "== lualatex + unicode-math =="; \
    lualatex -interaction=nonstopmode -halt-on-error lualatex_math.tex; \
    test -f lualatex_math.pdf; \
    echo "== biblatex + biber via latexmk =="; \
    latexmk -pdf -interaction=nonstopmode bib.tex; \
    test -f bib.pdf; grep -q "Smith" bib.pdf || grep -rq "Smith" bib.bbl; \
    echo "== makeindex + glossaries via latexmk =="; \
    latexmk -pdf -interaction=nonstopmode glos.tex; \
    test -f glos.pdf; \
    echo "== minted under restricted shell-escape =="; \
    latexmk -pdf -interaction=nonstopmode mint.tex; \
    test -f mint.pdf; \
    echo "== beamer metropolis (Fira) =="; \
    latexmk -pdf -interaction=nonstopmode deck.tex || \
      xelatex -interaction=nonstopmode -halt-on-error deck.tex; \
    test -f deck.pdf; \
    echo "ALL SMOKE COMPILES PASSED"; \
    latexmk -C >/dev/null 2>&1 || true

LABEL org.overbranch.texlive="${TEXLIVE_YEAR}"


# ============================================================
# Stage 2: Application
# ============================================================
FROM ${TEX_BASE} AS app

ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1

# 1. Assert the base really is the TeX base
RUN pdflatex --version | head -1 | grep -q "TeX Live" && \
    kpsewhich beamer.cls && \
    kpsewhich tikz.sty && \
    echo "TeX base OK"

# 2. Install Bun
RUN npm install -g bun@latest

# 3. Application directory
WORKDIR /app

# 4. Install Node.js dependencies
COPY package.json bun.lock* ./
RUN bun install

# 5. Install Python dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN python3 -m pip install \
    --no-cache-dir \
    --break-system-packages \
    -r backend/requirements.txt

# 6. Copy application
COPY . .

# 7. Production environment
ENV NODE_ENV=production

# 8. Build Next.js application
RUN bun run build

# 9. Runtime configuration
EXPOSE 3000
EXPOSE 8000

# 10. Persistent project uploads
VOLUME ["/app/uploads"]

# 11. Health check
HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=30s \
    --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

# 12. Entrypoint
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
