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

