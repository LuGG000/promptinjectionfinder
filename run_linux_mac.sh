#!/usr/bin/env sh
# PromptInjectionFinder – starts the offline web interface (Linux / macOS).
# The first start creates a private virtual environment (.venv), so nothing has to be
# installed system-wide (PEP 668: Arch, Debian 12+, Ubuntu 23+, Homebrew).
set -e
cd "$(dirname "$0")"

find_python() {
  for cand in "${PYTHON:-}" python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
    [ -n "$cand" ] || continue
    if command -v "$cand" >/dev/null 2>&1 &&
       "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      echo "$cand"; return 0
    fi
  done
  return 1
}

if [ ! -x .venv/bin/python ]; then
  PY=$(find_python) || {
    echo "Python 3.9 or newer was not found. Install it:"
    echo "  Debian/Ubuntu: sudo apt install python3 python3-venv"
    echo "  Arch:          sudo pacman -S python"
    echo "  Fedora:        sudo dnf install python3"
    echo "  macOS:         brew install python   (or https://www.python.org)"
    exit 1
  }
  echo "Creating virtual environment (one time) ..."
  if ! "$PY" -m venv .venv; then
    rm -rf .venv
    echo "Could not create the virtual environment."
    echo "  Debian/Ubuntu: sudo apt install python3-venv   and start again."
    exit 1
  fi
fi

if ! .venv/bin/python -c "import pymupdf, numpy" >/dev/null 2>&1; then
  echo "Installing dependencies (one time, needs internet) ..."
  .venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m pif gui "$@"
