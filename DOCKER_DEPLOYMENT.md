# 🐳 Universal Docker Deployment Guide for OverBranch

**OverBranch** is 100% self-contained. It packages the Next.js Frontend (**Port 3000**), Python FastAPI TeX Engine (**Port 8000**), and the full TeX Live compilation suite into a single Docker image.

You can run OverBranch on **any system or virtual machine** (Azure Ubuntu VM, AWS EC2, DigitalOcean, self-hosted Linux servers, Windows with Docker Desktop, or macOS) with zero external dependencies.

---

## 🎛️ Architecture Overview

| Service | Container Internal Port | Host Port | Purpose |
|---|---|---|---|
| **Next.js Web App** | `3000` | `3000` | Collaborative TeX Editor, UI & Dashboard |
| **FastAPI TeX Engine** | `8000` | `8000` | TeX Live Compiler & AI TeX Copilot Router |

---

## 🚀 Quick Start (Any OS / Local System)

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & Docker Compose installed.

### 1-Command Execution
```bash
# Clone the repository
git clone https://github.com/abin-karukappallil/overbranch.git
cd overbranch

# Copy default environment configuration
cp .env.example .env

# Build and start OverBranch containers
docker compose up --build -d
```

Access the application:
- 🌐 **Web Interface**: `http://localhost:3000`
- ⚙️ **FastAPI TeX API**: `http://localhost:8000/docs`

---

## 🐍 Backend-Only Docker Deployment (FastAPI + TeX Live)

If you want to host **only the Python + TeX Live compiler & AI backend** in Docker (and host the frontend separately on Cloudflare Workers, Vercel, or standalone), OverBranch provides multiple options:

### Option A: Dedicated Docker Compose (Recommended)
```bash
docker compose -f docker-compose.backend.yml up --build -d
```

### Option B: Root Compose Selecting Backend Service
```bash
docker compose up --build -d backend
```

### Option C: Direct Docker Build from Repo Root
```bash
# Build standalone backend image
docker build -f Dockerfile.backend -t overbranch-backend .

# Run standalone backend container on port 8000
docker run -d \
  --name overbranch-backend \
  --restart always \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/backend/templates:/app/backend/templates:ro \
  overbranch-backend
```

### Option D: Build Directly Inside `backend/` Folder
```bash
cd backend
docker build -t overbranch-backend .
docker run -d -p 8000:8000 --env-file ../.env overbranch-backend
```

---

## ☁️ Frontend Deployment on Cloudflare Workers

OverBranch is fully compatible with **Cloudflare Workers** using `@opennextjs/cloudflare` and `wrangler`.

### 1. Prerequisites
- A Cloudflare account
- Authenticated with Wrangler CLI:
  ```bash
  bun x wrangler login
  # or: npx wrangler login
  ```
- Your backend Docker container running and accessible via public URL (e.g. `https://overapi.yourdomain.com`).

### 2. Configure Environment Variables
In your `.env` or Cloudflare Worker environment settings:
```env
NEXT_PUBLIC_BACKEND_URL="https://overapi.yourdomain.com"
BACKEND_URL="https://overapi.yourdomain.com"
BETTER_AUTH_SECRET="your-better-auth-secret"
BETTER_AUTH_URL="https://overbranch.your-subdomain.workers.dev"
NEXT_PUBLIC_APP_URL="https://overbranch.your-subdomain.workers.dev"
```

### 3. Build & Deploy to Cloudflare Workers
Run the dedicated Cloudflare Workers scripts:
```bash
# Build for Cloudflare Workers
bun run build:worker

# Deploy to Cloudflare Workers
bun run deploy:worker
```

Or preview locally in the Cloudflare Workers runtime (Workerd):
```bash
bun run preview:worker
```

---

## ☁️ Ubuntu VM/Server Deployment (Standalone VM)

This setup uses **only standard Azure,Aws,Gcp,Linode,Digital Ocean VM compute**.

### Step 1: Open Server/VM Ports (3000 & 8000)

*Via **Cloud Provider Portal**: Go to Virtual Machine -> Networking -> Inbound Port Rules -> Add Inbound Rule for TCP ports `3000` and `8000`.*

### Step 2: Install Docker on Ubuntu server/vm

SSH into your Ubuntu server/vm (`ssh username@<YOUR_VM_PUBLIC_IP>`):

```bash

sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER
newgrp docker
```

---

### Step 3: Configure Environment (.env)

```bash
git clone https://github.com/abin-karukappallil/overbranch.git
cd overbranch
cp .env.example .env
nano .env
```

Set `NEXT_PUBLIC_BACKEND_URL` to your VM Public IP:
```env
NEXT_PUBLIC_BACKEND_URL="http://<YOUR_VM_PUBLIC_IP>:8000"
BACKEND_URL="http://localhost:8000"

NVIDIA_API_KEY="your-nvidia-api-key"
NVIDIA_LLM_MODEL="openai/gpt-oss-120b"
GROQ_API_KEY="your-groq-api-key"
```

