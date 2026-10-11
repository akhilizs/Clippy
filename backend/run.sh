#!/usr/bin/env bash
# Start the Clippy backend on a Mac (or Linux). The first run installs everything and takes a few minutes.
set -e
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is missing. Install it with:  brew install ffmpeg   (get Homebrew from https://brew.sh)"
  exit 1
fi

PY=$(command -v python3.12 || command -v python3.11 || command -v python3 || true)
if [ -z "$PY" ]; then
  echo "Python 3 is missing. Install it from https://www.python.org/downloads/ (3.11 or 3.12) and run this again."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting things up (a few minutes)..."
  "$PY" -m venv .venv
fi
# (Re)install when pyproject.toml changed since the last install.
if [ ! -f .venv/.installed ] || [ pyproject.toml -nt .venv/.installed ]; then
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e .
  touch .venv/.installed
fi

[ -f .env ] || cp .env.example .env
exec .venv/bin/python -m app
