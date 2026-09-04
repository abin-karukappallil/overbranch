FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1

# 1. Install System Dependencies: TeX Live Compilation Suite, Python3, Bun & Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    texlive-base \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-bibtex-extra \
    texlive-extra-utils \
    texlive-pictures \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-science \
    texlive-publishers \
    texlive-xetex \
    texlive-luatex \
    texlive-lang-greek \
    cm-super \
    fonts-dejavu \
    fonts-lmodern \
    fonts-urw-base35 \
    latexmk \
    ghostscript \
    poppler-utils \
    perl \
    ca-certificates \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Bun package manager globally
RUN npm install -g bun

WORKDIR /app

# 2. Install Node.js Dependencies using Bun
COPY package.json bun.lock* ./
RUN bun install

# 3. Install Python Dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r backend/requirements.txt

# 4. Copy Project Files & Build Next.js Application with Bun
COPY . .
ENV NODE_ENV=production
RUN bun run build

# 5. Expose Ports & Volume
EXPOSE 3000
EXPOSE 8000

VOLUME ["/app/uploads"]

# Health check to ensure containers remain responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
