#!/bin/bash
# Azure App Service startup script.
#
# Oryx builds the app, compresses it to output.tar.zst, and extracts it to a
# runtime dir (e.g. /tmp/<id>) with the venv at <dir>/antenv. It puts the
# venv's site-packages on PYTHONPATH but NOT the app root, so a plain
# `gunicorn api.server:app` fails with "ModuleNotFoundError: No module named
# 'api'". This script locates the app root (where the `api/` package lives)
# and puts it on PYTHONPATH before launching gunicorn.

find_app_dir() {
  # 1. Parent of the active virtualenv (Oryx sets VIRTUAL_ENV to <dir>/antenv).
  if [ -n "$VIRTUAL_ENV" ] && [ -d "$(dirname "$VIRTUAL_ENV")/api" ]; then
    dirname "$VIRTUAL_ENV"; return 0
  fi
  # 2. Uncompressed deploy lands directly in wwwroot.
  if [ -d "/home/site/wwwroot/api" ]; then
    echo "/home/site/wwwroot"; return 0
  fi
  # 3. Most recent /tmp/<id> that contains the api/ package.
  local d
  d="$(ls -dt /tmp/*/api 2>/dev/null | head -1)"
  if [ -n "$d" ]; then
    dirname "$d"; return 0
  fi
  return 1
}

APP_DIR="$(find_app_dir)"
if [ -n "$APP_DIR" ]; then
  export PYTHONPATH="$APP_DIR:$PYTHONPATH"
  cd "$APP_DIR" || true
fi
echo "[startup.sh] APP_DIR='$APP_DIR' PYTHONPATH='$PYTHONPATH' CWD='$(pwd)'"

exec gunicorn \
  --bind=0.0.0.0:8000 \
  --workers=1 \
  --timeout=120 \
  -k uvicorn.workers.UvicornWorker \
  api.server:app
