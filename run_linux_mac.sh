#!/usr/bin/env sh
# PromptInjectionFinder – starts the offline web interface (Linux / macOS).
# The first start creates a private virtual environment (.venv), so nothing has to be
# installed system-wide (PEP 668: Arch, Debian 12+, Ubuntu 23+, Homebrew).
# A venv belongs to one Python minor version; after a system upgrade (e.g. 3.13 -> 3.14 via
# pacman/yay or brew) it is recreated automatically.
# With PIF_LAUNCH=cli (the "pif" command from install.sh) it runs "pif <args>" in the current
# directory instead of the interface. Messages go to stderr so --json output stays clean.
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
VPY="$DIR/.venv/bin/python"
MODE="${PIF_LAUNCH:-}"
unset PIF_LAUNCH

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

# 0 = ready, 1 = dependencies missing, anything else = broken (base Python gone or another version)
state=1
if [ -e "$DIR/.venv" ]; then
  state=0
  "$VPY" -c 'import os, sys, importlib.util as u
if not os.path.isdir(os.path.join(sys.prefix, "lib", "python%d.%d" % sys.version_info[:2], "site-packages")):
    sys.exit(3)
sys.exit(0 if u.find_spec("pymupdf") and u.find_spec("numpy") else 1)' >/dev/null 2>&1 || state=$?
  if [ "$state" -gt 1 ]; then
    echo "The Python environment no longer matches the installed Python (system update?) - recreating it ..." >&2
    rm -rf "$DIR/.venv"
    state=1
  fi
fi

if [ ! -e "$DIR/.venv" ]; then
  PY=$(find_python) || {
    echo "Python 3.9 or newer was not found. Install it:" >&2
    echo "  Debian/Ubuntu: sudo apt install python3 python3-venv" >&2
    echo "  Arch:          sudo pacman -S python" >&2
    echo "  Fedora:        sudo dnf install python3" >&2
    echo "  macOS:         brew install python   (or https://www.python.org)" >&2
    exit 1
  }
  echo "Creating virtual environment (one time) ..." >&2
  if ! "$PY" -m venv "$DIR/.venv" >&2; then
    rm -rf "$DIR/.venv"
    echo "Could not create the virtual environment." >&2
    echo "  Debian/Ubuntu: sudo apt install python3-venv   and start again." >&2
    exit 1
  fi
fi

if [ "$state" = 1 ]; then
  echo "Installing dependencies (one time, needs internet) ..." >&2
  "$VPY" -m pip install --upgrade pip >/dev/null 2>&1 || true
  "$VPY" -m pip install -r "$DIR/requirements.txt" >&2
fi

export PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}"
if [ "$MODE" = cli ]; then
  exec "$VPY" -m pif "$@"
fi
cd "$DIR"
exec "$VPY" -m pif gui "$@"
