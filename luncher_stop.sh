#!/bin/zsh
pkill -f "uvicorn luncher.web.app:app" && echo "Server stopped." || echo "Server is not running."
