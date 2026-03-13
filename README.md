
# LaTeX Editor — Full System

A fast, single-user LaTeX web editor with Monaco editor, live PDF preview, and automated deployment.

## Architecture

- **Frontend**: Next.js (App Router), Monaco Editor, Tailwind CSS.
- **API Layer**: tRPC with Zod validation.
- **Backend**: Node.js standalone server with `latexmk` for compilation.
- **Infrastructure**: AWS EC2 (Ubuntu 22.04), PM2 process manager.
- **CI/CD**: GitHub Actions for automated SSH-based deployment.

## Project Structure

```text
overbranch/
├── frontend/           # Next.js application (Monaco editor + preview)
├── backend/            # Standalone Node.js tRPC server
│   ├── src/index.ts    # Express entry point
│   └── src/trpc/       # Router and compilation logic
├── scripts/            # Infrastructure scripts
│   └── install.sh      # Idempotent Ubuntu setup script
└── .github/workflows/  # CI/CD pipeline
    └── deploy.yml      # GitHub Actions deployment workflow
```

## Features

- **Split-Screen Layout**: Monaco editor on the left with LaTeX syntax highlighting, PDF preview on the right.
- **Fast Compilation**: Powered by `latexmk -pdf -silent`.
- **Security**: Compilations run in isolated temporary directories with timeouts and cleanup.
- **Error Handling**: Displays structured compilation logs if an error occurs.
- **PDF Preview**: Automatic preview updates using blob URLs.
- **Download**: Download the last compiled PDF.

## Setup Instructions

### Prerequisites
- Node.js & npm (or Bun)
- TeX Live and `latexmk` installed on the system.

### Local Installation

1. Clone the repository.
2. Run the installation script (Ubuntu):
   ```bash
   bash scripts/install.sh
   ```
3. Start the backend:
   ```bash
   cd backend && npm run dev
   ```
4. Start the frontend:
   ```bash
   cd frontend && npm run dev
   ```
5. Open `http://localhost:3000`.

## EC2 Deployment Guide

1. Launch an Ubuntu 22.04 EC2 instance.
2. Configure GitHub Secrets:
   - `EC2_HOST`: IP/Hostname of your instance.
   - `EC2_SSH_KEY`: Private SSH key for access.
3. Push to `main` to trigger the deployment pipeline.

## Usage

- Write your LaTeX code in the Monaco editor.
- Click **Compile** to generate the PDF.
- Use **Download PDF** to save the result.
