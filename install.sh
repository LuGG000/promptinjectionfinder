#!/usr/bin/env sh
# PromptInjectionFinder – install / update for Linux and macOS.
#
#   curl -fsSL https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.sh | sh
#   or inside a downloaded copy:  sh install.sh
#
# Installs to ~/.local/share/promptinjectionfinder (change with PIF_DIR), creates a private Python
# environment, the commands "pif" and "promptinjectionfinder" in ~/.local/bin (PIF_BIN) and, on
# Linux, a menu entry (skip: PIF_NO_SHORTCUTS). Running it again updates to the newest release.
# The chosen options are kept in <dir>/.pif-install; after an update the program runs this script
# with PIF_LAUNCHERS_ONLY=1 to refresh the commands. The commands only call run_linux_mac.sh,
# which recreates .venv when a system Python upgrade (e.g. 3.13 -> 3.14) has broken it.
set -e

REPO="${PIF_REPO:-https://gitlab.com/LuGG000/promptinjectionfinder.git}"
DIR="${PIF_DIR:-$HOME/.local/share/promptinjectionfinder}"

# options of an earlier installation, unless set explicitly now
if [ -f "$DIR/.pif-install" ]; then
  while IFS='=' read -r key val; do
    case "$key" in
      PIF_BIN|PIF_NO_SHORTCUTS) eval "[ -n \"\${$key:-}\" ] || $key=\$val" ;;
    esac
  done < "$DIR/.pif-install"
fi
BIN="${PIF_BIN:-$HOME/.local/bin}"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

write_launchers() {
  mkdir -p "$BIN"
  if grep -q PIF_LAUNCH "$DIR/run_linux_mac.sh" 2>/dev/null; then
    cat > "$BIN/pif" <<EOF
#!/usr/bin/env sh
PIF_LAUNCH=cli exec sh "$DIR/run_linux_mac.sh" "\$@"
EOF
    cat > "$BIN/promptinjectionfinder" <<EOF
#!/usr/bin/env sh
exec sh "$DIR/run_linux_mac.sh" "\$@"
EOF
  else  # program version without command line mode in run_linux_mac.sh (before 1.3)
    cat > "$BIN/pif" <<EOF
#!/usr/bin/env sh
PYTHONPATH="$DIR\${PYTHONPATH:+:\$PYTHONPATH}" exec "$DIR/.venv/bin/python" -m pif "\$@"
EOF
    cat > "$BIN/promptinjectionfinder" <<EOF
#!/usr/bin/env sh
PYTHONPATH="$DIR\${PYTHONPATH:+:\$PYTHONPATH}" exec "$DIR/.venv/bin/python" -m pif gui "\$@"
EOF
  fi
  chmod +x "$BIN/pif" "$BIN/promptinjectionfinder"
}

if [ -n "${PIF_LAUNCHERS_ONLY:-}" ]; then
  write_launchers
  exit 0
fi

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

# A venv belongs to one Python minor version: after a system upgrade (pacman/yay, brew, ...) its
# python no longer starts or no longer finds lib/pythonX.Y/site-packages. Then build it again.
venv_works() {
  "$DIR/.venv/bin/python" -c 'import os, sys
sys.exit(0 if os.path.isdir(os.path.join(sys.prefix, "lib", "python%d.%d" % sys.version_info[:2], "site-packages")) else 1)' >/dev/null 2>&1
}

setup_venv() {
  if [ -e "$DIR/.venv" ] && ! venv_works; then
    say "The Python environment no longer matches the installed Python (system update?) – recreating it"
    rm -rf "$DIR/.venv"
  fi
  if [ ! -x "$DIR/.venv/bin/python" ]; then
    say "Creating Python environment"
    "$PY" -m venv "$DIR/.venv" || { rm -rf "$DIR/.venv"; die "venv is missing. Debian/Ubuntu: sudo apt install python3-venv"; }
  fi
  say "Installing dependencies"
  "$DIR/.venv/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip >/dev/null 2>&1 || true
  "$DIR/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$DIR/requirements.txt"
}

# ---------------------------------------------------------------- program files
if [ -d "$DIR/pif" ]; then
  say "Existing installation found: $DIR – updating"
  setup_venv
  PYTHONPATH="$DIR" "$DIR/.venv/bin/python" -m pif update || say "Update not possible – the installed version is kept."
elif [ -n "${PIF_SOURCE:-}" ]; then
  say "Copying program from $PIF_SOURCE"
  mkdir -p "$DIR"
  (cd "$PIF_SOURCE" && tar cf - --exclude=.venv --exclude=.git --exclude=dist --exclude=build \
     --exclude=./bin --exclude=.pif-install --exclude=.pif-launchers .) | (cd "$DIR" && tar xf -)
  setup_venv
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
  setup_venv
fi
chmod +x "$DIR"/*.sh "$DIR"/*.command 2>/dev/null || true

# ---------------------------------------------------------------- launchers
write_launchers

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

printf 'PIF_BIN=%s\nPIF_NO_SHORTCUTS=%s\n' "${PIF_BIN:-}" "${PIF_NO_SHORTCUTS:-}" > "$DIR/.pif-install"
VERSION=$("$DIR/.venv/bin/python" -c "import sys; sys.path.insert(0, '$DIR'); import pif; print(pif.__version__)")
echo "$VERSION" > "$DIR/.pif-launchers"
say "Done: PromptInjectionFinder $VERSION in $DIR"
echo "    Start:         promptinjectionfinder      (opens the browser)"
echo "    Command line:  pif scan <file>   ·   pif scan-url <link>   (add --lang de for German)"
echo "    Update:        pif update"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "    Note: $BIN is not in PATH. Add it with:  echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.profile" ;;
esac
