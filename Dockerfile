FROM node:20-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# 1. Install System Dependencies: TeX Live Compilation Suite, Python3 & Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    latexmk \
    poppler-utils \
    perl \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Install Node.js Dependencies
COPY package.json package-lock.json ./
RUN npm ci

# 3. Install Python Dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r backend/requirements.txt

# 4. Copy Project Files & Build Next.js Application
COPY . .
RUN npm run build

# 5. Expose Ports & Volume
EXPOSE 3000
EXPOSE 8000

VOLUME ["/app/uploads"]

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
