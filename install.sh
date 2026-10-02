#!/usr/bin/env sh
# PromptInjectionFinder – install / update for Linux and macOS.
#
#   curl -fsSL https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.sh | sh
#   or inside a downloaded copy:  sh install.sh
#
# Installs to ~/.local/share/promptinjectionfinder (change with PIF_DIR), creates a private Python
# environment, the commands "pif" and "promptinjectionfinder" in ~/.local/bin and, on Linux, a
# menu entry. Running it again updates to the newest release.
set -e

REPO="${PIF_REPO:-https://gitlab.com/LuGG000/promptinjectionfinder.git}"
DIR="${PIF_DIR:-$HOME/.local/share/promptinjectionfinder}"
BIN="${PIF_BIN:-$HOME/.local/bin}"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

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

PY=$(find_python) || die "Python 3.9 or newer is missing.
  Debian/Ubuntu: sudo apt install python3 python3-venv git
  Arch:          sudo pacman -S python git
  Fedora:        sudo dnf install python3 git
  macOS:         brew install python git"

# ---------------------------------------------------------------- program files
if [ -d "$DIR/pif" ]; then
  say "Existing installation found: $DIR – updating"
  if [ -x "$DIR/.venv/bin/python" ]; then
    PYTHONPATH="$DIR" "$DIR/.venv/bin/python" -m pif update || say "Update not possible – the installed version is kept."
  fi
elif [ -n "${PIF_SOURCE:-}" ]; then
  say "Copying program from $PIF_SOURCE"
  mkdir -p "$DIR"
  (cd "$PIF_SOURCE" && tar cf - --exclude=.venv --exclude=.git --exclude=dist --exclude=build .) | (cd "$DIR" && tar xf -)
else
  command -v git >/dev/null 2>&1 || die "git is missing (needed for download and updates). Please install it and run again."
  TAG=$(git ls-remote --tags "$REPO" 2>/dev/null | "$PY" -c 'import re, sys
tags = re.findall(r"refs/tags/(v\d+\.\d+(?:\.\d+)?)$", sys.stdin.read(), re.M)
print(max(tags, key=lambda t: tuple(int(x) for x in t[1:].split("."))) if tags else "")')
  say "Downloading PromptInjectionFinder ${TAG:-(development version)}"
  mkdir -p "$(dirname "$DIR")"
  git clone --quiet "$REPO" "$DIR"
  if [ -n "$TAG" ]; then
    git -C "$DIR" -c advice.detachedHead=false checkout --quiet "$TAG"
  fi
fi

# ---------------------------------------------------------------- python environment
if [ ! -x "$DIR/.venv/bin/python" ]; then
  say "Creating Python environment"
  "$PY" -m venv "$DIR/.venv" || die "venv is missing. Debian/Ubuntu: sudo apt install python3-venv"
fi
say "Installing dependencies"
"$DIR/.venv/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip >/dev/null 2>&1 || true
"$DIR/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$DIR/requirements.txt"
chmod +x "$DIR"/*.sh "$DIR"/*.command 2>/dev/null || true

# ---------------------------------------------------------------- launchers
mkdir -p "$BIN"
cat > "$BIN/pif" <<EOF
#!/usr/bin/env sh
PYTHONPATH="$DIR\${PYTHONPATH:+:\$PYTHONPATH}" exec "$DIR/.venv/bin/python" -m pif "\$@"
EOF
cat > "$BIN/promptinjectionfinder" <<EOF
#!/usr/bin/env sh
PYTHONPATH="$DIR\${PYTHONPATH:+:\$PYTHONPATH}" exec "$DIR/.venv/bin/python" -m pif gui "\$@"
EOF
chmod +x "$BIN/pif" "$BIN/promptinjectionfinder"

if [ "$(uname -s)" = "Linux" ] && [ -z "${PIF_NO_SHORTCUTS:-}" ]; then
  APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$APPS"
  cat > "$APPS/promptinjectionfinder.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PromptInjectionFinder
Comment=Check documents and web pages for hidden prompt injections
Exec="$BIN/promptinjectionfinder"
Terminal=true
Categories=Utility;Security;
EOF
fi

VERSION=$("$DIR/.venv/bin/python" -c "import sys; sys.path.insert(0, '$DIR'); import pif; print(pif.__version__)")
say "Done: PromptInjectionFinder $VERSION in $DIR"
echo "    Start:         promptinjectionfinder      (opens the browser)"
echo "    Command line:  pif scan <file>   ·   pif scan-url <link>   (add --lang de for German)"
echo "    Update:        pif update"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "    Note: $BIN is not in PATH. Add it with:  echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.profile" ;;
esac