---

### Step 4: Run OverBranch on server/vm

```bash
docker compose up --build -d
```

> **📌 Important Note on Disconnecting from VM**:
> Passing the `-d` flag runs Docker in **detached background mode**. You can safely close your SSH session or disconnect from the VM — **OverBranch will stay 100% running in the background**.
> Furthermore, `docker-compose.yml` includes `restart: always`, ensuring OverBranch **automatically restarts if your server reboots**.

That's it! OverBranch is now live on your VM:
- **Web App**: `http://<YOUR_VM_PUBLIC_IP>:3000`
- **FastAPI Engine**: `http://<YOUR_VM_PUBLIC_IP>:8000`

---

## 🪟 Windows Deployment (Docker Desktop / WSL2)

1. Open PowerShell or Command Prompt.
2. Clone repository & build:
   ```powershell
   git clone https://github.com/abin-karukappallil/overbranch.git
   cd overbranch
   copy .env.example .env
   docker compose up --build -d
   ```
3. Open `http://localhost:3000` in your browser.

---

## 🍎 macOS Deployment

1. Open Terminal.
2. Clone repository & build:
   ```bash
   git clone https://github.com/abin-karukappallil/overbranch.git
   cd overbranch
   cp .env.example .env
   docker compose up --build -d
   ```
3. Open `http://localhost:3000` in your browser.

---

## 🛠️ Useful Docker Management Commands

| Action | Command |
|---|---|
| **View Live Logs** | `docker compose logs -f` |
| **Check Running Status** | `docker compose ps` |
| **Stop OverBranch** | `docker compose down` |
| **Rebuild Container** | `docker compose up --build -d` |
| **Inspect Uploads Volume** | `docker volume ls` |

---

## 🌐 Production Nginx Reverse Proxy Setup (Preventing 502 Bad Gateway)

If you use Nginx to reverse proxy traffic to OverBranch Docker containers, **default Nginx settings will cause intermittent 502 Bad Gateway errors** after running for some time due to:
1. **Uvicorn Keep-Alive Race**: Uvicorn drops idle TCP connections after 5s by default, while Nginx upstream keepalive defaults to 65s. When Nginx sends a request over a dead connection, it returns 502.
2. **Short Read Timeouts**: Nginx's default `proxy_read_timeout` is 60s. Heavy LaTeX builds (`pdflatex`/`latexmk`) or multi-step AI Agent LLM streams can take 30–90s, causing Nginx to terminate with 502/504.
3. **Response Buffering**: Default Nginx buffers responses, which breaks Server-Sent Events (SSE) in the AI Agent Reasoning Window.

### 1. Ready-to-Use Configuration
A production-hardened configuration is included in [`nginx/overbranch.conf`](nginx/overbranch.conf).

Key settings implemented:
```nginx
upstream overbranch_backend {
    server 127.0.0.1:8000;
    keepalive 32;                # Connection pooling prevents socket exhaustion
}

server {
    server_name overapi.yourdomain.com;
    client_max_body_size 100M;   # Allows large PDFs and asset bundles

    location / {
        proxy_pass http://overbranch_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection ""; # Required for upstream keepalive
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;        # Accommodates long TeX compiles & LLM streaming
        proxy_buffering off;            # Real-time SSE streaming (Agent Reasoning Window)
        proxy_cache off;
        proxy_next_upstream error timeout invalid_header http_502 http_503; # Auto-retry on worker recycle
    }
}
```

### 2. Apply to Your Server (Ubuntu / Debian)
```bash
# Copy site configuration to Nginx
sudo cp nginx/overbranch.conf /etc/nginx/sites-available/overbranch.conf

# Enable site
sudo ln -sf /etc/nginx/sites-available/overbranch.conf /etc/nginx/sites-enabled/

# Test syntax and reload
sudo nginx -t && sudo systemctl reload nginx

# (Optional) Provision free Let's Encrypt SSL certificates
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d overapi.yourdomain.com -d overbranch.yourdomain.com
```

---

## ⚡ Automated CI/CD Deployment with GitHub Actions

OverBranch includes an automated GitHub Actions CI/CD pipeline ([`.github/workflows/deploy.yml`](file:///.github/workflows/deploy.yml)).

Whenever you push to the `main` branch, GitHub Actions will automatically connect to your Azure VM over SSH, write the production `.env` configuration from your secrets, and deploy the updated container using `docker compose up -d --build`.

### Required GitHub Repository Secrets

Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**:

| Secret Name | Example Value / Description |
|---|---|
| `AZURE_VM_IP` | `20.xxx.xxx.xxx` (Your Azure VM Public IP) |
| `AZURE_VM_USERNAME` | `azureuser` or `ubuntu` |
| `AZURE_VM_SSH_KEY` | Contents of your private SSH key (`~/.ssh/id_rsa` or Azure SSH Key PEM) |
| `AZURE_VM_PORT` | `22` (Default SSH port) |
| `ENV_FILE` | Complete contents of your production `.env` file |

