# ============================================================
# OverBranch TeX base image  —  overbranch-texlive:2026.<n>
# ============================================================
#
# This is the heavy, slow-changing half of the production image: a full,
# upstream TeX Live plus the system fonts Overleaf serves to XeLaTeX/LuaLaTeX.
# The application image (../Dockerfile) builds `FROM` this, so TeX Live is
# built ONCE and every app deploy reuses the cached layers instead of
# re-shipping ~5 GB of TeX.
#
# Build (from the repo root):
#   docker build -f docker/texlive.Dockerfile -t overbranch-texlive:2026.1 .
# then build the app image with that tag:
#   docker build --build-arg TEX_BASE=overbranch-texlive:2026.1 -t overbranch:latest .
#
# Rebuild this image only to move TeX Live years or change the font set;
# `deploy.sh` does that for you when the tag is missing or --rebuild-tex is given.
# ============================================================

FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# TeX Live release to install. The build asserts the installed tree really is
# this release, so bumping it to a year tlnet does not serve yet fails fast
# instead of silently shipping whatever is current. New Overleaf projects
# compile on the latest TeX Live, so this tracks it.
ARG TEXLIVE_YEAR=2026

# ============================================================
# 1. System dependencies + system fonts
# ============================================================
#
# No texlive-* apt packages: Debian bookworm ships TeX Live 2022, four years
# behind Overleaf. The whole TeX tree (engines, latexmk, biber, every TeX font
# package) comes from the upstream installer in step 2. What stays here is the
# non-TeX side: Python, PDF tooling, and the SYSTEM fonts that fontconfig
# serves to XeLaTeX/LuaLaTeX by name and that Ghostscript substitutes with.
#
# The font set mirrors Overleaf's "Which OTF/TTF fonts are supported via
# fontspec" list as closely as Debian bookworm allows. Microsoft core fonts
# (Times New Roman, Arial, Courier New, Georgia, Verdana, …) are added
# separately in step 1b because they live in contrib and need the EULA.
RUN sed -i 's/ main$/ main contrib/' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/ main$/ main contrib/' /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    \
    # ---- Python (backend + minted's latexminted) ----
    python3 \
    python3-pip \
    python3-venv \
    \
    # ---- PDF tooling ----
    ghostscript \
    poppler-utils \
    \
    # ---- general utilities ----
    perl \
    ca-certificates \
    curl \
    wget \
    unzip \
    xz-utils \
    fontconfig \
    \
    # ---- Latin: metric-compatible with the Microsoft core fonts ----
    # Carlito≈Calibri, Caladea≈Cambria, Arimo≈Arial, Tinos≈Times New Roman,
    # Cousine≈Courier New (fonts-croscore + fonts-crosextra-*).
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    fonts-croscore \
    fonts-liberation \
    fonts-liberation2 \
    fonts-urw-base35 \
    fonts-dejavu \
    \
    # ---- Latin: common families Overleaf lists ----
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
    \
    # ---- CJK ----
    fonts-noto-cjk \
    fonts-ipafont-gothic \
    fonts-ipafont-mincho \
    fonts-nanum \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    fonts-arphic-uming \
    fonts-arphic-ukai \
    \
    # ---- Noto coverage for other scripts ----
    fonts-noto-core \
    fonts-noto-extra \
    fonts-noto-ui-core \
    fonts-noto-color-emoji \
    \
    # ---- Indic (Malayalam etc.), Arabic, Hebrew, Thai, SIL ----
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
    \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# 1b. Microsoft core fonts (contrib; EULA preseeded)
# ============================================================
#
# Overleaf has these installed, and XeLaTeX/LuaLaTeX documents select them by
# name (Times New Roman, Arial, Courier New, Georgia, Verdana, …). Without
# them a \setmainfont{Times New Roman} fails on the server. The installer
# downloads from SourceForge at build time and accepts the EULA non-
# interactively. If the download mirror is flaky the build retries; a hard
# failure here is intentional — we want to know the fonts are missing.
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

# ============================================================
# 2. TeX Live (upstream installer, scheme-full)
# ============================================================
#
# scheme-full so arbitrary user documents compile: Beamer and its themes,
# TikZ/PGF, newtx, unicode-math, firamath, the publishers/science classes,
# glossaries, minted and every TeX font package. Docs and sources are skipped
# (the -doc/-src containers are roughly half the download and never read by a
# compile server).
RUN set -eux; \
    mkdir -p /tmp/install-tl; \
    cd /tmp/install-tl; \
    curl -fsSL https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz \
        -o install-tl-unx.tar.gz; \
    tar -xzf install-tl-unx.tar.gz --strip-components=1; \
    # The installer is only ever the current release, so refuse to continue if
    # that is not the release this image is pinned to.
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
    # bin/ holds exactly one platform directory (x86_64-linux, aarch64-linux,
    # ...); tlmgr symlinks its binaries into /usr/local/bin so no PATH entry
    # has to name the architecture.
    mkdir -p /usr/local/bin /usr/local/man/man1 /usr/local/share/info; \
    "$(echo /usr/local/texlive/${TEXLIVE_YEAR}/bin/*)"/tlmgr path add; \
    pdflatex --version | head -1 | grep -q "TeX Live ${TEXLIVE_YEAR}"

# ============================================================
# 3. Refresh fonts + TeX databases
# ============================================================
#
# TeX Live installs outside fontconfig's search path, so expose its OTF/TTF/
# Type1 trees: fontconfig-by-name lookups from fontspec (TeX Gyre, Latin
# Modern, Fira, Source Sans, EB Garamond when not from apt, …) need them.
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

# ============================================================
# 4. Font coverage gate
# ============================================================
# Fails the build if any font in the CORE set is missing, so a renamed or
# dropped Debian package is caught here, not by a user document months later.
COPY docker/overleaf-fonts.txt /usr/local/share/overbranch/overleaf-fonts.txt
COPY docker/check-fonts.sh /usr/local/bin/ob-check-fonts
RUN chmod +x /usr/local/bin/ob-check-fonts && ob-check-fonts

# ============================================================
# 5. Build-time smoke compiles
# ============================================================
# Each runs under the real compile flags. A regression in the TeX install or
# the font set fails the build instead of a user's compile.
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

# A minimal label so the app image and deploy script can assert the base.
LABEL org.overbranch.texlive="${TEXLIVE_YEAR}"
