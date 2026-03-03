#!/bin/zsh
source "$(dirname "$0")/venv/bin/activate"
if [ $# -eq 0 ]; then
    luncher today
else
    luncher "$@"
fi
