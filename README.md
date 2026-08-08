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