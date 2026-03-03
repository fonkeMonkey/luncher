#!/bin/zsh
source "$(dirname "$0")/venv/bin/activate"

LOG="$HOME/.luncher/server.log"
mkdir -p "$HOME/.luncher"

if lsof -i :8000 -sTCP:LISTEN -t &>/dev/null; then
    open http://localhost:8000
else
    nohup uvicorn luncher.web.app:app >> "$LOG" 2>&1 &
    sleep 2 && open http://localhost:8000
fi

