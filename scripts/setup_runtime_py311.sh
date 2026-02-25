#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime/python311"
VENV_DIR="$ROOT_DIR/.venv311"
PY_URL='https://github.com/astral-sh/python-build-standalone/releases/download/20260211/cpython-3.11.14%2B20260211-aarch64-apple-darwin-install_only.tar.gz'
PY_TAR='/tmp/cpython-3.11.14-aarch64-apple-darwin-install_only.tar.gz'

mkdir -p "$RUNTIME_DIR"

if [ ! -x "$RUNTIME_DIR/python/bin/python3.11" ]; then
  echo "[setup] Downloading Python 3.11 standalone runtime..."
  curl -L -o "$PY_TAR" "$PY_URL"
  find "$RUNTIME_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  tar -xzf "$PY_TAR" -C "$RUNTIME_DIR"
fi

PY311_BIN="$RUNTIME_DIR/python/bin/python3.11"
if [ ! -x "$PY311_BIN" ]; then
  echo "[setup] Python 3.11 runtime not found after extraction." >&2
  exit 1
fi

if [ -L "$VENV_DIR/bin/python3.11" ]; then
  VENV_TARGET="$(readlink "$VENV_DIR/bin/python3.11" || true)"
  if [ "$VENV_TARGET" != "$PY311_BIN" ]; then
    echo "[setup] Recreating venv to bind it to repo-local runtime."
    rm -rf "$VENV_DIR"
  fi
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[setup] Creating venv: $VENV_DIR"
  "$PY311_BIN" -m venv "$VENV_DIR"
fi

PIP_BIN="$VENV_DIR/bin/pip"

"$PIP_BIN" install --upgrade pip setuptools wheel
"$PIP_BIN" install pypdf python-docx pillow lxml paddlepaddle paddleocr easyocr markitdown docling
"$PIP_BIN" uninstall -y chardet || true

echo "[setup] Completed."
echo "[setup] Runtime python: $VENV_DIR/bin/python"
echo "[setup] Run commands with: $VENV_DIR/bin/python <script>.py ..."
