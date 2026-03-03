#!/bin/bash

# Luncher Setup Script
# This script helps you get started with Luncher

set -e

echo "🍽️  Luncher Setup"
echo "================="
echo

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run: python3 -m venv venv"
    exit 1
fi

echo "✅ Virtual environment found"

# Activate virtual environment
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import requests" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
else
    echo "✅ Dependencies already installed"
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your ANTHROPIC_API_KEY"
else
    echo "✅ .env file exists"
fi

# Check if Playwright browsers are installed
echo
echo "🎭 Checking Playwright browsers..."
if playwright --version >/dev/null 2>&1; then
    echo "Installing Playwright Chromium browser..."
    playwright install chromium
    echo "✅ Playwright browsers installed"
else
    echo "⚠️  Playwright command not found (this is okay if not using PORKE scraper)"
fi

echo
echo "✅ Setup complete!"
echo
echo "Try these commands:"
echo "  luncher list          # List all restaurants"
echo "  luncher today         # Show today's menus"
echo "  luncher show utelleru # Show specific restaurant"
echo
echo "Start web interface:"
echo "  uvicorn luncher.web.app:app --reload"
echo "  Then visit: http://localhost:8000"
echo
echo "📚 See QUICKSTART.md for more information"
