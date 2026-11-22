@AGENTS.md

# OverBranch

OverBranch is a self-hosted LaTeX workspace with a collaborative editor, local TeX compilation, AI-assisted editing, and PDF-to-LaTeX import.

- `app/`, `components/`, and `trpc/` contain the Next.js workspace, editor, and project management UI. Better Auth handles sessions, and `db/` contains the Drizzle PostgreSQL schema.
- `backend/` contains the FastAPI service for compilation, project files, collaboration, and import. The compile queue runs TeX jobs, and project files and build artifacts live under `UPLOADS_BASE_DIR`.
- The Dashboard and Projects pages share `components/dashboard/PaperSheet.tsx`. The same-origin preview route checks access and revalidates the compiled PDF’s first page with the backend.

See [README.md](README.md) for local development and Docker setup. From the repository root, run `npm run build` to verify the frontend and `PYTHONPATH=backend python -m pytest tests/test_paper_preview.py` with the backend dependencies installed to verify the preview flow.
