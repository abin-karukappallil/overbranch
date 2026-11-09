<div align="center">

<img width="80" height="80" alt="OverBranch Logo" src="https://github.com/user-attachments/assets/f59b468a-5687-4778-b7a0-94a956b18e28" />

# OverBranch

**The Open-Source, Self-Hosted Agentic LaTeX Studio**

*Lightning-fast local TeX compilation, autonomous AI reasoning & edits, reverse PDF-to-LaTeX engineering, and real-time multi-user collaboration.*

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-10b981.svg" alt="MIT License" /></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-15-090d16?logo=nextdotjs&logoColor=white" alt="Next.js 15" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="docker-compose.yml"><img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker Ready" /></a>
  <a href="https://github.com/abin-karukappallil/overbranch/pulls"><img src="https://img.shields.io/badge/PRs-welcome-10b981.svg" alt="PRs Welcome" /></a>
</p>

<p align="center">
  <a href="#-demo-walkthrough"><strong>Watch Demo</strong></a> •
  <a href="#-features"><strong>Features</strong></a> •
  <a href="#-1-command-docker-deployment"><strong>Quick Start</strong></a> •
  <a href="#-local-development-setup"><strong>Local Dev</strong></a> •
  <a href="#-license"><strong>License</strong></a>
</p>

</div>

---

## 🎬 Demo Walkthrough

https://github.com/user-attachments/assets/a6e810dc-1a75-4633-a287-b356854843de

> **38s Overview**: Zero-delay PDF compilation • Agentic AI copilot editing & auto-repair • Live multi-cursor collaboration • Instant asset management and inline previews.

---

## ✨ Features

- **⚡ Instant TeX & Compilation**: Real-time PDF compilation via `pdflatex` & `latexmk` with instant fallback renderer.
- **🤖 Built-in AI Copilot Router**: Autonomous LaTeX edits, document generation, and syntax repairs powered by Groq and custom model endpoints.
- **👥 Real-time Collaborative Editing**: Seamless multi-user co-authoring with live cursor presence and automatic document saving.
- **📄 PDF → LaTeX Reverse Importer**: Upload an existing PDF to extract text, fonts, colors, layouts, and figures into compilable LaTeX with per-page fidelity scoring.
- **🖼️ Asset Manager & Inline Preview**: Upload images and figures with one-click LaTeX snippet insertion and instant modal previews.
- **📱 Fully Responsive Design**: Collapsible drawer workspace designed for seamless authoring across desktop, tablet, and mobile.
- **🐳 100% Self-Contained Docker Container**: Zero external cloud dependency. Deploy locally or on any cloud VM in seconds.

---

## 🚀 1-Command Docker Deployment

Deploy OverBranch anywhere in seconds with Docker:

```bash
git clone https://github.com/abin-karukappallil/overbranch.git
cd overbranch
cp .env.example .env
docker compose up --build -d
```

| Service | URL |
| :--- | :--- |
| **Web Workspace** | `http://localhost:3000` |
| **FastAPI Engine** | `http://localhost:8000` |

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

The PDF importer requires pdfLaTeX (TeX Live with `texlive-latex-extra`, `texlive-pictures`, `texlive-fonts-recommended`) and `pdftoppm` (poppler).

- **Debian / Ubuntu**: `sudo apt install texlive-latex-extra texlive-pictures texlive-fonts-recommended poppler-utils`
- **Arch Linux**: `sudo pacman -S texlive-latexextra texlive-pictures poppler`

To run backend tests:
```bash
cd backend && pytest tests/test_pdf2latex_*.py -v   # integration test is skipped without a TeX engine
```

---

## 📜 License

Distributed under the [MIT License](LICENSE).


