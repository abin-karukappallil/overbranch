#!/bin/bash

# Exit on error
set -e

echo "Starting installation of LaTeX Editor dependencies..."

# Update package list
sudo apt update

# Install Node.js and npm if not present
if ! command -v node &> /dev/null; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi

# Install TeX Live and latexmk
echo "Installing TeX Live and latexmk (this may take a while)..."
sudo apt install -y texlive-latex-extra latexmk

# Install PM2 globally
if ! command -v pm2 &> /dev/null; then
    echo "Installing PM2..."
    sudo npm install -g pm2
fi

# Install project dependencies
echo "Installing project dependencies..."
cd "$(dirname "$0")/.."
cd frontend && npm install
cd ../backend && npm install

echo "Installation complete!"
echo "You can now start the backend with: cd backend && pm2 start src/index.ts --name latex-backend"
echo "And the frontend with: cd frontend && npm run build && npm start"
