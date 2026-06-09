#!/bin/zsh

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$APP_DIR/backend"
venv/bin/pip install -r requirements.txt
venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "$APP_DIR/frontend"
npm install

(sleep 2 && open "http://127.0.0.1:3000/") &
npm run dev -- --host 127.0.0.1 --port 3000
