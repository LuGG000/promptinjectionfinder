#!/usr/bin/env sh
# PromptInjectionFinder – Installation / Update für Linux und macOS.
#
#   curl -fsSL https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.sh | sh
#   oder im heruntergeladenen Ordner:  sh install.sh
#
# Installiert nach ~/.local/share/promptinjectionfinder (PIF_DIR ändert das), legt eine eigene
# Python-Umgebung an, die Befehle "pif" und "promptinjectionfinder" in ~/.local/bin und unter Linux
# einen Startmenü-Eintrag. Ein erneuter Aufruf aktualisiert auf das neueste Release.
set -e

REPO="${PIF_REPO:-https://gitlab.com/LuGG000/promptinjectionfinder.git}"
DIR="${PIF_DIR:-$HOME/.local/share/promptinjectionfinder}"
BIN="${PIF_BIN:-$HOME/.local/bin}"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

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

PY=$(find_python) || die "Python 3.9 oder neuer fehlt.
  Debian/Ubuntu: sudo apt install python3 python3-venv git
  Arch:          sudo pacman -S python git
  Fedora:        sudo dnf install python3 git
  macOS:         brew install python git"

# ---------------------------------------------------------------- program files
if [ -d "$DIR/pif" ]; then
  say "Bestehende Installation gefunden: $DIR – aktualisiere"
  if [ -x "$DIR/.venv/bin/python" ]; then
    "$DIR/.venv/bin/python" -m pif update || say "Update nicht möglich – vorhandene Version bleibt installiert."
  fi
elif [ -n "${PIF_SOURCE:-}" ]; then
  say "Kopiere Programm aus $PIF_SOURCE"
  mkdir -p "$DIR"
  (cd "$PIF_SOURCE" && tar cf - --exclude=.venv --exclude=.git --exclude=dist --exclude=build .) | (cd "$DIR" && tar xf -)
else
  command -v git >/dev/null 2>&1 || die "git fehlt (für Download und Updates). Bitte installieren und erneut starten."
  TAG=$(git ls-remote --tags "$REPO" 2>/dev/null | "$PY" -c 'import re, sys
tags = re.findall(r"refs/tags/(v\d+\.\d+(?:\.\d+)?)$", sys.stdin.read(), re.M)
print(max(tags, key=lambda t: tuple(int(x) for x in t[1:].split("."))) if tags else "")')
  say "Lade PromptInjectionFinder ${TAG:-(Entwicklungsstand)} herunter"
  mkdir -p "$(dirname "$DIR")"
  if [ -n "$TAG" ]; then
    git -c advice.detachedHead=false clone --quiet --depth 50 --branch "$TAG" "$REPO" "$DIR"
  else
    git clone --quiet "$REPO" "$DIR"
  fi
fi

# ---------------------------------------------------------------- python environment
if [ ! -x "$DIR/.venv/bin/python" ]; then
  say "Lege Python-Umgebung an"
  "$PY" -m venv "$DIR/.venv" || die "venv fehlt. Debian/Ubuntu: sudo apt install python3-venv"
fi
say "Installiere Abhängigkeiten"
"$DIR/.venv/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip >/dev/null 2>&1 || true
"$DIR/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$DIR/requirements.txt"
chmod +x "$DIR"/*.sh "$DIR"/*.command 2>/dev/null || true

# ---------------------------------------------------------------- launchers
mkdir -p "$BIN"
cat > "$BIN/pif" <<EOF
#!/usr/bin/env sh
exec "$DIR/.venv/bin/python" -m pif "\$@"
EOF
cat > "$BIN/promptinjectionfinder" <<EOF
#!/usr/bin/env sh
exec "$DIR/.venv/bin/python" -m pif gui "\$@"
EOF
chmod +x "$BIN/pif" "$BIN/promptinjectionfinder"

if [ "$(uname -s)" = "Linux" ] && [ -z "${PIF_NO_SHORTCUTS:-}" ]; then
  APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$APPS"
  cat > "$APPS/promptinjectionfinder.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PromptInjectionFinder
Comment=Dokumente und Webseiten auf versteckte Prompt Injections prüfen
Exec="$BIN/promptinjectionfinder"
Terminal=true
Categories=Utility;Security;
EOF
fi

VERSION=$("$DIR/.venv/bin/python" -c "import sys; sys.path.insert(0, '$DIR'); import pif; print(pif.__version__)")
say "Fertig: PromptInjectionFinder $VERSION in $DIR"
echo "    Starten:       promptinjectionfinder      (öffnet den Browser)"
echo "    Kommandozeile: pif scan <datei>   ·   pif scan-url <link>"
echo "    Aktualisieren: pif update"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "    Hinweis: $BIN ist nicht im PATH. Ergänzen mit:  echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.profile" ;;
esac
