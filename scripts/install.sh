#!/bin/bash

# Exit on error
set -e

echo "Starting installation of LaTeX Editor dependencies..."

# Install TeX Live and latexmk
if [ -f /etc/arch-release ]; then
    echo "Detected Arch Linux. Installing TeX Live packages via pacman..."
    sudo pacman -S --needed --noconfirm texlive-latexextra texlive-bibtexextra latexmk
elif command -v apt &> /dev/null; then
    echo "Detected Debian/Ubuntu. Installing TeX Live packages via apt..."
    sudo apt update
    sudo apt install -y texlive-latex-extra texlive-bibtex-extra latexmk
else
    echo "Unsupported OS. Please install texlive-latexextra, texlive-bibtexextra, and latexmk manually."
    exit 1
fi

# Install PM2 globally
if ! command -v pm2 &> /dev/null; then
    echo "Installing PM2..."
    sudo npm install -g pm2
fi

# Install project dependencies
echo "Installing project dependencies..."
cd "$(dirname "$0")/.."

# Backend setup
echo "Setting up backend..."
cd backend
npm install
npm run build
# Start/Restart backend with PM2
pm2 restart latex-backend || pm2 start dist/backend/src/index.js --name "latex-backend"

# Frontend setup
echo "Setting up frontend..."
cd ../frontend
npm install
# Note: Next.js build requires environment variables at build time if using static optimization
npm run build
# Start/Restart frontend with PM2
pm2 restart latex-frontend || pm2 start npm --name "latex-frontend" -- start

echo "Installation complete!"
echo "Backend running on port 8080 (PM2: latex-backend)"
echo "Frontend running on port 3000 (PM2: latex-frontend)"
