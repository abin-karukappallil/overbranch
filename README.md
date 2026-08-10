<svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="obFaviconGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10b981" />
      <stop offset="60%" stop-color="#059669" />
      <stop offset="100%" stop-color="#d97706" />
    </linearGradient>
  </defs>

  <!-- Dark rounded container background for high contrast across browser themes -->
  <rect width="36" height="36" rx="8" fill="#090d16" />

  <!-- Main Document Body Contour -->
  <path
    d="M10 6C10 4.89543 10.8954 4 12 4H22L27 9V30C27 31.1046 26.1046 32 25 32H12C10.8954 32 10 31.1046 10 30V6Z"
    stroke="url(#obFaviconGrad)"
    stroke-width="2.2"
    stroke-linecap="round"
    stroke-linejoin="round"
  />

  <!-- Folded Corner -->
  <path
    d="M22 4V9H27"
    stroke="url(#obFaviconGrad)"
    stroke-width="2.2"
    stroke-linecap="round"
    stroke-linejoin="round"
  />

  <!-- Central Branching Nodes (OverBranch) -->
  <path
    d="M18 27V15"
    stroke="url(#obFaviconGrad)"
    stroke-width="2.2"
    stroke-linecap="round"
  />
  <path
    d="M18 22L13 17"
    stroke="url(#obFaviconGrad)"
    stroke-width="2.2"
    stroke-linecap="round"
  />
  <path
    d="M18 22L23 17"
    stroke="url(#obFaviconGrad)"
    stroke-width="2.2"
    stroke-linecap="round"
  />

  <!-- Node Dots -->
  <circle cx="18" cy="27" r="2" fill="url(#obFaviconGrad)" />
  <circle cx="13" cy="17" r="2" fill="url(#obFaviconGrad)" />
  <circle cx="23" cy="17" r="2" fill="url(#obFaviconGrad)" />
  <circle cx="18" cy="15" r="2" fill="url(#obFaviconGrad)" />
</svg>

<img width="36" height="36" alt="icon" src="https://github.com/user-attachments/assets/f59b468a-5687-4778-b7a0-94a956b18e28" />


# OverBranch — Collaborative LaTeX & Beamer Workspace

OverBranch is a modern, open-source collaborative LaTeX and Beamer slides workspace built for students, researchers, and scientific authors who demand precision, real-time co-authoring, AI document copilot editing, and sub-second PDF compilation.

---

##  Features

- ** Instant TeX & Beamer Compilation**: Real-time PDF compilation via `pdflatex` & `latexmk` with instant fallback renderer.
- ** Built-in AI Copilot Router**: Instant AI LaTeX edits powered by NVIDIA NIM (`openai/gpt-oss-120b`) and Groq (`qwen/qwen3.6-27b`).
- ** Real-time Collaborative Editing**: Seamless multi-user co-authoring with cursor presence and automatic document saving.
- ** Asset Manager & Inline Preview**: Upload images and assets with one-click LaTeX code copying and instant image preview modal.
- ** Fully Responsive**: Custom layout collapsed drawers for mobile & tablet authoring.
- ** 100% Self-Contained Docker Container**: Zero external cloud dependency. Runs on any Azure VM, Linux server, Windows, or Mac.

---

## 1-Command Universal Docker Deployment

Deploy OverBranch anywhere in seconds with Docker:

```bash
git clone https://github.com/abin-karukappallil/overbranch.git
cd overbranch
cp .env.example .env
docker compose up --build -d
```

- **Web Workspace**: `http://localhost:3000`
- **FastAPI Engine**: `http://localhost:8000`

> 📄 For step-by-step Ubuntu VM setup and port rules, see [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md).

---

## 💻 Local Development Setup

### 1. Frontend (Next.js)
```bash
bun install
bun dev
```

### 2. Backend (FastAPI Python Engine)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📜 License

Licensed under the [MIT License](LICENSE).
