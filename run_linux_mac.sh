#!/usr/bin/env sh
# PromptInjectionFinder – startet die Offline-Weboberflaeche (Linux / macOS).
# Beim ersten Start wird eine eigene virtuelle Umgebung (.venv) angelegt, damit
# nichts systemweit installiert werden muss (PEP 668: Arch, Debian 12+, Ubuntu 23+, Homebrew).
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
    echo "Python 3.9 oder neuer wurde nicht gefunden. Installation:"
    echo "  Debian/Ubuntu: sudo apt install python3 python3-venv"
    echo "  Arch:          sudo pacman -S python"
    echo "  Fedora:        sudo dnf install python3"
    echo "  macOS:         brew install python   (oder https://www.python.org)"
    exit 1
  }
  echo "Lege virtuelle Umgebung an (einmalig) ..."
  if ! "$PY" -m venv .venv; then
    rm -rf .venv
    echo "Konnte keine virtuelle Umgebung anlegen."
    echo "  Debian/Ubuntu: sudo apt install python3-venv   und danach erneut starten."
    exit 1
  fi
fi

if ! .venv/bin/python -c "import pymupdf, numpy" >/dev/null 2>&1; then
  echo "Installiere Abhaengigkeiten (einmalig, benoetigt Internet) ..."
  .venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m pif gui "$@"
