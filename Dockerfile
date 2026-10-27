# ============================================================
# OverBranch application image
# ============================================================
# TeX Live and the production fonts live in a separate base image, built once
# (docker/texlive.Dockerfile → overbranch-texlive:<year>.<n>). This image only
# layers the app on top, so an app deploy ships app layers, not ~5 GB of TeX.
#
#   docker build -f docker/texlive.Dockerfile -t overbranch-texlive:2026.1 .
#   docker build --build-arg TEX_BASE=overbranch-texlive:2026.1 -t overbranch:latest .
#
# `deploy.sh` builds the base automatically when its tag is missing.
# ============================================================

ARG TEX_BASE=overbranch-texlive:2026.1
FROM ${TEX_BASE}

ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1

# ============================================================
# 1. Assert the base really is the TeX base (not some other image)
# ============================================================
RUN pdflatex --version | head -1 | grep -q "TeX Live" && \
    kpsewhich beamer.cls && \
    kpsewhich tikz.sty && \
    echo "TeX base OK"

# ============================================================
# 2. Install Bun
# ============================================================
RUN npm install -g bun@latest

# ============================================================
# 3. Application directory
# ============================================================
WORKDIR /app

# ============================================================
# 4. Install Node.js dependencies
# ============================================================
COPY package.json bun.lock* ./
RUN bun install

# ============================================================
# 5. Install Python dependencies
# ============================================================
COPY backend/requirements.txt ./backend/requirements.txt
RUN python3 -m pip install \
    --no-cache-dir \
    --break-system-packages \
    -r backend/requirements.txt

# ============================================================
# 6. Copy application
# ============================================================
COPY . .

# ============================================================
# 7. Production environment
# ============================================================
ENV NODE_ENV=production

# ============================================================
# 8. Build Next.js application
# ============================================================
RUN bun run build

# ============================================================
# 9. Runtime configuration
# ============================================================
EXPOSE 3000
EXPOSE 8000

# ============================================================
# 10. Persistent project uploads
# ============================================================
VOLUME ["/app/uploads"]

# ============================================================
# 11. Health check
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
