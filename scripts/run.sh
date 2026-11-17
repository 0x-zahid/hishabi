#!/usr/bin/env bash
# Hishabi - Start Local Backend Server
cd "$(dirname "$0")/.."

source .venv/bin/activate
echo "Starting Hishabi Backend on http://127.0.0.1:8000 ..."
echo "API Docs available at: http://127.0.0.1:8000/docs"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
