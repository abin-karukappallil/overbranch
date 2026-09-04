# ==============================================================================
# OverBranch - Standalone LaTeX & Python Backend Container (Backend Context)
# ==============================================================================

FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 1. Install System Dependencies: Complete TeX Live Suite & PDF Processing Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
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

WORKDIR /app/backend

# 2. Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy Backend Code & Templates
COPY . .

# 4. Create uploads directory for project storage
RUN mkdir -p /app/uploads/projects

ENV PORT=8000
ENV HOST=0.0.0.0
ENV UPLOADS_BASE_DIR=/app/uploads/projects

EXPOSE 8000

VOLUME ["/app/uploads"]

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
