#!/bin/zsh
source "$(dirname "$0")/venv/bin/activate"
echo "Starting web server at http://localhost:8000"
sleep 1 && open http://localhost:8000 &
uvicorn luncher.web.app:app --reload
